import pytest

from omar_core.router import OmarRouter, RouteError


def test_routes_registered_businesses():
    router = OmarRouter()
    expected = {
        "zmart-consumer": "riveranelso/zmart-consumer-rights",
        "scan": "riveranelso/scan-water-intelligence",
        "zerolag": "riveranelso/zerolag",
        "los-duros": "riveranelso/LosDuros",
    }
    for business_id, repository in expected.items():
        assert router.route(business_id).repository == repository


def test_unknown_business_fails_closed():
    with pytest.raises(RouteError):
        OmarRouter().route("not-a-business")


def test_missing_business_fails_closed():
    with pytest.raises(RouteError):
        OmarRouter().route("")


def test_visual_requires_asset_gate():
    plan = OmarRouter().route("scan", visual=True)
    assert plan.visual_gate_required is True
    assert plan.asset_registry


def test_zerolag_conflict_is_exposed():
    plan = OmarRouter().route("zerolag")
    assert plan.asset_status == "CONFLICT_REQUIRES_RESOLUTION"
