"""Wiring tests: question validation inside antiphon.draft_reply.

Canonical: LOS_DUROS.md "Engagement questions".
"""
import pytest

from zion_core import antiphon


def _comment(text, cid="c-q-1", **over):
    payload = {
        "comment_id": cid, "video_id": "v1", "author": "fan1", "text": text,
    }
    payload.update(over)
    return antiphon.intake_comment(payload)


def _brand():
    return antiphon.BrandResolution(
        business_id="los-duros", isolation_key="los-duros",
        context_refs=(), resolved=True, reason="BRAND_RESOLVED",
    )


def test_question_failure_blocks_draft(monkeypatch):
    # Prove the wiring: when validation reports a violation, draft_reply
    # fails closed instead of appending a generic question.
    monkeypatch.setattr(
        antiphon.question_mod, "validate_question",
        lambda *a, **k: ("QUESTION_GENERIC",),
    )
    comment = _comment("Anuel es el mejor")
    classification = antiphon.classify_comment(comment)
    assert classification.route == antiphon.ROUTINE
    with pytest.raises(antiphon.AntiphonError, match="QUESTION_QUALITY"):
        antiphon.draft_reply(comment, classification, brand=_brand())


def test_approved_frames_pass_question_validation():
    # Every approved frame (standard + elevated) must produce a question
    # that passes structural validation for a representative comment.
    samples = {
        "opinion": "creo que ese tema esta duro",
        "disagreement": "no estoy de acuerdo con eso",
        "artist_support": "Anuel es el mejor",
        "artist_comparison": "Anuel le gana a Bad Bunny",
        "entertainment": "jajaja que risa ese clip",
        "simple_question": "cuando salio ese tema",
    }
    for subtype, text in samples.items():
        comment = _comment(text, cid=f"c-q-{subtype}")
        classification = antiphon.classify_comment(comment)
        assert classification.route == antiphon.ROUTINE, subtype
        draft = antiphon.draft_reply(comment, classification, brand=_brand())
        assert draft.text.rstrip().endswith(
            ("?", "? 😂", "?.", "?😂")
        ) or "?" in draft.text, subtype
