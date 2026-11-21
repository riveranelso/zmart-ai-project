"""ZERO LAG WI-FI META LEAD ADS INGESTION (owned, GoHighLevel bypass).

Receives Meta Instant Form leads via Meta's native Lead Ads webhooks,
fetches the full lead via the Graph API, translates Meta field_data into
the ZeroLag lead schema, dedupes on leadgen_id, and forwards durably to
n8n. OMAR verification happens downstream in n8n (fail-open) -- this
module never blocks lead capture on OMAR.

Wire contract (Meta -> this receiver):
  GET  /meta/webhooks/leadgen  -- webhook verification challenge
  POST /meta/webhooks/leadgen  -- leadgen deliveries (object == "page",
                                   changes[].field == "leadgen")

Security model (mirrors zion_core.meta_webhook -- reused by import):
  - X-Hub-Signature-256 HMAC-SHA256 verification on RAW bytes (mandatory).
  - Tenant is FIXED to business_id "zerolag" in code. Caller-supplied
    business_id/brand claims are never read, never trusted.
  - Secrets resolved ONCE at construction via resolve_secret_ref (env:
    refs). Never logged, never echoed, never committed.
  - Meta's retry contract: after signature verification passes, ALWAYS
    answer 200 (even when downstream fetch/forward is pending) so Meta
    stops retrying; WE own the retry via the durable pending queue.
  - 4xx only for auth/structural failures (bad signature, malformed JSON,
    wrong object/field). 5xx never for Meta's benefit.

Observability: structured JSON records on the zion.meta_leadgen logger.
NEVER logged: secrets, tokens, signatures, raw bodies, lead PII
(names, phones, emails, addresses, answers), raw Meta ids. Only opaque
truncated hashes (_opaque_id) for correlation.

stdlib only. No new dependencies (repo hermetic invariant).
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Reused by import from the proven Los Duros receiver. That module is NOT
# modified; its Los Duros Instagram path is untouched.
from .meta_webhook import (
    MetaWebhookError,
    _log_event,
    handle_verification_request,
    resolve_secret_ref,
    verify_post_signature,
)

logger = logging.getLogger("zion.meta_leadgen")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CALLBACK_PATH = "/meta/webhooks/leadgen"
HEALTH_PATH = "/health"

META_OBJECT_PAGE = "page"
LEADGEN_FIELD = "leadgen"

# Tenant is FIXED here. Never from caller input.
ZEROLAG_BUSINESS_ID = "zerolag"

GRAPH_API_VERSION = "v21.0"
GRAPH_TIMEOUT_SECS = 15

MAX_BODY_BYTES = 5 * 1024 * 1024

# Forward retry schedule (seconds): exponential backoff.
FORWARD_BACKOFF_SECS = (1.0, 2.0, 4.0)
# Graph fetch attempts before marking fetch_pending.
GRAPH_MAX_ATTEMPTS = 3

# Dedupe statuses.
STATUS_RECEIVED = "received"
STATUS_FORWARDED = "forwarded"
STATUS_FETCH_PENDING = "fetch_pending"
STATUS_FORWARD_PENDING = "forward_pending"
_PENDING_STATUSES = (STATUS_FETCH_PENDING, STATUS_FORWARD_PENDING)


def _opaque_id(value: str) -> str:
    """Truncated SHA-256 for safe correlation (no raw ids in logs)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _nonempty_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


# ---------------------------------------------------------------------------
# Leadgen event (fixed tenant)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeadgenEvent:
    """One translated Meta Lead Ads delivery. business_id is FIXED."""

    leadgen_id: str
    page_id: str | None
    form_id: str | None
    ad_id: str | None
    adgroup_id: str | None
    created_time: str | None
    business_id: str = ZEROLAG_BUSINESS_ID


