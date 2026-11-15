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
  - Persistence is a single SQLite database file (stdlib sqlite3, WAL
    mode): an ``events`` table gives durable idempotency (one row per
    event fingerprint, PRIMARY KEY), ``approvals`` holds the records,
    ``approval_history`` is the append-only audit trail. Enqueue is one
    atomic transaction (BEGIN IMMEDIATE): the fingerprint PRIMARY KEY is
    the single arbiter, so the same event can never create two approvals,
    even across threads or machine restarts. Any failure rolls back
    completely. Deploy target is a Fly persistent volume
    (e.g. /data/approvals.db); without a volume the file is ephemeral
    like the rest of the machine disk.
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
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .glossolalia import IntegrationConfig, MetaProcessResult

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


# Durable store (SQLite, single file, crash-safe)
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  fingerprint TEXT PRIMARY KEY,
  approval_id TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  business_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL,
  brand_id TEXT NOT NULL,
  integration_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_fingerprint TEXT NOT NULL REFERENCES events(fingerprint),
  comment_id_hash TEXT NOT NULL,
  sender_id_hash TEXT NOT NULL,
  draft_text TEXT NOT NULL,
  processing_route TEXT NOT NULL,
  processing_subtype TEXT NOT NULL,
  processing_reasons TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','APPROVED','EDITED','REJECTED')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  reviewed_at TEXT,
  reviewer TEXT,
  decision TEXT,
  edited_text TEXT
);
CREATE TABLE IF NOT EXISTS approval_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  approval_id TEXT NOT NULL REFERENCES approvals(approval_id),
  at TEXT NOT NULL,
  from_status TEXT NOT NULL,
  to_status TEXT NOT NULL,
  reviewer TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status, created_at);
