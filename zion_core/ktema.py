"""KTEMA: FL property county-resolution adapter for ZION.

Canonical naming record (per zmart360/BIBLIA/GLOBAL.md naming law):
  1. Technical function: resolve a Florida property query (ZIP, address,
     parcel ID, coordinates) to the county that holds the property record,
     before downstream property-intelligence work proceeds.
  2. Tradition searched: Greek (Koine) legal and documentary vocabulary.
  3. Source: Greek ktema ("ktema"), "a possession, property, estate; that
     which is acquired" -- in legal and documentary Greek, registered
     landed property (cf. the property/land acquired in Acts 5:1).
  4. Correspondence: the module establishes which county holds the
     "possession" (the property record); the name describes the function
     (registered possession), not a rank.
  5. Respectful functional correspondence; no claim of absolute truth.

Design notes:
  - Deterministic and pure: no network, no geocoding calls, no LLM.
    The transport (fetching parcel data, calling PA/GIS services) lives
    OUTSIDE ZION. KTEMA receives already-acquired query signals and emits
    county resolutions against an embedded, versioned ZIP->county table.
    Intent only: it resolves jurisdiction, never fetches property data.
  - business_id is ALWAYS re-validated through SAN PEDRO
    (zion_core/registry.py::sanpedro_resolve), following the
    antiphon.resolve_brand pattern. Unknown, disabled, or spoofed
    business IDs fail closed: no resolution is ever produced for them,
    and there are no default businesses.
  - External input is never authority: every signal is validated and
    normalized; malformed input is rejected, never guessed.
  - Incremental table: zion_core/ktema_county_data.json. A ZIP absent
    from the table resolves OUT_OF_COVERAGE -- never invented. A ZIP
    present in 2+ counties raises KTEMA_COUNTY_AMBIGUOUS -- never guessed.
  - PARCEL_PATTERNS ships EMPTY: parcel-ID patterns enter only after
    verification against the official Property Appraiser source.

Table provenance (2026-10-04, Increment 1b):
  The coordinator populated the table against 4 official FL sources
  (listed verbatim in meta.built_from): Orange County Parcels_BCC
  (SITUS_ZIP), Seminole County Property Appraiser daily CAMA CSV
  (PrimaryAddress, vintage 2026-10-03), Volusia County GIS Address Situs,
  and Lake County GIS Address Locations. Coverage: 114 unique ZIPs --
  Orange 45, Seminole 17, Volusia 32, Lake 29 -- including 9 genuinely
  cross-county ZIPs verified on both sides. Caveats live in meta.notes
  (e.g. Seminole parcels with empty PrimaryAddress contributed no ZIP,
  fail-closed). A ZIP absent from the table resolves
  KTEMA_COUNTY_OUT_OF_COVERAGE -- never invented. A ZIP present in 2+
  counties raises KTEMA_COUNTY_AMBIGUOUS -- never guessed.

Known real-world multi-county reference (coordinator-verified, documented
here; outside Increment-1 county coverage so NOT in the shipped table):
  ZIP 33935 spans Hendry and Glades counties -- the canonical example of
  why a multi-county ZIP must raise KTEMA_COUNTY_AMBIGUOUS instead of
  being guessed.

Precedence: parcel_id -> zip+address -> zip -> address -> coordinates.
Exactly one primary signal is required; address+zip is allowed as
corroboration (resolution still by ZIP).

Increment 2: PropertyProfile + SourceProvenance + VerificationStatus.
  - VerificationStatus is a closed string set (VERIFIED, NOT_FOUND,
    UNAVAILABLE, INCONCLUSIVE; case-sensitive). NOT_FOUND means "this
    source produced no match" -- never an existence claim. NOT_FOUND
    requires property_exists is None; any existence claim on NOT_FOUND
    fails closed.
  - SourceProvenance carries retrieval metadata only; raw_reference is an
    opaque retrieval pointer and is NEVER constructed by interpolating PII.
  - Owner (PII) only survives validation when owner_authorized=True;
    otherwise KTEMA_OWNER_UNAUTHORIZED -- fail closed, never silently
    dropped. owner="" normalizes to None.
  - to_cronicas_event emits a redacted operational event: never owner,
    raw_reference truncated to 64 chars.
  - is_fresh judges freshness from source_updated_at, never retrieved_at.
  - Future SCAN water fields exist as None placeholders only; SCAN is NOT
    implemented here and ktema never imports the SCAN water adapter module.
"""
from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .registry import SanPedroError, sanpedro_resolve


