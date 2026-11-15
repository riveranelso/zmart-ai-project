"""QUESTION: structural validation for engagement questions.

Canonical: zmart360/BIBLIA/LOS_DUROS.md, section "Engagement questions"
(owner-approved 2026-10-05).

The closing question must grow from the actual comment/context -- never a
generic appendage added merely because a rule says to close with a question.

Deterministic structural validation (validate_question returns violation
codes; empty tuple means compliant):

1. QUESTION_NO_QUESTION_MARK -- the text must end with "?".
2. QUESTION_GENERIC -- the whole normalized question matches a known
   generic template (exact match after normalization, never substring, so
   substantive questions like "¿Tú qué opinas, fue justo o se pasó?" pass).
3. QUESTION_UNANCHORED -- no content token of the question intersects the
   comment's content tokens, the provided context tokens (artist, title),
   or the subtype anchor lexicon.

Anchor lexicons are structural, deterministic, and derived from the
approved frame vocabulary. Lexical overlap is a NECESSARY structural
signal, never proof of semantic relevance: when relevance cannot be
established the caller must route/review rather than fabricate.

Deterministic and pure: no network, no external calls.
"""
from __future__ import annotations

import re
import unicodedata

QUESTION_NO_QUESTION_MARK = "QUESTION_NO_QUESTION_MARK"
QUESTION_GENERIC = "QUESTION_GENERIC"
QUESTION_UNANCHORED = "QUESTION_UNANCHORED"


class QuestionError(ValueError):
    """Invalid input to question validation."""


def _norm(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


# Generic templates: matched on the WHOLE normalized question only, so
# substantive questions containing similar words are never rejected.
_GENERIC_QUESTIONS = (
    "que tu crees",
    "que opinas",
    "que dicen",
    "estas de acuerdo",
    "si o no",
    "te gusto",
    "que tal",
    "de acuerdo o no",
    "y tu que dices",
)

_STOPWORDS = frozenset(
    "para porque pero como cuando donde este esta esto esos esas muy mas tan "
    "solo tambien entonces pues aqui ahi alli ahora entre sobre desde hasta "
    "cada otro otra otros otras mismo misma cual quien tienen fue eran estan "
    "son ser hacia durante segun mientras aunque sino aquel tiene entre "
    "para por con los las una unos unas del".split()
)

# Subtype anchor lexicon: content words from the approved frame vocabulary
# (standard + elevated). Normalized, no accents.
_SUBTYPE_ANCHORS: dict[str, frozenset[str]] = {
    "opinion": frozenset(
        "razon parte momento tema show principio cierre encima camino "
        "exageraron hablar mundo capas vista solida floja argumento tesis "
        "escondida opinion evidencia sostendria tumbaria".split()
    ),
    "disagreement": frozenset(
        "punto forma argumento debate postura dicho acuerdo objecion apunta "
        "ruido premisa conclusion fundamento suma dato reconsiderar posicion "
        "valen cuadro".split()
    ),
    "artist_support": frozenset(
        "tema fan tiene demas apoyo fieles dia siente lealtad respeta "
        "argumentos hizo artista concretamente hecho exigir nivel mejorar "
        "haters agarrarse convirtio".split()
    ),
    "artist_comparison": frozenset(
        "categoria gana round consistencia comparacion tuyo prende criterios "
        "claros gritar metrica discusion versus historia nacio consistente "
        "ultimos anos".split()
    ),
    "entertainment": frozenset(
        "reaccion viste momento risa video comentarios rompio internet rato "
        "humor dice genero revelador clip contexto importa espontaneo "
        "calculado camaras muero".split()
    ),
    "simple_question": frozenset(
        "pregunta paso teoria ahi varios hicieron fondo parece sentido sabe "
        "ahora pieza informacion resolveria duda vez".split()
    ),
}
_FALLBACK_ANCHORS = frozenset("opinas justo paso hablar dio".split())


def content_tokens(text: str) -> frozenset[str]:
    """Content-bearing tokens: normalized, length>=4, stopwords removed."""
    if not isinstance(text, str):
        raise QuestionError("QUESTION_TEXT_REQUIRED")
    tokens = re.findall(r"[a-zñ]+", _norm(text))
    return frozenset(t for t in tokens if len(t) >= 4 and t not in _STOPWORDS)


def _normalized_whole(text: str) -> str:
    cleaned = re.sub(r"[¿?¡!.,;:]", " ", _norm(text))
    return re.sub(r"\s+", " ", cleaned).strip()


def validate_question(
    question_text: str,
    comment_text: str,
    *,
    context_tokens: tuple[str, ...] | frozenset[str] = (),
    subtype: str = "",
) -> tuple[str, ...]:
    """Structural validation for an engagement question.

    Returns violation codes; empty tuple means the question is structurally
    acceptable. Deterministic.
    """
    if not isinstance(question_text, str) or not isinstance(comment_text, str):
        raise QuestionError("QUESTION_TEXT_REQUIRED")
    violations: list[str] = []
    stripped = question_text.strip()
    if not stripped:
        return (QUESTION_NO_QUESTION_MARK,)
    if not stripped.endswith("?"):
        violations.append(QUESTION_NO_QUESTION_MARK)
    if _normalized_whole(stripped) in _GENERIC_QUESTIONS:
        violations.append(QUESTION_GENERIC)
    anchors = (
        content_tokens(comment_text)
        | frozenset(_norm(t) for t in context_tokens)
        | _SUBTYPE_ANCHORS.get(subtype, _FALLBACK_ANCHORS)
    )
    if not (content_tokens(stripped) & anchors):
        violations.append(QUESTION_UNANCHORED)
    return tuple(violations)