def parse_form_allowlist(raw: str | None) -> frozenset[str] | None:
    """Parse a comma-separated form_id allowlist.

    Returns None (no filtering) when unset or blank -- backward compatible.
    A form is authorized only if its form_id is in the returned set; a
    missing form_id never matches (fail-closed on unidentifiable forms).
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    ids = frozenset(
        part.strip() for part in raw.split(",") if part.strip()
    )
    return ids if ids else None


def translate_leadgen_payload(payload: dict[str, Any]) -> tuple[LeadgenEvent, ...]:
    """Translate a Meta-native Lead Ads webhook payload. Fail closed.

    Accepts ONLY object == "page" and changes[].field == "leadgen".
    Extracts leadgen_id (required), page_id, form_id, ad_id/adgroup_id,
    created_time. Raises MetaWebhookError on wrong object/field or a
    missing leadgen_id. Caller-supplied business_id is never read.
    """
    if not isinstance(payload, dict):
        raise MetaWebhookError("PAYLOAD_OBJECT_REQUIRED")
    if payload.get("object") != META_OBJECT_PAGE:
        raise MetaWebhookError("OBJECT_NOT_PAGE")
    entry = payload.get("entry")
    if not isinstance(entry, list) or not entry:
        raise MetaWebhookError("ENTRY_REQUIRED")

    events: list[LeadgenEvent] = []
    for item in entry:
        if not isinstance(item, dict):
            continue
        page_id = _nonempty_str(item.get("id"))
        changes = item.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            if change.get("field") != LEADGEN_FIELD:
                # Not a leadgen change: not ours. The caller (ingest_post)
                # treats a zero-event translation as safely ignorable.
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            leadgen_id = _nonempty_str(value.get("leadgen_id"))
            if leadgen_id is None:
                raise MetaWebhookError("LEADGEN_ID_REQUIRED")
            events.append(
                LeadgenEvent(
                    leadgen_id=leadgen_id,
                    page_id=page_id,
                    form_id=_nonempty_str(value.get("form_id")),
                    ad_id=_nonempty_str(value.get("ad_id")),
                    adgroup_id=_nonempty_str(value.get("adgroup_id")),
                    created_time=_nonempty_str(value.get("created_time"))
                    or _nonempty_str(value.get("created_time_unix")),
                )
            )
    return tuple(events)


# ---------------------------------------------------------------------------
# Graph API lead fetch (stdlib urllib; no new dependencies)
# ---------------------------------------------------------------------------


def fetch_lead_graph(
    leadgen_id: str,
    *,
    page_token: str,
    api_version: str = GRAPH_API_VERSION,
    timeout: int = GRAPH_TIMEOUT_SECS,
) -> dict[str, Any]:
    """Fetch full lead data for a leadgen_id from the Graph API.

    GET https://graph.facebook.com/{api_version}/{leadgen_id}
        ?fields=field_data,form_id,ad_id,created_time
    with Authorization: Bearer <page_token>. Returns parsed JSON.
    Raises MetaWebhookError on HTTP error / timeout / malformed JSON --
    the caller owns retry.
    """
    if not isinstance(leadgen_id, str) or not leadgen_id.strip():
        raise MetaWebhookError("LEADGEN_ID_REQUIRED")
    if not isinstance(page_token, str) or not page_token:
        raise MetaWebhookError("PAGE_TOKEN_NOT_CONFIGURED")
    url = (
        f"https://graph.facebook.com/{api_version}/{leadgen_id.strip()}"
        "?fields=field_data,form_id,ad_id,created_time"
    )
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {page_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise MetaWebhookError(f"GRAPH_HTTP_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise MetaWebhookError("GRAPH_NETWORK_ERROR") from exc
    except TimeoutError as exc:
        raise MetaWebhookError("GRAPH_TIMEOUT") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MetaWebhookError("GRAPH_MALFORMED_JSON") from exc
    if not isinstance(data, dict):
        raise MetaWebhookError("GRAPH_MALFORMED_JSON")
    return data


# ---------------------------------------------------------------------------
# Meta field_data -> ZeroLag schema translation
# ---------------------------------------------------------------------------

# Meta standard question keys -> ZeroLag schema keys.
_STANDARD_FIELD_MAP = {
    "full_name": "full_name",
    "first_name": "first_name",
    "last_name": "last_name",
    "phone_number": "phone",
    "phone": "phone",
    "email": "email",
    "street_address": "street_address",
    "city": "city",
    "state": "state",
    "province": "state",
    "zip": "zip",
    "zip_code": "zip",
    "postal_code": "zip",
    "country": "country",
}


def _first_value(values: Any) -> str | None:
    """Meta field_data values arrive as a list; take the first string."""
    if isinstance(values, list) and values:
        return _nonempty_str(values[0])
    return _nonempty_str(values)


def translate_lead_fields(
    field_data: list[dict[str, Any]] | Any, *, event: LeadgenEvent
) -> dict[str, Any]:
    """Map Meta field_data name/value pairs to the ZeroLag lead schema.

    Output keys: full_name, first_name, last_name, phone, email, address,
    custom_questions (list of {question, answer}), form_id, leadgen_id,
    page_id, ad_id, created_time, source="meta", business_id="zerolag".
    Fields Meta did not deliver are OMITTED (never null-string, never
    invented). Custom (non-standard) questions land in custom_questions.
    """
    out: dict[str, Any] = {
        "leadgen_id": event.leadgen_id,
        "source": "meta",
        "business_id": event.business_id,
    }
    if event.form_id:
        out["form_id"] = event.form_id
    if event.page_id:
        out["page_id"] = event.page_id
    if event.ad_id:
        out["ad_id"] = event.ad_id
    if event.adgroup_id:
        out["adgroup_id"] = event.adgroup_id
    if event.created_time:
        out["created_time"] = event.created_time

    if not isinstance(field_data, list):
        return out

    address_parts: dict[str, str] = {}
    custom: list[dict[str, str]] = []
    for item in field_data:
        if not isinstance(item, dict):
            continue
        name = _nonempty_str(item.get("name"))
        value = _first_value(item.get("values"))
        if name is None or value is None:
            continue
        key = name.strip().lower()
        mapped = _STANDARD_FIELD_MAP.get(key)
        if mapped is None:
            custom.append({"question": name.strip(), "answer": value})
        elif mapped in ("street_address", "city", "state", "zip", "country"):
            address_parts[mapped] = value
        else:
            out[mapped] = value

    if address_parts:
        ordered = [
            address_parts.get("street_address"),
            address_parts.get("city"),
            address_parts.get("state"),
            address_parts.get("zip"),
            address_parts.get("country"),
        ]
        out["address"] = ", ".join(p for p in ordered if p)
    if custom:
        out["custom_questions"] = custom
    return out


# ---------------------------------------------------------------------------
# Durable dedupe store (SQLite, stdlib)
# ---------------------------------------------------------------------------


class LeadDedupeStore:
    """Durable leadgen_id dedupe. Thread-safe via lock.

    Table: lead_events(leadgen_id TEXT PRIMARY KEY, received_at TEXT,
    status TEXT). A leadgen_id is a duplicate iff a row exists, regardless
    of status -- the pending queue (retry_pending) owns unfinished rows.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS lead_events ("
                "leadgen_id TEXT PRIMARY KEY, "
                "received_at TEXT NOT NULL, "
                "status TEXT NOT NULL)"
            )
            self._conn.commit()

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def is_duplicate(self, leadgen_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM lead_events WHERE leadgen_id = ?",
                (leadgen_id,),
            )
            return cur.fetchone() is not None

    def record(self, leadgen_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO lead_events "
                "(leadgen_id, received_at, status) VALUES (?, ?, ?)",
                (leadgen_id, self._now(), status),
            )
            self._conn.commit()

    def set_status(self, leadgen_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE lead_events SET status = ? WHERE leadgen_id = ?",
                (status, leadgen_id),
            )
            self._conn.commit()

    def pending(self) -> list[str]:
        """leadgen_ids needing retry (fetch_pending / forward_pending)."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT leadgen_id FROM lead_events WHERE status IN (?, ?)",
                (STATUS_FETCH_PENDING, STATUS_FORWARD_PENDING),
            )
            return [row[0] for row in cur.fetchall()]

    def status_of(self, leadgen_id: str) -> str | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT status FROM lead_events WHERE leadgen_id = ?",
                (leadgen_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# n8n forwarder (retry, never logs payload/URL secrets)
# ---------------------------------------------------------------------------


class N8nForwarder:
    """POST normalized leads to n8n with exponential-backoff retry.

    Returns True on 2xx, False after exhausting retries. Never logs the
    payload body, the webhook URL, or any secret material.
    """

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: int = 15,
        max_retries: int = 3,
        backoff_secs: tuple[float, ...] = FORWARD_BACKOFF_SECS,
    ) -> None:
        if not isinstance(webhook_url, str) or not webhook_url.strip():
            raise MetaWebhookError("N8N_URL_REQUIRED")
        self._url = webhook_url.strip()
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff = backoff_secs

    def _post_once(self, payload: dict[str, Any]) -> bool:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return 200 <= resp.status < 300
        except urllib.error.HTTPError as exc:
            # 5xx: retryable. 4xx: the payload is bad; do not retry forever
            # (still counts as an attempt; caller records forward_pending so
            # a human can inspect -- no silent loss).
            if 500 <= exc.code < 600:
                raise MetaWebhookError(f"N8N_HTTP_{exc.code}") from exc
            return False
        except (urllib.error.URLError, TimeoutError) as exc:
            raise MetaWebhookError("N8N_NETWORK_ERROR") from exc

    def post_lead(self, payload: dict[str, Any]) -> bool:
        attempts = 0
        while True:
            attempts += 1
            try:
                if self._post_once(payload):
                    return True
                # 4xx: not retryable; stop.
                return False
            except MetaWebhookError:
                if attempts > self._max_retries:
                    return False
                delay = self._backoff[min(attempts - 1, len(self._backoff) - 1)]
                time.sleep(delay)


# ---------------------------------------------------------------------------
# Ingest report
# ---------------------------------------------------------------------------


@dataclass
class IngestReport:
    status: int
    body: dict[str, Any]
    events: tuple[dict[str, Any], ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# ZeroLag lead receiver
# ---------------------------------------------------------------------------


class ZeroLagLeadReceiver:
    """Fixed-tenant (zerolag) Meta Lead Ads receiver.

    Secrets (verify token, App Secret, Page token, n8n URL) are resolved
    ONCE at construction via resolve_secret_ref -- fail fast if missing.
    Meta's retry contract: after signature verification passes, ALWAYS
    answer 200; unfinished work goes to the durable pending queue and is
    retried by retry_pending() (background thread, every 60s in main).
    """

    def __init__(
        self,
        *,
        verify_token_ref: str,
        app_secret_ref: str,
        page_token_ref: str,
        n8n_url_ref: str,
        store_path: Path,
        expected_page_id: str | None = None,
        allowed_form_ids: frozenset[str] | None = None,
    ) -> None:
        self._verify_token = resolve_secret_ref(verify_token_ref)
        self._app_secret = resolve_secret_ref(app_secret_ref)
        self._page_token = resolve_secret_ref(page_token_ref)
        self._forwarder = N8nForwarder(resolve_secret_ref(n8n_url_ref))
        self._store = LeadDedupeStore(Path(store_path))
        self._expected_page_id = (
            expected_page_id.strip()
            if isinstance(expected_page_id, str) and expected_page_id.strip()
            else None
        )
        # Form allowlist: None = no filtering (backward compatible).
        # When set, events whose form_id is absent from the set (or missing)
        # are safely ignored: no Graph fetch, no n8n forward, no Gmail.
        self._allowed_form_ids = allowed_form_ids
        self._lock = threading.Lock()

    # -- GET ------------------------------------------------------------
    def verify_get(self, query: dict[str, str]) -> tuple[int, str]:
        status, body = handle_verification_request(
            query, expected_verify_token=self._verify_token
        )
        _log_event(
            "verification_request",
            {
                "result": "accepted" if status == 200 else "rejected",
                "reason": "OK" if status == 200 else "VERIFY_FAILED",
            },
        )
        return status, body

    # -- POST -----------------------------------------------------------
    def ingest_post(
        self, raw_body: bytes, signature_header: str | None
    ) -> IngestReport:
        """Ingest one Meta POST delivery.

        Status contract:
          200 -- accepted (processed / duplicate / pending-retry). Meta
                 stops retrying; WE own the retry via the pending queue.
          400 -- malformed JSON, wrong object/field, structural problems.
          401 -- missing or invalid X-Hub-Signature-256.

        Emits structured observability events (also on IngestReport.events)
        with NO secrets, tokens, signatures, bodies, PII, or raw Meta ids --
        only opaque truncated hashes and counts.
        """
        request_id = secrets.token_hex(8)
        events: list[dict[str, Any]] = []

        def emit(event: str, **fields: Any) -> None:
            events.append(
                _log_event(event, {"request_id": request_id, **fields})
            )

        def finish(status: int, body: dict[str, Any]) -> IngestReport:
            emit("webhook_complete", http_status=status)
            return IngestReport(
                status=status, body=body, events=tuple(events)
            )

        emit("webhook_received")
        try:
            verify_post_signature(
                raw_body, signature_header, app_secret=self._app_secret
            )
        except MetaWebhookError as exc:
            emit("signature_rejected", reason=str(exc))
            return finish(401, {"ok": False, "error": str(exc)})
        emit("signature_valid")

        if len(raw_body) > MAX_BODY_BYTES:
            emit("payload_rejected", reason="BODY_TOO_LARGE")
            return finish(400, {"ok": False, "error": "BODY_TOO_LARGE"})
        try:
            payload = json.loads(bytes(raw_body).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            emit("payload_rejected", reason="MALFORMED_JSON")
            return finish(400, {"ok": False, "error": "MALFORMED_JSON"})
        emit("payload_parsed")

        try:
            lead_events = translate_leadgen_payload(payload)
        except MetaWebhookError as exc:
            emit("payload_rejected", reason=str(exc))
            return finish(400, {"ok": False, "error": str(exc)})
        if not lead_events:
            # Signed, well-formed, but no leadgen changes: safely ignorable.
            emit("translation_complete", accepted=0, ignored_no_leadgen=True)
            return finish(200, {"ok": True, "accepted": 0})

        processed = 0
        duplicates = 0
        pending = 0
        ignored_form = 0
        with self._lock:
            for event in lead_events:
                lid_hash = _opaque_id(event.leadgen_id)
                if (
                    self._expected_page_id is not None
                    and event.page_id is not None
                    and event.page_id != self._expected_page_id
                ):
                    emit("tenant_rejected", reason="PAGE_ID_MISMATCH",
                         leadgen_id_hash=lid_hash)
                    continue
                if (
                    self._allowed_form_ids is not None
                    and event.form_id not in self._allowed_form_ids
                ):
                    # Not an authorized form: safely ignore. No Graph fetch,
                    # no dedupe record, no n8n forward, no Gmail. Meta gets
                    # 200 (it will not retry; the lead stays in Meta's
                    # Lead Center if the allowlist is later expanded).
                    ignored_form += 1
                    emit("form_ignored", reason="FORM_NOT_ALLOWED",
                         leadgen_id_hash=lid_hash)
                    continue
                if self._store.is_duplicate(event.leadgen_id):
                    duplicates += 1
                    emit("event_processed", leadgen_id_hash=lid_hash,
                         duplicate=True, result="IGNORED_DUPLICATE")
                    continue
                self._store.record(event.leadgen_id, STATUS_RECEIVED)
                outcome = self._process_one(event, emit)
                if outcome == "forwarded":
                    processed += 1
                else:
                    pending += 1

        return finish(
            200,
            {
                "ok": True,
                "received": len(lead_events),
                "processed": processed,
                "duplicates": duplicates,
                "pending": pending,
                "ignored_form": ignored_form,
            },
        )

    # -- single-lead pipeline -------------------------------------------
    def _process_one(self, event: LeadgenEvent, emit) -> str:
        """Fetch -> translate -> forward one lead. Returns final status."""
        lid_hash = _opaque_id(event.leadgen_id)
        lead_data: dict[str, Any] | None = None
        for attempt in range(GRAPH_MAX_ATTEMPTS):
            try:
                lead_data = fetch_lead_graph(
                    event.leadgen_id, page_token=self._page_token
                )
                break
            except MetaWebhookError as exc:
                emit("graph_fetch_retry", leadgen_id_hash=lid_hash,
                     attempt=attempt + 1, reason=str(exc))
        if lead_data is None:
            # Meta gets 200 (stops retrying); WE retry via pending queue.
            self._store.set_status(event.leadgen_id, STATUS_FETCH_PENDING)
            emit("graph_fetch_pending", leadgen_id_hash=lid_hash)
            return STATUS_FETCH_PENDING

        normalized = translate_lead_fields(
            lead_data.get("field_data"), event=event
        )
        # Enrich with Graph-level attribution when present.
        for key in ("form_id", "ad_id", "created_time"):
            value = _nonempty_str(lead_data.get(key))
            if value and key not in normalized:
                normalized[key] = value

        if self._forwarder.post_lead(normalized):
            self._store.set_status(event.leadgen_id, STATUS_FORWARDED)
            emit("lead_forwarded", leadgen_id_hash=lid_hash)
            return STATUS_FORWARDED
        self._store.set_status(event.leadgen_id, STATUS_FORWARD_PENDING)
        emit("forward_pending", leadgen_id_hash=lid_hash)
        return STATUS_FORWARD_PENDING

    # -- pending retry sweep --------------------------------------------
    def retry_pending(self) -> dict[str, int]:
        """Retry all fetch_pending/forward_pending leads. Returns counts."""
        summary = {"retried": 0, "forwarded": 0, "still_pending": 0}

        def emit(event: str, **fields: Any) -> None:
            _log_event(event, fields)

        with self._lock:
            pending_ids = self._store.pending()
        for leadgen_id in pending_ids:
            summary["retried"] += 1
            # Rebuild a minimal event; stored rows carry no PII, only the id.
            # Page/form/ad attribution is re-fetched from Graph when needed.
            event = LeadgenEvent(
                leadgen_id=leadgen_id,
                page_id=None,
                form_id=None,
                ad_id=None,
                adgroup_id=None,
                created_time=None,
            )
            with self._lock:
                outcome = self._process_one(event, emit)
            if outcome == STATUS_FORWARDED:
                summary["forwarded"] += 1
            else:
                summary["still_pending"] += 1
        if summary["retried"]:
            _log_event("retry_sweep_complete", summary)
        return summary


__all__ = [
    "CALLBACK_PATH",
    "HEALTH_PATH",
    "ZEROLAG_BUSINESS_ID",
    "LeadgenEvent",
    "IngestReport",
    "LeadDedupeStore",
    "N8nForwarder",
    "ZeroLagLeadReceiver",
    "translate_leadgen_payload",
    "translate_lead_fields",
    "fetch_lead_graph",
    "parse_form_allowlist",
]
