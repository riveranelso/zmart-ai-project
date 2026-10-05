"""APPROVAL QUEUE: durable human approval gate for Los Duros reply drafts.

Pipeline position (this increment ends at approval state management):
  webhook -> GLOSSOLALIA -> ANTIPHON draft -> APPROVAL QUEUE (this module)
      -> human APPROVE / EDIT / REJECT
  APPROVED does NOT mean published.

Safety invariant:
  Approval operations mutate internal state only. This module contains no
  publication transport, builds no MetaActionIntent, calls no Meta endpoint,
  and never flips attempt_action. Publication is a later, separately
  authorized increment; there is deliberately no code path from here to it.

Design (reuse, never duplicate):
  - Tenant identity comes from the resolved IntegrationConfig (fixed in
    trusted configuration), never from the inbound payload.
  - Event identity reuses glossolalia.meta_event_fingerprint; the
    approval_id is derived deterministically from it, so a retried Meta
    delivery can never create a second pending record.
  - Drafts reuse antiphon.ReplyDraft (ROUTINE text events only).
    MAIN_BRAIN / HUMAN_REVIEW produce no draft and therefore no approval
    record; their route is preserved explicitly on every record that exists
    and is never silently converted to ROUTINE.
  - Persistence reuses persistence.LocalOperationLock and the atomic
    temp-file + fsync + replace pattern from PersistentCorrectionMemory.
    JSON (not JSONL) because approval records mutate (status transitions);
    append-only would need a compaction protocol. Human-inspectable,
    stdlib-only, no external database.
  - Observability follows the meta_webhook JSON INFO contract: structured
    events on logger "zion.approval_queue". Never logs secrets, tokens,
    signatures, raw bodies, comment/message text, usernames, names, or raw
    Meta ids. Source identifiers are truncated SHA-256 hashes only; the
    inbound comment text itself is NOT persisted or logged (the draft text
    is ZION-generated content and is safe to persist).

State machine:
  PENDING -> APPROVED | EDITED | REJECTED
  APPROVED, EDITED, REJECTED are terminal (no outgoing transitions).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .glossolalia import IntegrationConfig, MetaProcessResult
from .persistence import LocalOperationLock

logger = logging.getLogger("zion.approval_queue")

PENDING = "PENDING"
APPROVED = "APPROVED"
EDITED = "EDITED"
REJECTED = "REJECTED"
STATUSES = (PENDING, APPROVED, EDITED, REJECTED)
TERMINAL_STATUSES = (APPROVED, EDITED, REJECTED)

# approval_id prefix + deterministic derivation (see _approval_id).
APPROVAL_ID_PREFIX = "appr_"

# PENDING may move to any terminal state; terminal states have no exits.
_VALID_TRANSITIONS: dict[str, tuple[str, ...]] = {
    PENDING: (APPROVED, EDITED, REJECTED),
}


class ApprovalError(ValueError):
    """Rejected approval record, transition, or store misuse."""


class ApprovalStoreError(ValueError):
    """Persisted approval state cannot be safely decoded."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _opaque_id(value: str) -> str:
    """Truncated SHA-256 for safe correlation (mirrors meta_webhook)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _log_event(event: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Emit one structured observability record (JSON, INFO level).

    Contract: fields must never contain secrets, tokens, signatures,
    raw bodies, comment/message text, usernames, names, or raw Meta ids.
    """
    record = {"event": event, **fields}
    logger.info(json.dumps(record, sort_keys=True))
    return record


def _approval_id(event_fingerprint: str) -> str:
    if not isinstance(event_fingerprint, str) or not event_fingerprint.strip():
        raise ApprovalError("EVENT_FINGERPRINT_REQUIRED")
    return APPROVAL_ID_PREFIX + event_fingerprint.strip()[:16]


def approval_id_for_fingerprint(event_fingerprint: str) -> str:
    """Deterministic approval id for an event fingerprint (public helper)."""
    return _approval_id(event_fingerprint)


