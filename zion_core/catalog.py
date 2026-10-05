"""CATALOG: retention-aware catalog link selection.

Canonical: zmart360/BIBLIA/LOS_DUROS.md, section "YouTube retention and
catalog" (owner-approved 2026-10-05).

Runtime boundary note: this section belongs to CONTENT STRATEGY (fixed
comments, descriptions, end screens, cards, playlists, internal links),
NOT to comment drafting. It is therefore implemented here as a standalone
Brain service, not inside zion_core.antiphon.

Enforced canonical idea: content/reply/linking decisions must consider
catalog relevance rather than blindly pushing unrelated content.

Selection rules (deterministic):

- Relevance first: same artist (+30), each shared topic (+10, cap 30),
  recent (published within 180 days of as_of, +5).
- Contextual relationship beats "biggest video wins": an unrelated video
  never outranks a relevant one on performance. Performance only breaks
  ties AMONG relevant candidates.
- Unknown performance is unknown: never invented, never assumed, never
  claimed in reasons. Invalid performance values are rejected, not
  guessed.
- Sort: (-relevance, -performance_rank_if_relevant, -published_at,
  video_id). Fully deterministic; ties break by video_id ascending.
- The current video is always excluded.
- Boundary: this module never alters captions or any existing content;
  it only selects candidates. The canon boundary ("do not alter existing
  captions if Nelson flagged them") is the caller's responsibility and is
  documented, not silently bypassed.

Deterministic and pure: no network, no external calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

PERFORMANCE_LEVELS = ("strong", "average", "weak", "unknown")
_PERFORMANCE_RANK = {"strong": 3, "average": 2, "weak": 1, "unknown": 0}

_SAME_ARTIST_SCORE = 30
_TOPIC_SCORE = 10
_TOPIC_CAP = 30
_RECENT_DAYS = 180
_RECENT_SCORE = 5


class CatalogError(ValueError):
    """Invalid catalog input (e.g. invented/unknown performance level)."""


@dataclass(frozen=True)
class Video:
    video_id: str
    title: str
    artist: str
    topics: tuple[str, ...] = ()
    published_at: str = ""  # ISO YYYY-MM-DD; "" means unknown date
    performance: str = "unknown"  # strong | average | weak | unknown

    def __post_init__(self) -> None:
        if not isinstance(self.video_id, str) or not self.video_id.strip():
            raise CatalogError("CATALOG_VIDEO_ID_REQUIRED")
        if self.performance not in PERFORMANCE_LEVELS:
            raise CatalogError(f"CATALOG_PERFORMANCE_INVALID:{self.performance}")
        if self.published_at:
            try:
                year, month, day = (int(p) for p in self.published_at.split("-"))
                date(year, month, day)
            except (ValueError, AttributeError) as exc:
                raise CatalogError(
                    f"CATALOG_DATE_INVALID:{self.published_at}"
                ) from exc


@dataclass(frozen=True)
class CatalogPick:
    video: Video
    score: int  # relevance score (performance excluded by design)
    reasons: tuple[str, ...] = ()


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        year, month, day = (int(p) for p in value.split("-"))
        return date(year, month, day)
    except (ValueError, AttributeError):
        return None


def _relevance(
    video: Video,
    context_artist: str,
    context_topics: frozenset[str],
    as_of: date,
) -> tuple[int, tuple[str, ...]]:
    score = 0
    reasons: list[str] = []
    if context_artist and video.artist.strip().lower() == context_artist.strip().lower():
        score += _SAME_ARTIST_SCORE
        reasons.append("same_artist")
    shared = sorted(
        {t.strip().lower() for t in video.topics if t.strip()}
        & context_topics
    )
    if shared:
        score += min(len(shared) * _TOPIC_SCORE, _TOPIC_CAP)
        reasons.extend(f"shared_topic:{t}" for t in shared)
    published = _parse_date(video.published_at)
    if published is not None and 0 <= (as_of - published).days <= _RECENT_DAYS:
        score += _RECENT_SCORE
        reasons.append("recent")
    return score, tuple(reasons)


def select_catalog_links(
    catalog: tuple[Video, ...] | list[Video],
    *,
    current_video_id: str,
    context_artist: str = "",
    context_topics: tuple[str, ...] | frozenset[str] = (),
    limit: int = 3,
    as_of: str | None = None,
) -> tuple[CatalogPick, ...]:
    """Select catalog link candidates by contextual relevance.

    Deterministic. Performance never outranks relevance; unknown
    performance is never invented or claimed.
    """
    if not isinstance(catalog, (tuple, list)):
        raise CatalogError("CATALOG_SEQUENCE_REQUIRED")
    if not isinstance(current_video_id, str) or not current_video_id.strip():
        raise CatalogError("CATALOG_CURRENT_VIDEO_REQUIRED")
    if not isinstance(limit, int) or limit < 0:
        raise CatalogError("CATALOG_LIMIT_INVALID")
    reference = _parse_date(as_of) if as_of else date.today()
    if reference is None:
        raise CatalogError(f"CATALOG_DATE_INVALID:{as_of}")
    topics = frozenset(t.strip().lower() for t in context_topics if t.strip())

    scored: list[tuple[tuple[int, int, int, str], CatalogPick]] = []
    for video in catalog:
        if not isinstance(video, Video):
            raise CatalogError("CATALOG_VIDEO_OBJECT_REQUIRED")
        if video.video_id == current_video_id:
            continue
        relevance, reasons = _relevance(video, context_artist, topics, reference)
        rank = _PERFORMANCE_RANK[video.performance] if relevance > 0 else 0
        if relevance > 0 and video.performance != "unknown":
            reasons = reasons + (f"historical_strength:{video.performance}",)
        published = _parse_date(video.published_at)
        ordinal = published.toordinal() if published else 0
        key = (-relevance, -rank, -ordinal, video.video_id)
        scored.append((key, CatalogPick(video=video, score=relevance, reasons=reasons)))
    scored.sort(key=lambda item: item[0])
    return tuple(pick for _, pick in scored[:limit])