class KtemaError(ValueError):
    """Fail-closed KTEMA error. The message always starts with the KTEMA_* code."""


TABLE_FILENAME = "ktema_county_data.json"
TABLE_BUILT_AT_FALLBACK = "unknown"

# Increment-1 coverage: the four coordinator-listed FL counties.
CANONICAL_COUNTIES = ("Orange", "Seminole", "Volusia", "Lake")
COUNTY_FIPS = {
    "Orange": "12095",
    "Seminole": "12117",
    "Volusia": "12127",
    "Lake": "12069",
}

RESOLVED = "RESOLVED"
INCONCLUSIVE = "INCONCLUSIVE"
OUT_OF_COVERAGE = "OUT_OF_COVERAGE"
COUNTY_STATUSES = (RESOLVED, INCONCLUSIVE, OUT_OF_COVERAGE)

RESOLVE_CONFIDENCE = 0.95

# Parcel-ID patterns per county, verified against the official Property
# Appraiser source. EMPTY by design in Increment 1: patterns enter only
# verified. Any parcel_id therefore resolves INCONCLUSIVE.
PARCEL_PATTERNS: dict[str, dict[str, str]] = {}

_ZIP = re.compile(r"^\d{5}$")


# ---------------------------------------------------------------------------
# Query and resolution contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PropertyQuery:
    business_id: str | None
    zip: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    parcel_id: str | None = None


@dataclass(frozen=True)
class CountyResolution:
    status: str
    county: str | None
    candidates: tuple[str, ...]
    confidence: float
    reason: str
    evidence_refs: tuple[str, ...]


def _make_resolution(
    *,
    status: str,
    county: str | None,
    candidates: tuple[str, ...],
    confidence: float,
    reason: str,
    evidence_refs: tuple[str, ...],
) -> CountyResolution:
    if status not in COUNTY_STATUSES:
        raise KtemaError("KTEMA_STATUS_INVALID")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise KtemaError("KTEMA_CONFIDENCE_INVALID")
    if not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
        raise KtemaError("KTEMA_REASON_REQUIRED")
    refs = []
    for ref in evidence_refs:
        if not isinstance(ref, str) or not ref.strip() or ref != ref.strip():
            raise KtemaError("KTEMA_EVIDENCE_INVALID")
        refs.append(ref)
    refs = tuple(refs)
    if status == RESOLVED:
        if county is None:
            raise KtemaError("KTEMA_RESOLVED_COUNTY_REQUIRED")
        if candidates:
            raise KtemaError("KTEMA_RESOLVED_CANDIDATES_FORBIDDEN")
        if not refs:
            raise KtemaError("KTEMA_RESOLVED_EVIDENCE_REQUIRED")
    elif county is not None:
        raise KtemaError("KTEMA_UNRESOLVED_COUNTY_FORBIDDEN")
    return CountyResolution(
        status=status,
        county=county,
        candidates=tuple(candidates),
        confidence=float(confidence),
        reason=reason.strip(),
        evidence_refs=refs,
    )


# ---------------------------------------------------------------------------
# County table loading (pure local file; no network)
# ---------------------------------------------------------------------------


def _default_table_path() -> Path:
    return Path(__file__).with_name(TABLE_FILENAME)


def load_county_table(table_path: Path | str | None = None) -> tuple[dict, dict[str, tuple[str, ...]]]:
    """Load and validate the ZIP->county table.

    Returns (meta, zips) where zips maps a 5-digit ZIP to a sorted tuple of
    canonical county names. Malformed tables fail closed with
    KTEMA_TABLE_INVALID. Pure local file read; no network.
    """
    path = Path(table_path) if table_path is not None else _default_table_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KtemaError(f"KTEMA_TABLE_INVALID:{exc}") from exc
    if not isinstance(data, dict):
        raise KtemaError("KTEMA_TABLE_INVALID:not-an-object")
    meta = data.get("meta")
    raw_zips = data.get("zips")
    if not isinstance(meta, dict) or not isinstance(raw_zips, dict):
        raise KtemaError("KTEMA_TABLE_INVALID:meta-or-zips-missing")
    built_at = meta.get("built_at")
    if not isinstance(built_at, str) or not built_at.strip():
        raise KtemaError("KTEMA_TABLE_INVALID:built_at-missing")
    zips: dict[str, tuple[str, ...]] = {}
    for zip_code, counties in raw_zips.items():
        if not isinstance(zip_code, str) or not _ZIP.fullmatch(zip_code) or zip_code == "00000":
            raise KtemaError(f"KTEMA_TABLE_INVALID:bad-zip:{zip_code!r}")
        if not isinstance(counties, list) or not counties:
            raise KtemaError(f"KTEMA_TABLE_INVALID:bad-counties:{zip_code}")
        for county in counties:
            if not isinstance(county, str) or county != county.strip() or county not in CANONICAL_COUNTIES:
                raise KtemaError(f"KTEMA_TABLE_INVALID:bad-county:{zip_code}:{county!r}")
        if len(set(counties)) != len(counties):
            raise KtemaError(f"KTEMA_TABLE_INVALID:duplicate-county:{zip_code}")
        zips[zip_code] = tuple(sorted(counties))
    return meta, zips


