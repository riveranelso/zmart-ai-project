"""Tests for zion_core.provenance (GAP 6: fact/context/opinion/inference).

Canonical: LOS_DUROS.md "Facts vs context vs opinion" (owner-approved
2026-10-05). Internal semantic provenance labels: FACT / CONTEXT / OPINION /
INFERENCE / UNKNOWN. INFERENCE must never silently upgrade to FACT. OPINION
must never silently upgrade to FACT. UNKNOWN must remain unknown.
"""
import pytest

from zion_core import posture, provenance


def test_fact_owner_established():
    prov = provenance.classify_statement(
        "Randy es una leyenda del genero",
        established=posture.established_positions(),
    )
    assert prov.label == provenance.FACT


def test_context_observed_content():
    prov = provenance.classify_statement(
        "ese clip estuvo duro",
        context_tokens=frozenset({"clip", "video"}),
    )
    assert prov.label == provenance.CONTEXT


def test_opinion_first_person():
    prov = provenance.classify_statement("yo creo que es el mejor")
    assert prov.label == provenance.OPINION


def test_opinion_rumor():
    prov = provenance.classify_statement("dicen que se retira")
    assert prov.label == provenance.OPINION


def test_inference_comparative_without_evidence():
    prov = provenance.classify_statement("es mejor que todos por eso")
    assert prov.label == provenance.INFERENCE


def test_unknown_stays_unknown():
    prov = provenance.classify_statement("qwerty asdf zzz")
    assert prov.label == provenance.UNKNOWN


def test_prohibited_promotions_raise():
    with pytest.raises(provenance.ProvenanceError):
        provenance.check_promotion(provenance.INFERENCE, provenance.FACT)
    with pytest.raises(provenance.ProvenanceError):
        provenance.check_promotion(provenance.OPINION, provenance.FACT)
    with pytest.raises(provenance.ProvenanceError):
        provenance.check_promotion(provenance.UNKNOWN, provenance.FACT)
    with pytest.raises(provenance.ProvenanceError):
        provenance.check_promotion(provenance.UNKNOWN, provenance.OPINION)
    with pytest.raises(provenance.ProvenanceError):
        provenance.check_promotion(provenance.UNKNOWN, provenance.INFERENCE)


def test_allowed_transitions_pass():
    provenance.check_promotion(provenance.FACT, provenance.FACT)
    provenance.check_promotion(provenance.CONTEXT, provenance.FACT)
    provenance.check_promotion(provenance.OPINION, provenance.OPINION)
    provenance.check_promotion(provenance.INFERENCE, provenance.INFERENCE)


def test_upgrade_guard_flags_certainty_on_inference():
    violations = provenance.check_upgrade(
        "Es un hecho que es el mejor.", provenance.INFERENCE
    )
    assert "PROVENANCE_UPGRADE" in violations


def test_upgrade_guard_flags_certainty_on_unknown():
    violations = provenance.check_upgrade(
        "Definitivamente eso paso asi.", provenance.UNKNOWN
    )
    assert "PROVENANCE_UPGRADE" in violations


def test_upgrade_guard_clean_for_neutral_body():
    violations = provenance.check_upgrade(
        "Se nota que eres de los fieles.", provenance.OPINION
    )
    assert violations == ()


def test_upgrade_guard_clean_for_fact_source():
    violations = provenance.check_upgrade(
        "Es un hecho que la payola siempre existio.", provenance.FACT
    )
    assert violations == ()


def test_deterministic():
    first = provenance.classify_statement("yo creo que es mejor que todos por eso")
    second = provenance.classify_statement("yo creo que es mejor que todos por eso")
    assert first == second


def test_invalid_input_rejected():
    with pytest.raises(provenance.ProvenanceError):
        provenance.classify_statement(None)
    with pytest.raises(provenance.ProvenanceError):
        provenance.check_promotion("bogus", provenance.FACT)
