"""Adversarial tests for zion_core.ktema Increment 3 (source protocol).

PropertySource protocol + registry + router + FixturePropertySource +
FetchIntent + plan_ktema_batch.

All fixtures are in-memory and synthetic: parcel IDs, addresses and source
URIs below are TEST-ONLY values with no real-world referent. Timestamps are
fixed ISO strings; no live services are ever touched. The module under test
performs no network I/O (intent only, no transport) and never builds URLs.
"""
import ast
import re
import unittest
from pathlib import Path

from zion_core import ktema
from zion_core.ktema import (
    FIXTURE_SOURCE_ID,
    NOT_FOUND,
    OPERATION_PARCEL_LOOKUP,
    RESOLVED,
    UNAVAILABLE,
    VERIFIED,
    CountyResolution,
    FetchIntent,
    FixturePropertySource,
    KtemaBatchItem,
    KtemaBatchPlan,
    KtemaError,
    PropertyQuery,
    PropertySource,
    PropertySourceRegistry,
    PropertySourceRouter,
    fixture_registry,
    plan_ktema_batch,
    query_fingerprint,
    resolve_county,
)

BUSINESS = "los-duros"
ISOLATION_KEY = "los-duros"
SOURCE_UPDATED_AT = "2026-10-03T12:00:00+00:00"
RETRIEVED_AT = "2026-10-04T09:00:00+00:00"
PARCEL_ID = "12-34-56-78-90-1234"
# Real-world fact (downtown Orlando -> Orange County), exercised against the
# shipped Increment-1 table via the default path.
ORLANDO_ZIP = "32801"


def _good_record(parcel_id=PARCEL_ID):
    """Well-formed synthetic fixture record (no real-world referent)."""
    return {
        "source_record_id": parcel_id,
        "parcel_id": parcel_id,
        "state": "FL",
        "county": "Orange",
        "site_address": "200 S Orange Ave, Orlando, FL",
        "zip": ORLANDO_ZIP,
        "property_type": "Single Family",
        "land_use": "Residential",
        "year_built": 1985,
        "living_sqft": 1800.0,
        "lot_acres": 0.25,
        "source_updated_at": SOURCE_UPDATED_AT,
        "retrieved_at": RETRIEVED_AT,
    }


def _query(**kwargs):
    params = {"business_id": BUSINESS, "parcel_id": PARCEL_ID, "zip": ORLANDO_ZIP}
    params.update(kwargs)
    return PropertyQuery(**params)


def _resolved_orange():
    return CountyResolution(
        status=RESOLVED,
        county="Orange",
        candidates=(),
        confidence=0.95,
        reason="KTEMA_ZIP_SINGLE_COUNTY",
        evidence_refs=("ktema:table:test-fixture",),
    )


class _StubSource:
    """Minimal protocol-conformant source with a caller-chosen source_id."""

    def __init__(self, source_id):
        self._source_id = source_id

    @property
    def source_id(self):
        return self._source_id

    def fetch_intent(self, query):
        raise AssertionError("stub never used for fetch")

    def normalize(self, record, query, isolation_key):
        raise AssertionError("stub never used for normalize")


class RegistryTests(unittest.TestCase):
    def test_source_unknown_id_fails_closed(self):
        registry = PropertySourceRegistry()
        with self.assertRaisesRegex(KtemaError, r"^KTEMA_SOURCE_UNKNOWN"):
            registry.get("no-such-source")

    def test_register_get_roundtrip(self):
        registry = PropertySourceRegistry()
        source = FixturePropertySource({})
        registry.register(source)
        self.assertIs(registry.get(FIXTURE_SOURCE_ID), source)

    def test_duplicate_registration_fails_closed(self):
        registry = PropertySourceRegistry()
        registry.register(FixturePropertySource({}))
        with self.assertRaisesRegex(KtemaError, r"^KTEMA_SOURCE_DUPLICATE"):
            registry.register(FixturePropertySource({}))

    def test_protocol_membership(self):
        self.assertIsInstance(FixturePropertySource({}), PropertySource)


