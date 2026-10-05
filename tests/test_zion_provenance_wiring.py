"""Wiring tests: provenance guard inside antiphon classify/draft.

Canonical: LOS_DUROS.md "Facts vs context vs opinion".
"""
import pytest

from zion_core import antiphon, provenance


def _comment(text, cid="c-prov-1"):
    return antiphon.intake_comment({
        "comment_id": cid, "video_id": "v1", "author": "fan1", "text": text,
    })


def _brand():
    return antiphon.BrandResolution(
        business_id="los-duros", isolation_key="los-duros",
        context_refs=(), resolved=True, reason="BRAND_RESOLVED",
    )


def test_provenance_label_recorded_on_routine():
    classification = antiphon.classify_comment(_comment("Anuel es el mejor"))
    assert classification.route == antiphon.ROUTINE
    assert any(r.startswith("PROVENANCE:") for r in classification.reasons)


def test_upgrade_violation_blocks_draft(monkeypatch):
    # Prove the wiring: when the provenance guard reports an upgrade, the
    # draft fails closed.
    monkeypatch.setattr(
        antiphon.provenance_mod, "check_upgrade",
        lambda *a, **k: ("PROVENANCE_UPGRADE",),
    )
    comment = _comment("Anuel es el mejor")
    classification = antiphon.classify_comment(comment)
    assert classification.route == antiphon.ROUTINE
    with pytest.raises(antiphon.AntiphonError, match="PROVENANCE_UPGRADE"):
        antiphon.draft_reply(comment, classification, brand=_brand())


def test_approved_frames_pass_provenance_guard():
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
        comment = _comment(text, cid=f"c-prov-{i}")
        classification = antiphon.classify_comment(comment)
        assert classification.route == antiphon.ROUTINE, text
        draft = antiphon.draft_reply(comment, classification, brand=_brand())
        assert draft.text


def test_no_silent_upgrade_paths_in_pipeline():
    # Every prohibited promotion raises; the pipeline never silently
    # converts a label.
    for from_label in (provenance.INFERENCE, provenance.OPINION, provenance.UNKNOWN):
        with pytest.raises(provenance.ProvenanceError):
            provenance.check_promotion(from_label, provenance.FACT)
