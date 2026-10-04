"""Adversarial tests for zion_core.ktema (FL property county resolution).

Test fixtures below are TEST-ONLY tables and are NOT shipped data. The
shipped zion_core/ktema_county_data.json was populated in Increment 1b
(2026-10-04): 114 unique ZIPs across Orange (45), Seminole (17),
Volusia (32) and Lake (29), verified by the coordinator against the 4
official sources listed in meta.built_from. Shipped-table tests below
resolve against the real table via the default path. Real-world facts
used in fixtures:

- 32801 is downtown Orlando, Orange County (county seat; the Orange County
  Property Appraiser sits at 200 S Orange Ave, Orlando, FL 32801).
- 33935 spans Hendry and Glades counties (coordinator-verified real
  multi-county case, documented in zion_core/ktema.py; outside Increment-1
  county coverage, so it is documented here rather than loaded).
- Multi-county fixture ZIP 32799 is SYNTHETIC (no real-world claim); it
  exercises the KTEMA_COUNTY_AMBIGUOUS code path.
"""
import dataclasses
import json
import re
import tempfile
import unittest
from pathlib import Path

from zion_core import ktema
from zion_core.ktema import (
    INCONCLUSIVE,
    OUT_OF_COVERAGE,
    PARCEL_PATTERNS,
    RESOLVED,
    CountyResolution,
    PropertyQuery,
    load_county_table,
    resolve_county,
)

BUSINESS = "zmart-consumer-rights"

# 1:1 fixture: real-world fact (downtown Orlando -> Orange County).
SINGLE_ZIP = "32801"
# Synthetic multi-county fixture (no real-world claim).
MULTI_ZIP = "32799"


def _write_table(zips, directory):
    data = {
        "meta": {
            "built_from": ["test-fixture"],
            "built_at": "2026-10-04",
            "coverage": [],
        },
        "zips": zips,
    }
    path = Path(directory) / "ktema_county_data.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _query(**kwargs):
    params = {"business_id": BUSINESS}
    params.update(kwargs)
    return PropertyQuery(**params)


class KtemaCountyResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture_table = _write_table(
            {SINGLE_ZIP: ["Orange"], MULTI_ZIP: ["Orange", "Seminole"]},
            self.tmp.name,
        )

    # -- ZIP resolution ----------------------------------------------------

    def test_single_county_zip_resolves(self):
        result = resolve_county(
            _query(zip=SINGLE_ZIP), table_path=self.fixture_table
        )
        self.assertIsInstance(result, CountyResolution)
        self.assertEqual(result.status, RESOLVED)
        self.assertEqual(result.county, "Orange")
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.confidence, 0.95)
        self.assertTrue(result.reason)
        self.assertTrue(result.evidence_refs)

    def test_multi_county_zip_raises_ambiguous_with_candidates(self):
        with self.assertRaisesRegex(ValueError, "KTEMA_COUNTY_AMBIGUOUS") as ctx:
            resolve_county(_query(zip=MULTI_ZIP), table_path=self.fixture_table)
        message = str(ctx.exception)
        self.assertIn(MULTI_ZIP, message)
        self.assertIn("Orange", message)
        self.assertIn("Seminole", message)

    def test_documented_real_multicounty_case_33935(self):
        # Coordinator-verified real case (Hendry/Glades), documented in the
        # module docstring; outside Increment-1 coverage so not loadable.
        self.assertIn("33935", ktema.__doc__)
        self.assertIn("Hendry", ktema.__doc__)
        self.assertIn("Glades", ktema.__doc__)

    def test_invalid_zips_rejected(self):
        # Blank strings count as absent signals (see test_no_signal_rejected);
        # present-but-malformed ZIPs are rejected as KTEMA_ZIP_INVALID.
        for bad in ("00000", "1234", "ABCDE", " 32801", "3280a", "328011"):
            with self.subTest(zip=bad):
                with self.assertRaisesRegex(ValueError, "KTEMA_ZIP_INVALID"):
                    resolve_county(_query(zip=bad), table_path=self.fixture_table)

    def test_non_string_zip_rejected(self):
        with self.assertRaisesRegex(ValueError, "KTEMA_ZIP_INVALID"):
            resolve_county(_query(zip=32801), table_path=self.fixture_table)

    def test_unknown_zip_out_of_coverage(self):
        result = resolve_county(_query(zip="99999"), table_path=self.fixture_table)
        self.assertEqual(result.status, OUT_OF_COVERAGE)
        self.assertIsNone(result.county)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.reason, "KTEMA_COUNTY_OUT_OF_COVERAGE")

    # -- shipped table (Increment 1b: populated from 4 official sources) --

    def _assert_shipped_resolved(self, zip_code, county):
        result = resolve_county(_query(zip=zip_code))
        self.assertEqual(result.status, RESOLVED)
        self.assertEqual(result.county, county)
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.confidence, 0.95)
        self.assertEqual(result.reason, "KTEMA_ZIP_SINGLE_COUNTY")

    def _assert_shipped_ambiguous(self, zip_code, expected_candidates):
        with self.assertRaisesRegex(ValueError, "KTEMA_COUNTY_AMBIGUOUS") as ctx:
            resolve_county(_query(zip=zip_code))
        message = str(ctx.exception)
        self.assertIn(zip_code, message)
        found = message.split("candidates=")[1]
        self.assertEqual(set(found.split(",")), set(expected_candidates))

    def test_shipped_table_coverage_shape(self):
        # Guard against table corruption: exact coverage the coordinator
        # verified in Increment 1b.
        meta, zips = load_county_table()
        self.assertEqual(len(zips), 114)
        self.assertEqual(len(meta["built_from"]), 4)
        self.assertEqual(set(meta["coverage"]), {"Orange", "Seminole", "Volusia", "Lake"})
        multi = sorted(z for z, counties in zips.items() if len(counties) > 1)
        self.assertEqual(
            multi,
            ["32102", "32703", "32720", "32751", "32757", "32776", "32789", "32792", "34787"],
        )

    def test_shipped_32801_resolves_orange(self):
        self._assert_shipped_resolved("32801", "Orange")

    def test_shipped_32701_resolves_seminole(self):
        self._assert_shipped_resolved("32701", "Seminole")

    def test_shipped_32114_resolves_volusia(self):
        self._assert_shipped_resolved("32114", "Volusia")

    def test_shipped_32778_resolves_lake(self):
        self._assert_shipped_resolved("32778", "Lake")

    def test_shipped_32102_ambiguous_lake_volusia(self):
        self._assert_shipped_ambiguous("32102", {"Lake", "Volusia"})

    def test_shipped_32703_ambiguous_orange_seminole(self):
        self._assert_shipped_ambiguous("32703", {"Orange", "Seminole"})

    def test_shipped_32757_ambiguous_lake_orange(self):
        self._assert_shipped_ambiguous("32757", {"Lake", "Orange"})

    def test_shipped_34787_ambiguous_lake_orange(self):
        self._assert_shipped_ambiguous("34787", {"Lake", "Orange"})

    def test_shipped_90210_out_of_coverage_not_error(self):
        # Outside the four-county coverage: OUT_OF_COVERAGE is a normal
        # result, not an exception.
        result = resolve_county(_query(zip="90210"))
        self.assertEqual(result.status, OUT_OF_COVERAGE)
        self.assertIsNone(result.county)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.reason, "KTEMA_COUNTY_OUT_OF_COVERAGE")

    def test_shipped_absent_zip_out_of_coverage_fail_closed(self):
        # 32207 is a real Jacksonville FL ZIP, outside coverage. Absence
        # from the table never falls back to a default county.
        result = resolve_county(_query(zip="32207"))
        self.assertEqual(result.status, OUT_OF_COVERAGE)
        self.assertIsNone(result.county)

    def test_address_plus_zip_corrobation_resolves_by_zip(self):
        result = resolve_county(
            _query(zip=SINGLE_ZIP, address="200 S Orange Ave, Orlando, FL"),
            table_path=self.fixture_table,
        )
        self.assertEqual(result.status, RESOLVED)
        self.assertEqual(result.county, "Orange")

    # -- business_id: always re-validated, fail closed ----------------------

    def test_business_none_required(self):
        with self.assertRaisesRegex(ValueError, "KTEMA_BUSINESS_REQUIRED"):
            resolve_county(PropertyQuery(None, zip=SINGLE_ZIP), table_path=self.fixture_table)

    def test_business_empty_required(self):
        with self.assertRaisesRegex(ValueError, "KTEMA_BUSINESS_REQUIRED"):
            resolve_county(_query(business_id="   ", zip=SINGLE_ZIP), table_path=self.fixture_table)

    def test_business_spoofs_fail_closed(self):
        spoofs = (
            " zmart-consumer-rights",   # whitespace padding
            "ZMART-CONSUMER-RIGHTS",   # case change
            "zmart-consumer-rights2",  # suffix
        )
        for spoof in spoofs:
            with self.subTest(spoof=spoof):
                with self.assertRaisesRegex(ValueError, "KTEMA_BUSINESS_INVALID"):
                    resolve_county(_query(business_id=spoof, zip=SINGLE_ZIP), table_path=self.fixture_table)

    def test_business_display_name_and_typo_fail_closed(self):
        for spoof in ("Zmart Consumer Rights", "zmart-consumer-right"):
            with self.subTest(spoof=spoof):
                with self.assertRaisesRegex(ValueError, "KTEMA_BUSINESS_INVALID"):
                    resolve_county(_query(business_id=spoof, zip=SINGLE_ZIP), table_path=self.fixture_table)

    def test_no_default_business(self):
        # business_id is required: omitting it is a TypeError, never a default.
        with self.assertRaises(TypeError):
            PropertyQuery(zip=SINGLE_ZIP)  # type: ignore[call-arg]

    # -- signal precedence and inconclusive paths ---------------------------

    def test_parcel_id_inconclusive_patterns_empty(self):
        self.assertEqual(PARCEL_PATTERNS, {})
        result = resolve_county(
            _query(parcel_id="12-34-56-78-90-1234"), table_path=self.fixture_table
        )
        self.assertEqual(result.status, INCONCLUSIVE)
        self.assertIsNone(result.county)
        self.assertEqual(result.reason, "KTEMA_PARCEL_PATTERN_UNKNOWN")

    def test_address_only_inconclusive(self):
        result = resolve_county(
            _query(address="200 S Orange Ave, Orlando, FL"), table_path=self.fixture_table
        )
        self.assertEqual(result.status, INCONCLUSIVE)
        self.assertEqual(result.reason, "KTEMA_ADDRESS_NEEDS_ZIP")

    def test_coordinates_inconclusive_no_geometry_embedded(self):
        result = resolve_county(
            _query(latitude=28.5383, longitude=-81.3792), table_path=self.fixture_table
        )
        self.assertEqual(result.status, INCONCLUSIVE)
        self.assertIsNone(result.county)
        self.assertEqual(result.reason, "KTEMA_COORDS_GEOMETRY_NOT_EMBEDDED")

    def test_two_primary_signals_rejected(self):
        with self.assertRaisesRegex(ValueError, "KTEMA_QUERY_SIGNAL_INVALID"):
            resolve_county(
                _query(zip=SINGLE_ZIP, parcel_id="12-34-56-78-90-1234"),
                table_path=self.fixture_table,
            )

    def test_no_signal_rejected(self):
        with self.assertRaisesRegex(ValueError, "KTEMA_QUERY_SIGNAL_INVALID"):
            resolve_county(_query(), table_path=self.fixture_table)

    def test_partial_coordinates_rejected(self):
        with self.assertRaisesRegex(ValueError, "KTEMA_QUERY_SIGNAL_INVALID"):
            resolve_county(_query(latitude=28.5383), table_path=self.fixture_table)

    def test_out_of_range_coordinates_rejected(self):
        with self.assertRaisesRegex(ValueError, "KTEMA_COORDS_INVALID"):
            resolve_county(
                _query(latitude=28.5383, longitude=-181.0), table_path=self.fixture_table
            )

    # -- contracts ----------------------------------------------------------

    def test_frozen_dataclasses(self):
        query = _query(zip=SINGLE_ZIP)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            query.zip = "99999"  # type: ignore[misc]
        result = resolve_county(query, table_path=self.fixture_table)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.county = "Lake"  # type: ignore[misc]

    def test_malformed_table_fails_closed(self):
        bad = _write_table({"ABCDE": ["Orange"]}, self.tmp.name)
        with self.assertRaisesRegex(ValueError, "KTEMA_TABLE_INVALID"):
            load_county_table(bad)
        bad_county = _write_table({SINGLE_ZIP: ["Atlantis"]}, self.tmp.name)
        with self.assertRaisesRegex(ValueError, "KTEMA_TABLE_INVALID"):
            load_county_table(bad_county)

    def test_missing_table_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "KTEMA_TABLE_INVALID"):
            resolve_county(
                _query(zip=SINGLE_ZIP),
                table_path=Path(self.tmp.name) / "nope.json",
            )

    # -- isolation: no network, no SCAN -------------------------------------

    def test_module_has_no_network_imports(self):
        source = Path(ktema.__file__).read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            self.assertIsNone(
                re.match(r"(import|from)\s+(urllib|requests|http|socket)\b", stripped),
                f"network import at line {lineno}: {line}",
            )

    def test_module_does_not_import_scan_water(self):
        source = Path(ktema.__file__).read_text(encoding="utf-8")
        self.assertNotIn("scan_water", source)

    def test_ktema_error_is_value_error(self):
        self.assertTrue(issubclass(ktema.KtemaError, ValueError))


