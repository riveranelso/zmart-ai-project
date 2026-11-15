"""POSTURE: editorial-posture (statement provenance) detection.

Canonical: zmart360/BIBLIA/LOS_DUROS.md, section "Editorial neutrality"
(owner-approved 2026-10-05).

Los Duros must not accidentally assume or invent an editorial position
that was not established by the source/context/owner. This module draws
the boundary between:

- SOURCE POSITION     -- a claim attributed to a source in the text.
- COMMENTER POSITION  -- the commenter's own opinion, hedge, or rumor.
- LOS DUROS ESTABLISHED POSITION -- an explicit owner/editorial position
  registered in the Brain (owner-approved only).
- UNRESOLVED          -- none of the above can be established.

A generated reply must never convert a commenter's claim, a rumor, or an
inference into Los Duros' own factual/editorial stance. This is provenance
of the statement, not politics: no ideological profiling is attempted.

check_draft_posture() flags two upgrade modes in draft text:
- POSTURE_CERTAINTY_UPGRADE: certainty markers ("es un hecho que", ...)
  applied to a COMMENTER / SOURCE / UNRESOLVED stance.
- POSTURE_ENDORSEMENT_UPGRADE: first-person endorsement of the
  commenter's claim as Los Duros' own fact.

Deterministic and pure: regex/substring signals over normalized text.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

COMMENTER = "commenter"
SOURCE = "source"
ESTABLISHED = "established"
UNRESOLVED = "unresolved"
STANCES = (COMMENTER, SOURCE, ESTABLISHED, UNRESOLVED)

SOURCE_BIBLIA_CANON = "BIBLIA_CANON"
SOURCE_OWNER = "OWNER"


class PostureError(ValueError):
    """Invalid input or unapproved registration."""


def _norm(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


@dataclass(frozen=True)
class EstablishedPosition:
    statement: str  # normalized statement
    note: str = ""
    source: str = SOURCE_BIBLIA_CANON


@dataclass(frozen=True)
class Posture:
    stance: str
    signals: tuple[str, ...] = ()


def _canon_positions() -> tuple[EstablishedPosition, ...]:
    # Owner-marked editorial positions from LOS_DUROS.md
    # "Historical/contextual knowledge" (owner context, not independently
    # verified facts). Seeded minimally; additions require owner approval.
    return (
        EstablishedPosition(
            statement="randy es una leyenda",
            note="owner context: Randy is a legend, not a new artist trying to break",
            source=SOURCE_BIBLIA_CANON,
        ),
        EstablishedPosition(
            statement="la payola siempre existio",
            note="owner context: promotion has long been part of the genre",
            source=SOURCE_BIBLIA_CANON,
        ),
    )


_CANON = _canon_positions()


def established_positions() -> tuple[EstablishedPosition, ...]:
    """Owner-approved established positions. Immutable snapshot."""
    return _CANON


def register_position(
    positions: tuple[EstablishedPosition, ...],
    statement: str,
    *,
    owner_approved: bool,
    note: str = "",
) -> tuple[EstablishedPosition, ...]:
    """Register an explicit owner/editorial position. Requires explicit
    owner approval. Returns a new tuple."""
    if owner_approved is not True:
        raise PostureError("POSTURE_REGISTER_REQUIRES_OWNER_APPROVAL")
    if not isinstance(statement, str) or not statement.strip():
        raise PostureError("POSTURE_STATEMENT_REQUIRED")
    normalized = _norm(statement)
    kept = tuple(p for p in positions if p.statement != normalized)
    return kept + (
        EstablishedPosition(statement=normalized, note=note, source=SOURCE_OWNER),
    )


_FIRST_PERSON = (
    r"\byo\s+creo\b",
    r"\bpara\s+m[ií]\b",
    r"\bpienso\s+que\b",
    r"\bopino\s+que\b",
    r"\ben\s+mi\s+opini[oó]n\b",
)
_RUMOR = (
    r"\bdicen\s+que\b",
    r"\bsupuestamente\b",
    r"\bme\s+dijeron\b",
    r"\bescuch[eé]\s+que\b",
    r"\bse\s+dice\s+que\b",
    r"\bal\s+parecer\b",
)
_SOURCE = (
    r"\bdijo\s+que\b",
    r"\bseg[uú]n\b",
    r"\bafirm[oó]\b",
    r"\bdeclar[oó]\s+que\b",
    r"\ben\s+la\s+entrevista\b",
    r"\bcont[oó]\s+que\b",
)

_COMPILED_FIRST_PERSON = tuple(re.compile(p) for p in _FIRST_PERSON)
_COMPILED_RUMOR = tuple(re.compile(p) for p in _RUMOR)
_COMPILED_SOURCE = tuple(re.compile(p) for p in _SOURCE)

# Certainty markers: presenting something as settled fact.
_CERTAINTY = (
    "es un hecho que",
    "esta claro que",
    "claramente",
    "definitivamente",
    "sin duda",
    "todo el mundo sabe",
    "nadie puede negar",
    "es la verdad absoluta",
    "esta confirmado",
)
# First-person endorsement of the commenter's claim as our own fact.
_ENDORSEMENT = (
    "tienes razon",
    "tienes toda la razon",
    "es cierto lo que dices",
)


def assess_posture(
    text: str,
    *,
    established: tuple[EstablishedPosition, ...] | None = None,
) -> Posture:
    """Determine the provenance stance of a statement.

    Priority: ESTABLISHED > COMMENTER markers > SOURCE attribution >
    UNRESOLVED. A commenter's framing of a source ("yo creo que dijo que")
    stays COMMENTER.
    """
    if not isinstance(text, str):
        raise PostureError("POSTURE_TEXT_REQUIRED")
    active = established_positions() if established is None else established
    lowered = _norm(text)
    for position in active:
        if position.statement and position.statement in lowered:
            return Posture(stance=ESTABLISHED, signals=("owner_established",))
    signals: list[str] = []
    if any(p.search(lowered) for p in _COMPILED_FIRST_PERSON):
        signals.append("first_person")
    if any(p.search(lowered) for p in _COMPILED_RUMOR):
        signals.append("rumor_hedge")
    if any(p.search(lowered) for p in _COMPILED_SOURCE):
        signals.append("source_attribution")
    if "first_person" in signals or "rumor_hedge" in signals:
        return Posture(stance=COMMENTER, signals=tuple(signals))
    if "source_attribution" in signals:
        return Posture(stance=SOURCE, signals=tuple(signals))
    return Posture(stance=UNRESOLVED, signals=("no_stance_signals",))


def check_draft_posture(draft_text: str, posture: Posture) -> tuple[str, ...]:
    """Flag upgrades of a non-established stance into Los Duros' own
    factual/editorial voice. Returns violation codes; empty means clean."""
    if not isinstance(draft_text, str) or not isinstance(posture, Posture):
        raise PostureError("POSTURE_CHECK_INPUT_REQUIRED")
    if posture.stance == ESTABLISHED:
        return ()
    violations: list[str] = []
    lowered = _norm(draft_text)
    if any(m in lowered for m in _CERTAINTY):
        violations.append("POSTURE_CERTAINTY_UPGRADE")
    if any(m in lowered for m in _ENDORSEMENT):
        violations.append("POSTURE_ENDORSEMENT_UPGRADE")
    return tuple(violations)
