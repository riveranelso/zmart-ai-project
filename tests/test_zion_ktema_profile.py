"""Adversarial tests for zion_core.ktema Increment 2 (PropertyProfile).

All fixtures are in-memory and synthetic: the owner names, parcel IDs and
source URIs below are TEST-ONLY values with no real-world referent. Timestamps
are fixed ISO strings; no live services are ever touched.
"""
import dataclasses
import re
import unittest
from pathlib import Path

from zion_core import ktema
from zion_core.ktema import (
    INCONCLUSIVE,
    NOT_FOUND,
    UNAVAILABLE,
    VERIFICATION_STATUSES,
    VERIFIED,
    PropertyProfile,
    SourceProvenance,
    is_fresh,
    to_cronicas_event,
    validate_property_profile,
)

BUSINESS = "zmart-consumer-rights"
SOURCE_UPDATED_AT = "2026-10-03T12:00:00+00:00"
RETRIEVED_AT = "2026-10-04T09:00:00+00:00"
NOW_ISO = "2026-10-04T10:00:00+00:00"
# Synthetic fixture owner name (no real-world referent).
FIXTURE_OWNER = "Jane Doe (fixture)"


def _base_profile(**overrides):
    params = dict(
        state="FL",
        county="Orange",
        parcel_id="12-34-56-78-90-1234",
        site_address="200 S Orange Ave, Orlando, FL",
        zip="32801",
        property_type="Single Family",
        land_use="Residential",
        year_built=1985,
        living_sqft=1800.0,
        lot_acres=0.25,
        source="orange-county-pa-fixture",
        source_record_id="PA-12345",
        source_updated_at=SOURCE_UPDATED_AT,
        retrieved_at=RETRIEVED_AT,
        confidence=0.9,
        verification_status=VERIFIED,
        raw_reference="fixture://orange-county-pa/PA-12345",
        isolation_key=BUSINESS,
        property_exists=True,
        attempted_sources=("orange-county-pa-fixture",),
        reason="KTEMA_FIXTURE_MATCH",
    )
    params.update(overrides)
    return PropertyProfile(**params)


class KtemaVerificationStatusTests(unittest.TestCase):
    def test_verification_status_set_is_closed(self):
        self.assertEqual(
            VERIFICATION_STATUSES, (VERIFIED, NOT_FOUND, UNAVAILABLE, INCONCLUSIVE)
        )

    def test_missing_status_is_never_defaulted(self):
        # verification_status omitted / None / blank: never defaulted,
        # always KTEMA_STATUS_REQUIRED.
        for status in (None, "", "   "):
            with self.subTest(status=status):
                profile = _base_profile(verification_status=status)
                with self.assertRaisesRegex(ValueError, "KTEMA_STATUS_REQUIRED"):
                    validate_property_profile(profile)

    def test_unknown_status_string_rejected(self):
        # Case-sensitive: "verified" != VERIFIED.
        for status in ("verified", "FOUND", "PARTIAL"):
            with self.subTest(status=status):
                profile = _base_profile(verification_status=status)
                with self.assertRaisesRegex(ValueError, "KTEMA_STATUS_INVALID"):
                    validate_property_profile(profile)


class KtemaNotFoundTests(unittest.TestCase):
    def test_not_found_cannot_carry_existence_claim(self):
        # NOT_FOUND = "this source produced no match", never an existence
        # assertion in either direction.
        for existence in (False, True):
            with self.subTest(property_exists=existence):
                profile = _base_profile(
                    verification_status=NOT_FOUND, property_exists=existence
                )
                with self.assertRaisesRegex(
                    ValueError, "KTEMA_NOTFOUND_EXISTENCE_CLAIM_FORBIDDEN"
                ):
                    validate_property_profile(profile)

    def test_not_found_profile_records_attempt_not_existence(self):
        # A NOT_FOUND profile records the attempt (attempted_sources) with
        # property_exists left unknown (None).
        profile = _base_profile(
            verification_status=NOT_FOUND,
            property_exists=None,
            attempted_sources=("orange-county-pa-fixture",),
            reason="KTEMA_SOURCE_NO_MATCH",
        )
        result = validate_property_profile(profile)
        self.assertEqual(result.verification_status, NOT_FOUND)
        self.assertIsNone(result.property_exists)
        self.assertEqual(result.attempted_sources, ("orange-county-pa-fixture",))


