"""KTEMA public exports (Increment 5).

Verifies every KTEMA symbol listed for export is importable from
``zion_core`` and that nothing private leaves the module through the
package surface.
"""

import pytest

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
]


@pytest.mark.parametrize("name", EXPECTED_SYMBOLS)
def test_ktema_symbols_importable_from_zion_core(name):
    import zion_core

    assert name in zion_core.__all__, f"{name} missing from zion_core.__all__"
    assert callable(getattr(zion_core, name, None)) or getattr(
        zion_core, name, None
    ) is not None, f"{name} not accessible on zion_core"


def test_ktema_symbols_match_module_symbols():
    import zion_core
    from zion_core import ktema

    for name in EXPECTED_SYMBOLS:
        assert getattr(zion_core, name, None) is getattr(
            ktema, name, None
        ), f"{name} does not resolve to ktema.{name}"


def test_no_private_ktema_symbols_exported():
    import zion_core

    for name in zion_core.__all__:
        if name.startswith("_"):
            raise AssertionError(f"private symbol exported: {name}")
    assert not hasattr(zion_core, "_make_resolution")
    assert not hasattr(zion_core, "_parse_iso")


def test_ktema_all_consistency_when_defined():
    from zion_core import ktema

    if hasattr(ktema, "__all__"):
        assert set(ktema.__all__) == set(EXPECTED_SYMBOLS), (
            "ktema.__all__ does not match the published KTEMA exports"
        )
    else:
        import zion_core

        for name in EXPECTED_SYMBOLS:
            assert hasattr(zion_core, name), f"{name} not importable from zion_core"
