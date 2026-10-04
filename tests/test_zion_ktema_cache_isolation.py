"""Adversarial tests for zion_core.ktema Increment 4 (tenant-isolated cache).

KtemaCache + build_ktema_cache_key + rebind_profile_for_tenant.

All fixtures are in-memory and synthetic: the owner names, parcel IDs and
source URIs below are TEST-ONLY values with no real-world referent.
Timestamps are fixed ISO strings; the cache clock is injected, never real
time. No live services are ever touched: the cache performs no network I/O
and builds no URLs.
"""
import dataclasses
import hashlib
import unittest

from zion_core.ktema import (
    FIXTURE_SOURCE_ID,
    NOT_FOUND,
    VERIFIED,
    KtemaCache,
    KtemaError,
    PropertyProfile,
    PropertyQuery,
    build_ktema_cache_key,
    query_fingerprint,
    rebind_profile_for_tenant,
    validate_property_profile,
)

# Synthetic tenant isolation keys (no sanpedro lookup: the cache treats the
# isolation key as an opaque tenant string).
SCAN = "scan-water-intelligence"
OTHER = "zmart-consumer-rights"

NOW_ISO = "2026-10-04T10:00:00+00:00"
WITHIN_TTL_ISO = "2026-10-07T10:00:00+00:00"  # +3 days: inside the 7-day TTL
AT_EXPIRY_ISO = "2026-10-11T10:00:00+00:00"  # exactly +7 days: expired
PAST_EXPIRY_ISO = "2026-10-12T10:00:00+00:00"  # +8 days: expired
FAR_FUTURE_ISO = "2030-01-01T00:00:00+00:00"

SOURCE_UPDATED_AT = "2026-10-03T12:00:00+00:00"
RETRIEVED_AT = "2026-10-04T09:00:00+00:00"
# Synthetic fixture owner name (no real-world referent).
FIXTURE_OWNER = "Jane Doe (fixture)"
PARCEL_ID = "12-34-56-78-90-1234"
RECORD_ID = "PA-12345"
ADDRESS = "200 S Orange Ave, Orlando, FL"
ORLANDO_ZIP = "32801"


def _verified_profile(**overrides):
    """VERIFIED profile carrying owner PII, authorized at build time."""
    params = dict(
        state="FL",
        county="Orange",
        parcel_id=PARCEL_ID,
        site_address=ADDRESS,
        zip=ORLANDO_ZIP,
        source=FIXTURE_SOURCE_ID,
        source_record_id=RECORD_ID,
        source_updated_at=SOURCE_UPDATED_AT,
        retrieved_at=RETRIEVED_AT,
        confidence=0.9,
        verification_status=VERIFIED,
        raw_reference=f"fixture://{FIXTURE_SOURCE_ID}/{RECORD_ID}",
        isolation_key=SCAN,
        property_exists=True,
        attempted_sources=(FIXTURE_SOURCE_ID,),
        reason="KTEMA_FIXTURE_MATCH",
        owner=FIXTURE_OWNER,
    )
    params.update(overrides)
    return validate_property_profile(PropertyProfile(**params), owner_authorized=True)


def _not_found_profile(**overrides):
    params = dict(
        state="FL",
        county="",
        parcel_id=PARCEL_ID,
        site_address="",
        zip=ORLANDO_ZIP,
        source=FIXTURE_SOURCE_ID,
        source_record_id=None,
        source_updated_at=None,
        retrieved_at=RETRIEVED_AT,
        confidence=0.0,
        verification_status=NOT_FOUND,
        raw_reference=None,
        isolation_key=SCAN,
        property_exists=None,
        attempted_sources=(FIXTURE_SOURCE_ID,),
        reason="KTEMA_FIXTURE_NO_MATCH",
    )
    params.update(overrides)
    return validate_property_profile(PropertyProfile(**params))


def _parcel_fingerprint():
    return query_fingerprint(
        PropertyQuery(business_id=SCAN, parcel_id=PARCEL_ID, zip=ORLANDO_ZIP)
    )


def _address_fingerprint():
    return query_fingerprint(
        PropertyQuery(business_id=SCAN, address=ADDRESS, zip=ORLANDO_ZIP)
    )


def _cache(**kwargs):
    params = {"clock": lambda: NOW_ISO}
    params.update(kwargs)
    return KtemaCache(**params)


def _put_verified(cache, **overrides):
    params = dict(
        isolation_key=SCAN,
        source_id=FIXTURE_SOURCE_ID,
        query_fingerprint=_parcel_fingerprint(),
        source_record_id=RECORD_ID,
        profile=_verified_profile(),
        now_iso=NOW_ISO,
    )
    params.update(overrides)
    return cache.put(**params)


