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

Increment 3: PropertySource protocol, registry, router, FixturePropertySource,
FetchIntent, and KtemaBatchPlan.
  - Intent only, no transport: adapters NEVER perform network I/O and never
    build URLs (the module imports no urllib/requests/http). fetch_intent
    emits an opaque target_descriptor ("fixture://..." for the fixture); a
    real adapter's descriptor is equally opaque. The adapter never fetches:
    normalize() converts an INJECTED record (already obtained by external
    transport) into a PropertyProfile via validate_property_profile.
  - Source failures surface as UNAVAILABLE -- never NOT_FOUND. Ambiguous
    multi-match adapter responses raise KTEMA_MATCH_AMBIGUOUS with the
    candidate IDs preserved in the message; malformed adapter responses are
    rejected at the boundary with KTEMA_ADAPTER_RESPONSE_MALFORMED before
    any profile is half-built.
  - Only FixturePropertySource is published initially. Real sources enter
    only with a verified schema/endpoint -- never before.
  - The router maps a resolved county -> source_id and fails closed with
    KTEMA_COUNTY_SOURCE_UNREGISTERED when no source is registered for it;
    it NEVER falls back to a neighboring county's source.
  - plan_ktema_batch requires an explicit consumer business_id, re-validated
    through SAN PEDRO (spoofed/unknown IDs fail closed), and shares nothing
    with SCAN: no SCAN_* names, no SCAN-adapter import.

