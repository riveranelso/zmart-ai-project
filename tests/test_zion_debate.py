"""Tests for zion_core.debate (GAP 2: debater / intellectual-level detection).

Canonical: LOS_DUROS.md "Response psychology: when the commenter is a
debater". This is RESPONSE-STYLE classification, not a personality
diagnosis: it detects when the comment/context supports a higher-level
debate response. It must never insult intelligence, invent traits, or
infer private mental state.
"""
import pytest

from zion_core import debate


def test_ordinary_comment_is_standard():
    assessment = debate.assess_debate_level("Anuel es el mejor")
    assert assessment.level == debate.STANDARD


def test_short_opinion_is_standard():
    assessment = debate.assess_debate_level("jajaja que risa ese clip")
    assert assessment.level == debate.STANDARD


def test_reasoned_argument_is_elevated():
    assessment = debate.assess_debate_level(
        "No estoy de acuerdo porque en el 2019 los numeros mostraron otra "
        "cosa, sin embargo la narrativa cambio despues"
    )
    assert assessment.level == debate.ELEVATED
    assert len(assessment.signals) >= 2


def test_substantive_historical_claim_is_elevated():
    assessment = debate.assess_debate_level(
        "En los 90 la payola se movia por radio, de hecho varios DJs lo han "
        "dicho en entrevistas"
    )
    assert assessment.level == debate.ELEVATED


def test_counterargument_is_elevated():
    assessment = debate.assess_debate_level(
        "Eso no es asi, te equivocas porque la evidencia contradice esa "
        "version de los hechos"
    )
    assert assessment.level == debate.ELEVATED


def test_single_connective_alone_is_not_enough():
    # One weak signal must not trigger elevation by itself.
    assessment = debate.assess_debate_level("me gusta porque es bueno")
    assert assessment.level == debate.STANDARD


def test_assessment_describes_text_not_person():
    assessment = debate.assess_debate_level(
        "No estoy de acuerdo porque los datos contradicen eso"
    )
    # The assessment carries text-feature signals only: no person traits,
    # no mental-state inference, no intelligence judgment.
    assert assessment.level == debate.ELEVATED
    for signal in assessment.signals:
        assert "person" not in signal and "intelligence" not in signal


def test_deterministic():
    text = "No estoy de acuerdo porque en el 2019 los numeros, de hecho, contradicen eso"
    first = debate.assess_debate_level(text)
    second = debate.assess_debate_level(text)
    assert first == second


def test_invalid_input_rejected():
    with pytest.raises(debate.DebateError):
        debate.assess_debate_level(None)
