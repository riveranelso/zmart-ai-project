"""Tests for zion_core.jerga (GAP 1: Puerto Rico jerga verification).

Canonical: LOS_DUROS.md section "Puerto Rican slang and ambiguous words"
(permanent, owner-approved 2026-10-05). When slang meaning is materially
relevant and not canonicalized with sufficient confidence: DO NOT GUESS.
"""
import pytest

from zion_core import jerga


def test_known_pr_meaning_charro():
    assessment = jerga.assess_jerga("jajaja ese tipo es un charro")
    assert not assessment.verification_required
    assert len(assessment.known) == 1
    hit = assessment.known[0]
    assert hit.term == "charro"
    assert hit.meaning.region == "PR"
    assert hit.meaning.source == "BRAIN_CANON"
    assert "ridiculous" in hit.meaning.meaning or "corny" in hit.meaning.meaning


def test_known_pr_meaning_charriando_variant():
    assessment = jerga.assess_jerga("deja de estar charriando")
    assert not assessment.verification_required
    assert any(h.term == "charro" for h in assessment.known)


def test_cross_country_meaning_must_not_override_pr():
    # The registry carries the PR meaning as authoritative and flags that
    # other countries differ; nothing may silently inherit a foreign meaning.
    assessment = jerga.assess_jerga("que charro")
    hit = assessment.known[0]
    assert hit.meaning.region == "PR"
    assert hit.meaning.cross_country_risk is True
    # Registering a non-PR meaning requires explicit owner approval too.
    with pytest.raises(jerga.JergaError):
        jerga.register_term(
            jerga.canonical_registry(), "charro",
            jerga.JergaMeaning(term="charro", meaning="funny guy", region="CO"),
            owner_approved=False,
        )


def test_unknown_ambiguous_slang_requires_verification():
    registry = jerga.canonical_registry()
    watchlist = jerga.flag_ambiguous((), "tripeo", owner_approved=True)
    assessment = jerga.assess_jerga(
        "eso fue un tripeo total", registry=registry, watchlist=watchlist
    )
    assert assessment.verification_required is True
    assert "tripeo" in assessment.unknown
    assert assessment.known == ()


def test_owner_corrected_meaning_becomes_canonical():
    registry = jerga.canonical_registry()
    watchlist = jerga.flag_ambiguous((), "tripeo", owner_approved=True)
    meaning = jerga.JergaMeaning(
        term="tripeo",
        meaning="relajo entre panas, vacilón sano",
        usage_note="owner-corrected 2026-10-05",
        source="OWNER_CORRECTION",
    )
    registry = jerga.register_term(registry, "tripeo", meaning, owner_approved=True)
    watchlist = jerga.resolve_ambiguous(watchlist, "tripeo")
    assessment = jerga.assess_jerga(
        "eso fue un tripeo total", registry=registry, watchlist=watchlist
    )
    assert assessment.verification_required is False
    assert assessment.known[0].meaning.source == "OWNER_CORRECTION"


def test_flag_ambiguous_requires_owner_approval():
    with pytest.raises(jerga.JergaError):
        jerga.flag_ambiguous((), "tripeo", owner_approved=False)


def test_no_slang_no_verification_needed():
    assessment = jerga.assess_jerga("Anuel es el mejor cantante")
    assert assessment.verification_required is False
    assert assessment.known == ()
    assert assessment.unknown == ()


def test_registry_is_immutable_snapshot():
    before = jerga.canonical_registry()
    jerga.flag_ambiguous((), "tripeo", owner_approved=True)
    assert jerga.canonical_registry() == before
