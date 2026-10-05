"""Tests for zion_core.posture (GAP 5: editorial posture detection).

Canonical: LOS_DUROS.md "Editorial neutrality" (owner-approved 2026-10-05).
Boundary between SOURCE POSITION / COMMENTER POSITION / LOS DUROS
ESTABLISHED POSITION / UNRESOLVED. A generated reply must never convert a
commenter's claim, a rumor, or an inference into Los Duros' own
factual/editorial stance. Provenance of the statement, not politics: no
ideological profiling.
"""
import pytest

from zion_core import posture


def test_commenter_opinion_stays_commenter_opinion():
    assessment = posture.assess_posture("yo creo que Anuel es el mejor de todos")
    assert assessment.stance == posture.COMMENTER


def test_rumor_is_commenter_unverified():
    assessment = posture.assess_posture("dicen que se retira el año que viene")
    assert assessment.stance == posture.COMMENTER
    assert "rumor_hedge" in assessment.signals


def test_source_claim_remains_attributed():
    assessment = posture.assess_posture(
        "según la entrevista que dio ayer, dijo que vuelve en verano"
    )
    assert assessment.stance == posture.SOURCE


def test_explicit_owner_position_can_be_used():
    assessment = posture.assess_posture("Randy es una leyenda del genero")
    assert assessment.stance == posture.ESTABLISHED
    # A draft affirming an established owner position is allowed.
    violations = posture.check_draft_posture(
        "Randy es una leyenda, eso no se discute.", assessment
    )
    assert violations == ()


def test_unresolved_does_not_become_first_person_certainty():
    assessment = posture.assess_posture("Anuel le gana a Bad Bunny")
    assert assessment.stance == posture.UNRESOLVED
    violations = posture.check_draft_posture(
        "Es un hecho que Anuel le gana a Bad Bunny.", assessment
    )
    assert "POSTURE_CERTAINTY_UPGRADE" in violations


def test_commenter_claim_not_endorsed_as_own_fact():
    assessment = posture.assess_posture("yo creo que ese tema es el mejor del año")
    violations = posture.check_draft_posture(
        "Tienes razón, es el mejor tema del año.", assessment
    )
    assert "POSTURE_ENDORSEMENT_UPGRADE" in violations


def test_neutral_reply_to_commenter_claim_passes():
    assessment = posture.assess_posture("yo creo que Anuel es el mejor")
    violations = posture.check_draft_posture(
        "Se nota que eres de los fieles desde el día uno.", assessment
    )
    assert violations == ()


def test_source_claim_without_attribution_in_draft_flagged():
    assessment = posture.assess_posture("él dijo que vuelve en verano")
    violations = posture.check_draft_posture(
        "Definitivamente vuelve en verano.", assessment
    )
    assert "POSTURE_CERTAINTY_UPGRADE" in violations


def test_register_position_requires_owner_approval():
    with pytest.raises(posture.PostureError):
        posture.register_position(posture.established_positions(), "x", owner_approved=False)


def test_registered_owner_position_is_usable():
    positions = posture.register_position(
        posture.established_positions(),
        "el underground ayudo a muchos",
        owner_approved=True,
    )
    assessment = posture.assess_posture(
        "el underground ayudo a muchos", established=positions
    )
    assert assessment.stance == posture.ESTABLISHED


def test_deterministic():
    text = "yo creo que dicen que vuelve"
    assert posture.assess_posture(text) == posture.assess_posture(text)


def test_invalid_input_rejected():
    with pytest.raises(posture.PostureError):
        posture.assess_posture(None)
