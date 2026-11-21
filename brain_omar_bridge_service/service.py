"""Brain -> Omar bridge HTTP service (Python stdlib only).

Endpoints:
- ``POST /bridge/route`` — body is ONE ESCALATION GATE item (JSON object,
  the internal item that still carries the trusted ``business_id``).
  Optional query flag ``?visual=1`` marks the work as visual.
  200 -> the BridgeResult as JSON. Any bridge failure -> non-200 with
  ``{"ok": false, "error": "<ErrorTypeName>"}`` and nothing else: no key,
  no payload echo, no exception text.
- ``GET /health`` — liveness only. Never calls Omar, never needs the key.

Caller authentication: ``POST /bridge/route`` spends the service's own
Omar credential, so callers must authenticate with a SEPARATE caller
secret, sent as the ``X-Bridge-Key`` header. The secret is configured
only via the ``BRIDGE_CALLER_KEY`` environment variable (never
hardcoded, never logged, never in any response). A missing or wrong
header -> 401 ``CallerAuthError`` and Omar is never called.

Fail-closed, like the bridge: with no Omar key configured the service
still boots and answers /health, while /bridge/route returns the typed
``OmarConfigError`` until a key is placed in the environment. With no
caller secret configured, /bridge/route rejects every caller (401).
"""
from __future__ import annotations

import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    from brain_omar_bridge import (
        BridgeError,
        OmarClient,
        route_for_brain_output,
    )
except ImportError:  # running from outside the repo root (e.g. Docker)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from brain_omar_bridge import (  # noqa: E402
        BridgeError,
        OmarClient,
        route_for_brain_output,
    )

SERVICE_NAME = "brain-omar-bridge"
SERVICE_VERSION = "0.1.0"
ROUTE_PATH = "/bridge/route"
HEALTH_PATH = "/health"
MAX_BODY_BYTES = 256 * 1024
CALLER_KEY_ENV = "BRIDGE_CALLER_KEY"
CALLER_KEY_HEADER = "X-Bridge-Key"

# Typed bridge error -> HTTP status. The response body carries ONLY the
# error type name; mapping by name keeps this table in lockstep with the
# bridge's exception taxonomy without importing every class.
ERROR_STATUS = {
    "BrainContractError": 422,
    "MissingBusinessContextError": 422,
    "UnknownBusinessError": 422,
    "OmarConfigError": 500,
    "OmarAuthError": 502,
    "OmarRejectedError": 502,
    "OmarResponseError": 502,
    "OmarUnreachableError": 503,
}


def result_to_json(result: Any) -> dict[str, Any]:
    """Serialize a BridgeResult. Contains no credential material."""
    return {
        "ok": True,
        "brain_business_id": result.brain_business_id,
        "omar_business_id": result.omar_business_id,
        "escalation_route": result.escalation_route,
        "escalation_reason": result.escalation_reason,
        "visual": result.visual,
        "omar_route": dict(result.omar_route),
    }


def make_handler(client: OmarClient,
                 caller_key: str | None = None) -> type[BaseHTTPRequestHandler]:
    """Build a request handler bound to one (injectable) Omar client.

    ``caller_key`` is the caller-authentication secret; when not given
    it is read from the ``BRIDGE_CALLER_KEY`` environment variable.
    When no secret is configured at all, /bridge/route fails closed:
    every caller is rejected with 401.
    """
    expected_caller_key = caller_key
    if expected_caller_key is None:
        expected_caller_key = os.environ.get(CALLER_KEY_ENV) or None

    class BridgeHandler(BaseHTTPRequestHandler):
        server_version = f"{SERVICE_NAME}/{SERVICE_VERSION}"
        # Quieten the default stderr access log; _send_json logs one
        # minimal line (method, path, status, error type) instead. The
        # request body and headers are never logged.
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass

        def _send_json(self, status: int, payload: dict[str, Any],
                       error_type: str | None = None) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            note = f" error={error_type}" if error_type else ""
            sys.stderr.write(
                f"{SERVICE_NAME}: {self.command} {urlparse(self.path).path} "
                f"-> {status}{note}\n")

        def _error(self, status: int, error_type: str) -> None:
            self._send_json(status, {"ok": False, "error": error_type},
                            error_type=error_type)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == HEALTH_PATH:
                # Liveness only: deliberately no Omar call, so a sick
                # upstream never marks this service dead (and vice versa).
                self._send_json(200, {"ok": True, "service": SERVICE_NAME,
                                      "version": SERVICE_VERSION})
            elif path == ROUTE_PATH:
                self._error(405, "MethodNotAllowed")
            else:
                self._error(404, "NotFound")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != ROUTE_PATH:
                self._error(404, "NotFound")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._error(400, "InvalidContentLength")
                return
            if length < 0:
                # A negative Content-Length is invalid; rfile.read(-1)
                # would block until EOF (pinning this handler thread)
                # and read(<-1) raises ValueError, dropping the
                # connection with no response at all.
                self._error(400, "InvalidContentLength")
                return
            if length > MAX_BODY_BYTES:
                self._error(413, "PayloadTooLarge")
                return
            raw = self.rfile.read(length) if length else b""
            try:
                item = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError, RecursionError):
                # RecursionError: pathologically nested JSON within the
                # size cap still blows the decoder's recursion limit.
                self._error(400, "InvalidJsonBody")
                return
            if not isinstance(item, dict):
                # A gate item is a JSON object; anything else cannot
                # satisfy the Brain contract.
                self._error(ERROR_STATUS["BrainContractError"], "BrainContractError")
                return
            provided_caller_key = self.headers.get(CALLER_KEY_HEADER)
            if (expected_caller_key is None or provided_caller_key is None
                    or not hmac.compare_digest(provided_caller_key,
                                               expected_caller_key)):
                # Never call Omar for an unauthenticated caller: the
                # request would be spent with the service's own Omar key.
                self._error(401, "CallerAuthError")
                return
            visual = parse_qs(parsed.query).get("visual", [""])[0].lower() in (
                "1", "true", "yes")
            try:
                result = route_for_brain_output(item, client=client, visual=visual)
            except BridgeError as exc:
                error_type = type(exc).__name__
                self._error(ERROR_STATUS.get(error_type, 500), error_type)
                return
            except Exception:  # never leak internals to the caller
                self._error(500, "InternalError")
                return
            self._send_json(200, result_to_json(result))

        # Unsupported methods get the JSON error contract, not the
        # stdlib 501 HTML page BaseHTTPRequestHandler serves by default.
        def _method_not_allowed(self) -> None:
            self._error(405, "MethodNotAllowed")

        do_PUT = _method_not_allowed
        do_DELETE = _method_not_allowed
        do_PATCH = _method_not_allowed
        do_OPTIONS = _method_not_allowed

    return BridgeHandler


def create_server(host: str, port: int, client: OmarClient,
                  caller_key: str | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(client, caller_key))


def main() -> int:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    # Key (if any) comes from OMAR_API_KEY / OMAR_API_KEY_FILE via the
    # bridge's own env loader. Absent key -> typed OmarConfigError per
    # request, service still boots (fail closed, health stays up).
    client = OmarClient.from_env()
    caller_key = os.environ.get(CALLER_KEY_ENV) or None
    if caller_key is None:
        sys.stderr.write(
            f"{SERVICE_NAME}: WARNING {CALLER_KEY_ENV} is not set; "
            "/bridge/route will reject every caller with 401\n")
    server = create_server(host, port, client, caller_key=caller_key)
    sys.stderr.write(f"{SERVICE_NAME}: listening on {host}:{port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