class RouterTests(unittest.TestCase):
    def test_county_without_registered_source_fails_closed(self):
        # Empty registry: the mapped source_id ("fixture") is not published.
        registry = PropertySourceRegistry()
        router = PropertySourceRouter()
        with self.assertRaisesRegex(
            KtemaError, r"^KTEMA_COUNTY_SOURCE_UNREGISTERED"
        ):
            router.route(_resolved_orange(), registry)

    def test_router_never_falls_back_to_neighbor_source(self):
        # Seminole has a registered source; Orange's mapped source does not
        # exist. Routing Orange must fail closed, never borrow Seminole's.
        registry = PropertySourceRegistry()
        registry.register(_StubSource("seminole-pa"))
        router = PropertySourceRouter(
            {"Orange": "orange-pa", "Seminole": "seminole-pa"}
        )
        with self.assertRaisesRegex(
            KtemaError, r"^KTEMA_COUNTY_SOURCE_UNREGISTERED"
        ):
            router.route(_resolved_orange(), registry)
        # ...while Seminole itself still routes to its own source.
        seminole = CountyResolution(
            status=RESOLVED,
            county="Seminole",
            candidates=(),
            confidence=0.95,
            reason="KTEMA_ZIP_SINGLE_COUNTY",
            evidence_refs=("ktema:table:test-fixture",),
        )
        self.assertEqual(router.route(seminole, registry).source_id, "seminole-pa")

    def test_unresolved_county_cannot_route(self):
        registry = fixture_registry({})
        router = PropertySourceRouter()
        inconclusive = CountyResolution(
            status="INCONCLUSIVE",
            county=None,
            candidates=(),
            confidence=0.0,
            reason="KTEMA_ADDRESS_NEEDS_ZIP",
            evidence_refs=("ktema:table:test-fixture",),
        )
        with self.assertRaisesRegex(KtemaError, r"^KTEMA_COUNTY_UNRESOLVED"):
            router.route(inconclusive, registry)

    def test_resolve_then_route_integration(self):
        # Increment 1 -> 3: a real table resolution flows into the router and
        # fails closed when the county's source is not registered.
        resolution = resolve_county(_query(zip=ORLANDO_ZIP, parcel_id=None))
        self.assertEqual(resolution.status, RESOLVED)
        self.assertEqual(resolution.county, "Orange")
        router = PropertySourceRouter()
        with self.assertRaisesRegex(
            KtemaError, r"^KTEMA_COUNTY_SOURCE_UNREGISTERED"
        ):
            router.route(resolution, PropertySourceRegistry())


