"""Tests for zion_core.question (GAP 3: engagement question quality).

Canonical: LOS_DUROS.md "Engagement questions" (owner-approved 2026-10-05).
The closing question must grow from the actual comment/context. Deterministic
structural validation: generic appendages and unanchored questions are
rejected. Lexical overlap is a necessary structural signal, never proof of
semantic relevance.
"""
import pytest

from zion_core import question


def test_context_derived_question_accepted():
    violations = question.validate_question(
        "¿En qué categoría gana el tuyo sin discusión?",
        "Anuel le gana a Bad Bunny",
        subtype="artist_comparison",
    )
    assert violations == ()


def test_question_anchored_by_comment_token():
    violations = question.validate_question(
        "¿Qué parte te gustó más?",
        "esa parte del video me encanto",
        subtype="opinion",
    )
    assert violations == ()


def test_question_anchored_by_artist_context():
    violations = question.validate_question(
        "¿Qué tiene ANUEL que los demás no tienen?",
        "el mejor sin duda",
        context_tokens=("anuel",),
        subtype="artist_support",
    )
    assert violations == ()


def test_generic_question_rejected():
    violations = question.validate_question(
        "¿Qué tú crees?",
        "Anuel le gana a Bad Bunny",
        subtype="artist_comparison",
    )
    assert "QUESTION_GENERIC" in violations


def test_unrelated_question_rejected():
    violations = question.validate_question(
        "¿Te gusta la pizza?",
        "Anuel le gana a Bad Bunny",
        subtype="artist_comparison",
    )
    assert "QUESTION_UNANCHORED" in violations


def test_question_must_end_with_question_mark():
    violations = question.validate_question(
        "Dime que opinas",
        "Anuel le gana a Bad Bunny",
        subtype="artist_comparison",
    )
    assert "QUESTION_NO_QUESTION_MARK" in violations


def test_generic_denylist_does_not_false_positive_on_substantive():
    # "¿Tú qué opinas, fue justo o se pasó?" is substantive, not generic.
    violations = question.validate_question(
        "¿Tú qué opinas, fue justo o se pasó?",
        "eso dio de que hablar",
        subtype="fallback",
    )
    assert violations == ()


def test_empty_question_rejected():
    violations = question.validate_question(
        "", "Anuel es el mejor", subtype="opinion"
    )
    assert violations != ()


def test_deterministic():
    kwargs = dict(
        question_text="¿En qué categoría gana el tuyo sin discusión?",
        comment_text="Anuel le gana a Bad Bunny",
        subtype="artist_comparison",
    )
    assert question.validate_question(**kwargs) == question.validate_question(**kwargs)


def test_invalid_input_rejected():
    with pytest.raises(question.QuestionError):
        question.validate_question(None, "text", subtype="opinion")
