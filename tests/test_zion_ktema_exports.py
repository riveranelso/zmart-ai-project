"""KTEMA public exports (Increment 5).

Verifies every KTEMA symbol listed for export is importable from
``zion_core`` and that nothing private leaves the module through the
package surface. Pure unittest: CI has no pytest.
"""

import unittest

EXPECTED_SYMBOLS = [
    "KtemaError",
    "PropertyQuery",
    "CountyResolution",
    "resolve_county",
    "load_county_table",
    "VERIFIED",
    "NOT_FOUND",
    "UNAVAILABLE",
    "INCONCLUSIVE",
    "VERIFICATION_STATUSES",
    "SourceProvenance",
    "PropertyProfile",
    "validate_property_profile",
    "to_cronicas_event",
    "is_fresh",
    "FetchIntent",
    "PropertySource",
    "PropertySourceRegistry",
    "PropertySourceRouter",
    "FixturePropertySource",
    "fixture_registry",
    "KtemaBatchPlan",
    "KtemaBatchItem",
    "plan_ktema_batch",
    "KtemaCache",
    "build_ktema_cache_key",
    "rebind_profile_for_tenant",
    "CANONICAL_COUNTIES",
    "ORANGE_PARCELS_BCC_SOURCE_ID",
    "ORANGE_PARCELS_BCC_FIELDS",
    "OrangeParcelsBccSource",
    "orange_property_registry",
]


class KtemaExportsTests(unittest.TestCase):
    def test_ktema_symbols_importable_from_zion_core(self):
        import zion_core

        for name in EXPECTED_SYMBOLS:
            with self.subTest(name=name):
                self.assertIn(name, zion_core.__all__,
                              f"{name} missing from zion_core.__all__")
                self.assertIsNotNone(getattr(zion_core, name, None),
                                     f"{name} not accessible on zion_core")

    def test_ktema_symbols_match_module_symbols(self):
        import zion_core
        from zion_core import ktema

        for name in EXPECTED_SYMBOLS:
            with self.subTest(name=name):
                self.assertIs(getattr(zion_core, name, None),
                              getattr(ktema, name, None),
                              f"{name} does not resolve to ktema.{name}")

    def test_no_private_ktema_symbols_exported(self):
        import zion_core

        for name in zion_core.__all__:
            self.assertFalse(name.startswith("_"),
                             f"private symbol exported: {name}")
        self.assertFalse(hasattr(zion_core, "_make_resolution"))
        self.assertFalse(hasattr(zion_core, "_parse_iso"))

    def test_ktema_all_consistency_when_defined(self):
        from zion_core import ktema

        if hasattr(ktema, "__all__"):
            self.assertEqual(set(ktema.__all__), set(EXPECTED_SYMBOLS),
                             "ktema.__all__ does not match the published KTEMA exports")


if __name__ == "__main__":
    unittest.main()