def _require_nonblank(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApprovalError(f"{field_name}_REQUIRED")
    return value.strip()


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApprovalTransition:
    """One auditable state change on an approval record."""

    at: str  # ISO-8601 UTC
    from_status: str
    to_status: str
    reviewer: str
    note: str = ""


@dataclass(frozen=True)
class ApprovalRecord:
    """Durable approval record for one generated Los Duros draft.

    Tenant fields (business_id/brand_id/integration_id) are fixed from the
    resolved integration, never from the inbound payload. Source identifiers
    are opaque hashes; the inbound comment text is intentionally NOT
    persisted. draft_text is ZION-generated content.
    """

    approval_id: str
    business_id: str
    brand_id: str
    integration_id: str
    channel: str
    event_type: str
    event_fingerprint: str
    comment_id_hash: str
    sender_id_hash: str
    draft_text: str
    processing_route: str
    processing_subtype: str
    processing_reasons: tuple[str, ...] = ()
    status: str = PENDING
    created_at: str = ""
    updated_at: str = ""
    reviewed_at: str | None = None
    reviewer: str | None = None
    decision: str | None = None
    edited_text: str | None = None
    history: tuple[ApprovalTransition, ...] = field(default_factory=tuple)


def _record_to_dict(record: ApprovalRecord) -> dict[str, Any]:
    data = asdict(record)
    data["processing_reasons"] = list(data["processing_reasons"])
    data["history"] = [asdict(t) for t in record.history]
    return data


def _record_from_dict(data: Any) -> ApprovalRecord:
    if not isinstance(data, dict):
        raise ApprovalStoreError("INVALID_APPROVAL_RECORD")
    try:
        history = tuple(
            ApprovalTransition(
                at=_require_nonblank(h.get("at"), "HISTORY_AT"),
                from_status=_require_nonblank(h.get("from_status"), "HISTORY_FROM"),
                to_status=_require_nonblank(h.get("to_status"), "HISTORY_TO"),
                reviewer=_require_nonblank(h.get("reviewer"), "HISTORY_REVIEWER"),
                note=h.get("note") if isinstance(h.get("note"), str) else "",
            )
            for h in data.get("history", [])
        )
        reasons = data.get("processing_reasons", [])
        if not isinstance(reasons, list) or not all(
            isinstance(r, str) for r in reasons
        ):
            raise ApprovalStoreError("INVALID_APPROVAL_REASONS")
        record = ApprovalRecord(
            approval_id=_require_nonblank(data.get("approval_id"), "APPROVAL_ID"),
            business_id=_require_nonblank(data.get("business_id"), "BUSINESS_ID"),
            brand_id=_require_nonblank(data.get("brand_id"), "BRAND_ID"),
            integration_id=_require_nonblank(
                data.get("integration_id"), "INTEGRATION_ID"
            ),
            channel=_require_nonblank(data.get("channel"), "CHANNEL"),
            event_type=_require_nonblank(data.get("event_type"), "EVENT_TYPE"),
            event_fingerprint=_require_nonblank(
                data.get("event_fingerprint"), "EVENT_FINGERPRINT"
            ),
            comment_id_hash=_require_nonblank(
                data.get("comment_id_hash"), "COMMENT_ID_HASH"
            ),
            sender_id_hash=_require_nonblank(
                data.get("sender_id_hash"), "SENDER_ID_HASH"
            ),
            draft_text=_require_nonblank(data.get("draft_text"), "DRAFT_TEXT"),
            processing_route=_require_nonblank(
                data.get("processing_route"), "PROCESSING_ROUTE"
            ),
            processing_subtype=_require_nonblank(
                data.get("processing_subtype"), "PROCESSING_SUBTYPE"
            ),
            processing_reasons=tuple(reasons),
            history=history,
        )
    except ApprovalError as exc:
        raise ApprovalStoreError(f"INVALID_APPROVAL_RECORD:{exc}") from exc
    status = data.get("status", PENDING)
    if status not in STATUSES:
        raise ApprovalStoreError(f"INVALID_APPROVAL_STATUS:{status}")
    created_at = data.get("created_at") or ""
    updated_at = data.get("updated_at") or ""
    if not isinstance(created_at, str) or not isinstance(updated_at, str):
        raise ApprovalStoreError("INVALID_APPROVAL_TIMESTAMPS")
    for key in ("reviewed_at", "reviewer", "decision", "edited_text"):
        value = data.get(key)
        if value is not None and not isinstance(value, str):
            raise ApprovalStoreError(f"INVALID_APPROVAL_FIELD:{key}")
    return replace(
        record,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
        reviewed_at=data.get("reviewed_at"),
        reviewer=data.get("reviewer"),
        decision=data.get("decision"),
        edited_text=data.get("edited_text"),
    )


# ---------------------------------------------------------------------------
# Durable store (JSON file, atomic replace, crash-safe local lock)
# ---------------------------------------------------------------------------


class ApprovalStore:
    """File-backed approval record store.

    One JSON object keyed by approval_id, written atomically
    (temp file + fsync + os.replace + directory fsync) under
    LocalOperationLock, mirroring PersistentCorrectionMemory. Single-host
    atomicity only -- not a distributed exactly-once guarantee; a future
    multi-machine deployment needs a real database with an atomic
    uniqueness boundary.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._locks = LocalOperationLock(
            self.path.parent / (self.path.name + ".locks")
        )

    def _load_unlocked(self) -> dict[str, dict[str, Any]]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApprovalStoreError(f"UNREADABLE_APPROVAL_STORE:{exc}") from exc
        if not isinstance(raw, dict):
            raise ApprovalStoreError("INVALID_APPROVAL_STORE")
        for key, value in raw.items():
            if not isinstance(key, str) or not key.startswith(APPROVAL_ID_PREFIX):
                raise ApprovalStoreError("INVALID_APPROVAL_STORE_KEY")
            if not isinstance(value, dict):
                raise ApprovalStoreError("INVALID_APPROVAL_STORE_VALUE")
        return raw

    def _save_unlocked(self, data: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True, ensure_ascii=False))
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(self.path)
        try:
            dir_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            # The atomic replacement is already logically committed.
            pass

    def ensure_ready(self) -> None:
        """Fail fast at startup: ensure the store is readable/writable.

        Creates parent directories and an empty store when missing;
        validates existing content. Lets a misconfigured path surface at
        construction time instead of on the first webhook delivery.
        """
        with self._locks.hold("APPROVAL", "APPROVAL_ENSURE_READY", str(self.path)):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                self._save_unlocked({})
            else:
                self._load_unlocked()

    def put_new(self, record: ApprovalRecord) -> tuple[ApprovalRecord, bool]:
        """Insert record; return (record, created). Idempotent by approval_id.

        When the approval_id already exists the stored record is returned
        unchanged and created=False -- a retried Meta delivery can never
        create a second pending record.
        """
        if not isinstance(record, ApprovalRecord):
            raise ApprovalError("APPROVAL_RECORD_REQUIRED")
        with self._locks.hold(
            record.business_id, "APPROVAL_PUT", record.approval_id
        ):
            data = self._load_unlocked()
            existing = data.get(record.approval_id)
            if existing is not None:
                return _record_from_dict(existing), False
            data[record.approval_id] = _record_to_dict(record)
            self._save_unlocked(data)
            return record, True

    def get(self, approval_id: str) -> ApprovalRecord | None:
        approval_id = _require_nonblank(approval_id, "APPROVAL_ID")
        with self._locks.hold("APPROVAL", "APPROVAL_GET", approval_id):
            data = self._load_unlocked()
        raw = data.get(approval_id)
        return _record_from_dict(raw) if raw is not None else None

    def list_by_status(self, status: str) -> tuple[ApprovalRecord, ...]:
        if status not in STATUSES:
            raise ApprovalError(f"UNKNOWN_STATUS:{status}")
        with self._locks.hold("APPROVAL", "APPROVAL_LIST", status):
            data = self._load_unlocked()
        records = [
            _record_from_dict(raw)
            for raw in data.values()
            if isinstance(raw, dict) and raw.get("status", PENDING) == status
        ]
        records.sort(key=lambda r: (r.created_at, r.approval_id))
        return tuple(records)

    def transition(
        self,
        approval_id: str,
        to_status: str,
        *,
        reviewer: str,
        edited_text: str | None = None,
        note: str = "",
    ) -> ApprovalRecord:
        """Move a PENDING record to a terminal state. Auditable; fail closed."""
        approval_id = _require_nonblank(approval_id, "APPROVAL_ID")
        reviewer = _require_nonblank(reviewer, "REVIEWER")
        if to_status not in TERMINAL_STATUSES:
            raise ApprovalError(f"INVALID_TARGET_STATUS:{to_status}")
        if to_status == EDITED:
            edited_text = _require_nonblank(edited_text, "EDITED_TEXT")
        if not isinstance(note, str):
            raise ApprovalError("NOTE_MUST_BE_STRING")
        with self._locks.hold("APPROVAL", "APPROVAL_TRANSITION", approval_id):
            data = self._load_unlocked()
            raw = data.get(approval_id)
            if raw is None:
                raise ApprovalError(f"APPROVAL_NOT_FOUND:{approval_id}")
            record = _record_from_dict(raw)
            allowed = _VALID_TRANSITIONS.get(record.status, ())
            if to_status not in allowed:
                raise ApprovalError(
                    f"INVALID_TRANSITION:{record.status}->{to_status}"
                )
            now = _utcnow()
            transition = ApprovalTransition(
                at=now,
                from_status=record.status,
                to_status=to_status,
                reviewer=reviewer,
                note=note,
            )
            updated = replace(
                record,
                status=to_status,
                updated_at=now,
                reviewed_at=now,
                reviewer=reviewer,
                decision=to_status,
                edited_text=edited_text if to_status == EDITED else None,
                history=record.history + (transition,),
            )
            data[approval_id] = _record_to_dict(updated)
            self._save_unlocked(data)
            return updated


# ---------------------------------------------------------------------------
# Queue service (domain operations over the store)
# ---------------------------------------------------------------------------


class ApprovalQueue:
    """Human approval queue for generated Los Duros drafts.

    enqueue_from_result() is the only entry point from the webhook path: it
    accepts a MetaProcessResult and creates (or reuses) exactly one PENDING
    record per event fingerprint, and only when a draft exists (ROUTINE).
    Approval operations mutate internal state only -- they never publish.
    """

    def __init__(self, store: ApprovalStore) -> None:
        if not isinstance(store, ApprovalStore):
            raise ApprovalError("APPROVAL_STORE_REQUIRED")
        self._store = store

    @property
    def store(self) -> ApprovalStore:
        return self._store

    def enqueue_from_result(
        self,
        result: MetaProcessResult,
        integration: IntegrationConfig,
    ) -> tuple[ApprovalRecord, bool] | None:
        """Create (or reuse) the PENDING record for a drafted result.

        Returns None when there is no draft (MAIN_BRAIN / HUMAN_REVIEW /
        duplicates): no approval record is appropriate, and the route is
        never converted to ROUTINE. Otherwise returns (record, created).
        """
        if result.draft is None:
            return None
        if not isinstance(integration, IntegrationConfig):
            raise ApprovalError("INTEGRATION_REQUIRED")
        now = _utcnow()
        record = ApprovalRecord(
            approval_id=_approval_id(result.fingerprint),
            business_id=integration.business_id,
            brand_id=integration.brand_id,
            integration_id=integration.integration_id,
            channel=result.event.channel,
            event_type=result.event.event_type,
            event_fingerprint=result.fingerprint,
            comment_id_hash=_opaque_id(result.event.message_id),
            sender_id_hash=_opaque_id(result.event.sender_id),
            draft_text=result.draft.text,
            processing_route=result.decision.route,
            processing_subtype=result.decision.subtype,
            processing_reasons=tuple(result.decision.reasons),
            status=PENDING,
            created_at=now,
            updated_at=now,
            history=(
                ApprovalTransition(
                    at=now,
                    from_status="NONE",
                    to_status=PENDING,
                    reviewer="system",
                    note="draft_enqueued",
                ),
            ),
        )
        stored, created = self._store.put_new(record)
        _log_event(
            "approval_created" if created else "approval_reused",
            {
                "approval_id": stored.approval_id,
                "business_id": stored.business_id,
                "integration_id": stored.integration_id,
                "channel": stored.channel,
                "event_type": stored.event_type,
                "processing_route": stored.processing_route,
                "comment_id_hash": stored.comment_id_hash,
                "status": stored.status,
            },
        )
        return stored, created

    def list_pending(self) -> tuple[ApprovalRecord, ...]:
        """Oldest first (FIFO for the human reviewer)."""
        return self._store.list_by_status(PENDING)

    def inspect(self, approval_id: str) -> ApprovalRecord:
        record = self._store.get(approval_id)
        if record is None:
            raise ApprovalError(f"APPROVAL_NOT_FOUND:{approval_id}")
        return record

    def approve(self, approval_id: str, *, reviewer: str) -> ApprovalRecord:
        """Mark PENDING -> APPROVED. Internal state only; never publishes."""
        record = self._store.transition(
            approval_id, APPROVED, reviewer=reviewer, note="approved"
        )
        _log_event(
            "approval_approved",
            {"approval_id": record.approval_id, "reviewer": reviewer},
        )
        return record

    def edit_and_approve(
        self, approval_id: str, *, reviewer: str, edited_text: str
    ) -> ApprovalRecord:
        """Mark PENDING -> EDITED with the reviewer's edited reply text."""
        record = self._store.transition(
            approval_id,
            EDITED,
            reviewer=reviewer,
            edited_text=edited_text,
            note="edited_and_approved",
        )
        _log_event(
            "approval_edited",
            {"approval_id": record.approval_id, "reviewer": reviewer},
        )
        return record

    def reject(
        self, approval_id: str, *, reviewer: str, reason: str = ""
    ) -> ApprovalRecord:
        """Mark PENDING -> REJECTED. The draft is discarded, nothing sends."""
        record = self._store.transition(
            approval_id, REJECTED, reviewer=reviewer, note=reason
        )
        _log_event(
            "approval_rejected",
            {"approval_id": record.approval_id, "reviewer": reviewer},
        )
        return record


__all__ = [
    "PENDING",
    "APPROVED",
    "EDITED",
    "REJECTED",
    "STATUSES",
    "TERMINAL_STATUSES",
    "APPROVAL_ID_PREFIX",
    "ApprovalError",
    "ApprovalStoreError",
    "ApprovalTransition",
    "ApprovalRecord",
    "ApprovalStore",
    "ApprovalQueue",
    "approval_id_for_fingerprint",
]