class KtemaProvenanceTests(unittest.TestCase):
    def test_verified_without_provenance_rejected(self):
        for source, record_id in (("", ""), ("", "PA-12345"), ("orange-county-pa-fixture", "")):
            with self.subTest(source=source, source_record_id=record_id):
                profile = _base_profile(
                    verification_status=VERIFIED,
                    source=source,
                    source_record_id=record_id,
                )
                with self.assertRaisesRegex(
                    ValueError, "KTEMA_PROVENANCE_SOURCE_REQUIRED"
                ):
                    validate_property_profile(profile)

    def test_verified_with_provenance_passes(self):
        result = validate_property_profile(_base_profile())
        self.assertEqual(result.verification_status, VERIFIED)
        self.assertEqual(result.source, "orange-county-pa-fixture")
        self.assertEqual(result.source_record_id, "PA-12345")

    def test_provenance_time_inversion_rejected(self):
        profile = _base_profile(
            source_updated_at="2026-10-04T09:00:00+00:00",
            retrieved_at="2026-10-03T12:00:00+00:00",
        )
        with self.assertRaisesRegex(ValueError, "KTEMA_PROVENANCE_TIME_INVERSION"):
            validate_property_profile(profile)

    def test_freshness_uses_source_updated_at(self):
        # retrieved_at is fresh but source_updated_at is 64 days old:
        # judged NOT fresh -- freshness never looks at retrieved_at.
        old_source = SourceProvenance(
            source="orange-county-pa-fixture",
            source_record_id="PA-12345",
            source_updated_at="2026-08-01T12:00:00+00:00",
            retrieved_at=NOW_ISO,
        )
        self.assertFalse(is_fresh(old_source, 30, now_iso=NOW_ISO))
        # Fresh source_updated_at with a stale retrieved_at is still fresh.
        fresh_source = SourceProvenance(
            source="orange-county-pa-fixture",
            source_record_id="PA-12345",
            source_updated_at=NOW_ISO,
            retrieved_at="2020-01-01T00:00:00+00:00",
        )
        self.assertTrue(is_fresh(fresh_source, 30, now_iso=NOW_ISO))

    def test_freshness_unknown_source_updated_at_fails_closed(self):
        provenance = SourceProvenance(retrieved_at=NOW_ISO)
        self.assertFalse(is_fresh(provenance, 30, now_iso=NOW_ISO))

    def test_freshness_window_invalid_rejected(self):
        provenance = SourceProvenance(source_updated_at=NOW_ISO)
        for bad in (-1, True, "30"):
            with self.subTest(max_age_days=bad):
                with self.assertRaisesRegex(ValueError, "KTEMA_FRESHNESS_WINDOW_INVALID"):
                    is_fresh(provenance, bad, now_iso=NOW_ISO)


class KtemaOwnerTests(unittest.TestCase):
    def test_owner_without_authorization_fails_closed(self):
        # Present owner without owner_authorized=True: hard fail, never a
        # silent drop to None.
        profile = _base_profile(owner=FIXTURE_OWNER)
        with self.assertRaisesRegex(ValueError, "KTEMA_OWNER_UNAUTHORIZED"):
            validate_property_profile(profile)

    def test_authorized_consumer_receives_owner(self):
        profile = _base_profile(owner=FIXTURE_OWNER)
        result = validate_property_profile(profile, owner_authorized=True)
        self.assertEqual(result.owner, FIXTURE_OWNER)

    def test_owner_never_leaks_into_cronicas_event(self):
        profile = validate_property_profile(
            _base_profile(owner=FIXTURE_OWNER), owner_authorized=True
        )
        event = to_cronicas_event(profile)
        self.assertNotIn("owner", event)
        self.assertNotIn(FIXTURE_OWNER, str(event))
        # Operational fields survive redaction.
        self.assertEqual(event["source"], "orange-county-pa-fixture")
        self.assertEqual(event["verification_status"], VERIFIED)
        self.assertEqual(event["isolation_key"], BUSINESS)

    def test_owner_empty_string_normalizes_to_absent(self):
        # owner="" normalizes to None; no owner key in the event dict.
        result = validate_property_profile(_base_profile(owner=""))
        self.assertIsNone(result.owner)
        event = to_cronicas_event(result)
        self.assertNotIn("owner", event)

    def test_unauthorized_owner_blocked_even_on_not_found(self):
        profile = _base_profile(
            verification_status=NOT_FOUND,
            property_exists=None,
            owner=FIXTURE_OWNER,
        )
        with self.assertRaisesRegex(ValueError, "KTEMA_OWNER_UNAUTHORIZED"):
            validate_property_profile(profile)


class KtemaContractTests(unittest.TestCase):
    def test_confidence_out_of_range_rejected(self):
        for confidence in (-0.1, 1.5, True, "0.9"):
            with self.subTest(confidence=confidence):
                profile = _base_profile(confidence=confidence)
                with self.assertRaisesRegex(ValueError, "KTEMA_CONFIDENCE_INVALID"):
                    validate_property_profile(profile)

    def test_isolation_key_required(self):
        for key in (None, "", "   "):
            with self.subTest(isolation_key=key):
                profile = _base_profile(isolation_key=key)
                with self.assertRaisesRegex(ValueError, "KTEMA_BUSINESS_REQUIRED"):
                    validate_property_profile(profile)

    def test_profile_is_frozen(self):
        profile = _base_profile()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            profile.county = "Lake"  # type: ignore[misc]
        provenance = SourceProvenance(source="orange-county-pa-fixture")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            provenance.source = "other"  # type: ignore[misc]

    def test_cronicas_event_truncates_raw_reference(self):
        profile = _base_profile(raw_reference="x" * 100)
        event = to_cronicas_event(profile)
        self.assertEqual(len(event["raw_reference"]), 64)

    def test_future_scan_fields_are_placeholders(self):
        # Future SCAN water fields exist as None placeholders only; SCAN
        # is NOT implemented in this increment.
        profile = _base_profile()
        self.assertIsNone(profile.water_source)
        self.assertIsNone(profile.pwsid)
        self.assertIsNone(profile.utility)
        self.assertIsNone(profile.service_area)
        self.assertIsNone(profile.well_probability)
        self.assertIsNone(profile.permit_intelligence)

    def test_module_has_no_network_imports(self):
        source = Path(ktema.__file__).read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            self.assertIsNone(
                re.match(r"(import|from)\s+(urllib|requests|http|socket)\b", stripped),
                f"network import at line {lineno}: {line}",
            )

    def test_no_scan_water_import(self):
        source = Path(ktema.__file__).read_text(encoding="utf-8")
        self.assertNotIn("scan_water", source)

    def test_validate_rejects_non_profile(self):
        with self.assertRaisesRegex(ValueError, "KTEMA_PROFILE_INVALID"):
            validate_property_profile("not-a-profile")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
