"""Wiring tests: jerga fail-safe inside antiphon.classify_comment / draft_reply.

Canonical: LOS_DUROS.md "Puerto Rican slang and ambiguous words".
"""
import pytest

from zion_core import antiphon, jerga


def _comment(text, **over):
    payload = {
        "comment_id": "c-jerga-1",
        "video_id": "v1",
        "author": "fan1",
        "text": text,
    }
    payload.update(over)
    return antiphon.intake_comment(payload)


def test_unknown_slang_routes_to_main_brain(monkeypatch):
    # Force the module-level assessment to report an unknown term by using
    # the real registry plus a flagged watchlist term present in the text.
    watchlist = jerga.flag_ambiguous((), "tripeo", owner_approved=True)
    real_assess = jerga.assess_jerga

    def patched(text, **kw):
        kw.setdefault("watchlist", watchlist)
        return real_assess(text, **kw)

    monkeypatch.setattr(antiphon.jerga, "assess_jerga", patched)
    classification = antiphon.classify_comment(_comment("eso fue un tripeo brutal jajaja"))
    assert classification.route == antiphon.MAIN_BRAIN
    assert classification.subtype == "jerga_unknown"
    assert "JERGA_VERIFY_REQUIRED" in classification.reasons


def test_unknown_slang_blocks_direct_draft(monkeypatch):
    watchlist = jerga.flag_ambiguous((), "tripeo", owner_approved=True)
    real_assess = jerga.assess_jerga

    def patched(text, **kw):
        kw.setdefault("watchlist", watchlist)
        return real_assess(text, **kw)

    monkeypatch.setattr(antiphon.jerga, "assess_jerga", patched)
    comment = _comment("eso fue un tripeo brutal jajaja")
    classification = antiphon.Classification(
        route=antiphon.ROUTINE, subtype="entertainment", reasons=("ROUTINE_MATCH",)
    )
    brand = antiphon.BrandResolution(
        business_id="los-duros", isolation_key="los-duros",
        context_refs=(), resolved=True, reason="BRAND_RESOLVED",
    )
    with pytest.raises(antiphon.AntiphonError, match="JERGA_VERIFY_REQUIRED"):
        antiphon.draft_reply(comment, classification, brand=brand)


def test_known_pr_slang_does_not_block_and_is_recorded():
    classification = antiphon.classify_comment(_comment("jajaja ese charro me mato de risa"))
    assert classification.route == antiphon.ROUTINE
    assert any(r.startswith("JERGA_KNOWN:") for r in classification.reasons)
