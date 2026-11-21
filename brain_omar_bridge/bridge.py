"""Brain -> Omar bridge (adapter).

Takes ONE completed Zmart Brain result (the item emitted by the n8n
ESCALATION GATE node, which still carries the trusted ``business_id``
stamped by PROFILE LOADER), resolves the Omar Core ``business_id``,
and asks Omar Core for the canonical route of that business.

Fail-closed contract:
- The Brain's public webhook response strips ``business_id`` on purpose
  (RESPOND node). The bridge therefore consumes the internal gate item,
  or an equivalent trusted side channel. If ``business_id`` is absent it
  raises instead of guessing: a route for the wrong business is worse
  than no route.
- Unknown or unmapped business ids raise before any HTTP call.
- If Omar is unreachable, rejects the request, or answers anything
  other than a well-formed ``{"ok": true, "route": {...}}`` whose
  ``route.business_id`` matches the request, the bridge raises a typed
  error. It NEVER fabricates, caches, or falls back to a local route.

Configuration (never hardcode secrets):
- ``OMAR_CORE_BASE_URL``  base URL of Omar Core (default below).
- ``OMAR_API_KEY``        the key itself, or
- ``OMAR_API_KEY_FILE``   path to a file containing only the key.

The key is sent as the ``X-Omar-Key`` header and is never logged,
returned, or included in error messages.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

DEFAULT_BASE_URL = "https://omar-core.fly.dev"
ROUTE_PATH = "/omar/route"
DEFAULT_TIMEOUT_SECONDS = 10.0

# Omar Core business ids (verified live 2026-11-20: POST /omar/route
# returns 200 for exactly these four, 400 for anything else).
OMAR_BUSINESS_IDS = frozenset({"zmart-consumer", "scan", "zerolag", "los-duros"})

# Brain profile id -> Omar business id.
# Only "zmart" is a live Brain profile today (PROFILE LOADER in
# "NELSON AI | Zmart Brain v1"); its Omar id differs, hence the map.
# The other three are identity mappings for future Brain profiles whose
# trusted ids already match Omar's; they are NOT live Brain profiles.
BRAIN_TO_OMAR_BUSINESS_ID = {
    "zmart": "zmart-consumer",
    "scan": "scan",
    "zerolag": "zerolag",
    "los-duros": "los-duros",
}

# Fields the ESCALATION GATE item must carry (STRUCTURED OUTPUT fields
# plus the gate's own deterministic derivation). Verified against the
# live workflow 2026-11-20.
BRAIN_REQUIRED_FIELDS = (
    "intent",
    "channel",
    "language",
    "lead_status",
    "priority",
    "recommended_action",
    "response",
    "requires_human",
    "reason",
    "escalation_route",
    "escalation_reason",
)
ESCALATION_ROUTES = frozenset({"routine", "main_brain", "human_review"})


class BridgeError(Exception):
    """Base class for every bridge failure. Any BridgeError means: no route."""


class BrainContractError(BridgeError):
    """The Brain payload does not match the verified gate output contract."""


class MissingBusinessContextError(BridgeError):
    """The Brain payload carries no trusted business_id. Refusing to guess."""


class UnknownBusinessError(BridgeError):
    """The Brain business_id has no Omar mapping. Raised before any HTTP call."""


class OmarConfigError(BridgeError):
    """The bridge is not configured (e.g. no API key available)."""


class OmarUnreachableError(BridgeError):
    """Omar Core could not be reached (DNS, connection, timeout, ...)."""


class OmarAuthError(BridgeError):
    """Omar Core rejected the bridge credential (HTTP 401/403)."""


class OmarRejectedError(BridgeError):
    """Omar Core rejected the route request (HTTP 400, fail-closed router)."""


class OmarResponseError(BridgeError):
    """Omar Core answered, but not with a well-formed, matching route."""


@dataclass(frozen=True)
class BridgeResult:
    """A verified pairing of the Brain's escalation decision with Omar's route."""

    brain_business_id: str
    omar_business_id: str
    escalation_route: str
    escalation_reason: str
    visual: bool
    omar_route: Mapping[str, Any]


# Transport signature: (method, url, headers, body_bytes, timeout)
#   -> (status_code, response_body_bytes)
Transport = Callable[[str, str, Mapping[str, str], bytes, float], tuple[int, bytes]]


def _urllib_transport(method: str, url: str, headers: Mapping[str, str],
                      body: bytes, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method=method)
    for name, value in headers.items():
        req.add_header(name, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        # An HTTP error status is still an answer from Omar; the client
        # layer decides what it means. Read the body without the key.
        return exc.code, exc.read()


class OmarClient:
    """Minimal Omar Core client. One job: POST /omar/route, verified."""

    def __init__(self, *, base_url: str = DEFAULT_BASE_URL, api_key: str | None = None,
                 transport: Transport | None = None,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._transport = transport or _urllib_transport
        self._timeout = timeout

    def __repr__(self) -> str:  # never include the key
        return f"OmarClient(base_url={self._base_url!r})"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None, **kwargs: Any) -> "OmarClient":
        """Build a client from OMAR_CORE_BASE_URL / OMAR_API_KEY / OMAR_API_KEY_FILE."""
        env = os.environ if environ is None else environ
        api_key = env.get("OMAR_API_KEY") or None
        if api_key is None:
            key_file = env.get("OMAR_API_KEY_FILE")
            if key_file:
                try:
                    api_key = Path(key_file).read_text(encoding="utf-8").strip() or None
                except OSError as exc:
                    # Missing file, directory, permission, ... — a config
                    # problem, surfaced typed so callers (e.g. the HTTP
                    # service) fail closed instead of dying on a raw OSError.
                    raise OmarConfigError(
                        f"could not read OMAR_API_KEY_FILE: {type(exc).__name__}") from exc
        base_url = env.get("OMAR_CORE_BASE_URL") or DEFAULT_BASE_URL
        return cls(base_url=base_url, api_key=api_key, **kwargs)

    def route(self, business_id: str, *, visual: bool = False) -> Mapping[str, Any]:
        """Ask Omar for the canonical route of one business. Fail-closed."""
        if not isinstance(business_id, str) or business_id not in OMAR_BUSINESS_IDS:
            raise UnknownBusinessError(f"unknown Omar business_id: {business_id!r}")
        if not self._api_key:
            raise OmarConfigError("no Omar API key configured (OMAR_API_KEY or OMAR_API_KEY_FILE)")
        body = json.dumps({"business_id": business_id, "visual": bool(visual)}).encode("utf-8")
        headers = {"Content-Type": "application/json", "X-Omar-Key": self._api_key}
        url = self._base_url + ROUTE_PATH
        try:
            status, raw = self._transport("POST", url, headers, body, self._timeout)
        except Exception as exc:  # DNS, connection, timeout, TLS, ...
            raise OmarUnreachableError(f"Omar Core unreachable: {type(exc).__name__}") from exc
        if status == 400:
            raise OmarRejectedError(f"Omar rejected route request for {business_id!r} (HTTP 400)")
        if status in (401, 403):
            raise OmarAuthError(f"Omar rejected the bridge credential (HTTP {status})")
        if status != 200:
            raise OmarResponseError(f"unexpected Omar status HTTP {status}")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise OmarResponseError("Omar returned a non-JSON body") from exc
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise OmarResponseError("Omar returned ok != true")
        route = payload.get("route")
        if not isinstance(route, dict):
            raise OmarResponseError("Omar response has no route object")
        if route.get("business_id") != business_id:
            raise OmarResponseError(
                f"Omar route business_id mismatch: asked {business_id!r}, "
                f"got {route.get('business_id')!r}")
        return route


def resolve_omar_business_id(brain_output: Mapping[str, Any]) -> str:
    """Map the Brain item's trusted business_id to Omar's id. Fail-closed."""
    raw = brain_output.get("business_id")
    if not isinstance(raw, str) or not raw.strip():
        raise MissingBusinessContextError(
            "Brain payload has no trusted business_id; the bridge does not guess. "
            "Feed it the ESCALATION GATE item (or a trusted side channel), "
            "not the public webhook response, which strips business_id.")
    brain_id = raw.strip()
    omar_id = BRAIN_TO_OMAR_BUSINESS_ID.get(brain_id)
    if omar_id is None:
        raise UnknownBusinessError(f"no Omar mapping for Brain business_id: {brain_id!r}")
    return omar_id


def validate_brain_output(brain_output: Mapping[str, Any]) -> None:
    """Check the payload against the verified ESCALATION GATE contract."""
    if not isinstance(brain_output, Mapping):
        raise BrainContractError(
            f"Brain payload is not an object: {type(brain_output).__name__}")
    missing = [f for f in BRAIN_REQUIRED_FIELDS if brain_output.get(f) is None]
    if missing:
        raise BrainContractError(f"Brain payload missing fields: {', '.join(missing)}")
    route_value = brain_output["escalation_route"]
    if not isinstance(route_value, str) or route_value not in ESCALATION_ROUTES:
        raise BrainContractError(f"unknown escalation_route: {route_value!r}")


def route_for_brain_output(brain_output: Mapping[str, Any], *, client: OmarClient,
                           visual: bool = False) -> BridgeResult:
    """Bridge one Brain result to Omar's canonical route. Fail-closed.

    Raises a BridgeError subclass on any doubt; returns only when Omar
    has verified the business and returned its route.
    """
    validate_brain_output(brain_output)
    omar_id = resolve_omar_business_id(brain_output)
    route = client.route(omar_id, visual=visual)
    return BridgeResult(
        brain_business_id=str(brain_output["business_id"]).strip(),
        omar_business_id=omar_id,
        escalation_route=str(brain_output["escalation_route"]),
        escalation_reason=str(brain_output["escalation_reason"]),
        visual=bool(visual),
        omar_route=route,
    )
