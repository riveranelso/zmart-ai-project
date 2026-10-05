"""Tests for zion_core.catalog (GAP 7: retention / catalog logic).

Canonical: LOS_DUROS.md "YouTube retention and catalog" (owner-approved
2026-10-05). Content/reply/linking decisions must consider catalog
relevance (thematic playlists, related recent videos, historically strong
videos of the same artist/topic, end screens, cards, fixed comment,
internal links) to grow session time inside Los Duros' own catalog.
Contextual relationship beats "biggest video wins". Unknown performance
is unknown: never invented, never assumed.
"""
import pytest

from zion_core import catalog


def _video(vid, artist="Anuel", topics=("tiraera",), published="2026-09-01",
           performance="unknown", title=""):
    return catalog.Video(
        video_id=vid, title=title or vid, artist=artist, topics=topics,
        published_at=published, performance=performance,
    )


def test_contextually_relevant_beats_biggest_video():
    unrelated_strong = _video("v-pop", artist="Otro", topics=("pop",), performance="strong")
    related_weak = _video("v-rel", artist="Anuel", topics=("tiraera",), performance="weak")
    picks = catalog.select_catalog_links(
        [unrelated_strong, related_weak],
        current_video_id="v-now", context_artist="Anuel",
        context_topics=("tiraera",), limit=2, as_of="2026-10-05",
    )
    assert [p.video.video_id for p in picks] == ["v-rel", "v-pop"]
    assert "same_artist" in picks[0].reasons


def test_unknown_performance_stays_unknown():
    candidate = _video("v-rel", performance="unknown")
    picks = catalog.select_catalog_links(
        [candidate], current_video_id="v-now", context_artist="Anuel",
        context_topics=("tiraera",), limit=1, as_of="2026-10-05",
    )
    assert picks[0].video.performance == "unknown"
    assert not any("strength" in r for r in picks[0].reasons)


def test_unknown_performance_never_wins_on_performance():
    unknown = _video("v-u", artist="Anuel", topics=("tiraera",), performance="unknown")
    weak = _video("v-w", artist="Anuel", topics=("tiraera",), performance="weak")
    picks = catalog.select_catalog_links(
        [unknown, weak], current_video_id="v-now", context_artist="Anuel",
        context_topics=("tiraera",), limit=2, as_of="2026-10-05",
    )
    # Same relevance: performance breaks the tie, unknown ranks last.
    assert [p.video.video_id for p in picks] == ["v-w", "v-u"]


def test_historical_strength_only_counts_when_relevant():
    strong_related = _video("v-s", performance="strong")
    avg_related = _video("v-a", performance="average")
    picks = catalog.select_catalog_links(
        [avg_related, strong_related], current_video_id="v-now",
        context_artist="Anuel", context_topics=("tiraera",),
        limit=2, as_of="2026-10-05",
    )
    assert [p.video.video_id for p in picks] == ["v-s", "v-a"]
    assert "historical_strength:strong" in picks[0].reasons


def test_deterministic_ties():
    a = _video("v-a", published="2026-09-01")
    b = _video("v-b", published="2026-09-01")
    first = catalog.select_catalog_links(
        [b, a], current_video_id="v-now", context_artist="Anuel",
        context_topics=("tiraera",), limit=2, as_of="2026-10-05",
    )
    second = catalog.select_catalog_links(
        [a, b], current_video_id="v-now", context_artist="Anuel",
        context_topics=("tiraera",), limit=2, as_of="2026-10-05",
    )
    assert [p.video.video_id for p in first] == [p.video.video_id for p in second] == ["v-a", "v-b"]


def test_current_video_excluded():
    current = _video("v-now", performance="strong")
    other = _video("v-o")
    picks = catalog.select_catalog_links(
        [current, other], current_video_id="v-now", context_artist="Anuel",
        context_topics=("tiraera",), limit=5, as_of="2026-10-05",
    )
    assert [p.video.video_id for p in picks] == ["v-o"]


def test_invalid_performance_rejected_not_invented():
    with pytest.raises(catalog.CatalogError):
        _video("v-x", performance="viral")


def test_empty_catalog():
    assert catalog.select_catalog_links([], current_video_id="v-now") == ()


def test_limit_respected():
    vids = [_video(f"v-{i}") for i in range(5)]
    picks = catalog.select_catalog_links(
        vids, current_video_id="v-now", context_artist="Anuel",
        context_topics=("tiraera",), limit=2, as_of="2026-10-05",
    )
    assert len(picks) == 2


def test_shared_topic_relevance():
    topical = _video("v-t", artist="Otro", topics=("tiraera", "genero"))
    picks = catalog.select_catalog_links(
        [topical], current_video_id="v-now", context_artist="Anuel",
        context_topics=("tiraera",), limit=1, as_of="2026-10-05",
    )
    assert any(r.startswith("shared_topic:") for r in picks[0].reasons)