class KtemaCacheKeyTests(unittest.TestCase):
    def test_key_is_versioned_sha256_of_key_material(self):
        fp = _parcel_fingerprint()
        key = build_ktema_cache_key(SCAN, FIXTURE_SOURCE_ID, fp, RECORD_ID)
        material = "v1|" + SCAN + "|" + FIXTURE_SOURCE_ID + "|" + fp + "|" + RECORD_ID
        self.assertEqual(key, hashlib.sha256(material.encode("utf-8")).hexdigest())

    def test_key_binds_isolation_key(self):
        # The isolation key is part of the key material: two tenants
        # querying the same parcel through the same source get different
        # keys, so tenant separation never depends on ambient state.
        fp = _parcel_fingerprint()
        self.assertNotEqual(
            build_ktema_cache_key(SCAN, FIXTURE_SOURCE_ID, fp, RECORD_ID),
            build_ktema_cache_key(OTHER, FIXTURE_SOURCE_ID, fp, RECORD_ID),
        )

    def test_cache_key_separates_input_kinds(self):
        # Same normalized parcel value, different input kind (ADDRESS vs
        # PARCEL_ID): different fingerprints -> different keys, and a
        # cross-kind lookup is a miss.
        fp_parcel = _parcel_fingerprint()
        fp_address = _address_fingerprint()
        self.assertNotEqual(fp_parcel, fp_address)
        key_parcel = build_ktema_cache_key(
            SCAN, FIXTURE_SOURCE_ID, fp_parcel, RECORD_ID
        )
        key_address = build_ktema_cache_key(
            SCAN, FIXTURE_SOURCE_ID, fp_address, RECORD_ID
        )
        self.assertNotEqual(key_parcel, key_address)

        cache = _cache()
        returned_key = _put_verified(cache, query_fingerprint=fp_parcel)
        self.assertEqual(returned_key, key_parcel)
        self.assertIsNone(
            cache.get(key_address, requesting_isolation_key=SCAN, now_iso=NOW_ISO)
        )

    def test_key_rejects_malformed_inputs(self):
        fp = _parcel_fingerprint()
        good = {
            "isolation_key": SCAN,
            "source_id": FIXTURE_SOURCE_ID,
            "query_fingerprint": fp,
            "source_record_id": RECORD_ID,
        }
        for field in good:
            bad = dict(good)
            bad[field] = "   "
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    ValueError,
                    "KTEMA_CACHE_KEY_INPUT_INVALID|KTEMA_FINGERPRINT_INVALID",
                ):
                    build_ktema_cache_key(**bad)
        with self.assertRaisesRegex(ValueError, "KTEMA_FINGERPRINT_INVALID"):
            build_ktema_cache_key(SCAN, FIXTURE_SOURCE_ID, "not-a-fingerprint", RECORD_ID)


class KtemaCacheTenantIsolationTests(unittest.TestCase):
    def test_cache_hit_requires_same_isolation_key(self):
        # SCAN stores a VERIFIED profile (with owner) for a parcel. Another
        # business querying the same parcel gets a miss (different keys),
        # and reading SCAN's exact key with a foreign tenant fails closed.
        cache = _cache()
        profile = _verified_profile()
        key = _put_verified(cache, profile=profile)

        other_key = build_ktema_cache_key(
            OTHER, FIXTURE_SOURCE_ID, _parcel_fingerprint(), RECORD_ID
        )
        self.assertNotEqual(key, other_key)
        self.assertIsNone(
            cache.get(other_key, requesting_isolation_key=OTHER, now_iso=NOW_ISO)
        )

        with self.assertRaisesRegex(ValueError, "KTEMA_CACHE_TENANT_MISMATCH"):
            cache.get(key, requesting_isolation_key=OTHER, now_iso=NOW_ISO)

        hit = cache.get(key, requesting_isolation_key=SCAN, now_iso=NOW_ISO)
        self.assertEqual(hit, profile)
        self.assertEqual(hit.owner, FIXTURE_OWNER)

    def test_no_global_cache_singleton(self):
        # Two KtemaCache() instances never share entries: put in one, get
        # in the other (same key, rightful tenant) is a miss.
        first, second = _cache(), _cache()
        profile = _verified_profile()
        key = _put_verified(first, profile=profile)
        self.assertIsNone(
            second.get(key, requesting_isolation_key=SCAN, now_iso=NOW_ISO)
        )
        # No cross-talk in either direction: the first instance still hits.
        self.assertEqual(
            first.get(key, requesting_isolation_key=SCAN, now_iso=NOW_ISO), profile
        )

    def test_deserialized_profile_is_rebound_to_requesting_tenant(self):
        # A profile stored under SCAN, deserialized later, consumed with a
        # foreign tenant: the binding is re-validated at consumption time
        # and never inherited from the object.
        profile = _verified_profile()
        with self.assertRaisesRegex(ValueError, "KTEMA_PROFILE_TENANT_MISMATCH"):
            rebind_profile_for_tenant(profile, OTHER)
        self.assertEqual(rebind_profile_for_tenant(profile, SCAN), profile)
        # A deserialized copy (same data, new object) behaves identically.
        clone = dataclasses.replace(profile)
        with self.assertRaisesRegex(ValueError, "KTEMA_PROFILE_TENANT_MISMATCH"):
            rebind_profile_for_tenant(clone, OTHER)
        self.assertEqual(rebind_profile_for_tenant(clone, SCAN), clone)