Increment 4: KtemaCache -- tenant-isolated in-memory cache.
  - KtemaCache is an explicitly injected instance: NEVER a module-global
    singleton and NEVER module-level state. Two instances share nothing.
  - The cache key embeds the isolation_key ("v1|isolation_key|source_id|
    query_fingerprint|source_record_id" sha256); the isolation_key is part
    of the key, never ambient. query_fingerprint already binds business_id
    (it comes from the FetchIntent query), so a key is unique per
    tenant x source x query x record.
  - get re-validates the requesting tenant against the entry's isolation
    key: a known key presented by the wrong tenant raises
    KTEMA_CACHE_TENANT_MISMATCH -- fail closed, never served.
  - Negative (NOT_FOUND) entries are TTL-bounded: put requires a configured
    validity for the source, otherwise KTEMA_CACHE_TTL_REQUIRED. A
    permanent negative would be an eternal NOT_FOUND -- forbidden.
  - Expired entries are misses (None), for positives and negatives alike;
    expired entries are lazily evicted on read.
  - rebind_profile_for_tenant re-validates the tenant binding of a
    (possibly deserialized) profile at consumption time: a profile whose
    isolation_key disagrees with the requesting tenant raises
    KTEMA_PROFILE_TENANT_MISMATCH. Tenant binding is re-checked on every
    consumption, never inherited from the stored object.
  - The cache performs no network I/O and builds no URLs; it stores
    already-validated PropertyProfile objects. The owner gate is never
    dispensed at store time: put() fails closed by default and only a
    caller holding a REAL upstream authorization passes
    owner_authorized=True explicitly (the authorization decision happens
    at intake/normalize, never in the cache).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

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
      -> KTEMA_PROVENANCE_TIME_INVERSION (both parsed to aware datetimes
      and compared as instants, never as strings -- mixed offsets compare
      by absolute time). Unparseable timestamps fail closed with
      KTEMA_PROVENANCE_TIME_INVALID, never a raw TypeError.
    - Any future SCAN water field (water_source, pwsid, utility,
      service_area, well_probability, permit_intelligence) carrying a
      value -> KTEMA_SCAN_FIELD_UNIMPLEMENTED. They exist as None
      placeholders only; SCAN is NOT implemented here.
    - owner present without owner_authorized=True
      -> KTEMA_OWNER_UNAUTHORIZED (fail closed, never silently dropped).
      With owner_authorized=True the owner value is preserved.
    - isolation_key missing/blank -> KTEMA_BUSINESS_REQUIRED.
    - confidence outside [0, 1] -> KTEMA_CONFIDENCE_INVALID.
    """
    if not isinstance(profile, PropertyProfile):
        raise KtemaError("KTEMA_PROFILE_INVALID")

    for field_name in (
        "water_source",
        "pwsid",
        "utility",
        "service_area",
        "well_probability",
        "permit_intelligence",
    ):
        if getattr(profile, field_name) is not None:
            # SCAN is NOT implemented here: these fields are None
            # placeholders only, so any value is contraband -- fail closed.
            raise KtemaError(f"KTEMA_SCAN_FIELD_UNIMPLEMENTED:{field_name}")

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
        # Compare as instants, not strings: mixed ISO offsets (e.g.
        # "-05:00" vs "+00:00") break lexicographic ordering.
        updated_at = _parse_iso(profile.source_updated_at)
        retrieved_at = _parse_iso(profile.retrieved_at)
        if updated_at is None or retrieved_at is None:
            # Fail closed on format, never a raw TypeError from mixed
            # naive/aware or non-ISO values.
            raise KtemaError("KTEMA_PROVENANCE_TIME_INVALID")
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if retrieved_at.tzinfo is None:
            retrieved_at = retrieved_at.replace(tzinfo=timezone.utc)
        if retrieved_at < updated_at:
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


# ---------------------------------------------------------------------------
# Increment 3: PropertySource protocol, registry, router, fixture, batch plan
# ---------------------------------------------------------------------------
#
# Intent only, no transport. A PropertySource describes WHAT the external
# transport should fetch (FetchIntent, opaque target_descriptor) and converts
# an already-fetched record into a PropertyProfile (normalize). The adapter
# itself never touches the network, never builds URLs, and never guesses.

#: The only source_id published initially. Real sources enter only with a
#: verified schema/endpoint -- never before.
FIXTURE_SOURCE_ID = "fixture"

#: Canonical operation name for a parcel-record fetch intent.
OPERATION_PARCEL_LOOKUP = "parcel_lookup"

_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class FetchIntent:
    """What the external transport should fetch. Opaque by design.

    target_descriptor describes the lookup target WITHOUT building a URL
    (e.g. "fixture://fixture/<parcel_id>"); the module never constructs
    URLs. The gate lives in __post_init__ (never in a factory) so direct
    construction cannot bypass it: the descriptor MUST use an allowed
    scheme -- the "fixture://" scheme or the declaring source's own
    source_id as scheme. Scheme validation (not substring matching) means
    a parcel_id that happens to contain "http" still produces a valid
    intent while a real URL is rejected.
    query_fingerprint is the sha256 of the normalized query, for cache keys.
    """

    source_id: str
    operation: str
    target_descriptor: str
    query_fingerprint: str
    requested_at_iso: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip() or self.source_id != self.source_id.strip():
            raise KtemaError("KTEMA_INTENT_SOURCE_REQUIRED")
        if not isinstance(self.operation, str) or not self.operation.strip() or self.operation != self.operation.strip():
            raise KtemaError("KTEMA_INTENT_OPERATION_REQUIRED")
        if (
            not isinstance(self.target_descriptor, str)
            or not self.target_descriptor.strip()
            or self.target_descriptor != self.target_descriptor.strip()
        ):
            raise KtemaError("KTEMA_INTENT_DESCRIPTOR_REQUIRED")
        allowed_schemes = (f"{self.source_id}://", "fixture://")
        if not self.target_descriptor.startswith(allowed_schemes):
            # Intent only: KTEMA never builds URLs. A descriptor with any
            # other scheme means a transport concern leaked into the
            # adapter -- reject.
            raise KtemaError("KTEMA_INTENT_DESCRIPTOR_FORBIDDEN")
        if not isinstance(self.query_fingerprint, str) or not _FINGERPRINT_RE.fullmatch(self.query_fingerprint):
            raise KtemaError("KTEMA_FINGERPRINT_INVALID")
        if _parse_iso(self.requested_at_iso) is None:
            raise KtemaError("KTEMA_INTENT_TIME_INVALID")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_fetch_intent(
    *,
    source_id: str,
    operation: str,
    target_descriptor: str,
    query_fingerprint: str,
    requested_at_iso: str,
) -> FetchIntent:
    # Intent is a value object: all field validation (including the
    # target_descriptor scheme gate) lives in FetchIntent.__post_init__,
    # so constructing the dataclass directly can never bypass it.
    return FetchIntent(
        source_id=source_id,
        operation=operation,
        target_descriptor=target_descriptor,
        query_fingerprint=query_fingerprint,
        requested_at_iso=requested_at_iso,
    )


def _canonical_query_key(query: PropertyQuery) -> str:
    """Canonical, normalized string form of a query for fingerprinting.

    business_id is part of the key: two businesses querying the same parcel
    must never share a cache fingerprint (business isolation).
    """

    def _s(value: object) -> str:
        return value.strip().lower() if isinstance(value, str) else ""

    def _n(value: object) -> str:
        return "" if value is None else repr(float(value))

    return "|".join(
        (
            f"business_id={_s(query.business_id)}",
            f"parcel_id={_s(query.parcel_id)}",
            f"zip={_s(query.zip)}",
            f"address={_s(query.address)}",
            f"latitude={_n(query.latitude)}",
            f"longitude={_n(query.longitude)}",
        )
    )


def query_fingerprint(query: PropertyQuery) -> str:
    """sha256 of the normalized query, for transport cache keys."""
    if not isinstance(query, PropertyQuery):
        raise KtemaError("KTEMA_QUERY_INVALID")
    return hashlib.sha256(_canonical_query_key(query).encode("utf-8")).hexdigest()


@runtime_checkable
class PropertySource(Protocol):
    """Adapter contract for one property-record source.

    The adapter NEVER fetches: fetch_intent describes the fetch for the
    external transport; normalize converts an INJECTED record (already
    fetched) into a PropertyProfile via validate_property_profile.
    """

    @property
    def source_id(self) -> str: ...

    def fetch_intent(self, query: PropertyQuery) -> FetchIntent: ...

    def normalize(
        self, record: dict | None, query: PropertyQuery, isolation_key: str
    ) -> PropertyProfile: ...


class PropertySourceRegistry:
    """Published property sources, keyed by source_id.

    Initially only FixturePropertySource is published. Unknown source IDs
    fail closed with KTEMA_SOURCE_UNKNOWN; re-registration fails closed
    (never silently replaced).
    """

    def __init__(self) -> None:
        self._sources: dict[str, PropertySource] = {}

    def register(self, source: PropertySource) -> None:
        if not isinstance(source, PropertySource):
            raise KtemaError("KTEMA_SOURCE_PROTOCOL_INVALID")
        source_id = source.source_id
        if (
            not isinstance(source_id, str)
            or not source_id.strip()
            or source_id != source_id.strip()
        ):
            raise KtemaError("KTEMA_SOURCE_ID_INVALID")
        if source_id in self._sources:
            raise KtemaError(f"KTEMA_SOURCE_DUPLICATE:{source_id}")
        self._sources[source_id] = source

    def get(self, source_id: str) -> PropertySource:
        if not isinstance(source_id, str) or not source_id.strip():
            raise KtemaError("KTEMA_SOURCE_UNKNOWN:")
        try:
            return self._sources[source_id]
        except KeyError:
            raise KtemaError(f"KTEMA_SOURCE_UNKNOWN:{source_id}") from None


class PropertySourceRouter:
    """Maps a resolved county to its registered PropertySource.

    Fail closed: a RESOLVED county with no registered source raises
    KTEMA_COUNTY_SOURCE_UNREGISTERED. The router NEVER falls back to a
    neighboring county's source. Non-RESOLVED resolutions cannot be
    routed at all (KTEMA_COUNTY_UNRESOLVED).
    """

    def __init__(self, county_to_source_id: dict[str, str] | None = None) -> None:
        if county_to_source_id is None:
            county_to_source_id = {county: FIXTURE_SOURCE_ID for county in CANONICAL_COUNTIES}
        if not isinstance(county_to_source_id, dict):
            raise KtemaError("KTEMA_ROUTER_MAPPING_INVALID")
        mapping: dict[str, str] = {}
        for county, source_id in county_to_source_id.items():
            if (
                not isinstance(county, str)
                or not county.strip()
                or county != county.strip()
                or not isinstance(source_id, str)
                or not source_id.strip()
                or source_id != source_id.strip()
            ):
                raise KtemaError("KTEMA_ROUTER_MAPPING_INVALID")
            mapping[county] = source_id
        self._mapping = mapping

    def route(
        self, county_resolution: CountyResolution, registry: PropertySourceRegistry
    ) -> PropertySource:
        if not isinstance(county_resolution, CountyResolution):
            raise KtemaError("KTEMA_RESOLUTION_INVALID")
        if not isinstance(registry, PropertySourceRegistry):
            raise KtemaError("KTEMA_REGISTRY_INVALID")
        if county_resolution.status != RESOLVED or not county_resolution.county:
            raise KtemaError(
                f"KTEMA_COUNTY_UNRESOLVED:status={county_resolution.status}"
            )
        county = county_resolution.county
        source_id = self._mapping.get(county)
        if source_id is None:
            raise KtemaError(f"KTEMA_COUNTY_SOURCE_UNREGISTERED:county={county}")
        try:
            return registry.get(source_id)
        except KtemaError as exc:
            if str(exc).startswith("KTEMA_SOURCE_UNKNOWN"):
                raise KtemaError(
                    f"KTEMA_COUNTY_SOURCE_UNREGISTERED:county={county}:source_id={source_id}"
                ) from exc
            raise


class FixturePropertySource:
    """In-memory fixture source. Implements PropertySource; never network.

    records maps parcel_id -> raw record dict. A record value of
    {"__raise__": <BaseException instance>} simulates a source outage.
    A record with a "matches" list simulates a search response: >1 matches
    raises KTEMA_MATCH_AMBIGUOUS, exactly 1 is normalized, 0 is NOT_FOUND.
    """

    def __init__(self, records: dict) -> None:
        if not isinstance(records, dict):
            raise KtemaError("KTEMA_FIXTURE_RECORDS_INVALID")
        for parcel_id, record in records.items():
            if not isinstance(parcel_id, str) or not parcel_id.strip():
                raise KtemaError("KTEMA_FIXTURE_RECORDS_INVALID:bad-parcel-id")
            if not isinstance(record, dict):
                raise KtemaError("KTEMA_FIXTURE_RECORDS_INVALID:bad-record")
        self._records = dict(records)

    @property
    def source_id(self) -> str:
        return FIXTURE_SOURCE_ID

    def lookup(self, parcel_id: str) -> dict | None:
        """Fixture-only convenience: fetch the raw record for a parcel_id.

        Returns None when the fixture holds no record (normalize() then
        produces NOT_FOUND). This is test/transport scaffolding, not a
        network fetch.
        """
        if not isinstance(parcel_id, str):
            raise KtemaError("KTEMA_FIXTURE_LOOKUP_INVALID")
        return self._records.get(parcel_id)

    def fetch_intent(self, query: PropertyQuery) -> FetchIntent:
        if not isinstance(query, PropertyQuery):
            raise KtemaError("KTEMA_QUERY_INVALID")
        if _present(query.parcel_id):
            key = str(query.parcel_id).strip()
        else:
            # Fully opaque when no parcel signal is present.
            key = f"q-{query_fingerprint(query)[:16]}"
        return _make_fetch_intent(
            source_id=FIXTURE_SOURCE_ID,
            operation=OPERATION_PARCEL_LOOKUP,
            target_descriptor=f"fixture://{FIXTURE_SOURCE_ID}/{key}",
            query_fingerprint=query_fingerprint(query),
            requested_at_iso=_now_iso(),
        )

    # -- normalize ---------------------------------------------------------

    def _profile_base(self, query: PropertyQuery, isolation_key: str) -> dict:
        parcel_id = str(query.parcel_id).strip() if _present(query.parcel_id) else ""
        zip_code = str(query.zip).strip() if _present(query.zip) else ""
        return {
            "state": "FL",
            "county": "",
            "parcel_id": parcel_id,
            "site_address": "",
            "zip": zip_code,
            "source": FIXTURE_SOURCE_ID,
            "isolation_key": isolation_key.strip(),
            "confidence": 0.0,
            "property_exists": None,
            "attempted_sources": (FIXTURE_SOURCE_ID,),
        }

    def _not_found(self, query: PropertyQuery, isolation_key: str) -> PropertyProfile:
        params = self._profile_base(query, isolation_key)
        params.update(
            verification_status=NOT_FOUND,
            reason="KTEMA_FIXTURE_NO_MATCH",
        )
        return validate_property_profile(PropertyProfile(**params))

    def _unavailable(
        self, query: PropertyQuery, isolation_key: str, exc: object
    ) -> PropertyProfile:
        exc_name = type(exc).__name__ if isinstance(exc, BaseException) else "UnknownError"
        params = self._profile_base(query, isolation_key)
        params.update(
            verification_status=UNAVAILABLE,
            # A source outage is never NOT_FOUND: the source did not answer,
            # so nothing can be claimed about the parcel.
            reason=f"KTEMA_SOURCE_OUTAGE:{FIXTURE_SOURCE_ID}:{exc_name}",
        )
        return validate_property_profile(PropertyProfile(**params))

    def normalize(
        self, record: dict | None, query: PropertyQuery, isolation_key: str
    ) -> PropertyProfile:
        """Convert an INJECTED fixture record into a PropertyProfile.

        record=None (fixture holds nothing for the parcel) -> NOT_FOUND.
        record={"__raise__": exc} -> UNAVAILABLE (source outage, never
        NOT_FOUND). Malformed records -> KTEMA_ADAPTER_RESPONSE_MALFORMED
        at the boundary, before any profile is half-built.
        """
        if not isinstance(query, PropertyQuery):
            raise KtemaError("KTEMA_QUERY_INVALID")
        if not isinstance(isolation_key, str) or not isolation_key.strip():
            raise KtemaError("KTEMA_BUSINESS_REQUIRED")
        if record is None:
            return self._not_found(query, isolation_key)
        if not isinstance(record, dict):
            raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:not-a-record")
        if "__raise__" in record:
            return self._unavailable(query, isolation_key, record["__raise__"])
        if "matches" in record:
            matches = record["matches"]
            if not isinstance(matches, list):
                raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:bad-matches")
            if len(matches) > 1:
                candidates = ",".join(
                    str(m.get("source_record_id", "?"))
                    if isinstance(m, dict)
                    else "?"
                    for m in matches
                )
                raise KtemaError(f"KTEMA_MATCH_AMBIGUOUS:candidates={candidates}")
            if not matches:
                return self._not_found(query, isolation_key)
            record = matches[0]
            if not isinstance(record, dict):
                raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:bad-match")

        source_record_id = record.get("source_record_id")
        if (
            not isinstance(source_record_id, str)
            or not source_record_id.strip()
        ):
            raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:source_record_id-missing")
        source_updated_at = record.get("source_updated_at")
        if source_updated_at is not None and _parse_iso(source_updated_at) is None:
            raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:source_updated_at-not-iso")
        raw_retrieved_at = record.get("retrieved_at")
        if not _present(raw_retrieved_at):
            # Absent/blank retrieval timestamp: the transport handed the
            # record to ZION now.
            retrieved_at = _now_iso()
        elif _parse_iso(raw_retrieved_at) is None:
            # A non-ISO retrieved_at (e.g. a raw int) is a malformed
            # adapter response -- rejected at the boundary, never a raw
            # TypeError downstream.
            raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:retrieved_at-not-iso")
        else:
            retrieved_at = (
                raw_retrieved_at.strip()
                if isinstance(raw_retrieved_at, str)
                else raw_retrieved_at
            )

        record_id = source_record_id.strip()
        provided_reference = record.get("raw_reference")
        if isinstance(provided_reference, str) and provided_reference.strip():
            # Opaque retrieval pointer OWNED BY THE SOURCE: used verbatim,
            # never rebuilt or interpolated.
            raw_reference = provided_reference
        else:
            # Deterministic surrogate pointer: sha256(source_id |
            # source_record_id), first 16 hex chars. The record id NEVER
            # appears in clear -- the docstring contract ("NEVER
            # constructed by interpolating PII") holds even when the
            # source ships PII inside source_record_id.
            digest = hashlib.sha256(
                f"{FIXTURE_SOURCE_ID}|{record_id}".encode("utf-8")
            ).hexdigest()[:16]
            raw_reference = f"fixture://ref-{digest}"
        params = self._profile_base(query, isolation_key)
        params.update(
            county=str(record.get("county") or "").strip(),
            parcel_id=str(record.get("parcel_id") or record_id).strip(),
            site_address=str(record.get("site_address") or "").strip(),
            zip=str(record.get("zip") or params["zip"]).strip(),
            property_type=record.get("property_type"),
            land_use=record.get("land_use"),
            year_built=record.get("year_built"),
            living_sqft=record.get("living_sqft"),
            lot_acres=record.get("lot_acres"),
            source_record_id=record_id,
            source_updated_at=(
                source_updated_at.strip()
                if isinstance(source_updated_at, str)
                else None
            ),
            retrieved_at=retrieved_at,
            confidence=1.0,
            verification_status=VERIFIED,
            # The fixture record always uses source_id "fixture", whatever
            # the injected record claims. raw_reference is an opaque
            # pointer: verbatim when the source provides one, otherwise a
            # sha256-derived surrogate -- NEVER interpolated PII.
            raw_reference=raw_reference,
            property_exists=True,
            reason="KTEMA_FIXTURE_MATCH",
        )
        return validate_property_profile(PropertyProfile(**params))


def fixture_registry(records: dict) -> PropertySourceRegistry:
    """Build a registry with only the FixturePropertySource published."""
    registry = PropertySourceRegistry()
    registry.register(FixturePropertySource(records))
    return registry


# ---------------------------------------------------------------------------
# Batch planning (KTEMA-owned; shares nothing with SCAN)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KtemaBatchItem:
    """One normalized batch item: the query plus its cache fingerprint."""

    query: PropertyQuery
    query_fingerprint: str


@dataclass(frozen=True)
class KtemaBatchPlan:
    """Plan for a KTEMA batch: explicit consumer business, isolation key,
    and normalized items. Carries no lookup results."""

    batch_id: str
    business_id: str
    isolation_key: str
    items: tuple[KtemaBatchItem, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))


def _normalize_batch_query(query: PropertyQuery, default_business_id: str) -> PropertyQuery:
    def _clean(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return value  # type: ignore[return-value]

    business_id = _clean(query.business_id) or default_business_id
    if business_id != default_business_id:
        # One batch, one consumer: mixing businesses would break isolation.
        raise KtemaError(
            f"KTEMA_BATCH_BUSINESS_MISMATCH:item={business_id}:batch={default_business_id}"
        )
    latitude = query.latitude
    longitude = query.longitude
    if latitude is not None or longitude is not None:
        # Coordinates must be numeric BEFORE fingerprinting: the
        # fingerprint path calls float(), which would otherwise leak a raw
        # ValueError. (Pair completeness is resolve_county's job; here only
        # the numeric type is enforced.)
        for value in (latitude, longitude):
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise KtemaError("KTEMA_QUERY_SIGNAL_INVALID")
    return PropertyQuery(
        business_id=business_id,
        zip=_clean(query.zip),
        address=_clean(query.address),
        latitude=query.latitude,
        longitude=query.longitude,
        parcel_id=_clean(query.parcel_id),
    )


def plan_ktema_batch(
    items,
    batch_id: str,
    business_id: str | None,
    *,
    registry_path: Path | None = None,
) -> KtemaBatchPlan:
    """Plan a KTEMA batch for an explicit consumer business.

    business_id is REQUIRED and re-validated through SAN PEDRO (unknown,
    disabled, or spoofed IDs fail closed -- the Increment 1 pattern).
    Returns the plan with the resolved isolation_key and normalized items.
    Shares nothing with SCAN.
    """
    if not isinstance(business_id, str) or not business_id.strip():
        raise KtemaError("KTEMA_BUSINESS_REQUIRED")
    try:
        context = sanpedro_resolve(business_id, registry_path)
    except SanPedroError as exc:
        raise KtemaError(f"KTEMA_BUSINESS_INVALID:{exc}") from exc
    if not isinstance(batch_id, str) or not batch_id.strip():
        raise KtemaError("KTEMA_BATCH_ID_REQUIRED")
    try:
        item_list = list(items)
    except TypeError as exc:
        raise KtemaError("KTEMA_BATCH_ITEMS_INVALID") from exc
    if not item_list:
        raise KtemaError("KTEMA_BATCH_ITEMS_REQUIRED")
    normalized: list[KtemaBatchItem] = []
    for item in item_list:
        if not isinstance(item, PropertyQuery):
            raise KtemaError("KTEMA_BATCH_ITEM_INVALID")
        query = _normalize_batch_query(item, context.business_id)
        normalized.append(
            KtemaBatchItem(query=query, query_fingerprint=query_fingerprint(query))
        )
    return KtemaBatchPlan(
        batch_id=batch_id.strip(),
        business_id=context.business_id,
        isolation_key=context.isolation_key,
        items=tuple(normalized),
    )


# ---------------------------------------------------------------------------
# Increment 4: tenant-isolated cache (KtemaCache)
# ---------------------------------------------------------------------------
#
# In-memory cache for PropertyProfile objects with TOTAL multi-tenant
# isolation. Explicit instance injection only: KtemaCache is constructed by
# the caller and passed where needed; there is deliberately NO module-level
# singleton and NO module-level entry store, so two instances can never
# observe each other's entries.

#: Cache-key material version. Bumped only if the key composition changes;
#: old keys never collide with new ones across versions.
KTEMA_CACHE_KEY_VERSION = "v1"

#: Default source validity (days) for cached entries. Only the fixture
#: source is published, so only it gets a default.
DEFAULT_CACHE_VALIDITY_DAYS = {FIXTURE_SOURCE_ID: 7}


def _require_isolation_key(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise KtemaError("KTEMA_BUSINESS_REQUIRED")
    return value


def _require_source_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise KtemaError("KTEMA_CACHE_SOURCE_INVALID")
    return value


def _require_cache_key(value: object) -> str:
    if not isinstance(value, str) or not _FINGERPRINT_RE.fullmatch(value):
        raise KtemaError("KTEMA_CACHE_KEY_INVALID")
    return value


def _require_fingerprint(value: object) -> str:
    if not isinstance(value, str) or not _FINGERPRINT_RE.fullmatch(value):
        raise KtemaError("KTEMA_FINGERPRINT_INVALID")
    return value


def build_ktema_cache_key(
    isolation_key: str,
    source_id: str,
    query_fingerprint: str,
    source_record_id: str,
) -> str:
    """Build the tenant-isolated cache key for one profile lookup.

    key = sha256("v1|"+isolation_key+"|"+source_id+"|"+query_fingerprint
    +"|"+source_record_id) in hex. The isolation_key is PART of the key,
    never ambient: two tenants querying the same parcel through the same
    source get different keys even if one tenant learns the other's key
    material. query_fingerprint already binds business_id (it is produced
    by query_fingerprint()/FetchIntent from the normalized query).
    """
    for value in (isolation_key, source_id, source_record_id):
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise KtemaError("KTEMA_CACHE_KEY_INPUT_INVALID")
    _require_fingerprint(query_fingerprint)
    material = "|".join(
        (KTEMA_CACHE_KEY_VERSION, isolation_key, source_id, query_fingerprint, source_record_id)
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _KtemaCacheEntry:
    """One stored cache entry. Private: never leaves the cache except as
    the profile it carries (via get), after tenant re-validation."""

    profile: PropertyProfile
    isolation_key: str
    source_id: str
    stored_at_iso: str
    expires_at_iso: str | None


class KtemaCache:
    """In-memory, tenant-isolated cache for PropertyProfile objects.

    Explicit instance: construct one and inject it; instances never share
    entries. ``validity_days`` maps source_id -> days of validity for
    cached entries (default: {"fixture": 7}); ``clock`` is a callable
    returning ISO "now" (for deterministic tests; default: real UTC time).

    No network, no URLs, no PII interpolation: the cache stores
    already-validated profiles only.
    """

    def __init__(
        self,
        *,
        validity_days: dict[str, int] | None = None,
        clock=None,
    ) -> None:
        if validity_days is None:
            validity_days = dict(DEFAULT_CACHE_VALIDITY_DAYS)
        if not isinstance(validity_days, dict):
            raise KtemaError("KTEMA_CACHE_VALIDITY_INVALID")
        parsed: dict[str, float] = {}
        for source_id, days in validity_days.items():
            if (
                not isinstance(source_id, str)
                or not source_id.strip()
                or source_id != source_id.strip()
            ):
                raise KtemaError("KTEMA_CACHE_VALIDITY_INVALID")
            if (
                isinstance(days, bool)
                or not isinstance(days, (int, float))
                or not days > 0
            ):
                raise KtemaError("KTEMA_CACHE_VALIDITY_INVALID")
            parsed[source_id] = float(days)
        self._validity_days = parsed
        if clock is None:
            clock = _now_iso
        if not callable(clock):
            raise KtemaError("KTEMA_CACHE_CLOCK_INVALID")
        self._clock = clock
        # Instance-level store only. No module/class-level state: two
        # KtemaCache() instances never see each other's entries.
        self._entries: dict[str, _KtemaCacheEntry] = {}

    def _now(self, now_iso: str | None) -> datetime:
        if now_iso is not None:
            parsed = _parse_iso(now_iso)
            if parsed is None:
                raise KtemaError("KTEMA_CACHE_TIME_INVALID")
        else:
            parsed = _parse_iso(self._clock())
            if parsed is None:
                # A clock that does not return ISO time fails closed.
                raise KtemaError("KTEMA_CACHE_TIME_INVALID")
        if parsed.tzinfo is None:
            # Same convention as is_fresh: naive ISO means UTC.
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def put(
        self,
        *,
        isolation_key: str,
        source_id: str,
        query_fingerprint: str,
        source_record_id: str,
        profile: PropertyProfile,
        owner_authorized: bool = False,
        now_iso: str | None = None,
    ) -> str:
        """Store a profile under its tenant-isolated key. Returns the key.

        The profile is structurally re-validated. The owner gate is NEVER
        dispensed here: ``owner_authorized`` defaults to False (fail
        closed), and a profile carrying owner PII with the default raises
        KTEMA_OWNER_UNAUTHORIZED. A caller that holds a REAL upstream
        authorization (the decision lives at intake/normalize, never in
        the cache) passes ``owner_authorized=True`` explicitly.

        The profile must already be bound to the same isolation_key it is
        stored under (KTEMA_CACHE_PROFILE_TENANT_MISMATCH otherwise --
        binding bugs fail closed at store time).

        Negative (NOT_FOUND) entries REQUIRE a configured validity for the
        source: a permanent negative would be an eternal NOT_FOUND --
        forbidden. Missing validity raises KTEMA_CACHE_TTL_REQUIRED.
        Positive entries use the configured validity when present; without
        one they carry no expiry and live until invalidated.
        """
        isolation_key = _require_isolation_key(isolation_key)
        source_id = _require_source_id(source_id)
        _require_fingerprint(query_fingerprint)
        if not isinstance(profile, PropertyProfile):
            raise KtemaError("KTEMA_PROFILE_INVALID")
        if not isinstance(owner_authorized, bool):
            raise KtemaError("KTEMA_CACHE_OWNER_AUTHORIZATION_INVALID")
        # Structural re-validation; the owner-authorization decision lives
        # upstream (intake/normalize), never in the cache -- the default
        # fails closed and only an explicit True dispenses the gate.
        profile = validate_property_profile(profile, owner_authorized=owner_authorized)
        if profile.isolation_key != isolation_key:
            raise KtemaError("KTEMA_CACHE_PROFILE_TENANT_MISMATCH")
        key = build_ktema_cache_key(
            isolation_key, source_id, query_fingerprint, source_record_id
        )
        now = self._now(now_iso)
        ttl_days = self._validity_days.get(source_id)
        if profile.verification_status == NOT_FOUND and ttl_days is None:
            raise KtemaError(f"KTEMA_CACHE_TTL_REQUIRED:source_id={source_id}")
        expires_at_iso: str | None = None
        if ttl_days is not None:
            # now is always tz-aware UTC (see _now).
            expires_at_iso = (now + timedelta(days=ttl_days)).isoformat()
        self._entries[key] = _KtemaCacheEntry(
            profile=profile,
            isolation_key=isolation_key,
            source_id=source_id,
            # Derived from the single parsed "now" above: one clock read,
            # no drift between expiry arithmetic and the stored timestamp.
            stored_at_iso=now.isoformat(),
            expires_at_iso=expires_at_iso,
        )
        return key

    def get(
        self,
        key: str,
        *,
        requesting_isolation_key: str,
        max_source_age_days: int | float | None = None,
        now_iso: str | None = None,
    ) -> PropertyProfile | None:
        """Return the cached profile for key, or None on a miss.

        Fail closed on tenant mismatch: if the requesting tenant differs
        from the entry's isolation_key, KTEMA_CACHE_TENANT_MISMATCH is
        raised even when the requester knows the exact key.
        Expired entries are misses (None) -- for positives and negatives
        alike -- and are lazily evicted on read. A missing key is a miss.

        Source vintage: the TTL above only bounds how long ago the entry
        was STORED, not how fresh the underlying record is. When
        max_source_age_days is passed, the profile's source_updated_at is
        parsed and the entry is a MISS (None) if the source record is
        older than the window. Consumers that need freshness guarantees
        must use max_source_age_days here or is_fresh() on the profile's
        provenance; freshness is always judged from source_updated_at,
        never from retrieved_at.
        """
        _require_cache_key(key)
        requesting_isolation_key = _require_isolation_key(requesting_isolation_key)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.isolation_key != requesting_isolation_key:
            raise KtemaError("KTEMA_CACHE_TENANT_MISMATCH")
        if entry.expires_at_iso is not None:
            expires_at = _parse_iso(entry.expires_at_iso)
            if expires_at is None:
                # Stored by put(); an unparseable stored expiry is an
                # internal inconsistency -- fail closed, never serve.
                raise KtemaError("KTEMA_CACHE_TIME_INVALID")
            if self._now(now_iso) >= expires_at:
                del self._entries[key]
                return None
        if max_source_age_days is not None:
            if (
                isinstance(max_source_age_days, bool)
                or not isinstance(max_source_age_days, (int, float))
                or max_source_age_days < 0
            ):
                raise KtemaError("KTEMA_FRESHNESS_WINDOW_INVALID")
            now = self._now(now_iso)
            updated = _parse_iso(entry.profile.source_updated_at)
            if updated is None:
                # No usable source vintage: fail closed as a miss rather
                # than serve an unverifiable record as current.
                return None
            if updated.tzinfo is None:
                # Same convention as is_fresh: naive ISO means UTC.
                updated = updated.replace(tzinfo=timezone.utc)
            age_days = (now - updated).total_seconds() / 86400.0
            if age_days > float(max_source_age_days):
                return None
        return entry.profile

    def invalidate(self, key: str) -> bool:
        """Explicitly drop a cached entry. True if one was removed."""
        _require_cache_key(key)
        return self._entries.pop(key, None) is not None


def rebind_profile_for_tenant(
    profile: PropertyProfile, requesting_isolation_key: str
) -> PropertyProfile:
    """Re-validate a (possibly deserialized) profile's tenant binding.

    Returns the profile unchanged when its isolation_key matches the
    requesting tenant; raises KTEMA_PROFILE_TENANT_MISMATCH otherwise.
    Tenant binding is a property of the consumption context: it is
    re-checked on EVERY consumption and never inherited from the object
    that arrived (cache hit, queue message, deserialized payload).
    """
    if not isinstance(profile, PropertyProfile):
        raise KtemaError("KTEMA_PROFILE_INVALID")
    requesting_isolation_key = _require_isolation_key(requesting_isolation_key)
    if profile.isolation_key != requesting_isolation_key:
        raise KtemaError("KTEMA_PROFILE_TENANT_MISMATCH")
    return profile
