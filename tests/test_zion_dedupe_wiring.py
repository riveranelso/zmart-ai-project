"""Wiring tests: process_batch dedupe inside antiphon.

Canonical: LOS_DUROS.md "Screenshots and comments".
"""
import pytest

from zion_core import antiphon, dedupe


def _payload(cid, text, **over):
    payload = {
        "comment_id": cid, "video_id": "v1", "author": "fan1", "text": text,
    }
    payload.update(over)
    return payload


def test_answered_comment_gets_no_duplicate_draft():
    results = antiphon.process_batch(
        [_payload("c1", "Anuel es el mejor"), _payload("c2", "jajaja que risa")],
        answered_ids={"c1"},
    )
    by_id = {r.comment_id: r for r in results}
    assert by_id["c1"].state == dedupe.ALREADY_REPLIED
    assert by_id["c1"].result is None
    assert by_id["c2"].state == dedupe.ELIGIBLE
    assert by_id["c2"].result is not None
    assert by_id["c2"].result.draft is not None


def test_marked_answered_payload_suppressed():
    results = antiphon.process_batch(
        [_payload("c1", "Anuel es el mejor", marked_answered=True)],
    )
    assert results[0].state == dedupe.ALREADY_REPLIED
    assert results[0].result is None


def test_same_text_different_identity_both_drafted():
    results = antiphon.process_batch(
        [_payload("c1", "Anuel es el mejor"), _payload("c2", "Anuel es el mejor")],
    )
    assert all(r.state == dedupe.ELIGIBLE for r in results)
    assert all(r.result.draft is not None for r in results)


def test_unverified_identity_fails_safe_to_human_review():
    results = antiphon.process_batch(
        [_payload("c1", "Anuel es el mejor", identity_verified=False)],
    )
    assert results[0].state == dedupe.AMBIGUOUS
    assert results[0].result.classification.route == antiphon.HUMAN_REVIEW
    assert results[0].result.classification.subtype == "identity_ambiguous"
    assert results[0].result.draft is None


def test_batch_is_deterministic_and_ordered():
    payloads = [
        _payload("c1", "Anuel es el mejor"),
        _payload("c2", "jajaja que risa", marked_answered=True),
        _payload("c3", "creo que ese tema esta duro"),
    ]
    first = antiphon.process_batch(payloads, answered_ids={"c9"})
    second = antiphon.process_batch(payloads, answered_ids={"c9"})
    assert [r.comment_id for r in first] == ["c1", "c2", "c3"]
    assert [(r.comment_id, r.state) for r in first] == [
        (r.comment_id, r.state) for r in second
    ]
    assert [r.result.draft.text if r.result and r.result.draft else None for r in first] == [
        r.result.draft.text if r.result and r.result.draft else None for r in second
    ]


def test_batch_rejects_non_sequence():
    with pytest.raises(antiphon.AntiphonError):
        antiphon.process_batch("not-a-batch")