if __name__ == "__main__":
    unittest.main()


class KtemaBrandAndTypoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture_table = _write_table(
            {SINGLE_ZIP: ["Orange"], MULTI_ZIP: ["Orange", "Seminole"]},
            self.tmp.name,
        )

    """P2-4: brand IDs are not business IDs; typos inherit nothing.

    sanpedro_resolve is an exact dict lookup: "SCAN"/"scan" are not
    registered businesses and a typo near a canonical ID gets its own
    lookup -- never a canonical isolation_key.
    """

    def test_brand_ids_fail_closed(self):
        for brand in ("SCAN", "scan"):
            with self.subTest(brand=brand):
                with self.assertRaisesRegex(ValueError, "KTEMA_BUSINESS_INVALID"):
                    resolve_county(
                        _query(business_id=brand, zip=SINGLE_ZIP),
                        table_path=self.fixture_table,
                    )

    def test_typo_business_does_not_inherit_canonical(self):
        with self.assertRaisesRegex(ValueError, "KTEMA_BUSINESS_INVALID"):
            resolve_county(
                _query(business_id="scan-water-inteligence", zip=SINGLE_ZIP),
                table_path=self.fixture_table,
            )


class KtemaOutOfStateCoordinatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture_table = _write_table(
            {SINGLE_ZIP: ["Orange"], MULTI_ZIP: ["Orange", "Seminole"]},
            self.tmp.name,
        )

    """P2-4: coordinates outside FL resolve INCONCLUSIVE with no lookup.

    Increment 1 embeds no bounding-box geometry: any coordinate pair --
    inside or outside FL -- resolves INCONCLUSIVE, so an out-of-state
    point can never be guessed into a county.
    """

    def test_coordinates_outside_fl_are_inconclusive(self):
        # Georgia (north of FL) and the Gulf (west of FL).
        for latitude, longitude in ((31.5, -84.0), (28.0, -84.5)):
            with self.subTest(latitude=latitude, longitude=longitude):
                result = resolve_county(
                    _query(latitude=latitude, longitude=longitude),
                    table_path=self.fixture_table,
                )
                self.assertEqual(result.status, INCONCLUSIVE)
                self.assertIsNone(result.county)
                self.assertEqual(result.reason, "KTEMA_COORDS_GEOMETRY_NOT_EMBEDDED")