class FetchIntentTests(unittest.TestCase):
    def setUp(self):
        self.source = FixturePropertySource({PARCEL_ID: _good_record()})
        self.query = _query()

    def test_fetch_intent_is_opaque_no_urls(self):
        intent = self.source.fetch_intent(self.query)
        self.assertIsInstance(intent, FetchIntent)
        self.assertEqual(intent.source_id, FIXTURE_SOURCE_ID)
        self.assertEqual(intent.operation, OPERATION_PARCEL_LOOKUP)
        self.assertNotIn("http", intent.target_descriptor)
        self.assertTrue(intent.target_descriptor.startswith("fixture://"))
        self.assertRegex(intent.query_fingerprint, r"^[0-9a-f]{64}$")
        # Deterministic: same normalized query -> same fingerprint.
        again = self.source.fetch_intent(_query())
        self.assertEqual(intent.query_fingerprint, again.query_fingerprint)
        # Isolation: the business is part of the fingerprint.
        other = self.source.fetch_intent(_query(business_id="zmart-consumer-rights"))
        self.assertNotEqual(intent.query_fingerprint, other.query_fingerprint)

    def test_fetch_intent_without_parcel_stays_opaque(self):
        intent = self.source.fetch_intent(_query(parcel_id=None))
        self.assertNotIn("http", intent.target_descriptor)
        self.assertTrue(intent.target_descriptor.startswith("fixture://fixture/q-"))

    def test_module_imports_no_network_libraries(self):
        tree = ast.parse(Path(ktema.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[0])
        self.assertFalse({"urllib", "requests", "http"} & imported)


class FixtureNormalizeTests(unittest.TestCase):
    def setUp(self):
        self.records = {PARCEL_ID: _good_record()}
        self.source = FixturePropertySource(self.records)
        self.query = _query()

    def test_verified_fixture_roundtrip(self):
        profile = self.source.normalize(_good_record(), self.query, ISOLATION_KEY)
        self.assertEqual(profile.verification_status, VERIFIED)
        self.assertEqual(profile.confidence, 1.0)
        # Complete provenance.
        self.assertEqual(profile.source, FIXTURE_SOURCE_ID)
        self.assertEqual(profile.source_record_id, PARCEL_ID)
        self.assertEqual(profile.source_updated_at, SOURCE_UPDATED_AT)
        self.assertEqual(profile.retrieved_at, RETRIEVED_AT)
        self.assertTrue(profile.raw_reference.startswith("fixture://ref-"))
        # The record id never appears in clear in the generated pointer.
        self.assertNotIn(PARCEL_ID, profile.raw_reference)
        self.assertEqual(profile.isolation_key, ISOLATION_KEY)
        self.assertEqual(profile.attempted_sources, (FIXTURE_SOURCE_ID,))
        self.assertTrue(profile.property_exists)

    def test_not_found_profile_has_attempted_sources(self):
        # Integration: the fixture holds nothing for this parcel.
        record = self.source.lookup("99-99-99-99-99-9999")
        self.assertIsNone(record)
        profile = self.source.normalize(record, self.query, ISOLATION_KEY)
        self.assertEqual(profile.verification_status, NOT_FOUND)
        self.assertIsNone(profile.property_exists)
        self.assertEqual(profile.attempted_sources, (FIXTURE_SOURCE_ID,))

    def test_source_outage_is_unavailable_not_not_found(self):
        outage_records = {
            PARCEL_ID: {"__raise__": TimeoutError("simulated fixture outage")}
        }
        source = FixturePropertySource(outage_records)
        profile = source.normalize(
            outage_records[PARCEL_ID], self.query, ISOLATION_KEY
        )
        self.assertEqual(profile.verification_status, UNAVAILABLE)
        self.assertNotEqual(profile.verification_status, NOT_FOUND)
        self.assertIn(FIXTURE_SOURCE_ID, profile.reason)
        self.assertIsNone(profile.property_exists)
        self.assertEqual(profile.attempted_sources, (FIXTURE_SOURCE_ID,))

    def test_malformed_adapter_response_rejected_at_boundary(self):
        # Missing source_record_id.
        with self.assertRaisesRegex(
            KtemaError, r"^KTEMA_ADAPTER_RESPONSE_MALFORMED"
        ):
            self.source.normalize({"parcel_id": PARCEL_ID}, self.query, ISOLATION_KEY)
        # Non-ISO source_updated_at.
        bad_time = dict(_good_record())
        bad_time["source_updated_at"] = "yesterday-ish"
        with self.assertRaisesRegex(
            KtemaError, r"^KTEMA_ADAPTER_RESPONSE_MALFORMED"
        ):
            self.source.normalize(bad_time, self.query, ISOLATION_KEY)
        # Not a record at all: no half-built profile escapes.
        with self.assertRaisesRegex(
            KtemaError, r"^KTEMA_ADAPTER_RESPONSE_MALFORMED"
        ):
            self.source.normalize("not-a-record", self.query, ISOLATION_KEY)

    def test_ambiguous_source_match_preserves_candidates(self):
        record = {
            "matches": [
                {"source_record_id": "A-1", "parcel_id": "A-1"},
                {"source_record_id": "B-2", "parcel_id": "B-2"},
            ]
        }
        with self.assertRaisesRegex(KtemaError, r"^KTEMA_MATCH_AMBIGUOUS.*A-1.*B-2"):
            self.source.normalize(record, self.query, ISOLATION_KEY)

    def test_empty_matches_is_not_found(self):
        profile = self.source.normalize({"matches": []}, self.query, ISOLATION_KEY)
        self.assertEqual(profile.verification_status, NOT_FOUND)
        self.assertIsNone(profile.property_exists)


class BatchPlanTests(unittest.TestCase):
    def test_batch_requires_explicit_consumer_business(self):
        items = [_query()]
        for bad in (None, "", "   "):
            with self.assertRaisesRegex(KtemaError, r"^KTEMA_BUSINESS_REQUIRED"):
                plan_ktema_batch(items, "batch-1", bad)
        # Spoofed business: SAN PEDRO rejects it, the batch fails closed.
        with self.assertRaisesRegex(KtemaError, r"^KTEMA_BUSINESS_INVALID"):
            plan_ktema_batch(items, "batch-1", "los-duros-evil")

    def test_capability_dispatches_for_non_scan_consumer(self):
        plan = plan_ktema_batch(
            [PropertyQuery(business_id="los-duros", zip=ORLANDO_ZIP)],
            "batch-los-duros-1",
            "los-duros",
        )
        self.assertIsInstance(plan, KtemaBatchPlan)
        self.assertEqual(plan.business_id, "los-duros")
        self.assertEqual(plan.isolation_key, "los-duros")
        self.assertEqual(plan.batch_id, "batch-los-duros-1")
        self.assertEqual(len(plan.items), 1)
        item = plan.items[0]
        self.assertIsInstance(item, KtemaBatchItem)
        self.assertEqual(item.query.business_id, "los-duros")
        self.assertRegex(item.query_fingerprint, r"^[0-9a-f]{64}$")
        # KTEMA shares nothing with SCAN: no SCAN_* attributes, no scan_water
        # import anywhere in the module namespace.
        self.assertFalse(
            [name for name in vars(ktema) if name.startswith("SCAN_")]
        )
        self.assertNotIn("scan_water", vars(ktema))

    def test_batch_rejects_mixed_business_items(self):
        items = [
            PropertyQuery(business_id="los-duros", zip=ORLANDO_ZIP),
            PropertyQuery(business_id="zmart-consumer-rights", zip=ORLANDO_ZIP),
        ]
        with self.assertRaisesRegex(KtemaError, r"^KTEMA_BATCH_BUSINESS_MISMATCH"):
            plan_ktema_batch(items, "batch-1", "los-duros")

    def test_batch_stamps_missing_item_business(self):
        plan = plan_ktema_batch(
            [PropertyQuery(business_id=None, zip=ORLANDO_ZIP)],
            "batch-1",
            "los-duros",
        )
        self.assertEqual(plan.items[0].query.business_id, "los-duros")

    def test_batch_accepts_legacy_alias_for_same_tenant(self):
        # The contractual alias resolves to the canonical tenant: same tenant
        # under a different spelling is not a business mismatch.
        plan = plan_ktema_batch(
            [PropertyQuery(business_id="zerolag", zip=ORLANDO_ZIP)],
            "batch-1",
            "zero-lag-wifi",
        )
        self.assertEqual(plan.items[0].query.business_id, "zero-lag-wifi")

    def test_batch_rejects_empty_items(self):
        with self.assertRaisesRegex(KtemaError, r"^KTEMA_BATCH_ITEMS_REQUIRED"):
            plan_ktema_batch([], "batch-1", "los-duros")


if __name__ == "__main__":
    unittest.main()


class FixtureNormalizeBoundaryTests(unittest.TestCase):
    """P1-1 / P1-4: normalize boundary validation and opaque pointers."""

    def setUp(self):
        self.source = FixturePropertySource({PARCEL_ID: _good_record()})
        self.query = _query()

    def test_retrieved_at_int_is_malformed(self):
        # P1-1: a non-string retrieved_at (e.g. a raw int) used to escape
        # as a raw TypeError from the lexicographic time comparison.
        record = dict(_good_record(), retrieved_at=12345)
        with self.assertRaisesRegex(
            KtemaError, r"^KTEMA_ADAPTER_RESPONSE_MALFORMED"
        ):
            self.source.normalize(record, self.query, ISOLATION_KEY)

    def test_retrieved_at_non_iso_string_is_malformed(self):
        record = dict(_good_record(), retrieved_at="yesterday-ish")
        with self.assertRaisesRegex(
            KtemaError, r"^KTEMA_ADAPTER_RESPONSE_MALFORMED"
        ):
            self.source.normalize(record, self.query, ISOLATION_KEY)

    def test_missing_retrieved_at_defaults_to_now(self):
        record = {k: v for k, v in _good_record().items() if k != "retrieved_at"}
        profile = self.source.normalize(record, self.query, ISOLATION_KEY)
        self.assertIsNotNone(ktema._parse_iso(profile.retrieved_at))

    def test_supplied_raw_reference_used_verbatim(self):
        # P1-4: a source-provided pointer is opaque to the adapter and is
        # used exactly as given -- never rebuilt or interpolated.
        opaque = "source://opaque-fixture-pointer-xyz"
        record = dict(_good_record(), raw_reference=opaque)
        profile = self.source.normalize(record, self.query, ISOLATION_KEY)
        self.assertEqual(profile.raw_reference, opaque)

    def test_generated_raw_reference_never_carries_record_id(self):
        # P1-4: with no source-provided pointer, the surrogate is a
        # sha256-derived digest -- the record id NEVER appears in clear.
        pii_id = "PA-12345-OWNER-Jane-Doe-Fixture"
        record = dict(_good_record(), source_record_id=pii_id)
        profile = self.source.normalize(record, self.query, ISOLATION_KEY)
        self.assertEqual(profile.source_record_id, pii_id)
        self.assertTrue(profile.raw_reference.startswith("fixture://ref-"))
        self.assertNotIn(pii_id, profile.raw_reference)
        self.assertNotIn("Jane-Doe-Fixture", profile.raw_reference)


class FetchIntentGateTests(unittest.TestCase):
    """P2-1 / P2-3: the descriptor gate lives on the dataclass itself.

    __post_init__ validates the descriptor scheme, so direct construction
    cannot bypass the gate; and scheme validation (not substring matching)
    means a parcel_id that happens to contain "http" still produces a
    valid intent.
    """

    def _intent(self, **overrides):
        params = dict(
            source_id=FIXTURE_SOURCE_ID,
            operation=OPERATION_PARCEL_LOOKUP,
            target_descriptor=f"fixture://{FIXTURE_SOURCE_ID}/PA-1",
            query_fingerprint="0" * 64,
            requested_at_iso="2026-10-04T10:00:00+00:00",
        )
        params.update(overrides)
        return FetchIntent(**params)

    def test_direct_construction_rejects_url_descriptor(self):
        for bad in ("https://evil.example/payload", "http://evil.example/", "gopher://x"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(
                    KtemaError, r"^KTEMA_INTENT_DESCRIPTOR_FORBIDDEN"
                ):
                    self._intent(target_descriptor=bad)

    def test_parcel_id_containing_http_still_builds_intent(self):
        source = FixturePropertySource({})
        intent = source.fetch_intent(_query(parcel_id="ABCHTTP-1"))
        self.assertTrue(intent.target_descriptor.startswith("fixture://"))

    def test_descriptor_from_undeclared_scheme_rejected(self):
        with self.assertRaisesRegex(
            KtemaError, r"^KTEMA_INTENT_DESCRIPTOR_FORBIDDEN"
        ):
            self._intent(source_id="fixture", target_descriptor="other://fixture/x")


class BatchPlanCoordinateTests(unittest.TestCase):
    """P2-2: batch planning validates coordinates before fingerprinting."""

    def test_batch_rejects_non_numeric_coordinates(self):
        # The fingerprint path calls float(): a non-numeric coordinate
        # must fail closed with KTEMA_* instead of a raw ValueError.
        items = [
            PropertyQuery(business_id="los-duros", latitude="abc", longitude=-81.0)
        ]
        with self.assertRaisesRegex(KtemaError, r"^KTEMA_QUERY_SIGNAL_INVALID"):
            plan_ktema_batch(items, "batch-1", "los-duros")

    def test_batch_accepts_numeric_coordinates(self):
        items = [
            PropertyQuery(business_id="los-duros", latitude=28.5383, longitude=-81.3792)
        ]
        plan = plan_ktema_batch(items, "batch-1", "los-duros")
        self.assertEqual(plan.items[0].query.latitude, 28.5383)