# ---------------------------------------------------------------------------
# Signal validation
# ---------------------------------------------------------------------------


def _present(value: object) -> bool:
    """A signal is present only if non-None and (for strings) non-blank.

    Blank strings count as absent, so a blank signal can never masquerade
    as a malformed one: the query then fails KTEMA_QUERY_SIGNAL_INVALID.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _validate_zip(zip_code: object) -> str:
    if not isinstance(zip_code, str) or not _ZIP.fullmatch(zip_code) or zip_code == "00000":
        raise KtemaError("KTEMA_ZIP_INVALID")
    return zip_code


def _validate_coordinates(latitude: object, longitude: object) -> tuple[float, float]:
    for value in (latitude, longitude):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise KtemaError("KTEMA_COORDS_INVALID")
    lat, lon = float(latitude), float(longitude)
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise KtemaError("KTEMA_COORDS_INVALID")
    return lat, lon


def _resolve_business(business_id: object, registry_path: Path | None) -> None:
    if not isinstance(business_id, str) or not business_id.strip():
        raise KtemaError("KTEMA_BUSINESS_REQUIRED")
    try:
        sanpedro_resolve(business_id, registry_path)
    except SanPedroError as exc:
        raise KtemaError(f"KTEMA_BUSINESS_INVALID:{exc}") from exc


# ---------------------------------------------------------------------------
# County resolution
# ---------------------------------------------------------------------------


def resolve_county(
    query: PropertyQuery,
    table_path: Path | str | None = None,
    registry_path: Path | None = None,
) -> CountyResolution:
    """Resolve a property query to its FL county. Deterministic; no network.

    Precedence: parcel_id -> zip+address -> zip -> address -> coordinates.
    A multi-county ZIP raises KTEMA_COUNTY_AMBIGUOUS (never guessed).
    """
    if not isinstance(query, PropertyQuery):
        raise KtemaError("KTEMA_QUERY_INVALID")
    _resolve_business(query.business_id, registry_path)

    has_parcel = _present(query.parcel_id)
    has_zip = _present(query.zip)
    has_address = _present(query.address)
    has_lat = query.latitude is not None
    has_lon = query.longitude is not None
    if has_lat != has_lon:
        raise KtemaError("KTEMA_QUERY_SIGNAL_INVALID")
    has_coords = has_lat and has_lon

    signals = {
        name
        for name, present in (
            ("parcel_id", has_parcel),
            ("zip", has_zip),
            ("address", has_address),
            ("coordinates", has_coords),
        )
        if present
    }
    if signals != {"zip", "address"} and len(signals) != 1:
        raise KtemaError("KTEMA_QUERY_SIGNAL_INVALID")

    meta, zips = load_county_table(table_path)
    built_at = str(meta.get("built_at") or TABLE_BUILT_AT_FALLBACK)
    table_ref = f"ktema:table:{built_at}"

    if has_parcel:
        # PARCEL_PATTERNS is empty by design in Increment 1: no parcel ID
        # can be verified against an official PA pattern yet.
        return _make_resolution(
            status=INCONCLUSIVE,
            county=None,
            candidates=(),
            confidence=0.0,
            reason="KTEMA_PARCEL_PATTERN_UNKNOWN",
            evidence_refs=(table_ref,),
        )
    if has_zip:
        zip_code = _validate_zip(query.zip)
        counties = zips.get(zip_code)
        if counties is None:
            return _make_resolution(
                status=OUT_OF_COVERAGE,
                county=None,
                candidates=(),
                confidence=0.0,
                reason="KTEMA_COUNTY_OUT_OF_COVERAGE",
                evidence_refs=(table_ref,),
            )
        if len(counties) > 1:
            raise KtemaError(
                "KTEMA_COUNTY_AMBIGUOUS:"
                f"{zip_code}:candidates={','.join(counties)}"
            )
        county = counties[0]
        return _make_resolution(
            status=RESOLVED,
            county=county,
            candidates=(),
            confidence=RESOLVE_CONFIDENCE,
            reason="KTEMA_ZIP_SINGLE_COUNTY",
            evidence_refs=(table_ref, f"ktema:fips:{COUNTY_FIPS[county]}"),
        )
    if has_address:
        return _make_resolution(
            status=INCONCLUSIVE,
            county=None,
            candidates=(),
            confidence=0.0,
            reason="KTEMA_ADDRESS_NEEDS_ZIP",
            evidence_refs=(table_ref,),
        )
    # Coordinates: no bounding-box geometry is embedded in Increment 1.
    _validate_coordinates(query.latitude, query.longitude)
    return _make_resolution(
        status=INCONCLUSIVE,
        county=None,
        candidates=(),
        confidence=0.0,
        reason="KTEMA_COORDS_GEOMETRY_NOT_EMBEDDED",
        evidence_refs=(table_ref,),
    )


# ---------------------------------------------------------------------------
# Increment 2: PropertyProfile, SourceProvenance, VerificationStatus
# ---------------------------------------------------------------------------
#
# Property-intelligence contracts. Deterministic and pure: no network, no
# PII interpolation, no SCAN Water Intelligence imports. The future SCAN
# water fields on PropertyProfile are None placeholders only.

VERIFIED = "VERIFIED"
NOT_FOUND = "NOT_FOUND"
UNAVAILABLE = "UNAVAILABLE"
# INCONCLUSIVE is defined above with the county statuses and reused here:
# "the source could not decide" is the same semantic for both layers.
VERIFICATION_STATUSES = (VERIFIED, NOT_FOUND, UNAVAILABLE, INCONCLUSIVE)

# Redaction bound for the opaque retrieval pointer in operational events.
RAW_REFERENCE_MAX_LEN = 64


@dataclass(frozen=True)
class SourceProvenance:
    """Where a property fact came from. Retrieval metadata only.

    raw_reference is an opaque retrieval pointer (e.g. a fixture URI or a
    cache key). It is NEVER constructed by interpolating PII.
    """

    source: str | None = None
    source_record_id: str | None = None
    source_updated_at: str | None = None
    retrieved_at: str | None = None
    raw_reference: str | None = None


@dataclass(frozen=True)
class PropertyProfile:
    """One property record as seen by a single source.

    property_exists is tri-state: True / False / None (unknown). None is
    the default: absence of evidence is never evidence.

    The water_* / pwsid / utility / service_area / well_probability /
    permit_intelligence fields are future SCAN placeholders, always None in
    this increment. SCAN is NOT implemented here.
    """

    state: str
    county: str
    parcel_id: str
    site_address: str
    zip: str
    property_type: str | None = None
    land_use: str | None = None
    year_built: int | None = None
    living_sqft: float | None = None
    lot_acres: float | None = None
    owner: str | None = None
    source: str | None = None
    source_record_id: str | None = None
    source_updated_at: str | None = None
    retrieved_at: str | None = None
    confidence: float = 0.0
    verification_status: str | None = None
    raw_reference: str | None = None
    isolation_key: str | None = None
    property_exists: bool | None = None
    attempted_sources: tuple[str, ...] = ()
    reason: str = ""
    # --- future SCAN water fields: None placeholders only, NOT implemented.
    water_source: str | None = None
    pwsid: str | None = None
    utility: str | None = None
    service_area: str | None = None
    well_probability: float | None = None
    permit_intelligence: str | None = None


def validate_property_profile(
    profile: PropertyProfile, *, owner_authorized: bool = False
) -> PropertyProfile:
    """Constructor gate for PropertyProfile. Fail-closed; returns the
    validated profile (owner normalized: blank -> None).

    - verification_status missing/blank -> KTEMA_STATUS_REQUIRED; a string
      outside the closed set -> KTEMA_STATUS_INVALID (case-sensitive:
      "verified" != VERIFIED).
    - NOT_FOUND with any existence claim (property_exists True or False)
      -> KTEMA_NOTFOUND_EXISTENCE_CLAIM_FORBIDDEN. NOT_FOUND means "this
      source produced no match", never an assertion about existence, so it
      requires property_exists is None.
    - VERIFIED without complete provenance (source, source_record_id)
      -> KTEMA_PROVENANCE_SOURCE_REQUIRED.
    - retrieved_at earlier than source_updated_at
      -> KTEMA_PROVENANCE_TIME_INVERSION (compared when both present).
    - owner present without owner_authorized=True
      -> KTEMA_OWNER_UNAUTHORIZED (fail closed, never silently dropped).
      With owner_authorized=True the owner value is preserved.
    - isolation_key missing/blank -> KTEMA_BUSINESS_REQUIRED.
    - confidence outside [0, 1] -> KTEMA_CONFIDENCE_INVALID.
    """
    if not isinstance(profile, PropertyProfile):
        raise KtemaError("KTEMA_PROFILE_INVALID")

    status = profile.verification_status
    if status is None or (isinstance(status, str) and not status.strip()):
        raise KtemaError("KTEMA_STATUS_REQUIRED")
    if status not in VERIFICATION_STATUSES:
        raise KtemaError("KTEMA_STATUS_INVALID")

    if status == NOT_FOUND and profile.property_exists is not None:
        # NOT_FOUND = "this source produced no match". It can never carry
        # an existence claim in either direction.
        raise KtemaError("KTEMA_NOTFOUND_EXISTENCE_CLAIM_FORBIDDEN")

    if status == VERIFIED:
        if not _present(profile.source) or not _present(profile.source_record_id):
            raise KtemaError("KTEMA_PROVENANCE_SOURCE_REQUIRED")

    if _present(profile.source_updated_at) and _present(profile.retrieved_at):
        # ISO 8601 strings compare lexicographically under a single ISO
        # profile; both timestamps must come from the same source clock.
        if profile.retrieved_at < profile.source_updated_at:
            raise KtemaError("KTEMA_PROVENANCE_TIME_INVERSION")

    if not isinstance(profile.isolation_key, str) or not profile.isolation_key.strip():
        raise KtemaError("KTEMA_BUSINESS_REQUIRED")

    confidence = profile.confidence
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise KtemaError("KTEMA_CONFIDENCE_INVALID")

    owner = profile.owner
    if isinstance(owner, str) and not owner.strip():
        owner = None
    if owner is not None and not owner_authorized:
        raise KtemaError("KTEMA_OWNER_UNAUTHORIZED")

    if owner != profile.owner:
        profile = dataclasses.replace(profile, owner=owner)
    return profile


def to_cronicas_event(profile: PropertyProfile) -> dict:
    """Redacted operational event for CRONICAS. NEVER carries owner (PII).

    raw_reference is an opaque pointer: truncated to 64 chars, never
    expanded. No PII is ever interpolated into this event.
    """
    if not isinstance(profile, PropertyProfile):
        raise KtemaError("KTEMA_PROFILE_INVALID")
    event: dict = {
        "source": profile.source,
        "source_record_id": profile.source_record_id,
        "verification_status": profile.verification_status,
        "county": profile.county,
        "isolation_key": profile.isolation_key,
        "retrieved_at": profile.retrieved_at,
    }
    raw = profile.raw_reference
    if isinstance(raw, str) and raw.strip():
        event["raw_reference"] = raw[:RAW_REFERENCE_MAX_LEN]
    return event


def _parse_iso(value: object) -> datetime | None:
    """Parse an ISO 8601 timestamp; None on any failure (fail closed)."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text[-1] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def is_fresh(
    provenance: SourceProvenance,
    max_age_days: int | float,
    *,
    now_iso: str | None = None,
) -> bool:
    """Freshness is judged from source_updated_at, NEVER retrieved_at.

    now_iso pins "now" for deterministic tests; when omitted, current UTC
    is used. Returns False (fail closed) when source_updated_at is absent
    or unparseable, or when the freshness window itself is invalid.
    """
    if not isinstance(provenance, SourceProvenance):
        raise KtemaError("KTEMA_PROVENANCE_INVALID")
    if (
        isinstance(max_age_days, bool)
        or not isinstance(max_age_days, (int, float))
        or max_age_days < 0
    ):
        raise KtemaError("KTEMA_FRESHNESS_WINDOW_INVALID")
    updated = _parse_iso(provenance.source_updated_at)
    if updated is None:
        return False
    now = _parse_iso(now_iso) if now_iso is not None else datetime.now(timezone.utc)
    if now is None:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_days = (now - updated).total_seconds() / 86400.0
    return age_days <= float(max_age_days)
