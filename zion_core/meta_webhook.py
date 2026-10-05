"""META WEBHOOK RECEIVER: Meta-native HTTP ingress for Meta webhook subscriptions.

Canonical naming record (per zmart360/BIBLIA/GLOBAL.md naming law):
  1. Technical function: answer Meta's GET webhook-verification challenge
     and ingest POSTed Instagram webhook deliveries (comments /
     live_comments) for one fixed integration, then translate them into
     GLOSSOLALIA canonical events for the ZION pipeline.
  2. Tradition searched: Christian (New Testament).
  3. Source: Greek "meta" -- "with, among, after": the module stands *with*
     Meta's platform at the boundary wire ("with"), *among* the tenant
     integrations to pick exactly one ("among"), and ZION acts *after* it
     ("after"). Respectful functional metaphor; no claim of absolute truth.
  4. Correspondence: Meta's native webhook tongue in, one fixed tenant's
     canonical events out.
  5. Respectful functional metaphor; no claim of absolute truth.

Canonical principle:
  Meta decides the wire format.
  This receiver decides authenticity (signature), identity (integration),
  and idempotency (dedupe).
  GLOSSOLALIA decides normalization, tenant binding, routing, drafting.
  A human decides publishing. Nothing here publishes.

Architecture:
  META GET  -> handle_verification_request (hub.mode / hub.verify_token /
               hub.challenge) -> 200 challenge | 403 fail closed
  META POST -> verify_post_signature (X-Hub-Signature-256, HMAC-SHA256 over
               RAW body with the App Secret) -> translate_instagram_payload
               (object/entry/changes -> canonical raw events) ->
               glossolalia.resolve_integration (fixed integration; caller
               claims never trusted) -> glossolalia.process_meta_event
               (attempt_action=False: drafts only, NO transport intents) ->
               200 summary.

Design notes:
  - Pure handler functions (handle_verification_request, verify_post_signature,
    translate_instagram_payload, MetaWebhookReceiver.ingest_post) are
    framework-agnostic: they take query dicts / raw bytes / headers and
    return (status, body). The thin stdlib http.server adapter at the bottom
    (serve()) exists only to mount them for real traffic.
  - Tenant is FIXED by the integration configuration built at startup.
    Event identity is matched on (channel, instagram_account_id) only.
    Any caller-supplied business_id/brand_id is never passed to resolution;
    a mismatched entry.id fails closed (INTEGRATION_NOT_FOUND).
  - Secrets come from env: references only (glossolalia convention), resolved
    once at receiver construction via resolve_secret_ref. Raw secret values
    are never logged, never echoed in responses, and never committed.
  - Dedupe reuses glossolalia.meta_event_fingerprint + the seen-set pattern
    of process_meta_event (stable Meta comment identifiers; no fuzzy
    matching). The seen set is in-memory per receiver process: it protects
    against Meta's retry deliveries within one running process. It is NOT a
    distributed exactly-once guarantee.
  - Receiving a comment MUST NOT publish a response: ingest_post calls
    process_meta_event with attempt_action=False, so no MetaActionIntent is
    ever built. Drafts end at the human approval boundary.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from .glossolalia import (
    GlossolaliaError,
    IntegrationConfig,
    MetaNormalizedEvent,
    MetaProcessResult,
    process_meta_event,
    resolve_integration,
    validate_integration_config,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CALLBACK_PATH = "/meta/webhooks/instagram"
META_OBJECT_INSTAGRAM = "instagram"

# Meta webhook subscription fields accepted by this increment.
# (DM/message events are explicitly NOT part of this increment.)
ACCEPTED_FIELDS = ("comments", "live_comments")

# Cap on POST body size (Meta batches at most 1000 updates; real comment
# payloads are small). Oversized bodies are rejected before parsing.
MAX_BODY_BYTES = 5 * 1024 * 1024

_SIGNATURE_RE = re.compile(r"^sha256=([0-9a-fA-F]{64})$")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Los Duros fixed integration identity (trusted configuration).
LOS_DUROS_BUSINESS_ID = "los-duros"
LOS_DUROS_BRAND_ID = "los-duros"
LOS_DUROS_IG_INTEGRATION_ID = "ig-losduros-webhook-1"
META_APP_SECRET_REF = "env:META_APP_SECRET"
LOS_DUROS_IG_VERIFY_TOKEN_REF = "env:LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN"
LOS_DUROS_IG_ACCOUNT_ID_ENV = "LOS_DUROS_IG_ACCOUNT_ID"


class MetaWebhookError(ValueError):
    """Rejected webhook request, payload, config, or receiver misuse."""


# ---------------------------------------------------------------------------
# Secret resolution (env: references only -- never log values)
# ---------------------------------------------------------------------------


def resolve_secret_ref(ref: str | None) -> str:
    """Resolve a secret reference to its value. Fail closed.

    Only the ``env:`` scheme is supported: the value is read from the named
    environment variable at receiver construction time. Any other scheme
    fails closed (no vault provider exists in this runtime). The returned
    value must never be logged, echoed, or committed.
    """
    if not isinstance(ref, str) or not ref.strip():
        raise MetaWebhookError("SECRET_REF_REQUIRED")
    ref = ref.strip()
    if not ref.startswith("env:"):
        raise MetaWebhookError("SECRET_REF_SCHEME_UNSUPPORTED")
    name = ref[4:].strip()
    if not _ENV_NAME_RE.fullmatch(name):
        raise MetaWebhookError("SECRET_ENV_NAME_INVALID")
    value = os.environ.get(name)
    if not value:
        raise MetaWebhookError("SECRET_ENV_UNSET")
    return value


# ---------------------------------------------------------------------------
# Los Duros fixed integration config
# ---------------------------------------------------------------------------


def build_los_duros_instagram_integration(
    *, instagram_account_id: str
) -> IntegrationConfig:
    """Build the trusted, fixed integration config for Los Duros Instagram.

    The tenant (business_id/brand_id = los-duros) is fixed HERE, in trusted
    configuration -- never from caller input. The instagram_account_id is a
    runtime identifier (the @losdurosconlosduros professional account id),
    required explicitly so a missing value fails closed instead of matching
    nothing silently.
    """
    if not isinstance(instagram_account_id, str) or not instagram_account_id.strip():
        raise MetaWebhookError("INSTAGRAM_ACCOUNT_ID_REQUIRED")
    return validate_integration_config(
        {
            "integration_id": LOS_DUROS_IG_INTEGRATION_ID,
            "business_id": LOS_DUROS_BUSINESS_ID,
            "brand_id": LOS_DUROS_BRAND_ID,
            "provider": "meta",
            "channel": "instagram",
            "instagram_account_id": instagram_account_id.strip(),
            "credential_ref": META_APP_SECRET_REF,
            "webhook_verify_ref": LOS_DUROS_IG_VERIFY_TOKEN_REF,
            # Narrowest scope: comment events only in this increment.
            "allowed_event_types": ["comment"],
            "allowed_action_types": [],
            "enabled": True,
            "read_enabled": True,
            "write_enabled": False,
        }
    )


# ---------------------------------------------------------------------------
# GET verification
# ---------------------------------------------------------------------------


def handle_verification_request(
    query: dict[str, str], *, expected_verify_token: str
) -> tuple[int, str]:
    """Pure Meta GET verification handler.

    query: parsed query params (first value wins for repeated keys).
    Returns (status, body). On success the body is hub.challenge verbatim.
    Fail closed: any mismatch -> 403 with a generic body that never echoes
    the token or the challenge.
    """
    if not isinstance(expected_verify_token, str) or not expected_verify_token:
        raise MetaWebhookError("VERIFY_TOKEN_NOT_CONFIGURED")
    mode = query.get("hub.mode")
    token = query.get("hub.verify_token")
    challenge = query.get("hub.challenge")
    if mode != "subscribe":
        return 403, "verification failed"
    if not isinstance(challenge, str) or not challenge:
        return 403, "verification failed"
    if not isinstance(token, str) or not token:
        return 403, "verification failed"
    if not hmac.compare_digest(token, expected_verify_token):
        return 403, "verification failed"
    return 200, challenge


# ---------------------------------------------------------------------------
# POST signature verification (official Meta scheme)
# ---------------------------------------------------------------------------


def verify_post_signature(
    raw_body: bytes, signature_header: str | None, *, app_secret: str
) -> None:
    """Verify X-Hub-Signature-256. Fail closed.

    Official scheme (developers.facebook.com/docs/graph-api/webhooks):
    HMAC-SHA256 over the RAW request bytes with the App Secret, compared
    against the hex digest after ``sha256=`` using a timing-safe compare.
    The raw bytes are signed -- never a re-serialized JSON form (key order
    / unicode escaping would break the digest).
    """
    if not isinstance(app_secret, str) or not app_secret:
        raise MetaWebhookError("APP_SECRET_NOT_CONFIGURED")
    if not isinstance(raw_body, (bytes, bytearray)):
        raise MetaWebhookError("BODY_BYTES_REQUIRED")
    if not isinstance(signature_header, str) or not signature_header.strip():
        raise MetaWebhookError("SIGNATURE_MISSING")
    match = _SIGNATURE_RE.fullmatch(signature_header.strip())
    if not match:
        raise MetaWebhookError("SIGNATURE_MALFORMED")
    expected = hmac.new(
        app_secret.encode("utf-8"), bytes(raw_body), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(match.group(1).lower(), expected):
        raise MetaWebhookError("SIGNATURE_INVALID")


# ---------------------------------------------------------------------------
# Meta-native payload translation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TranslatedChange:
    """One accepted Meta change translated toward the canonical boundary."""

    event_identity: dict[str, Any]
    raw: dict[str, Any]
    native_field: str
    comment_id: str


@dataclass(frozen=True)
class TranslationResult:
    accepted: tuple[TranslatedChange, ...]
    skipped_unsupported: int  # field not in ACCEPTED_FIELDS
    skipped_invalid: int  # structurally unusable (missing identifiers)


def _nonempty_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def translate_instagram_payload(payload: dict[str, Any]) -> TranslationResult:
    """Translate a Meta-native Instagram webhook payload.

    Accepts only object == "instagram" and fields in ACCEPTED_FIELDS
    (comments / live_comments). Both map to the canonical glossolalia
    event_type "comment"; the native field is preserved in raw_event_ref
    for provenance. Unknown fields are skipped safely (never routed).
    Changes missing stable identifiers are skipped (fail safe, no draft).
    """
    if not isinstance(payload, dict):
        raise MetaWebhookError("PAYLOAD_OBJECT_REQUIRED")
    if payload.get("object") != META_OBJECT_INSTAGRAM:
        raise MetaWebhookError("OBJECT_NOT_INSTAGRAM")
    entry = payload.get("entry")
    if not isinstance(entry, list) or not entry:
        raise MetaWebhookError("ENTRY_REQUIRED")

    accepted: list[TranslatedChange] = []
    skipped_unsupported = 0
    skipped_invalid = 0

    for item in entry:
        if not isinstance(item, dict):
            skipped_invalid += 1
            continue
        entry_id = _nonempty_str(item.get("id"))
        if entry_id is None:
            # No stable account identity: cannot bind to an integration.
            skipped_invalid += 1
            continue
        time_value = item.get("time")
        timestamp = str(time_value) if isinstance(time_value, int) else None
        changes = item.get("changes")
        if not isinstance(changes, list):
            skipped_invalid += 1
            continue
        for change in changes:
            if not isinstance(change, dict):
                skipped_invalid += 1
                continue
            field_name = change.get("field")
            if field_name not in ACCEPTED_FIELDS:
                skipped_unsupported += 1
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                skipped_invalid += 1
                continue
            comment_id = _nonempty_str(value.get("id")) or _nonempty_str(
                value.get("comment_id")
            )
            from_block = value.get("from")
            sender_id = (
                _nonempty_str(from_block.get("id"))
                if isinstance(from_block, dict)
                else None
            )
            media_block = value.get("media")
            media_id = (
                _nonempty_str(media_block.get("id"))
                if isinstance(media_block, dict)
                else None
            )
            if comment_id is None or sender_id is None:
                # Missing stable identifiers: fail safe, never draft.
                skipped_invalid += 1
                continue
            text = value.get("text")
            if text is not None and not isinstance(text, str):
                skipped_invalid += 1
                continue
            raw = {
                "channel": "instagram",
                "event_type": "comment",
                "sender_id": sender_id,
                "message_id": comment_id,
                "parent_id": _nonempty_str(value.get("parent_id")),
                "conversation_id": media_id,
                "timestamp": timestamp,
                "text": text.strip() if isinstance(text, str) and text.strip() else None,
                "raw_event_ref": f"meta:instagram:{field_name}:{comment_id}",
            }
            # NOTE: no business_id/brand_id claim is ever forwarded. Tenant
            # binding happens only through resolve_integration against the
            # fixed configuration.
            accepted.append(
                TranslatedChange(
                    event_identity={"channel": "instagram", "identity": entry_id},
                    raw=raw,
                    native_field=str(field_name),
                    comment_id=comment_id,
                )
            )

    return TranslationResult(
        accepted=tuple(accepted),
        skipped_unsupported=skipped_unsupported,
        skipped_invalid=skipped_invalid,
    )


# ---------------------------------------------------------------------------
# Receiver
# ---------------------------------------------------------------------------


@dataclass
class IngestReport:
    status: int
    body: dict[str, Any]
    results: tuple[MetaProcessResult, ...] = ()
    rejected: int = 0


class MetaWebhookReceiver:
    """Fixed-integration Meta webhook receiver.

    Owns one IntegrationConfig (Los Duros Instagram), resolves the verify
    token and App Secret from env: references once at construction, and
    keeps the in-memory dedupe set for Meta's retry deliveries.
    """

    def __init__(
        self,
        *,
        integration: IntegrationConfig,
        biblia_root: Path | None = None,
        registry_path: Path | None = None,
    ) -> None:
        if integration.channel != "instagram":
            raise MetaWebhookError("RECEIVER_REQUIRES_INSTAGRAM_INTEGRATION")
        if not integration.enabled or not integration.read_enabled:
            raise MetaWebhookError("INTEGRATION_NOT_READABLE")
        if not integration.webhook_verify_ref:
            raise MetaWebhookError("VERIFY_TOKEN_REF_REQUIRED")
        if not integration.credential_ref:
            raise MetaWebhookError("APP_SECRET_REF_REQUIRED")
        self._integration = integration
        # Resolved once; never logged or echoed.
        self._verify_token = resolve_secret_ref(integration.webhook_verify_ref)
        self._app_secret = resolve_secret_ref(integration.credential_ref)
        self._biblia_root = biblia_root
        self._registry_path = registry_path
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    @property
    def integration(self) -> IntegrationConfig:
        return self._integration

    # -- GET ------------------------------------------------------------
    def verify_get(self, query: dict[str, str]) -> tuple[int, str]:
        return handle_verification_request(
            query, expected_verify_token=self._verify_token
        )

    # -- POST -----------------------------------------------------------
    def ingest_post(
        self, raw_body: bytes, signature_header: str | None
    ) -> IngestReport:
        """Ingest one Meta POST delivery. Fail closed; never publishes.

        Status contract:
          200 -- delivery accepted (processed / duplicate / safely skipped)
          400 -- malformed JSON, non-instagram object, structural problems
          401 -- missing or invalid X-Hub-Signature-256
        """
        try:
            verify_post_signature(
                raw_body, signature_header, app_secret=self._app_secret
            )
        except MetaWebhookError as exc:
            return IngestReport(
                status=401, body={"ok": False, "error": str(exc)}
            )
        try:
            payload = json.loads(bytes(raw_body).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return IngestReport(
                status=400, body={"ok": False, "error": "MALFORMED_JSON"}
            )
        try:
            translation = translate_instagram_payload(payload)
        except MetaWebhookError as exc:
            return IngestReport(
                status=400, body={"ok": False, "error": str(exc)}
            )

        results: list[MetaProcessResult] = []
        processed = 0
        duplicates = 0
        rejected = 0
        # One lock around the whole delivery: the seen-set check/add inside
        # process_meta_event stays atomic per delivery batch.
        with self._lock:
            for change in translation.accepted:
                try:
                    resolve_integration(
                        change.event_identity, [self._integration]
                    )
                except GlossolaliaError:
                    # Unknown identity (spoof / misconfiguration): fail
                    # closed, count, never route.
                    rejected += 1
                    continue
                result = process_meta_event(
                    change.raw,
                    integration=self._integration,
                    biblia_root=self._biblia_root,
                    registry_path=self._registry_path,
                    attempt_action=False,  # drafts only; NEVER publish
                    seen_fingerprints=self._seen,
                )
                # Hard invariant: this receiver never builds transport intents.
                assert result.action is None, "RECEIVER_MUST_NOT_BUILD_ACTIONS"
                results.append(result)
                if result.duplicate:
                    duplicates += 1
                else:
                    processed += 1

        return IngestReport(
            status=200,
            body={
                "ok": True,
                "received": len(translation.accepted),
                "processed": processed,
                "duplicates": duplicates,
                "skipped_unsupported": translation.skipped_unsupported,
                "skipped_invalid": translation.skipped_invalid,
                "rejected": rejected,
            },
            results=tuple(results),
            rejected=rejected,
        )

    def decision_records(self, report: IngestReport) -> tuple[dict[str, Any], ...]:
        """Sanitized per-event records: no text, no secrets, no tokens."""
        records = []
        for result in report.results:
            records.append(
                {
                    "comment_id": result.event.message_id,
                    "business_id": result.event.business_id_internal,
                    "native_ref": result.event.raw_event_ref,
                    "route": result.decision.route,
                    "subtype": result.decision.subtype,
                    "drafted": result.draft is not None,
                    "duplicate": result.duplicate,
                    "action_built": result.action is not None,
                }
            )
        return tuple(records)


def receiver_from_env(
    *,
    biblia_root: Path | None = None,
    registry_path: Path | None = None,
) -> MetaWebhookReceiver:
    """Build the Los Duros receiver from runtime environment.

    Requires LOS_DUROS_IG_ACCOUNT_ID (identifier, not a secret),
    LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN and META_APP_SECRET (secrets).
    """
    account_id = os.environ.get(LOS_DUROS_IG_ACCOUNT_ID_ENV)
    integration = build_los_duros_instagram_integration(
        instagram_account_id=account_id or ""
    )
    return MetaWebhookReceiver(
        integration=integration, biblia_root=biblia_root, registry_path=registry_path
    )


# ---------------------------------------------------------------------------
# stdlib HTTP adapter (thin transport mount for the pure handlers)
# ---------------------------------------------------------------------------


class _WebhookHandler(BaseHTTPRequestHandler):
    """Routes GET/POST on CALLBACK_PATH to the receiver's pure handlers."""

    receiver: MetaWebhookReceiver  # set by serve()
    server_version = "ZIONMetaWebhook/1.0"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _path(self) -> str:
        return urlsplit(self.path).path

    def do_GET(self) -> None:  # noqa: N802 (http.server convention)
        if self._path() != CALLBACK_PATH:
            self._send(404, b"not found", "text/plain")
            return
        query = dict(parse_qsl(urlsplit(self.path).query))
        status, body = self.receiver.verify_get(query)
        self._send(status, body.encode("utf-8"), "text/plain")

    def do_POST(self) -> None:  # noqa: N802 (http.server convention)
        if self._path() != CALLBACK_PATH:
            self._send(404, b"not found", "text/plain")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            code = 400 if length <= 0 else 413
            self._send(
                code,
                json.dumps({"ok": False, "error": "INVALID_CONTENT_LENGTH"}).encode(),
                "application/json",
            )
            return
        raw_body = self.rfile.read(length)
        report = self.receiver.ingest_post(
            raw_body, self.headers.get("X-Hub-Signature-256")
        )
        self._send(
            report.status,
            json.dumps(report.body).encode("utf-8"),
            "application/json",
        )

    def log_message(self, fmt: str, *args: Any) -> None:
        # Minimal access logging that never includes the query string,
        # request bodies, or headers (they may carry tokens/signatures).
        # NOTE: must not call self.log_error (it delegates back here).
        sys.stderr.write(
            "%s - - [%s] %s %s\n"
            % (
                self.address_string(),
                self.log_date_time_string(),
                self.command,
                urlsplit(self.path).path,
            )
        )


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    receiver: MetaWebhookReceiver | None = None,
) -> ThreadingHTTPServer:
    """Mount the receiver on CALLBACK_PATH with the stdlib HTTP server.

    Production deployments terminate TLS in front of this (Meta requires
    HTTPS on the public callback URL). Returns the server; the caller runs
    serve_forever().
    """
    if receiver is None:
        receiver = receiver_from_env()
    _WebhookHandler.receiver = receiver
    server = ThreadingHTTPServer((host, port), _WebhookHandler)
    server.daemon_threads = True
    return server


__all__ = [
    "CALLBACK_PATH",
    "META_OBJECT_INSTAGRAM",
    "ACCEPTED_FIELDS",
    "MAX_BODY_BYTES",
    "LOS_DUROS_BUSINESS_ID",
    "LOS_DUROS_BRAND_ID",
    "LOS_DUROS_IG_INTEGRATION_ID",
    "META_APP_SECRET_REF",
    "LOS_DUROS_IG_VERIFY_TOKEN_REF",
    "LOS_DUROS_IG_ACCOUNT_ID_ENV",
    "MetaWebhookError",
    "TranslatedChange",
    "TranslationResult",
    "IngestReport",
    "MetaWebhookReceiver",
    "resolve_secret_ref",
    "build_los_duros_instagram_integration",
    "handle_verification_request",
    "verify_post_signature",
    "translate_instagram_payload",
    "receiver_from_env",
    "serve",
]
