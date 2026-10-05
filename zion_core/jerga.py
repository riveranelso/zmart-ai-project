"""JERGA: Puerto Rican slang verification boundary for the LOS DUROS brand.

Canonical: zmart360/BIBLIA/LOS_DUROS.md, section "Puerto Rican slang and
ambiguous words" (permanent, owner-approved 2026-10-05).

Fail-safe semantic boundary, not a slang dictionary:

- When slang/jerga meaning is materially relevant to a response and the
  meaning is not already known/canonicalized with sufficient confidence:
  DO NOT GUESS. The runtime surfaces verification_required=True so the
  caller routes to review instead of using an interpretation as fact.
- Known canonical meanings approved in the Brain are retrievable and
  reusable (JergaMeaning, region PR, source BRAIN_CANON / OWNER_CORRECTION).
- A term whose PR meaning is known (e.g. "charro") can NEVER silently
  inherit another country's meaning: cross_country_risk flags the conflict
  and every registration requires explicit owner approval, including
  non-PR meanings.
- No giant hard-coded dictionary: the registry holds only owner-approved
  canonical meanings; the watchlist holds owner-flagged ambiguous terms
  awaiting verification. Unknown unknowns are out of scope for the
  deterministic runtime and are documented as such.

Deterministic and pure: no network, no external calls.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

REGION_PR = "PR"
SOURCE_BRAIN_CANON = "BRAIN_CANON"
SOURCE_OWNER_CORRECTION = "OWNER_CORRECTION"


class JergaError(ValueError):
    """Misuse of the jerga registry (e.g. registration without owner approval)."""


def _norm(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


@dataclass(frozen=True)
class JergaMeaning:
    """An owner-approved canonical meaning for a term in Puerto Rico."""

    term: str  # canonical term, lowercase, accent-normalized
    meaning: str  # owner-approved PR meaning
    variants: tuple[str, ...] = ()  # other surface forms, normalized
    usage_note: str = ""
    region: str = REGION_PR
    cross_country_risk: bool = False  # True when other countries use it differently
    source: str = SOURCE_BRAIN_CANON


@dataclass(frozen=True)
class JergaHit:
    term: str
    meaning: JergaMeaning


@dataclass(frozen=True)
class JergaAssessment:
    known: tuple[JergaHit, ...] = ()
    unknown: tuple[str, ...] = ()  # watchlist terms found, no canonical meaning yet
    verification_required: bool = False


def _charro_meaning() -> JergaMeaning:
    # Canonical per LOS_DUROS.md: "charro / charriando, applied to a person,
    # comment or situation in PR, can mean ridiculous, corny, in bad taste,
    # or making a fool of oneself, depending on context."
    return JergaMeaning(
        term="charro",
        meaning=(
            "ridiculous, corny, in bad taste, or making a fool of oneself, "
            "depending on context"
        ),
        variants=("charriando", "charra", "charros"),
        usage_note="applied to a person, comment or situation in PR; context-dependent",
        region=REGION_PR,
        cross_country_risk=True,
        source=SOURCE_BRAIN_CANON,
    )


_CANON: tuple[JergaMeaning, ...] = (_charro_meaning(),)


def canonical_registry() -> tuple[JergaMeaning, ...]:
    """The Brain-approved registry snapshot. Immutable: registrations return
    new tuples, never mutate this one."""
    return _CANON


def _validate_meaning(meaning: JergaMeaning) -> None:
    if not isinstance(meaning, JergaMeaning):
        raise JergaError("JERGA_MEANING_OBJECT_REQUIRED")
    if not meaning.term or not meaning.term.strip():
        raise JergaError("JERGA_TERM_REQUIRED")
    if not meaning.meaning or not meaning.meaning.strip():
        raise JergaError("JERGA_MEANING_TEXT_REQUIRED")


def register_term(
    registry: tuple[JergaMeaning, ...],
    term: str,
    meaning: JergaMeaning,
    *,
    owner_approved: bool,
) -> tuple[JergaMeaning, ...]:
    """Add (or correct) a canonical meaning. Requires explicit owner
    approval -- including for non-PR meanings, which never override the PR
    meaning silently. Returns a new registry tuple."""
    if owner_approved is not True:
        raise JergaError("JERGA_REGISTER_REQUIRES_OWNER_APPROVAL")
    _validate_meaning(meaning)
    normalized = _norm(term)
    if _norm(meaning.term) != normalized:
        raise JergaError("JERGA_TERM_MISMATCH")
    kept = tuple(m for m in registry if _norm(m.term) != normalized)
    return kept + (meaning,)


def flag_ambiguous(
    watchlist: tuple[str, ...], term: str, *, owner_approved: bool
) -> tuple[str, ...]:
    """Flag a term as ambiguous-awaiting-verification. Requires explicit
    owner approval. Returns a new watchlist tuple."""
    if owner_approved is not True:
        raise JergaError("JERGA_FLAG_REQUIRES_OWNER_APPROVAL")
    normalized = _norm(term)
    if not normalized:
        raise JergaError("JERGA_TERM_REQUIRED")
    if normalized in watchlist:
        return watchlist
    return watchlist + (normalized,)


def resolve_ambiguous(watchlist: tuple[str, ...], term: str) -> tuple[str, ...]:
    """Remove a term from the watchlist once it has a canonical meaning."""
    normalized = _norm(term)
    return tuple(t for t in watchlist if t != normalized)


def _find_terms(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    lowered = _norm(text)
    found: list[str] = []
    for term in terms:
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            found.append(term)
    return tuple(found)


def assess_jerga(
    text: str,
    *,
    registry: tuple[JergaMeaning, ...] | None = None,
    watchlist: tuple[str, ...] = (),
) -> JergaAssessment:
    """Assess slang in text against the registry and watchlist.

    - Registry hits -> known, with the canonical PR meaning attached.
    - Watchlist hits (flagged ambiguous, no canonical meaning yet) ->
      unknown, verification_required=True.
    - Anything else: out of scope for the deterministic runtime.
    """
    if not isinstance(text, str):
        raise JergaError("JERGA_TEXT_REQUIRED")
    active_registry = canonical_registry() if registry is None else registry
    known: list[JergaHit] = []
    for meaning in active_registry:
        candidates = (meaning.term,) + tuple(meaning.variants)
        hits = _find_terms(text, tuple(_norm(c) for c in candidates))
        if hits:
            known.append(JergaHit(term=_norm(meaning.term), meaning=meaning))
    known_terms = {_norm(m.term) for m in active_registry}
    unknown = tuple(
        t for t in _find_terms(text, watchlist) if t not in known_terms
    )
    return JergaAssessment(
        known=tuple(known),
        unknown=unknown,
        verification_required=bool(unknown),
    )
