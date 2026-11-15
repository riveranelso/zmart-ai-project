"""Orange County Parcels_BCC source adapter for KTEMA.

No transport lives here. The adapter normalizes already-fetched ArcGIS JSON
from the official Orange County Parcels_BCC layer into PropertyProfile.
Schema verified 2026-10-04. Owner fields are intentionally not consumed.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from .ktema import (
    NOT_FOUND,
    OPERATION_PARCEL_LOOKUP,
    UNAVAILABLE,
    VERIFIED,
    FetchIntent,
    KtemaError,
    PropertyProfile,
    PropertyQuery,
    PropertySource,
    PropertySourceRegistry,
    query_fingerprint,
    validate_property_profile,
)

ORANGE_PARCELS_BCC_SOURCE_ID = "orange-parcels-bcc"
ORANGE_PARCELS_BCC_FIELDS = (
    "PARCEL", "SITUS", "SITUS_ZIP", "ZIP_SITUS", "SUBTYPE", "TYPE_CODE",
    "DOR_CODE", "LAND_DOR_CODE", "AYB", "LIVING_AREA", "ACREAGE",
)
_ZIP = re.compile(r"^\d{5}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _present(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:text-field-type")
    value = value.strip()
    return value or None


def _number(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise KtemaError(f"KTEMA_ADAPTER_RESPONSE_MALFORMED:{field}-type")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        # NaN/inf are not measurements: fail closed with the documented
        # adapter error instead of leaking a raw ValueError or caching
        # a non-finite profile.
        raise KtemaError(f"KTEMA_ADAPTER_RESPONSE_MALFORMED:{field}-non-finite")
    return result


def _integer(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise KtemaError(f"KTEMA_ADAPTER_RESPONSE_MALFORMED:{field}-type")
    if value != value or value in (float("inf"), float("-inf")):
        raise KtemaError(f"KTEMA_ADAPTER_RESPONSE_MALFORMED:{field}-non-finite")
    if int(value) != value:
        raise KtemaError(f"KTEMA_ADAPTER_RESPONSE_MALFORMED:{field}-fractional")
    return int(value)


class OrangeParcelsBccSource:
    """Normalize injected Orange County Parcels_BCC ArcGIS responses."""

    @property
    def source_id(self) -> str:
        return ORANGE_PARCELS_BCC_SOURCE_ID

    def fetch_intent(self, query: PropertyQuery) -> FetchIntent:
        if not isinstance(query, PropertyQuery):
            raise KtemaError("KTEMA_QUERY_INVALID")
        fp = query_fingerprint(query)
        if _present(query.parcel_id):
            mode = "parcel"
        elif _present(query.address) and _present(query.zip):
            mode = "address"
        else:
            raise KtemaError(
                "KTEMA_SOURCE_QUERY_UNSUPPORTED:"
                f"{self.source_id}:requires-parcel-or-address-plus-zip"
            )
        return FetchIntent(
            source_id=self.source_id,
            operation=OPERATION_PARCEL_LOOKUP,
            target_descriptor=f"{self.source_id}://{mode}/{fp[:24]}",
            query_fingerprint=fp,
            requested_at_iso=_now_iso(),
        )

    def _base(self, query: PropertyQuery, isolation_key: str) -> dict:
        if not isinstance(query, PropertyQuery):
            raise KtemaError("KTEMA_QUERY_INVALID")
        if not isinstance(isolation_key, str) or not isolation_key.strip():
            raise KtemaError("KTEMA_BUSINESS_REQUIRED")
        return {
            "state": "FL",
            "county": "Orange",
            "parcel_id": query.parcel_id.strip() if _present(query.parcel_id) else "",
            "site_address": "",
            "zip": query.zip.strip() if _present(query.zip) else "",
            "source": self.source_id,
            "isolation_key": isolation_key.strip(),
            "confidence": 0.0,
            "property_exists": None,
            "attempted_sources": (self.source_id,),
        }

    def _not_found(self, query: PropertyQuery, isolation_key: str) -> PropertyProfile:
        params = self._base(query, isolation_key)
        params.update(
            verification_status=NOT_FOUND,
            reason="KTEMA_ORANGE_PARCELS_BCC_NO_MATCH",
        )
        return validate_property_profile(PropertyProfile(**params))

    def _unavailable(self, query: PropertyQuery, isolation_key: str) -> PropertyProfile:
        params = self._base(query, isolation_key)
        params.update(
            verification_status=UNAVAILABLE,
            reason="KTEMA_SOURCE_OUTAGE:orange-parcels-bcc",
        )
        return validate_property_profile(PropertyProfile(**params))

    def normalize(
        self, record: dict | None, query: PropertyQuery, isolation_key: str
    ) -> PropertyProfile:
        if record is None:
            return self._not_found(query, isolation_key)
        if not isinstance(record, dict):
            raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:not-an-object")
        if "error" in record:
            return self._unavailable(query, isolation_key)

        features = record.get("features")
        if not isinstance(features, list):
            raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:features-required")
        if not features:
            return self._not_found(query, isolation_key)
        if len(features) > 1:
            candidates = []
            for feature in features:
                attrs = feature.get("attributes") if isinstance(feature, dict) else None
                parcel = attrs.get("PARCEL") if isinstance(attrs, dict) else None
                candidates.append(str(parcel or "?"))
            raise KtemaError("KTEMA_MATCH_AMBIGUOUS:candidates=" + ",".join(candidates))

        feature = features[0]
        if not isinstance(feature, dict) or not isinstance(feature.get("attributes"), dict):
            raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:attributes-required")
        attrs = feature["attributes"]

        parcel = _text(attrs.get("PARCEL"))
        situs = _text(attrs.get("SITUS"))
        situs_zip = _text(attrs.get("SITUS_ZIP")) or _text(attrs.get("ZIP_SITUS"))
        if parcel is None:
            raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:PARCEL-required")
        if situs is None:
            raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:SITUS-required")
        if situs_zip is None or not _ZIP.fullmatch(situs_zip) or situs_zip == "00000":
            raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:SITUS_ZIP-invalid")

        retrieved_at = record.get("_retrieved_at", _now_iso())
        if not isinstance(retrieved_at, str):
            raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:retrieved_at-type")
        source_updated_at = record.get("_source_updated_at")
        if source_updated_at is not None and not isinstance(source_updated_at, str):
            raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:source_updated_at-type")

        digest = hashlib.sha256(
            f"{self.source_id}|{parcel}".encode("utf-8")
        ).hexdigest()[:20]
        land_use = _text(attrs.get("LAND_DOR_CODE")) or _text(attrs.get("DOR_CODE"))
        subtype = attrs.get("SUBTYPE")
        type_code = _text(attrs.get("TYPE_CODE"))
        property_type = type_code
        if subtype is not None:
            if isinstance(subtype, bool) or not isinstance(subtype, (int, float, str)):
                raise KtemaError("KTEMA_ADAPTER_RESPONSE_MALFORMED:SUBTYPE-type")
            property_type = f"{subtype}:{type_code}" if type_code else str(subtype)

        params = self._base(query, isolation_key)
        params.update(
            parcel_id=parcel,
            site_address=situs,
            zip=situs_zip,
            property_type=property_type,
            land_use=land_use,
            year_built=_integer(attrs.get("AYB"), "AYB"),
            living_sqft=_number(attrs.get("LIVING_AREA"), "LIVING_AREA"),
            lot_acres=_number(attrs.get("ACREAGE"), "ACREAGE"),
            owner=None,
            source_record_id=parcel,
            source_updated_at=source_updated_at.strip() if isinstance(source_updated_at, str) else None,
            retrieved_at=retrieved_at.strip(),
            confidence=1.0,
            verification_status=VERIFIED,
            raw_reference=f"{self.source_id}://ref-{digest}",
            property_exists=True,
            reason="KTEMA_ORANGE_PARCELS_BCC_MATCH",
        )
        return validate_property_profile(PropertyProfile(**params))


def orange_property_registry() -> PropertySourceRegistry:
    registry = PropertySourceRegistry()
    registry.register(OrangeParcelsBccSource())
    return registry
