"""DEDUPE: reply dedupe for screenshot / comment-batch processing.

Canonical: zmart360/BIBLIA/LOS_DUROS.md, section "Screenshots and comments"
(owner-approved 2026-10-05).

When processing screenshots or comment batches, the runtime must not draft
a new reply for a comment visibly/already marked as answered.

Design (explicit states, deterministic, no fuzzy matching):

- Identity boundary: the stable platform comment_id. Dedupe NEVER uses
  text similarity: the same text under different identities belongs to
  different people and both stay ELIGIBLE.
- States:
    ELIGIBLE        -- safe to run the normal classify/draft pipeline.
    ALREADY_REPLIED -- the comment_id is in answered_ids, was marked
                       answered in the batch metadata, or already appeared
                       earlier in this batch (duplicate delivery).
    AMBIGUOUS       -- identity missing or not verified: fail safe, no
                       draft; the caller must route to human review.
- answered_ids: the set of comment ids visibly already answered (e.g.
  parsed from the screenshot/batch by the caller). Pure input, no I/O.
- Batch order is preserved; the first occurrence of an identity wins.

Deterministic and pure: no network, no external calls.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

ELIGIBLE = "eligible"
ALREADY_REPLIED = "already_replied"
AMBIGUOUS = "ambiguous"
STATES = (ELIGIBLE, ALREADY_REPLIED, AMBIGUOUS)


class DedupeError(ValueError):
    """Invalid input to dedupe assessment."""


@dataclass(frozen=True)
class BatchComment:
    """One comment in a batch, with screenshot/batch metadata."""

    comment_id: str
    marked_answered: bool = False  # visibly marked as answered in the source
    identity_verified: bool = True  # False when attribution is uncertain


@dataclass(frozen=True)
class DedupeAssessment:
    states: tuple[tuple[str, str], ...] = ()  # (comment_id, state), batch order

    def state_of(self, comment_id: str) -> str | None:
        for cid, state in self.states:
            if cid == comment_id:
                return state
        return None

    def eligible_ids(self) -> tuple[str, ...]:
        return tuple(cid for cid, state in self.states if state == ELIGIBLE)


def assess_dedupe(
    items: Sequence[BatchComment],
    answered_ids: Iterable[str],
) -> DedupeAssessment:
    """Assess a comment batch against already-answered identities.

    Deterministic: same inputs always yield the same states, in batch order.
    """
    if isinstance(items, (str, bytes)) or not isinstance(items, Sequence):
        raise DedupeError("DEDUPE_ITEMS_SEQUENCE_REQUIRED")
    if isinstance(answered_ids, (str, bytes)):
        raise DedupeError("DEDUPE_ANSWERED_IDS_ITERABLE_REQUIRED")
    try:
        answered = {str(a).strip() for a in answered_ids if str(a).strip()}
    except TypeError as exc:
        raise DedupeError(f"DEDUPE_ANSWERED_IDS_INVALID:{exc}") from exc

    seen: set[str] = set()
    states: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, BatchComment):
            raise DedupeError("DEDUPE_ITEM_OBJECT_REQUIRED")
        cid = item.comment_id.strip() if isinstance(item.comment_id, str) else ""
        if not cid or not item.identity_verified:
            states.append((item.comment_id, AMBIGUOUS))
            continue
        if item.marked_answered or cid in answered or cid in seen:
            states.append((cid, ALREADY_REPLIED))
            seen.add(cid)
            continue
        states.append((cid, ELIGIBLE))
        seen.add(cid)
    return DedupeAssessment(states=tuple(states))
