"""PROVENANCE: internal semantic provenance labels.

Canonical: zmart360/BIBLIA/LOS_DUROS.md, section "Facts vs context vs
opinion" (owner-approved 2026-10-05).

Before generating content, the runtime distinguishes internally between:

- FACT     -- owner-established or otherwise verified fact.
- CONTEXT  -- observed content context (the video/clip, artist, title).
- OPINION  -- first-person opinion, hedge, or rumor.
- INFERENCE -- causal/comparative claim without cited evidence.
- UNKNOWN  -- none of the above; must remain unknown.

Critical boundaries (enforced by check_promotion):
- INFERENCE must never silently upgrade to FACT.
- OPINION must never silently upgrade to FACT.
- UNKNOWN must never upgrade to anything.

These are internal reasoning/enforcement labels; they do not appear in
the public reply. check_upgrade() guards draft text against presenting
an INFERENCE/OPINION/UNKNOWN-sourced claim with fact-certainty markers.

Deterministic and pure: regex/substring signals over normalized text.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

FACT = "fact"
CONTEXT = "context"
OPINION = "opinion"
INFERENCE = "inference"
UNKNOWN = "unknown"
LABELS = (FACT, CONTEXT, OPINION, INFERENCE, UNKNOWN)

# Promotions that are never allowed: (from_label, to_label).
_PROHIBITED_PROMOTIONS = frozenset(
    {
        (INFERENCE, FACT),
        (OPINION, FACT),
        (UNKNOWN, FACT),
        (UNKNOWN, CONTEXT),
        (UNKNOWN, OPINION),
        (UNKNOWN, INFERENCE),
    }
)


class ProvenanceError(ValueError):
    """Invalid label use or prohibited provenance promotion."""


def _norm(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


@dataclass(frozen=True)
class Provenance:
    label: str
    basis: str  # short reason for the label


def check_promotion(from_label: str, to_label: str) -> None:
    """Raise ProvenanceError on a prohibited label promotion. Allowed
    transitions pass silently."""
    if from_label not in LABELS or to_label not in LABELS:
        raise ProvenanceError(f"PROVENANCE_LABEL_INVALID:{from_label}->{to_label}")
    if (from_label, to_label) in _PROHIBITED_PROMOTIONS:
        raise ProvenanceError(f"PROVENANCE_UPGRADE_FORBIDDEN:{from_label}->{to_label}")


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
)
_INFERENCE_MARKERS = (
    r"\bpor\s+eso\b",
    r"\bmejor\s+que\b",
    r"\bpeor\s+que\b",
    r"\beso\s+prueba\b",
    r"\besta\s+claro\s+que\b",
    r"\bsin\s+duda\b",
)
_CONTENT_WORDS = (
    "video",
    "clip",
    "tema",
    "episodio",
    "capitulo",
)

_COMPILED_FIRST_PERSON = tuple(re.compile(p) for p in _FIRST_PERSON)
_COMPILED_RUMOR = tuple(re.compile(p) for p in _RUMOR)
_COMPILED_INFERENCE = tuple(re.compile(p) for p in _INFERENCE_MARKERS)

# Certainty markers mirror posture._CERTAINTY: presenting a claim as
# settled fact. Kept local so this module stays dependency-free.
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


def classify_statement(
    text: str,
    *,
    context_tokens: frozenset[str] | tuple[str, ...] = frozenset(),
    established: tuple[str, ...] = (),
) -> Provenance:
    """Label a statement's semantic provenance.

    Priority: established (FACT) > observed context (CONTEXT) >
    opinion/rumor (OPINION) > unevidenced causal/comparative (INFERENCE) >
    UNKNOWN. `established` holds normalized owner-established statements;
    `context_tokens` holds normalized observed-content tokens.
    """
    if not isinstance(text, str):
        raise ProvenanceError("PROVENANCE_TEXT_REQUIRED")
    lowered = _norm(text)
    statements: list[str] = []
    for entry in established:
        # Accept raw normalized strings or objects carrying .statement
        # (e.g. posture.EstablishedPosition).
        if isinstance(entry, str):
            statements.append(entry)
        else:
            statement = getattr(entry, "statement", None)
            if isinstance(statement, str):
                statements.append(statement)
    for statement in statements:
        if statement and statement in lowered:
            return Provenance(label=FACT, basis="owner-established")
    tokens = set(re.findall(r"[a-zñ]+", lowered))
    normalized_context = {_norm(t) for t in context_tokens}
    if tokens & normalized_context or any(w in lowered for w in _CONTENT_WORDS):
        return Provenance(label=CONTEXT, basis="observed-content-context")
    if any(p.search(lowered) for p in _COMPILED_FIRST_PERSON) or any(
        p.search(lowered) for p in _COMPILED_RUMOR
    ):
        return Provenance(label=OPINION, basis="opinion-or-rumor-markers")
    if any(p.search(lowered) for p in _COMPILED_INFERENCE):
        return Provenance(label=INFERENCE, basis="unevidenced-causal-comparative")
    return Provenance(label=UNKNOWN, basis="no-provenance-signals")


def check_upgrade(body_text: str, source_label: str) -> tuple[str, ...]:
    """Flag draft text that presents an INFERENCE/OPINION/UNKNOWN-sourced
    claim with fact-certainty markers. Returns violation codes."""
    if not isinstance(body_text, str) or source_label not in LABELS:
        raise ProvenanceError("PROVENANCE_CHECK_INPUT_REQUIRED")
    if source_label in (INFERENCE, OPINION, UNKNOWN):
        lowered = _norm(body_text)
        if any(m in lowered for m in _CERTAINTY):
            return ("PROVENANCE_UPGRADE",)
    return ()
