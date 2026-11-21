"""ZEROLAG META LEADGEN WEBHOOK APP (stdlib http.server).

Mounts ZeroLagLeadReceiver on:
  GET  /health                 -> 200 {"status":"ok"} (platform probe)
  GET  /meta/webhooks/leadgen  -> Meta verification challenge
  POST /meta/webhooks/leadgen  -> Lead Ads delivery ingest

Required env (fail fast if missing; values never printed):
  ZEROLAG_WEBHOOK_VERIFY_TOKEN -- Meta dashboard verify token
  META_APP_SECRET              -- Meta App secret (HMAC signing key)
  META_PAGE_TOKEN              -- Page access token (Graph lead fetch)
  N8N_META_LEADS_URL           -- n8n webhook URL for normalized leads
Optional env:
  ZEROLAG_PAGE_ID              -- expected Page id (tenant allowlist)
  LEAD_STORE_PATH              -- SQLite path (default /data/leadgen.db)
  PORT                         -- listen port (default 8080)

A daemon thread runs receiver.retry_pending() every 60s so
fetch_pending/forward_pending leads are retried without Meta re-delivery.

stdlib only. TLS terminates in front (Meta requires HTTPS).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from .meta_leadgen import (
    CALLBACK_PATH,
    HEALTH_PATH,
    MAX_BODY_BYTES,
    ZeroLagLeadReceiver,
    parse_form_allowlist,
)
from .meta_webhook import MetaWebhookError

RETRY_SWEEP_SECS = 60


def _env_ref(name: str) -> str:
    """Build an env: secret reference (value resolved by the receiver)."""
    return f"env:{name}"


def build_receiver() -> ZeroLagLeadReceiver:
    """Build the receiver from runtime env. Fail fast on missing config."""
    return ZeroLagLeadReceiver(
        verify_token_ref=_env_ref("ZEROLAG_WEBHOOK_VERIFY_TOKEN"),
        app_secret_ref=_env_ref("META_APP_SECRET"),
        page_token_ref=_env_ref("META_PAGE_TOKEN"),
        n8n_url_ref=_env_ref("N8N_META_LEADS_URL"),
        store_path=Path(os.environ.get("LEAD_STORE_PATH", "/data/leadgen.db")),
        expected_page_id=os.environ.get("ZEROLAG_PAGE_ID"),
        allowed_form_ids=parse_form_allowlist(
            os.environ.get("ZEROLAG_FORM_ALLOWLIST")
        ),
    )


class _LeadgenHandler(BaseHTTPRequestHandler):
    """Routes health/verification/ingest to the receiver's pure handlers."""

    receiver: ZeroLagLeadReceiver  # set by serve()
    server_version = "ZerolagLeadgenWebhook/1.0"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _path(self) -> str:
        return urlsplit(self.path).path

    def do_GET(self) -> None:  # noqa: N802 (http.server convention)
        path = self._path()
        if path == HEALTH_PATH:
            self._send(
                200, json.dumps({"status": "ok"}).encode("utf-8"),
                "application/json",
            )
            return
        if path != CALLBACK_PATH:
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
        # Access log without query strings, bodies, or headers (may carry
        # tokens/signatures). Must not call self.log_error (delegates here).
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
    receiver: ZeroLagLeadReceiver | None = None,
) -> ThreadingHTTPServer:
    if receiver is None:
        receiver = build_receiver()
    _LeadgenHandler.receiver = receiver
    server = ThreadingHTTPServer((host, port), _LeadgenHandler)
    server.daemon_threads = True
    return server


def _retry_loop(receiver: ZeroLagLeadReceiver) -> None:
    while True:
        time.sleep(RETRY_SWEEP_SECS)
        try:
            receiver.retry_pending()
        except Exception as exc:  # never kill the sweeper
            logging.getLogger("zion.meta_leadgen").warning(
                json.dumps({"event": "retry_sweep_error",
                            "reason": type(exc).__name__})
            )


def main() -> None:
    """Container entrypoint: build receiver from env, start retry thread."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        receiver = build_receiver()
    except MetaWebhookError as exc:
        # Fail fast with the REASON only -- never secret values.
        sys.stderr.write(f"configuration error: {exc}\n")
        raise SystemExit(2) from exc
    port = int(os.environ.get("PORT", "8080"))
    thread = threading.Thread(
        target=_retry_loop, args=(receiver,), daemon=True,
        name="leadgen-retry-sweep",
    )
    thread.start()
    server = serve(host="0.0.0.0", port=port, receiver=receiver)
    server.serve_forever()


if __name__ == "__main__":
    main()


__all__ = ["build_receiver", "serve", "main"]
