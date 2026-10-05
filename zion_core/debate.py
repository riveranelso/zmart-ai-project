"""DEBATE: response-style classification for debate-level replies.

Canonical: zmart360/BIBLIA/LOS_DUROS.md, section "Response psychology: when
the commenter is a debater" (owner-approved 2026-10-05).

This is RESPONSE-STYLE classification, not a personality diagnosis. It
detects when the comment/context supports a higher-level debate response
(reasoned argument, substantive historical claim, counterargument,
analytical disagreement, debate-style conversational context) so the
response planner can raise specificity, reasoning depth, and the quality
of the counter-question.

Hard boundaries (canonical):
- NEVER insult intelligence, call someone stupid, invent traits, or infer
  private mental state. The assessment describes TEXT FEATURES only.
- The elevated style still respects every Los Duros rule: no gratuitous
  insults, no humiliation, no threats, no violence, no personal fights.

Deterministic and pure: regex signals over normalized text, no network.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

STANDARD = "STANDARD"
ELEVATED = "ELEVATED"
LEVELS = (STANDARD, ELEVATED)


class DebateError(ValueError):
    """Invalid input to debate assessment."""


def _norm(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


# Signal groups: (group_name, patterns). A group counts once no matter how
# many of its patterns hit, so elevation requires breadth of evidence.
_REASONING = (
    r"\bporque\b",
    r"\bsin\s+embargo\b",
    r"\baunque\b",
    r"\bpor\s+eso\b",
    r"\ben\s+cambio\b",
    r"\bde\s+hecho\b",
    r"\bes\s+decir\b",
    r"\bdado\s+que\b",
    r"\bpuesto\s+que\b",
)
_COUNTERARGUMENT = (
    r"\bno\s+estoy\s+de\s+acuerdo\b",
    r"\bte\s+equivocas\b",
    r"\beso\s+no\s+es\s+as[ií]\b",
    r"\bdiscrepo\b",
    r"\bpero\s+la\s+verdad\b",
)
_HISTORICAL = (
    r"\b(19|20)\d{2}\b",  # a concrete year: substantive historical claim
    r"\ben\s+los\s+\d0s?\b",
    r"\ben\s+la\s+[eé]poca\b",
    r"\bcuando\s+salio\b",
)
_ANALYTICAL = (
    r"\blos\s+datos\b",
    r"\bla\s+evidencia\b",
    r"\bcontradic(e|en|e)\b",
    r"\bcontradiccion\b",
    r"\bpruebas\b",
    r"\bversion\s+de\s+los\s+hechos\b",
)

_SIGNAL_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("reasoning", _REASONING),
    ("counterargument", _COUNTERARGUMENT),
    ("historical_claim", _HISTORICAL),
    ("analytical", _ANALYTICAL),
)

_COMPILED = tuple(
    (name, tuple(re.compile(p) for p in patterns))
    for name, patterns in _SIGNAL_GROUPS
)


@dataclass(frozen=True)
class DebateAssessment:
    level: str
    signals: tuple[str, ...] = ()  # text-feature signal groups that fired


def assess_debate_level(text: str) -> DebateAssessment:
    """Classify the response style a comment supports.

    ELEVATED when at least two distinct signal groups fire (breadth of
    evidence, not a single connective). Otherwise STANDARD. The assessment
    never describes the person, only the text.
    """
    if not isinstance(text, str):
        raise DebateError("DEBATE_TEXT_REQUIRED")
    lowered = _norm(text)
    fired = tuple(
        name for name, patterns in _COMPILED
        if any(p.search(lowered) for p in patterns)
    )
    if len(fired) >= 2:
        return DebateAssessment(level=ELEVATED, signals=fired)
    return DebateAssessment(level=STANDARD, signals=fired)