class KtemaCacheTtlTests(unittest.TestCase):
    def _put_negative(self, cache, **overrides):
        params = dict(
            isolation_key=SCAN,
            source_id=FIXTURE_SOURCE_ID,
            query_fingerprint=_parcel_fingerprint(),
            source_record_id=RECORD_ID,
            profile=_not_found_profile(),
            now_iso=NOW_ISO,
        )
        params.update(overrides)
        return cache.put(**params)

    def test_negative_cache_requires_configured_ttl(self):
        # A source with no configured validity: caching a NOT_FOUND raises
        # KTEMA_CACHE_TTL_REQUIRED. A permanent negative would be an
        # eternal NOT_FOUND -- forbidden.
        for validity_days in ({}, {"some-other-source": 30}):
            with self.subTest(validity_days=validity_days):
                cache = _cache(validity_days=validity_days)
                with self.assertRaisesRegex(ValueError, "KTEMA_CACHE_TTL_REQUIRED"):
                    self._put_negative(cache)

    def test_negative_cache_is_ttl_bounded(self):
        cache = _cache()  # default validity: {"fixture": 7}
        key = self._put_negative(cache)
        # Within TTL: the negative is served.
        hit = cache.get(key, requesting_isolation_key=SCAN, now_iso=WITHIN_TTL_ISO)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.verification_status, NOT_FOUND)
        # Expired negative: miss, forcing a refresh -- never served stale.
        self.assertIsNone(
            cache.get(key, requesting_isolation_key=SCAN, now_iso=PAST_EXPIRY_ISO)
        )
        # The exact expiry boundary is already a miss.
        key2 = self._put_negative(cache)
        self.assertIsNone(
            cache.get(key2, requesting_isolation_key=SCAN, now_iso=AT_EXPIRY_ISO)
        )

    def test_expired_entry_is_miss(self):
        # An expired positive profile is a miss (never served stale), and
        # stays a miss after lazy eviction -- no resurrection.
        cache = _cache()
        key = _put_verified(cache)
        self.assertIsNone(
            cache.get(key, requesting_isolation_key=SCAN, now_iso=PAST_EXPIRY_ISO)
        )
        self.assertIsNone(
            cache.get(key, requesting_isolation_key=SCAN, now_iso=PAST_EXPIRY_ISO)
        )

    def test_positive_without_configured_validity_never_expires(self):
        # Design decision: only negatives REQUIRE a TTL. A positive for a
        # source with no configured validity lives until invalidated.
        cache = _cache(validity_days={})
        profile = _verified_profile()
        key = _put_verified(cache, profile=profile)
        self.assertEqual(
            cache.get(key, requesting_isolation_key=SCAN, now_iso=FAR_FUTURE_ISO),
            profile,
        )


class KtemaCacheLifecycleTests(unittest.TestCase):
    def test_cache_put_get_roundtrip_same_tenant(self):
        # Happy path with a fixed injected clock (no now_iso passed).
        cache = KtemaCache(clock=lambda: NOW_ISO)
        profile = _verified_profile()
        fp = _parcel_fingerprint()
        key = cache.put(
            isolation_key=SCAN,
            source_id=FIXTURE_SOURCE_ID,
            query_fingerprint=fp,
            source_record_id=RECORD_ID,
            profile=profile,
        )
        self.assertEqual(key, build_ktema_cache_key(SCAN, FIXTURE_SOURCE_ID, fp, RECORD_ID))
        self.assertEqual(cache.get(key, requesting_isolation_key=SCAN), profile)

    def test_invalidate_drops_entry(self):
        cache = _cache()
        key = _put_verified(cache)
        self.assertTrue(cache.invalidate(key))
        self.assertFalse(cache.invalidate(key))
        self.assertIsNone(
            cache.get(key, requesting_isolation_key=SCAN, now_iso=NOW_ISO)
        )

    def test_put_rejects_profile_bound_to_other_tenant(self):
        # Storing a profile under an isolation_key different from its own
        # binding fails closed at store time.
        cache = _cache()
        with self.assertRaisesRegex(
            ValueError, "KTEMA_CACHE_PROFILE_TENANT_MISMATCH"
        ):
            _put_verified(cache, isolation_key=OTHER)

    def test_constructor_rejects_bad_validity_and_clock(self):
        for validity_days in ({"fixture": 0}, {"fixture": -3}, {"  ": 7}):
            with self.subTest(validity_days=validity_days):
                with self.assertRaisesRegex(ValueError, "KTEMA_CACHE_VALIDITY_INVALID"):
                    KtemaCache(validity_days=validity_days)
        with self.assertRaisesRegex(ValueError, "KTEMA_CACHE_CLOCK_INVALID"):
            KtemaCache(clock="not-a-callable")
        with self.assertRaisesRegex(ValueError, "KTEMA_CACHE_TIME_INVALID"):
            KtemaCache(clock=lambda: "not-iso").put(
                isolation_key=SCAN,
                source_id=FIXTURE_SOURCE_ID,
                query_fingerprint=_parcel_fingerprint(),
                source_record_id=RECORD_ID,
                profile=_verified_profile(),
            )


if __name__ == "__main__":
    unittest.main()
