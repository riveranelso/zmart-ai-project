"""Wiring tests: posture guard inside antiphon.draft_reply.

Canonical: LOS_DUROS.md "Editorial neutrality".
"""
import pytest

from zion_core import antiphon


def _comment(text, cid="c-post-1"):
    return antiphon.intake_comment({
        "comment_id": cid, "video_id": "v1", "author": "fan1", "text": text,
    })


def _brand():
    return antiphon.BrandResolution(
        business_id="los-duros", isolation_key="los-duros",
        context_refs=(), resolved=True, reason="BRAND_RESOLVED",
    )


def test_posture_violation_blocks_draft(monkeypatch):
    # Prove the wiring: when the posture check reports an upgrade, the
    # draft fails closed.
    monkeypatch.setattr(
        antiphon.posture_mod, "check_draft_posture",
        lambda *a, **k: ("POSTURE_CERTAINTY_UPGRADE",),
    )
    comment = _comment("Anuel es el mejor")
    classification = antiphon.classify_comment(comment)
    assert classification.route == antiphon.ROUTINE
    with pytest.raises(antiphon.AntiphonError, match="POSTURE_VIOLATION"):
        antiphon.draft_reply(comment, classification, brand=_brand())


def test_approved_frames_pass_posture_guard():
    # No approved frame converts a commenter's stance into Los Duros'
    # own certainty.
    samples = [
        "creo que ese tema esta duro",
        "no estoy de acuerdo con eso",
        "Anuel es el mejor",
        "Anuel le gana a Bad Bunny",
        "jajaja que risa ese clip",
        "cuando salio ese tema",
        "Randy es una leyenda, el mejor de todos",
    ]
    for i, text in enumerate(samples):
        comment = _comment(text, cid=f"c-post-{i}")
        classification = antiphon.classify_comment(comment)
        assert classification.route == antiphon.ROUTINE, text
        draft = antiphon.draft_reply(comment, classification, brand=_brand())
        assert draft.text
