"""ANTIPHON: YouTube comment response adapter for the LOS DUROS brand.

Canonical naming record (per zmart360/BIBLIA/GLOBAL.md naming law):
  1. Technical function: intake YouTube comments, resolve the brand, classify
     the comment, apply interaction rules and the safety/chotiaera gate, draft
     a brand-voiced reply, and emit a publish intent only behind an explicit
     write gate.
  2. Tradition searched: Greek liturgical (Christian) tradition.
  3. Source: Greek antiphonon (antiphonon), "sounding in answer" -- the
     short responsive verse sung alternately by two sides in liturgy.
  4. Correspondence: a YouTube comment thread is call-and-response; ANTIPHON
     is the voice that answers. The name describes the function, not a rank.
  5. Respectful functional correspondence; no claim of absolute truth.

Design notes:
  - Deterministic and pure: no network, no YouTube Data API calls, no LLM.
    The API transport (fetching comments, posting replies) lives OUTSIDE
    ZION. ANTIPHON receives already-fetched comment payloads and emits reply
    drafts plus write-gated publish intents.
  - Brand-scoped to business_id "los-duros". Any other business_id fails
    closed: no Los Duros draft is ever produced for another business.
  - External input is never authority: every payload is validated and
    normalized; malformed input is rejected, never guessed.
  - Reply drafts ALWAYS end at pending human review. Publication requires an
    explicit write gate (SecurityContext.production_write_allowed is True),
    and even then ANTIPHON performs no HTTP: it emits a transport-ready
    publish intent for an external publisher. Real YouTube publishing is NOT
    activated by this module.

Pipeline:
  intake_comment -> resolve_brand -> classify_comment (+ safety gate)
      -> draft_reply (ROUTINE only) -> publish_reply (write-gated intent)

Routing (CANONICAL per owner approval 2026-10-03):
  ROUTINE      -- normal opinion, disagreement, artist support, artist
                  comparison, entertainment, simple in-context question.
  MAIN_BRAIN   -- 1. comentario ambiguo; 2. multiples intenciones;
                  3. contexto insuficiente; 4. ironia / sarcasmo.
  HUMAN_REVIEW -- 1. chotiaera; 2. amenazas o violencia; 3. doxxing /
                  privacidad; 4. acusaciones serias; 5. solicitud de
                  informacion sensible; 6. casos sensibles (menores de edad,
                  procesos legales en curso); 7. conflicto con reglas de
                  marca que el adapter no pueda resolver de forma
                  deterministica.
                  Rule for #7: if a brand rule yields a clear deterministic
                  answer, do NOT escalate. Escalate only on real conflict or
                  uncertainty the adapter cannot resolve without additional
                  interpretation.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .gates import SecurityContext
from .registry import SanPedroError, sanpedro_resolve
from . import debate
from . import dedupe
from . import jerga
from . import question as question_mod

BUSINESS_ID = "los-duros"
ISOLATION_KEY = "los-duros"

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

ROUTINE = "ROUTINE"
MAIN_BRAIN = "MAIN_BRAIN"
HUMAN_REVIEW = "HUMAN_REVIEW"
ROUTES = (ROUTINE, MAIN_BRAIN, HUMAN_REVIEW)

# ---------------------------------------------------------------------------
# Normalized comment
# ---------------------------------------------------------------------------

MAX_TEXT_CHARS = 5000


class AntiphonError(ValueError):
    """Rejected comment payload or adapter misuse."""


@dataclass(frozen=True)
class NormalizedComment:
    comment_id: str
    video_id: str
    author: str
    text: str
    business_id: str
    channel_id: str | None = None
    author_channel_id: str | None = None
    published_at: str | None = None
    like_count: int = 0
    video_title: str | None = None
    video_artist: str | None = None
    truncated: bool = False


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AntiphonError(f"COMMENT_FIELD_REQUIRED:{key}")
    return value.strip()


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AntiphonError(f"COMMENT_FIELD_INVALID:{key}")
    return value.strip()


def intake_comment(payload: dict[str, Any]) -> NormalizedComment:
    """Validate and normalize an already-fetched YouTube comment payload.

    Raises AntiphonError on malformed input. Never guesses missing fields.
    Overlong text is truncated for processing and flagged (routes to
    MAIN_BRAIN as insufficient-context risk).
    """
    if not isinstance(payload, dict):
        raise AntiphonError("COMMENT_PAYLOAD_OBJECT_REQUIRED")
    comment_id = _require_str(payload, "comment_id")
    video_id = _require_str(payload, "video_id")
    author = _require_str(payload, "author")
    text = _require_str(payload, "text")
    business_id = payload.get("business_id", BUSINESS_ID)
    if not isinstance(business_id, str) or not business_id.strip():
        raise AntiphonError("COMMENT_FIELD_INVALID:business_id")
    business_id = business_id.strip()
    like_count = payload.get("like_count", 0)
    if not isinstance(like_count, int) or isinstance(like_count, bool) or like_count < 0:
        raise AntiphonError("COMMENT_FIELD_INVALID:like_count")
    truncated = False
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
        truncated = True
    return NormalizedComment(
        comment_id=comment_id,
        video_id=video_id,
        author=author,
        text=text,
        business_id=business_id,
        channel_id=_optional_str(payload, "channel_id"),
        author_channel_id=_optional_str(payload, "author_channel_id"),
        published_at=_optional_str(payload, "published_at"),
        like_count=like_count,
        video_title=_optional_str(payload, "video_title"),
        video_artist=_optional_str(payload, "video_artist"),
        truncated=truncated,
    )


# ---------------------------------------------------------------------------
# Brand resolution (SAN PEDRO, fail closed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrandResolution:
    business_id: str
    isolation_key: str
    context_refs: tuple[str, ...]
    resolved: bool
    reason: str


def resolve_brand(
    comment: NormalizedComment, registry_path: Path | None = None
) -> BrandResolution:
    """Resolve business_id through SAN PEDRO. Only los-duros proceeds.

    Unknown or disabled businesses, and any business_id other than los-duros,
    resolve to resolved=False: the adapter must not draft for them.
    """
    if comment.business_id != BUSINESS_ID:
        return BrandResolution(
            business_id=comment.business_id,
            isolation_key="",
            context_refs=(),
            resolved=False,
            reason="CROSS_BUSINESS_COMMENT",
        )
    try:
        ctx = sanpedro_resolve(BUSINESS_ID, registry_path)
    except SanPedroError as exc:
        return BrandResolution(
            business_id=BUSINESS_ID,
            isolation_key="",
            context_refs=(),
            resolved=False,
            reason=f"SANPEDRO_RESOLVE_FAILED:{exc}",
        )
    if ctx.isolation_key != ISOLATION_KEY:
        return BrandResolution(
            business_id=BUSINESS_ID,
            isolation_key="",
            context_refs=(),
            resolved=False,
            reason="ISOLATION_KEY_MISMATCH",
        )
    return BrandResolution(
        business_id=ctx.business_id,
        isolation_key=ctx.isolation_key,
        context_refs=tuple(ctx.context_refs),
        resolved=True,
        reason="BRAND_RESOLVED",
    )


# ---------------------------------------------------------------------------
# Classification + safety/chotiaera gate
# ---------------------------------------------------------------------------

# Detection patterns. These detect risky CONTENT in the incoming comment so
# the adapter refuses to engage/amplify it. The adapter never reproduces
# street codes, sensitive details, or accusations in its own output.
_CHOTIAERA = (
    r"\bchot\w*",
    r"\bsapo\b",
    r"\bsopl[oó]n\b",
    r"\bdelat\w*",
    r"\bconfidente\b",
    r"\btestigo\b.*\bpolic",
    r"\bfederales\b",
    r"\btira\s*pa'?lante\b",
)
_THREAT = (
    r"\bte\s*voy\s*a\s*matar\b",
    r"\bte\s*mato\b",
    r"\bvas\s*a\s*morir\b",
    r"\bplomo\b",
    r"\bbala\b.*\btu\b",
    r"\bte\s*busco\b",
    r"\bcu[ií]date\b",
    r"\bvas\s*a\s*ver\b.*\bcalle\b",
)
_DOXX = (
    r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
    r"\bd[oó]nde\s*vive\b",
    r"\bdirecci[oó]n\b.*\bcasa\b",
    r"\bsu\s*casa\s*queda\b",
    r"\bn[uú]mero\s*de\s*tel",
)
_ACCUSATION = (
    r"\basesin\w*",
    r"\bviolad\w*",
    r"\babusa\w*\b.*\bmenor",
    r"\bped[oó]fil\w*",
    r"\brater\w*",
    r"\bnarcotraficante\b",
    r"\bmat[oó]\s*a\b",
)
_SENSITIVE_REQUEST = (
    r"\bd[oó]nde\s*vive\b",
    r"\bcu[aá]l\s*es\s*su\s*n[uú]mero\b",
    r"\bpasa\s*el\s*contacto\b",
    r"\bdame\s*su\s*direcci",
)

# HUMAN_REVIEW #6 -- casos sensibles: menores de edad, procesos legales.
# Full trip: these patterns alone force HUMAN_REVIEW, no draft.
_SENSITIVE_CASE = (
    r"\bmenor(es)?\s+de\s+edad\b",
    r"\bniñ[oa]s?\b",
    r"\bchamac[oa]s?\b",
    r"\bjuicio\b",
    r"\bdemanda\b",
    r"\barrest\w*\b",
    r"\bpreso\b",
    r"\bc[aá]rcel\b",
    r"\btribunal\b",
    r"\bfianza\b",
    r"\bsentencia\b",
    r"\bcondena\b",
    r"\babogad[oa]\b",
)

_SAFETY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CHOTIAERA", _CHOTIAERA),
    ("THREAT_VIOLENCE", _THREAT),
    ("DOXXING_PRIVACY", _DOXX),
    ("SERIOUS_ACCUSATION", _ACCUSATION),
    ("SENSITIVE_INFO_REQUEST", _SENSITIVE_REQUEST),
    ("SENSITIVE_CASE", _SENSITIVE_CASE),
)

_COMPILED_SAFETY = tuple(
    (name, tuple(re.compile(p, re.IGNORECASE) for p in patterns))
    for name, patterns in _SAFETY_RULES
)

# ROUTINE subtype detectors (checked only after the safety gate passes).
_OPINION = (r"\bme\s*(encanta|gusta|fascina)\b", r"\best[aá]\s*(duro|cabr[oó]n|brutal)\b",
            r"\bqu[eé]\s*duro\b", r"\bdemasiado\b")
_DISAGREEMENT = (r"\bno\s*estoy\s*de\s*acuerdo\b", r"\beso\s*no\s*es\s*as[ií]\b",
                 r"\best[aá]s\s*mal\b", r"\bte\s*equivocas\b")
_SUPPORT = (r"\bel\s*mejor\b", r"\bteam\s+\w+", r"\bsiempre\s*he\s*dicho\b",
            r"\bmi\s*gallo\b", r"\bduro\s*desde\b")
_COMPARISON = (r"\bvs\.?\b", r"\ble\s*gana\s*a\b", r"\bmejor\s*que\b",
               r"\bpor\s*encima\s*de\b")
_ENTERTAINMENT = (r"\bjaj[aj]+\b", r"\blol\b", r"\bme\s*muero\b.*\brisa",
                  r"\bqu[eé]\s*risa\b", r"\U0001F602", r"\U0001F923")
_QUESTION = (r"\?", r"\bcu[aá]ndo\b", r"\bd[oó]nde\b.*\bfue\b", r"\bqu[eé]\s*pas[oó]\b")

_COMPILED_ROUTINE = tuple(
    (name, tuple(re.compile(p, re.IGNORECASE) for p in patterns))
    for name, patterns in (
        ("opinion", _OPINION),
        ("disagreement", _DISAGREEMENT),
        ("artist_support", _SUPPORT),
        ("artist_comparison", _COMPARISON),
        ("entertainment", _ENTERTAINMENT),
        ("simple_question", _QUESTION),
    )
)

# MAIN_BRAIN detectors (CANONICAL per owner approval 2026-10-03:
# 1. comentario ambiguo; 2. multiples intenciones; 3. contexto insuficiente;
# 4. ironia / sarcasmo).
_IRONY = (r"\bclaro\s*que\s*s[ií]\b.*\bjaj", r"\baj[aá]\b.*\bs[ií]\b.*\bclaro\b",
          r"\bqu[eé]\s*listo\b.*\bjaj", r'"[^"]*"\s*jaj')
_MULTI_INTENT = (r"\bpero\b.*\bpor\s*otro\s*lado\b", r"\bprimero\b.*\bsegundo\b")

_COMPILED_MAINBRAIN = tuple(
    (name, tuple(re.compile(p, re.IGNORECASE) for p in patterns))
    for name, patterns in (
        ("irony", _IRONY),
        ("multi_intent", _MULTI_INTENT),
    )
)

# HUMAN_REVIEW #7 -- conflicto con reglas de marca no resoluble de forma
# deterministica. Two deterministic triggers (canonical):
#   a) unverifiable_claim: the comment hedges a factual claim about a real
#      person ("dicen que", "supuestamente"...). The adapter cannot verify
#      facts, and brand rule 3 forbids confirming unverified facts, so any
#      draft risks amplifying a rumor -> human.
#   b) brand_rule_conflict: the comment matches routine subtypes with
#      opposing valence (support vs disagreement), or matches a routine
#      subtype while carrying a caution signal (sensitive-adjacent words
#      that do not fully trip the safety gate). A clean single-valence
#      routine match with no caution signal is deterministic -> ROUTINE,
#      never escalated.
_CLAIM_HEDGE = (
    r"\bdicen\s+que\b",
    r"\bescuch[eé]\s+que\b",
    r"\bsupuestamente\b",
    r"\bme\s+dijeron\s+que\b",
    r"\bes\s+verdad\s+que\b",
)
_CAUTION = (
    r"\bpolic[ií]a\b",
    r"\bjuez\b",
    r"\bla\s+corte\b",
    r"\ben\s+corte\b",
    r"\bhospital\b",
    r"\bfuneral\b",
    r"\bentierro\b",
)

_COMPILED_CLAIM_HEDGE = (
    ("claim_hedge", tuple(re.compile(p, re.IGNORECASE) for p in _CLAIM_HEDGE)),
)
_COMPILED_CAUTION = (
    ("caution", tuple(re.compile(p, re.IGNORECASE) for p in _CAUTION)),
)

# Opposing valence groups for conflict detection.
_SUPPORT_VALENCE = {"opinion", "artist_support"}
_CRITICAL_VALENCE = {"disagreement"}

_AMBIGUOUS_MIN_WORDS = 2


@dataclass(frozen=True)
class Classification:
    route: str
    subtype: str
    reasons: tuple[str, ...] = ()
    debate_level: str = debate.STANDARD


def _first_match(text: str, compiled: tuple[tuple[str, tuple], ...]) -> str | None:
    for name, patterns in compiled:
        for pattern in patterns:
            if pattern.search(text):
                return name
    return None


def _all_matches(text: str, compiled: tuple[tuple[str, tuple], ...]) -> tuple[str, ...]:
    hits: list[str] = []
    for name, patterns in compiled:
        for pattern in patterns:
            if pattern.search(text):
                hits.append(name)
                break
    return tuple(hits)


def _has_opposing_valence(subtypes: tuple[str, ...]) -> bool:
    names = set(subtypes)
    return bool(names & _SUPPORT_VALENCE) and bool(names & _CRITICAL_VALENCE)


def classify_comment(comment: NormalizedComment) -> Classification:
    """Classify a comment into ROUTINE / MAIN_BRAIN / HUMAN_REVIEW.

    Order is deliberate and deterministic:
      1. Safety gate (incl. SENSITIVE_CASE) -> HUMAN_REVIEW, never drafted.
      2. Truncated input -> MAIN_BRAIN (insufficient context).
      3. Too short -> MAIN_BRAIN (ambiguous).
      4. Claim hedge -> HUMAN_REVIEW (unverifiable_claim): the adapter
         cannot verify facts and must not amplify rumors.
      5. MAIN_BRAIN triggers (irony, multi_intent) -> MAIN_BRAIN.
      6. Routine matches + (opposing valence | caution signal) ->
         HUMAN_REVIEW (brand_rule_conflict): real conflict or uncertainty
         the adapter cannot resolve without interpretation.
      7. Clean routine match -> ROUTINE. A clear deterministic brand rule
         is never escalated.
      8. No match -> MAIN_BRAIN (ambiguous).
    """
    text = comment.text
    safety_hit = _first_match(text, _COMPILED_SAFETY)
    if safety_hit is not None:
        return Classification(
            route=HUMAN_REVIEW, subtype=safety_hit,
            reasons=(f"SAFETY_GATE_TRIP:{safety_hit}",),
        )
    if comment.truncated:
        return Classification(
            route=MAIN_BRAIN, subtype="insufficient_context",
            reasons=("INPUT_TRUNCATED",),
        )
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if len(words) < _AMBIGUOUS_MIN_WORDS:
        return Classification(
            route=MAIN_BRAIN, subtype="ambiguous",
            reasons=("TOO_SHORT_TO_CLASSIFY",),
        )
    # LOS_DUROS.md "Puerto Rican slang and ambiguous words" (permanent):
    # when slang meaning is materially relevant and not canonicalized with
    # sufficient confidence, DO NOT GUESS -- surface verification required.
    jerga_assessment = jerga.assess_jerga(text)
    if jerga_assessment.verification_required:
        return Classification(
            route=MAIN_BRAIN, subtype="jerga_unknown",
            reasons=("JERGA_VERIFY_REQUIRED",)
            + tuple(f"JERGA_UNKNOWN:{t}" for t in jerga_assessment.unknown),
        )
    jerga_reasons = tuple(f"JERGA_KNOWN:{h.term}" for h in jerga_assessment.known)
    # Response-style classification (LOS_DUROS.md "Response psychology"):
    # detects when the comment supports a higher-level debate response.
    debate_assessment = debate.assess_debate_level(text)
    debate_level = debate_assessment.level
    if _first_match(text, _COMPILED_CLAIM_HEDGE) is not None:
        return Classification(
            route=HUMAN_REVIEW, subtype="unverifiable_claim",
            reasons=("CLAIM_HEDGE_DETECTED",),
            debate_level=debate_level,
        )
    mainbrain_hit = _first_match(text, _COMPILED_MAINBRAIN)
    if mainbrain_hit is not None:
        return Classification(
            route=MAIN_BRAIN, subtype=mainbrain_hit,
            reasons=(f"MAINBRAIN_TRIGGER:{mainbrain_hit}",),
            debate_level=debate_level,
        )
    routine_hits = _all_matches(text, _COMPILED_ROUTINE)
    if routine_hits:
        if _has_opposing_valence(routine_hits):
            return Classification(
                route=HUMAN_REVIEW, subtype="brand_rule_conflict",
                reasons=("CONFLICTING_ROUTINE_SIGNALS:" + ",".join(routine_hits),),
                debate_level=debate_level,
            )
        if _first_match(text, _COMPILED_CAUTION) is not None:
            return Classification(
                route=HUMAN_REVIEW, subtype="brand_rule_conflict",
                reasons=("CAUTION_SIGNAL_OVERLAP:" + ",".join(routine_hits),),
                debate_level=debate_level,
            )
        return Classification(
            route=ROUTINE, subtype=routine_hits[0],
            reasons=("ROUTINE_MATCH",) + jerga_reasons,
            debate_level=debate_level,
        )
    return Classification(
        route=MAIN_BRAIN, subtype="ambiguous",
        reasons=("NO_ROUTINE_MATCH",),
        debate_level=debate_level,
    )


# ---------------------------------------------------------------------------
# Reply drafting (ROUTINE only) -- Los Duros interaction rules
# ---------------------------------------------------------------------------

# Brand rule: assume the commenter talks about the artist/persona of the
# content, NOT about Los Duros, unless the text clearly says otherwise.
_BRAND_SELF_REF = (
    r"\blos\s*duros\b",
    r"\bustedes\b.*\bcanal\b",
    r"\bsu\s*canal\b",
)

# Banned from every draft: forced slang / brand-prohibited words.
_BANNED_WORDS = ("acho", "mojate", "mójate")

# YOUTUBE COMMENT CTA ROTATION (permanent brand rule, owner-approved 2026-10-04).
# Every YouTube comment reply MUST close with a contextual SUBSCRIBE + SHARE
# CTA. Never repeat the same CTA mechanically across comments: the pool
# rotates and adapts to the comment's content and tone. ZION may compose new
# variants only if they sound natural and boricua, relate to the comment,
# carry SUBSCRIBE + SHARE intent, invite interaction, do not look like
# copy/paste, and respect every existing Los Duros rule (voice, caps, emoji
# budget, NO CHOTIAERA, no street codes, no automatic artist defense).
# New variants MUST pass validate_cta(); the approved pool below is pinned
# verbatim and also validated at draft time (fail closed).
CTA_VARIANTS: tuple[str, ...] = (
    "🔔 Suscribete pa que no te pierdas lo proximo y compartelo con tu pana a ver que dice 😂",
    "🔔 Suscribete pa que no te pierdas lo proximo y compartelo con ese pana que sabe la que hay.",
    "🔔 Suscribete pa que no te pierdas lo proximo y compartelo con el pana que va a entender esa 😂",
    "🔔 Suscribete pa que no te pierdas lo proximo y compartelo con tu pana pa que vea el revolu 😂",
)

# CONNECT -> POSITION/QUESTION frames per ROUTINE subtype.
# {artist} is filled from video context when available; frames also work
# without it. Never defensive of any artist; never confirming unverified facts.
_FRAMES: dict[str, tuple[tuple[str, str], ...]] = {
    "opinion": (
        ("Esa parte fue la que puso a todo el mundo a hablar.",
         "¿Tú crees que {artist} tenía razón o lo exageraron?"),
        ("Ese momento se quedó con el show.",
         "¿Eso lo pone por encima o todavía le falta camino?"),
        ("Ahí fue donde el tema se puso interesante.",
         "¿Qué parte te gustó más, el principio o el cierre?"),
    ),
    "disagreement": (
        ("Se vale no estar de acuerdo, aquí se debate de todo.",
         "¿Qué fue lo que no te cuadró, el punto o la forma?"),
        ("Esa es la tiraera sana que nos gusta ver.",
         "¿Tú cómo lo hubieras dicho entonces?"),
    ),
    "artist_support": (
        ("Se nota que eres de los fieles desde el día uno.",
         "¿Cuál fue el tema que te convirtió en fan?"),
        ("El apoyo se siente en los comentarios.",
         "¿Qué tiene {artist} que los demás no tienen?"),
    ),
    "artist_comparison": (
        ("Esa comparación siempre prende el debate.",
         "¿En qué categoría gana el tuyo sin discusión?"),
        ("Ahí hay tiraera de verdad entre fanbases.",
         "¿Quién se lleva el round si hablamos de consistencia?"),
    ),
    "entertainment": (
        ("Ese clip rompió el internet por un rato.",
         "¿Cuál fue tu reacción la primera vez que lo viste?"),
        ("Los comentarios están mejor que el video hoy.",
         "¿Qué otro momento te dio la misma risa?"),
    ),
    "simple_question": (
        ("Buena pregunta, varios la hicieron también.",
         "¿Qué crees tú que pasó ahí?"),
        ("Eso mismo nos preguntamos cuando lo vimos.",
         "¿Tú qué teoría tienes?"),
    ),
}

_FALLBACK_FRAMES = (
    ("Eso dio de qué hablar.",
     "¿Tú qué opinas, fue justo o se pasó?"),
)

# ELEVATED frames (LOS_DUROS.md "Response psychology", owner-approved
# 2026-10-05). Used when debate.assess_debate_level returns ELEVATED.
# Same CONNECT -> POSITION/QUESTION pattern with raised reasoning depth.
# They argue with the ARGUMENT, never attack the person: no insults, no
# humiliation, no threats, no inferred traits or mental states.
_ELEVATED_FRAMES: dict[str, tuple[tuple[str, str], ...]] = {
    "opinion": (
        ("Ese punto tiene más capas de lo que parece a primera vista.",
         "¿Cuál es la parte más sólida del argumento y cuál la más floja?"),
        ("Ahí hay una tesis interesante escondida entre la opinión.",
         "¿Qué evidencia la sostendría y qué la tumbaría?"),
    ),
    "disagreement": (
        ("Esa objeción apunta a algo real, no es solo ruido.",
         "¿El problema está en la premisa o en la conclusión?"),
        ("Discrepar con fundamento siempre suma al debate.",
         "¿Qué dato te haría reconsiderar esa posición?"),
    ),
    "artist_support": (
        ("La lealtad se respeta más cuando viene con argumentos.",
         "¿Qué hizo ese artista, concretamente, que los demás no han hecho?"),
        ("Ser fan de verdad también es saber exigir nivel.",
         "¿En qué tendría que mejorar para que ni sus haters tengan de qué agarrarse?"),
    ),
    "artist_comparison": (
        ("Comparar sin criterios claros es solo gritar más alto.",
         "¿En qué métrica gana el tuyo sin que haya discusión?"),
        ("Ese versus tiene historia, no nació ayer.",
         "¿Quién ha sido más consistente en los últimos años y por qué?"),
    ),
    "entertainment": (
        ("El humor también dice mucho del momento que vive el género.",
         "¿Qué fue lo más revelador de ese clip, más allá de la risa?"),
        ("Reírse está bien, pero el contexto importa.",
         "¿Ese momento fue espontáneo o calculado para las cámaras?"),
    ),
    "simple_question": (
        ("Buena pregunta, y tiene más fondo del que parece.",
         "¿Qué teoría tiene más sentido con lo que se sabe hasta ahora?"),
        ("Eso mismo se han preguntado varios, con razón.",
         "¿Qué pieza de información resolvería la duda de una vez?"),
    ),
}

# Person-attack words: never allowed in elevated frames (or any draft).
_PERSON_ATTACK_WORDS = (
    "estupido", "bruto", "ignorante", "idiota", "imbecil", "morboso",
)

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\uFE0F]"
)


def _enforce_single_emoji(text: str) -> str:
    """Keep at most one emoji (the first); strip the rest."""
    seen = 0

    def _keep(match: re.Match[str]) -> str:
        nonlocal seen
        seen += 1
        return match.group(0) if seen == 1 else ""

    return _EMOJI_RE.sub(_keep, text)


def _check_banned_words(text: str) -> None:
    lowered = text.lower()
    for word in _BANNED_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            raise AntiphonError(f"DRAFT_BANNED_WORD:{word}")


def _check_caps_ratio(text: str) -> None:
    """Only KEYWORDS in caps: reject drafts that are mostly uppercase."""
    words = [w.strip(".,!?¿¡") for w in text.split() if w.strip(".,!?¿¡")]
    alpha = [w for w in words if w.isalpha() and len(w) > 2]
    if not alpha:
        return
    upper = [w for w in alpha if w.isupper()]
    if len(upper) / len(alpha) >= 0.5:
        raise AntiphonError("DRAFT_CAPS_RATIO")


# ---------------------------------------------------------------------------
# CTA policy: intent markers and hard limits for every variant (approved pool
# and ZION-composed). Brand voice: no accent marks in social copy.
# ---------------------------------------------------------------------------

_SUBSCRIBE_MARKERS = ("suscrib",)
_SHARE_MARKERS = ("compart", "mandaselo", "mándaselo", "pasalo", "pásalo", "enviaselo")
# Matches the loosest owner-approved variant (bell + laugh emoji).
_CTA_MAX_EMOJIS = 2


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _cta_emoji_count(text: str) -> int:
    return len(_EMOJI_RE.findall(text))


def validate_cta(cta: str) -> tuple[str, ...]:
    """Policy violations for a CTA variant; empty tuple means compliant.

    Every variant (approved pool or ZION-composed) must carry SUBSCRIBE +
    SHARE intent, respect the emoji budget, avoid banned words and accent
    marks, and never be all-caps. Pure and deterministic.
    """
    violations: list[str] = []
    lowered = cta.lower()
    if not any(m in lowered for m in _SUBSCRIBE_MARKERS):
        violations.append("CTA_MISSING_SUBSCRIBE_INTENT")
    if not any(m in lowered for m in _SHARE_MARKERS):
        violations.append("CTA_MISSING_SHARE_INTENT")
    if _cta_emoji_count(cta) > _CTA_MAX_EMOJIS:
        violations.append("CTA_TOO_MANY_EMOJIS")
    for word in _BANNED_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            violations.append(f"CTA_BANNED_WORD:{word}")
    if any(c.isalpha() for c in cta) and cta == cta.upper():
        violations.append("CTA_ALL_CAPS")
    if re.search(r"[áéíóúñüÁÉÍÓÚÑÜ]", cta):
        violations.append("CTA_ACCENTED_CHARS")
    return tuple(violations)


_COMPOSE_TEMPLATES = (
    "🔔 Suscribete pa que no te pierdas lo proximo y compartelo con tu pana pa que vea {phrase}.",
    "🔔 Suscribete pa que no te pierdas lo proximo y mandaselo al pana que {phrase}.",
)


def compose_cta_variant(context_phrase: str) -> str:
    """Compose a new contextual CTA variant from a comment-derived phrase.

    The phrase is sanitized (whitespace-collapsed, lowercased,
    accent-stripped, length-capped) and the composed variant MUST pass
    validate_cta(); otherwise AntiphonError is raised. The composed variant
    is returned for one reply only -- it is never added to CTA_VARIANTS
    implicitly.
    """
    phrase = _strip_accents(" ".join(str(context_phrase).split()).lower())
    if not phrase:
        raise AntiphonError("CTA_EMPTY_PHRASE")
    phrase = phrase[:48].rstrip()
    index = int(hashlib.sha256(f"compose:{phrase}".encode()).hexdigest(), 16) % len(_COMPOSE_TEMPLATES)
    cta = _COMPOSE_TEMPLATES[index].format(phrase=phrase)
    violations = validate_cta(cta)
    if violations:
        raise AntiphonError(f"CTA_POLICY_VIOLATION:{','.join(violations)}")
    return cta


@dataclass(frozen=True)
class ReplyDraft:
    comment_id: str
    business_id: str
    route: str
    subtype: str
    text: str
    cta_variant: str
    brand_addressed: bool
    reasons: tuple[str, ...] = field(default=())


def _pick_frame(
    subtype: str,
    comment_id: str,
    pool: dict[str, tuple[tuple[str, str], ...]],
) -> tuple[str, str]:
    frames = pool.get(subtype, _FALLBACK_FRAMES)
    index = int(hashlib.sha256(f"{subtype}:{comment_id}".encode()).hexdigest(), 16) % len(frames)
    return frames[index]


def _pick_cta(comment_id: str, subtype: str = "") -> str:
    """Deterministic CTA rotation, adapted to the comment's tone via subtype.

    The same (comment_id, subtype) always yields the same variant; different
    comments and tones rotate across the pool instead of repeating the same
    CTA mechanically.
    """
    index = int(hashlib.sha256(f"cta:{subtype}:{comment_id}".encode()).hexdigest(), 16) % len(CTA_VARIANTS)
    return CTA_VARIANTS[index]


def draft_reply(
    comment: NormalizedComment,
    classification: Classification,
    *,
    brand: BrandResolution,
) -> ReplyDraft:
    """Draft a Los Duros reply for a ROUTINE comment.

    Pattern: CONNECT -> POSITION/QUESTION -> CTA. Deterministic: the same
    comment always yields the same draft. Raises AntiphonError if the comment
    is not ROUTINE, the brand is unresolved, or a brand rule is violated.
    The CTA always closes the reply, appended verbatim from the rotation
    pool (validated by validate_cta(); fail closed). The owner's example
    reply is NEVER returned verbatim.
    """
    if not brand.resolved or brand.business_id != BUSINESS_ID:
        raise AntiphonError("DRAFT_BRAND_UNRESOLVED")
    if classification.route != ROUTINE:
        raise AntiphonError(f"DRAFT_ROUTE_NOT_ROUTINE:{classification.route}")
    if comment.business_id != BUSINESS_ID:
        raise AntiphonError("DRAFT_CROSS_BUSINESS")
    # Jerga fail-safe holds on every call path, including direct calls:
    # never draft on a guessed interpretation of unverified slang.
    _jerga_assessment = jerga.assess_jerga(comment.text)
    if _jerga_assessment.verification_required:
        raise AntiphonError(
            "JERGA_VERIFY_REQUIRED:" + ",".join(_jerga_assessment.unknown)
        )
    brand_addressed = any(
        re.search(p, comment.text, re.IGNORECASE) for p in _BRAND_SELF_REF
    )
    # Response-style pool: elevated debate level uses the elevated frames.
    level = (
        classification.debate_level
        if classification.debate_level in debate.LEVELS
        else debate.STANDARD
    )
    pool = (
        _ELEVATED_FRAMES if level == debate.ELEVATED else _FRAMES
    )
    connect, question = _pick_frame(classification.subtype, comment.comment_id, pool)
    artist = (comment.video_artist or "").strip()
    if "{artist}" in question:
        # Brand rule: KEYWORDS in CAPS (artist names are keywords).
        question = question.format(artist=artist.upper()) if artist else question.replace("{artist}", "el artista")
    # LOS_DUROS.md "Engagement questions": the closing question must grow
    # from the actual comment/context. Fail closed instead of appending a
    # generic or unanchored question.
    _context_tokens = question_mod.content_tokens(
        f"{comment.video_artist or ''} {comment.video_title or ''}"
    )
    _q_violations = question_mod.validate_question(
        question,
        comment.text,
        context_tokens=_context_tokens,
        subtype=classification.subtype,
    )
    if _q_violations:
        raise AntiphonError("QUESTION_QUALITY:" + ",".join(_q_violations))
    cta = _pick_cta(comment.comment_id, classification.subtype)
    cta_violations = validate_cta(cta)
    if cta_violations:
        raise AntiphonError(f"CTA_POLICY_VIOLATION:{','.join(cta_violations)}")
    # The single-emoji rule applies to the reply body; the CTA is appended
    # verbatim (owner-approved variants carry their own emoji).
    body = _enforce_single_emoji(f"{connect} {question}")
    text = f"{body} {cta}"
    _check_banned_words(text)
    _check_caps_ratio(text)
    if len(text) > 280:
        raise AntiphonError("DRAFT_TOO_LONG")
    return ReplyDraft(
        comment_id=comment.comment_id,
        business_id=BUSINESS_ID,
        route=ROUTINE,
        subtype=classification.subtype,
        text=text,
        cta_variant=cta,
        brand_addressed=brand_addressed,
        reasons=classification.reasons,
    )


# ---------------------------------------------------------------------------
# Write-gated publishing (intent only -- no transport)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PublishIntent:
    comment_id: str
    video_id: str
    channel_id: str | None
    text: str
    business_id: str


@dataclass(frozen=True)
class PublishResult:
    published: bool
    reason: str
    draft: ReplyDraft | None = None
    intent: PublishIntent | None = None


def publish_reply(
    draft: ReplyDraft,
    comment: NormalizedComment,
    *,
    security: SecurityContext | None = None,
) -> PublishResult:
    """Publish ONLY when the write gate is explicitly enabled.

    The write gate is SecurityContext.production_write_allowed is True.
    Default (None / False): no intent is produced. Even when enabled, this
    function performs NO network I/O: it returns a transport-ready intent for
    an external publisher. Real YouTube publishing is NOT activated here.
    """
    if draft.business_id != BUSINESS_ID or comment.business_id != BUSINESS_ID:
        return PublishResult(published=False, reason="CROSS_BUSINESS_PUBLISH_DENIED", draft=draft)
    if draft.comment_id != comment.comment_id:
        return PublishResult(published=False, reason="DRAFT_COMMENT_MISMATCH", draft=draft)
    if security is None or security.production_write_allowed is not True:
        return PublishResult(published=False, reason="WRITE_GATE_DISABLED", draft=draft)
    intent = PublishIntent(
        comment_id=comment.comment_id,
        video_id=comment.video_id,
        channel_id=comment.channel_id,
        text=draft.text,
        business_id=BUSINESS_ID,
    )
    return PublishResult(published=False, reason="PUBLISH_INTENT_READY", draft=draft, intent=intent)


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AntiphonResult:
    comment: NormalizedComment
    brand: BrandResolution
    classification: Classification
    draft: ReplyDraft | None
    publish: PublishResult | None


def process_comment(
    payload: dict[str, Any],
    *,
    registry_path: Path | None = None,
    security: SecurityContext | None = None,
    attempt_publish: bool = False,
) -> AntiphonResult:
    """Run the full ANTIPHON pipeline on one comment payload.

    attempt_publish=True calls publish_reply (still write-gated; no network
    ever). Drafts are produced for ROUTINE only; MAIN_BRAIN and HUMAN_REVIEW
    never produce drafts.
    """
    comment = intake_comment(payload)
    brand = resolve_brand(comment, registry_path)
    if not brand.resolved:
        classification = Classification(
            route=HUMAN_REVIEW, subtype="brand_unresolved",
            reasons=(brand.reason,),
        )
        return AntiphonResult(comment, brand, classification, None, None)
    classification = classify_comment(comment)
    draft = None
    if classification.route == ROUTINE:
        draft = draft_reply(comment, classification, brand=brand)
    publish = None
    if attempt_publish and draft is not None:
        publish = publish_reply(draft, comment, security=security)
    return AntiphonResult(comment, brand, classification, draft, publish)


# ---------------------------------------------------------------------------
# Batch processing (screenshot / comment batches) with reply dedupe
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BatchResult:
    comment_id: str
    state: str  # dedupe.ELIGIBLE / dedupe.ALREADY_REPLIED / dedupe.AMBIGUOUS
    result: AntiphonResult | None  # None when suppressed (already replied)


def process_batch(
    payloads: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    answered_ids: Iterable[str] = (),
    registry_path: Path | None = None,
    security: SecurityContext | None = None,
    attempt_publish: bool = False,
) -> tuple[BatchResult, ...]:
    """Run the ANTIPHON pipeline over a comment batch with reply dedupe.

    Canonical: LOS_DUROS.md "Screenshots and comments". Comments visibly or
    already marked as answered never get a new draft (ALREADY_REPLIED,
    result=None). Comments with unverified identity fail safe to
    HUMAN_REVIEW/identity_ambiguous (AMBIGUOUS, no draft). Eligible comments
    run the normal single-comment pipeline, deterministically, in batch
    order. Payloads may carry screenshot metadata keys "marked_answered"
    and "identity_verified" (intake_comment ignores unknown keys).
    """
    if not isinstance(payloads, (list, tuple)):
        raise AntiphonError("BATCH_PAYLOADS_SEQUENCE_REQUIRED")
    comments = [intake_comment(p) for p in payloads]
    items = [
        dedupe.BatchComment(
            comment_id=c.comment_id,
            marked_answered=bool(p.get("marked_answered", False)),
            identity_verified=bool(p.get("identity_verified", True)),
        )
        for c, p in zip(comments, payloads)
    ]
    assessment = dedupe.assess_dedupe(items, answered_ids)
    out: list[BatchResult] = []
    for comment, payload, (cid, state) in zip(comments, payloads, assessment.states):
        if state == dedupe.ALREADY_REPLIED:
            out.append(BatchResult(comment_id=cid, state=state, result=None))
            continue
        if state == dedupe.AMBIGUOUS:
            brand = resolve_brand(comment, registry_path)
            classification = Classification(
                route=HUMAN_REVIEW, subtype="identity_ambiguous",
                reasons=("DEDUPE_AMBIGUOUS_IDENTITY",),
            )
            out.append(
                BatchResult(
                    comment_id=cid, state=state,
                    result=AntiphonResult(comment, brand, classification, None, None),
                )
            )
            continue
        out.append(
            BatchResult(
                comment_id=cid, state=state,
                result=process_comment(
                    payload, registry_path=registry_path,
                    security=security, attempt_publish=attempt_publish,
                ),
            )
        )
    return tuple(out)
