"""Live shadow end-to-end test (layer: LIVE API) for the bridge service.

Starts the real HTTP service on an ephemeral loopback port with a real
OmarClient (key from OMAR_API_KEY / OMAR_API_KEY_FILE — never printed),
POSTs ONE synthetic ESCALATION GATE item through it, and prints the
verified pairing. The payload is 100% synthetic: no customer data.

    OMAR_API_KEY_FILE=~/workspace/.secrets/omar-api-key \
        python3 -m brain_omar_bridge_service.shadow_e2e
"""
from __future__ import annotations

import json
import secrets
import threading
import urllib.request

from brain_omar_bridge import OmarClient
from brain_omar_bridge_service.service import create_server

SYNTHETIC_GATE_ITEM = {
    "intent": "shadow_test_synthetic",
    "channel": "synthetic",
    "language": "es",
    "lead_status": "test",
    "priority": "low",
    "recommended_action": "none_shadow_test",
    "response": "[SYNTHETIC] shadow test payload - no customer data.",
    "requires_human": False,
    "reason": "shadow_test",
    "escalation_route": "routine",
    "escalation_reason": "clear_low_risk",
    "business_id": "zmart",
    "config_version": "shadow-test",
}


def main() -> int:
    client = OmarClient.from_env()
    # Loopback-only test tool: a fresh in-process caller secret stands
    # in for BRIDGE_CALLER_KEY so the authenticated path is exercised.
    caller_key = secrets.token_hex(16)
    server = create_server("127.0.0.1", 0, client, caller_key=caller_key)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/bridge/route",
            data=json.dumps(SYNTHETIC_GATE_ITEM).encode("utf-8"),
            method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Bridge-Key", caller_key)
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            body = json.loads(resp.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
    print(f"HTTP {status}")
    print(json.dumps(body, indent=2))
    assert status == 200, f"expected 200, got {status}"
    assert body["omar_business_id"] == "zmart-consumer", body
    assert body["omar_route"]["business_id"] == "zmart-consumer", body
    print("SHADOW E2E: PASS - synthetic gate item paired zmart -> zmart-consumer "
          "through the live service against live Omar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
