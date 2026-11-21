"""Unit tests (layer: UNIT) for the Brain -> Omar bridge HTTP service.

The service runs on an ephemeral localhost port with an OmarClient whose
transport is faked; nothing here touches the network beyond loopback.
Live verification lives in brain_omar_bridge_service/shadow_e2e.py.
"""
import json
import threading
import unittest
import urllib.error
import urllib.request

from brain_omar_bridge import OmarClient
from brain_omar_bridge_service.service import create_server

# Same verified ESCALATION GATE item shape as tests/test_brain_omar_bridge.py.
BRAIN_OUTPUT = {
    "intent": "operational_request",
    "channel": "whatsapp",
    "language": "es",
    "lead_status": "needs_info",
    "priority": "medium",
    "recommended_action": "send_quiz_link",
    "response": "Claro, te comparto el formulario breve.",
    "requires_human": False,
    "reason": "pidio el formulario",
    "escalation_route": "routine",
    "escalation_reason": "clear_low_risk",
    "business_id": "zmart",
    "config_version": "1.0",
}

OMAR_ROUTE = {
    "business_id": "zmart-consumer",
    "name": "Zmart Consumer Rights",
    "repository": "riveranelso/zmart-consumer-rights",
    "rules": ["brand/COMPLIANCE.md"],
    "brain_mode": "project_rules",
    "status": "active",
    "visual_gate_required": False,
    "notes": "Consumer advocacy/consulting; not a law firm.",
    "asset_status": None,
}


class FakeTransport:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = {"ok": True, "route": dict(OMAR_ROUTE)} if payload is None else payload
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers),
                           "body": body, "timeout": timeout})
        raw = self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode()
        return self.status, raw


class ServiceTestCase(unittest.TestCase):
    transport_status = 200
    transport_payload = None

    def setUp(self):
        self.transport = FakeTransport(status=self.transport_status,
                                       payload=self.transport_payload)
        client = OmarClient(base_url="https://omar.example.test",
                            api_key="test-key", transport=self.transport)
        self.server = create_server("127.0.0.1", 0, client,
                                    caller_key="test-caller-key")
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path, body=None, caller_key="test-caller-key"):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if caller_key is not None:
            req.add_header("X-Bridge-Key", caller_key)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())


class HealthTests(ServiceTestCase):
    def test_health_ok_and_never_calls_omar(self):
        status, body = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["service"], "brain-omar-bridge")
        self.assertEqual(self.transport.calls, [])


class RouteTests(ServiceTestCase):
    def test_valid_gate_item_returns_pairing(self):
        status, body = self.request("POST", "/bridge/route", BRAIN_OUTPUT)
        self.assertEqual(status, 200)
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["brain_business_id"], "zmart")
        self.assertEqual(body["omar_business_id"], "zmart-consumer")
        self.assertEqual(body["escalation_route"], "routine")
        self.assertEqual(body["escalation_reason"], "clear_low_risk")
        self.assertEqual(body["visual"], False)
        self.assertEqual(body["omar_route"]["business_id"], "zmart-consumer")
        self.assertEqual(body["omar_route"]["repository"],
                         "riveranelso/zmart-consumer-rights")
        self.assertEqual(len(self.transport.calls), 1)
        sent = json.loads(self.transport.calls[0]["body"])
        self.assertEqual(sent, {"business_id": "zmart-consumer", "visual": False})
        self.assertNotIn("test-key", json.dumps(body))

    def test_public_response_shape_is_missing_context(self):
        # The public webhook response: business_id stripped by RESPOND.
        item = {k: v for k, v in BRAIN_OUTPUT.items() if k != "business_id"}
        status, body = self.request("POST", "/bridge/route", item)
        self.assertEqual(status, 422)
        self.assertEqual(body, {"ok": False, "error": "MissingBusinessContextError"})
        self.assertEqual(self.transport.calls, [])

    def test_missing_contract_field_is_contract_error(self):
        item = {k: v for k, v in BRAIN_OUTPUT.items() if k != "priority"}
        status, body = self.request("POST", "/bridge/route", item)
        self.assertEqual(status, 422)
        self.assertEqual(body, {"ok": False, "error": "BrainContractError"})
        self.assertEqual(self.transport.calls, [])

    def test_invalid_json_body_is_400(self):
        status, body = self.request("POST", "/bridge/route", b"{not json")
        self.assertEqual(status, 400)
        self.assertEqual(body, {"ok": False, "error": "InvalidJsonBody"})
        self.assertEqual(self.transport.calls, [])

    def test_non_object_json_is_contract_error(self):
        status, body = self.request("POST", "/bridge/route", [1, 2, 3])
        self.assertEqual(status, 422)
        self.assertEqual(body, {"ok": False, "error": "BrainContractError"})

    def test_unknown_path_404_and_get_route_405(self):
        status, body = self.request("POST", "/nope", BRAIN_OUTPUT)
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "NotFound")
        status, body = self.request("GET", "/bridge/route")
        self.assertEqual(status, 405)
        self.assertEqual(body["error"], "MethodNotAllowed")


class CallerAuthTests(ServiceTestCase):
    def test_missing_caller_key_is_401_and_never_calls_omar(self):
        status, body = self.request("POST", "/bridge/route", BRAIN_OUTPUT,
                                    caller_key=None)
        self.assertEqual(status, 401)
        self.assertEqual(body, {"ok": False, "error": "CallerAuthError"})
        self.assertEqual(self.transport.calls, [])

    def test_wrong_caller_key_is_401_and_never_calls_omar(self):
        status, body = self.request("POST", "/bridge/route", BRAIN_OUTPUT,
                                    caller_key="wrong-caller-key")
        self.assertEqual(status, 401)
        self.assertEqual(body, {"ok": False, "error": "CallerAuthError"})
        self.assertEqual(self.transport.calls, [])
        self.assertNotIn("test-caller-key", json.dumps(body))


class OmarAuthFailureTests(ServiceTestCase):
    transport_status = 401
    transport_payload = {"detail": "Unauthorized"}

    def test_omar_401_maps_to_auth_error_without_leaks(self):
        status, body = self.request("POST", "/bridge/route", BRAIN_OUTPUT)
        self.assertEqual(status, 502)
        self.assertEqual(body, {"ok": False, "error": "OmarAuthError"})
        self.assertNotIn("test-key", json.dumps(body))
        self.assertNotIn("Unauthorized", json.dumps(body))


if __name__ == "__main__":
    unittest.main()