CREATE INDEX IF NOT EXISTS idx_history_approval ON approval_history(approval_id, id);
"""

_REQUIRED_TABLES = ("events", "approvals", "approval_history")

_APPROVAL_COLUMNS = (
    "approval_id", "business_id", "brand_id", "integration_id",
    "channel", "event_type", "event_fingerprint",
    "comment_id_hash", "sender_id_hash", "draft_text",
    "processing_route", "processing_subtype", "processing_reasons",
    "status", "created_at", "updated_at",
    "reviewed_at", "reviewer", "decision", "edited_text",
)


class ApprovalStore:
    """SQLite-backed approval record store (single file).

    One SQLite database holds three tables: ``events`` (durable
    idempotency: one row per event fingerprint), ``approvals`` (the
    records), and ``approval_history`` (append-only audit trail).

    Atomicity: enqueue is a single transaction (BEGIN IMMEDIATE):
    INSERT OR IGNORE the fingerprint row, then insert the approval +
    initial history, then COMMIT. The PRIMARY KEY on events.fingerprint
    is the single arbiter -- the same fingerprint can never create two
    approvals, even across threads or machine restarts. Any failure
    rolls the whole transaction back: no event without an approval,
    no orphan history rows.

    Crash safety: WAL journal mode; committed transactions survive
    process/machine crashes (the -wal is replayed on open). Corrupt or
    foreign databases fail closed at ensure_ready/open -- never silently
    recreated.

    Concurrency: one connection serialized by a threading lock; SQLite's
    own locking (BEGIN IMMEDIATE + busy_timeout) is the mutual
    exclusion. Single-host design -- a future multi-machine deployment
    needs a real database with a distributed uniqueness boundary.

    Deploy target: the database file lives on a Fly persistent volume
    (e.g. /data/approvals.db). Without a volume the file is ephemeral,
    exactly like the rest of the machine's disk.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    # -- connection -------------------------------------------------
    def _open(self) -> sqlite3.Connection:
        """Open (once) and configure the database. Caller holds the lock."""
        if self._conn is not None:
            return self._conn
        try:
            conn = sqlite3.connect(
                str(self.path), check_same_thread=False, timeout=5.0,
                isolation_level=None,
            )
        except sqlite3.Error as exc:
            raise ApprovalStoreError(f"APPROVAL_DB_OPEN_FAILED:{exc}") from exc
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.Error as exc:
            conn.close()
            raise ApprovalStoreError(
                f"APPROVAL_DB_PRAGMA_FAILED:{exc}"
            ) from exc
        self._conn = conn
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection, *, preexisting: bool) -> None:
        """Create the schema; fail closed on a foreign/corrupt database."""
        if preexisting:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            missing = [t for t in _REQUIRED_TABLES if t not in tables]
            if missing:
                raise ApprovalStoreError(
                    "APPROVAL_DB_NOT_AN_APPROVAL_DATABASE:"
                    f"missing={','.join(missing)}"
                )
        try:
            conn.executescript(_SCHEMA)
        except sqlite3.Error as exc:
            raise ApprovalStoreError(f"APPROVAL_DB_SCHEMA_FAILED:{exc}") from exc

    def ensure_ready(self) -> None:
        """Fail fast at startup: ensure the database is openable/valid.

        Creates parent directories and initializes a new database when
        the file is missing/empty. Fails closed (no silent recreate) when
        the file exists but is not a usable approval database.
        """
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            preexisting = self.path.is_file() and self.path.stat().st_size > 0
            try:
                conn = self._open()
            except ApprovalStoreError:
                raise
            except Exception as exc:  # defensive: never leak driver errors
                raise ApprovalStoreError(
                    f"APPROVAL_DB_UNUSABLE:{type(exc).__name__}"
                ) from exc
            self._ensure_schema(conn, preexisting=preexisting)

    def close(self) -> None:
        """Close the database connection (test/shutdown hygiene)."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # -- row mapping ------------------------------------------------
    @staticmethod
    def _history_for(
        conn: sqlite3.Connection, approval_id: str
    ) -> tuple[ApprovalTransition, ...]:
        rows = conn.execute(
            "SELECT at, from_status, to_status, reviewer, note"
            " FROM approval_history WHERE approval_id=? ORDER BY id",
            (approval_id,),
        ).fetchall()
        return tuple(
            ApprovalTransition(
                at=_require_nonblank(r["at"], "HISTORY_AT"),
                from_status=_require_nonblank(r["from_status"], "HISTORY_FROM"),
                to_status=_require_nonblank(r["to_status"], "HISTORY_TO"),
                reviewer=_require_nonblank(r["reviewer"], "HISTORY_REVIEWER"),
                note=r["note"] if isinstance(r["note"], str) else "",
            )
            for r in rows
        )

    @classmethod
    def _row_to_record(
        cls, conn: sqlite3.Connection, row: sqlite3.Row
    ) -> ApprovalRecord:
        try:
            reasons = json.loads(row["processing_reasons"])
            if not isinstance(reasons, list) or not all(
                isinstance(r, str) for r in reasons
            ):
                raise ApprovalStoreError("INVALID_APPROVAL_REASONS")
            for key in ("reviewed_at", "reviewer", "decision", "edited_text"):
                value = row[key]
                if value is not None and not isinstance(value, str):
                    raise ApprovalStoreError(f"INVALID_APPROVAL_FIELD:{key}")
            status = row["status"]
            if status not in STATUSES:
                raise ApprovalStoreError(f"INVALID_APPROVAL_STATUS:{status}")
            return ApprovalRecord(
                approval_id=_require_nonblank(row["approval_id"], "APPROVAL_ID"),
                business_id=_require_nonblank(row["business_id"], "BUSINESS_ID"),
                brand_id=_require_nonblank(row["brand_id"], "BRAND_ID"),
                integration_id=_require_nonblank(
                    row["integration_id"], "INTEGRATION_ID"
                ),
                channel=_require_nonblank(row["channel"], "CHANNEL"),
                event_type=_require_nonblank(row["event_type"], "EVENT_TYPE"),
                event_fingerprint=_require_nonblank(
                    row["event_fingerprint"], "EVENT_FINGERPRINT"
                ),
                comment_id_hash=_require_nonblank(
                    row["comment_id_hash"], "COMMENT_ID_HASH"
                ),
                sender_id_hash=_require_nonblank(
                    row["sender_id_hash"], "SENDER_ID_HASH"
                ),
                draft_text=_require_nonblank(row["draft_text"], "DRAFT_TEXT"),
                processing_route=_require_nonblank(
                    row["processing_route"], "PROCESSING_ROUTE"
                ),
                processing_subtype=_require_nonblank(
                    row["processing_subtype"], "PROCESSING_SUBTYPE"
                ),
                processing_reasons=tuple(reasons),
                status=status,
                created_at=_require_nonblank(row["created_at"], "CREATED_AT"),
                updated_at=_require_nonblank(row["updated_at"], "UPDATED_AT"),
                reviewed_at=row["reviewed_at"],
                reviewer=row["reviewer"],
                decision=row["decision"],
                edited_text=row["edited_text"],
                history=cls._history_for(conn, row["approval_id"]),
            )
        except ApprovalStoreError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ApprovalStoreError(
                f"INVALID_APPROVAL_ROW:{type(exc).__name__}"
            ) from exc

    def _get_unlocked(
        self, conn: sqlite3.Connection, approval_id: str
    ) -> ApprovalRecord | None:
        row = conn.execute(
            f"SELECT {', '.join(_APPROVAL_COLUMNS)} FROM approvals WHERE approval_id=?",
            (approval_id,),
        ).fetchone()
        return self._row_to_record(conn, row) if row is not None else None

    # -- atomic operations ------------------------------------------
    def _insert_approval_rows(
        self, conn: sqlite3.Connection, record: ApprovalRecord
    ) -> None:
        """Insert the approval + initial history rows (inside a transaction)."""
        conn.execute(
            f"INSERT INTO approvals ({', '.join(_APPROVAL_COLUMNS)})"
            f" VALUES ({', '.join('?' * len(_APPROVAL_COLUMNS))})",
            (
                record.approval_id, record.business_id, record.brand_id,
                record.integration_id, record.channel, record.event_type,
                record.event_fingerprint, record.comment_id_hash,
                record.sender_id_hash, record.draft_text,
                record.processing_route, record.processing_subtype,
                json.dumps(list(record.processing_reasons), ensure_ascii=False),
                record.status, record.created_at, record.updated_at,
                record.reviewed_at, record.reviewer, record.decision,
                record.edited_text,
            ),
        )
        for t in record.history:
            conn.execute(
                "INSERT INTO approval_history"
                " (approval_id, at, from_status, to_status, reviewer, note)"
                " VALUES (?,?,?,?,?,?)",
                (
                    record.approval_id, t.at, t.from_status,
                    t.to_status, t.reviewer, t.note,
                ),
            )

    def put_new(self, record: ApprovalRecord) -> tuple[ApprovalRecord, bool]:
        """Atomically insert event + approval; idempotent by fingerprint.

        One transaction (BEGIN IMMEDIATE): establish fingerprint
        uniqueness first. When the fingerprint already exists, the stored
        approval is returned unchanged with created=False -- a retried
        delivery (even after a machine restart) can never create a second
        approval. Any failure rolls the transaction back completely:
        never an event row without its approval, never orphan history.
        """
        if not isinstance(record, ApprovalRecord):
            raise ApprovalError("APPROVAL_RECORD_REQUIRED")
        with self._lock:
            conn = self._open()
            self._ensure_schema(conn, preexisting=False)
            conn.execute("BEGIN IMMEDIATE")
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO events"
                    " (fingerprint, approval_id, first_seen_at, business_id)"
                    " VALUES (?,?,?,?)",
                    (
                        record.event_fingerprint,
                        record.approval_id,
                        record.created_at or _utcnow(),
                        record.business_id,
                    ),
                )
                if cur.rowcount == 0:
                    # Fingerprint already known: reuse the stored approval.
                    event_row = conn.execute(
                        "SELECT approval_id FROM events WHERE fingerprint=?",
                        (record.event_fingerprint,),
                    ).fetchone()
                    stored = (
                        self._get_unlocked(conn, event_row["approval_id"])
                        if event_row is not None
                        else None
                    )
                    conn.commit()
                    if stored is None:
                        # Defensive: event row without approval must never
                        # happen (single transaction); fail closed loudly.
                        raise ApprovalStoreError(
                            "APPROVAL_EVENT_WITHOUT_APPROVAL"
                        )
                    return stored, False
                self._insert_approval_rows(conn, record)
                conn.commit()
                return record, True
            except Exception:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
                raise

    def get(self, approval_id: str) -> ApprovalRecord | None:
        approval_id = _require_nonblank(approval_id, "APPROVAL_ID")
        with self._lock:
            conn = self._open()
            self._ensure_schema(conn, preexisting=False)
            return self._get_unlocked(conn, approval_id)

    def list_by_status(self, status: str) -> tuple[ApprovalRecord, ...]:
        if status not in STATUSES:
            raise ApprovalError(f"UNKNOWN_STATUS:{status}")
        with self._lock:
            conn = self._open()
            self._ensure_schema(conn, preexisting=False)
            rows = conn.execute(
                f"SELECT {', '.join(_APPROVAL_COLUMNS)} FROM approvals"
                " WHERE status=? ORDER BY created_at, approval_id",
                (status,),
            ).fetchall()
            return tuple(self._row_to_record(conn, row) for row in rows)

    def transition(
        self,
        approval_id: str,
        to_status: str,
        *,
        reviewer: str,
        edited_text: str | None = None,
        note: str = "",
    ) -> ApprovalRecord:
        """Move a PENDING record to a terminal state. Atomic; auditable."""
        approval_id = _require_nonblank(approval_id, "APPROVAL_ID")
        reviewer = _require_nonblank(reviewer, "REVIEWER")
        if to_status not in TERMINAL_STATUSES:
            raise ApprovalError(f"INVALID_TARGET_STATUS:{to_status}")
        if to_status == EDITED:
            edited_text = _require_nonblank(edited_text, "EDITED_TEXT")
        if not isinstance(note, str):
            raise ApprovalError("NOTE_MUST_BE_STRING")
        with self._lock:
            conn = self._open()
            self._ensure_schema(conn, preexisting=False)
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT status FROM approvals WHERE approval_id=?",
                    (approval_id,),
                ).fetchone()
                if row is None:
                    raise ApprovalError(f"APPROVAL_NOT_FOUND:{approval_id}")
                from_status = row["status"]
                allowed = _VALID_TRANSITIONS.get(from_status, ())
                if to_status not in allowed:
                    raise ApprovalError(
                        f"INVALID_TRANSITION:{from_status}->{to_status}"
                    )
                now = _utcnow()
                conn.execute(
                    "UPDATE approvals SET status=?, updated_at=?,"
                    " reviewed_at=?, reviewer=?, decision=?, edited_text=?"
                    " WHERE approval_id=?",
                    (
                        to_status, now, now, reviewer, to_status,
                        edited_text if to_status == EDITED else None,
                        approval_id,
                    ),
                )
                conn.execute(
                    "INSERT INTO approval_history"
                    " (approval_id, at, from_status, to_status, reviewer, note)"
                    " VALUES (?,?,?,?,?,?)",
                    (approval_id, now, from_status, to_status, reviewer, note),
                )
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
                raise
            return self._get_unlocked(conn, approval_id)

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
