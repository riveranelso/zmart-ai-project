"""Tests for zion_core.dedupe (GAP 4: screenshot reply dedupe).

Canonical: LOS_DUROS.md "Screenshots and comments" (owner-approved
2026-10-05). When processing screenshots/comment batches, never draft a new
reply for a comment visibly/already marked as answered. Dedupe at the
normalized identity boundary; explicit states already_replied / eligible /
ambiguous; deterministic; no unsafe fuzzy matching.
"""
import pytest

from zion_core import dedupe


def _item(cid, marked=False, verified=True):
    return dedupe.BatchComment(
        comment_id=cid, marked_answered=marked, identity_verified=verified
    )


def test_answered_id_is_already_replied():
    result = dedupe.assess_dedupe([_item("c1"), _item("c2")], answered_ids={"c1"})
    assert result.state_of("c1") == dedupe.ALREADY_REPLIED
    assert result.state_of("c2") == dedupe.ELIGIBLE


def test_marked_answered_is_already_replied():
    result = dedupe.assess_dedupe([_item("c1", marked=True)], answered_ids=set())
    assert result.state_of("c1") == dedupe.ALREADY_REPLIED


def test_same_text_different_identity_not_deduped():
    # No fuzzy matching: same text with different stable identities are
    # different people's comments and both stay eligible.
    result = dedupe.assess_dedupe([_item("c1"), _item("c2")], answered_ids=set())
    assert result.state_of("c1") == dedupe.ELIGIBLE
    assert result.state_of("c2") == dedupe.ELIGIBLE


def test_duplicate_identity_in_batch_suppressed():
    result = dedupe.assess_dedupe([_item("c1"), _item("c1")], answered_ids=set())
    states = [s for _, s in result.states]
    assert states == [dedupe.ELIGIBLE, dedupe.ALREADY_REPLIED]


def test_unverified_identity_is_ambiguous():
    result = dedupe.assess_dedupe([_item("c1", verified=False)], answered_ids=set())
    assert result.state_of("c1") == dedupe.AMBIGUOUS


def test_blank_identity_is_ambiguous():
    result = dedupe.assess_dedupe([_item("  ")], answered_ids=set())
    assert result.state_of("  ") == dedupe.AMBIGUOUS


def test_deterministic_batch():
    items = [_item("c1"), _item("c2", marked=True), _item("c3", verified=False)]
    first = dedupe.assess_dedupe(items, answered_ids={"c9"})
    second = dedupe.assess_dedupe(items, answered_ids={"c9"})
    assert first.states == second.states


def test_answered_ids_accepts_any_iterable():
    result = dedupe.assess_dedupe([_item("c1")], answered_ids=["c1"])
    assert result.state_of("c1") == dedupe.ALREADY_REPLIED


def test_invalid_items_rejected():
    with pytest.raises(dedupe.DedupeError):
        dedupe.assess_dedupe("not-a-sequence", answered_ids=set())
    with pytest.raises(dedupe.DedupeError):
        dedupe.assess_dedupe([_item("c1")], answered_ids="c1")
