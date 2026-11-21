"""Unit tests (layer: UNIT) for the Brain -> Omar bridge.

All HTTP is faked through an injected transport; nothing here touches
the network. The live API smoke test lives in
tests/test_brain_omar_bridge_live.py and is opt-in.
"""
import json
import tempfile
import unittest
from pathlib import Path

from brain_omar_bridge import (
    BrainContractError,
    MissingBusinessContextError,
    OmarAuthError,
    OmarClient,
    OmarConfigError,
    OmarRejectedError,
    OmarResponseError,
    OmarUnreachableError,
    UnknownBusinessError,
    route_for_brain_output,
)

# A realistic ESCALATION GATE item, shaped exactly like the verified
# live contract of "NELSON AI | Zmart Brain v1" (checked 2026-11-20):
# STRUCTURED OUTPUT fields + escalation_route/escalation_reason +
# the trusted business_id/config_version stamped by PROFILE LOADER.
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
    """Records calls; answers with a canned (status, payload) or raises."""

    def __init__(self, status=200, payload=None, error=None):
        self.status = status
        self.payload = {"ok": True, "route": dict(OMAR_ROUTE)} if payload is None else payload
        self.error = error
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers),
                           "body": body, "timeout": timeout})
        if self.error is not None:
            raise self.error
        raw = self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode()
        return self.status, raw


def make_client(transport, **kwargs):
    return OmarClient(base_url="https://omar.example.test", api_key="test-key",
                      transport=transport, **kwargs)


class MappingTests(unittest.TestCase):
    def test_zmart_maps_to_zmart_consumer_and_calls_omar(self):
        transport = FakeTransport()
        result = route_for_brain_output(BRAIN_OUTPUT, client=make_client(transport))
        self.assertEqual(result.brain_business_id, "zmart")
        self.assertEqual(result.omar_business_id, "zmart-consumer")
        self.assertEqual(result.escalation_route, "routine")
        self.assertEqual(result.escalation_reason, "clear_low_risk")
        self.assertEqual(result.omar_route["repository"], "riveranelso/zmart-consumer-rights")
        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], "https://omar.example.test/omar/route")
        self.assertEqual(call["headers"]["X-Omar-Key"], "test-key")
        self.assertEqual(call["headers"]["Content-Type"], "application/json")
        self.assertEqual(json.loads(call["body"]),
                         {"business_id": "zmart-consumer", "visual": False})

    def test_visual_flag_propagates(self):
        transport = FakeTransport()
        result = route_for_brain_output(BRAIN_OUTPUT, client=make_client(transport), visual=True)
        self.assertTrue(result.visual)
        self.assertEqual(json.loads(transport.calls[0]["body"])["visual"], True)

    def test_identity_mappings_for_future_brain_profiles(self):
        for brain_id in ("scan", "zerolag", "los-duros"):
            transport = FakeTransport(payload={"ok": True, "route": {"business_id": brain_id}})
            out = dict(BRAIN_OUTPUT, business_id=brain_id)
            result = route_for_brain_output(out, client=make_client(transport))
            self.assertEqual(result.omar_business_id, brain_id)

    def test_escalation_fields_pass_through_unchanged(self):
        out = dict(BRAIN_OUTPUT, escalation_route="human_review",
                   escalation_reason="sensitive_signal")
        result = route_for_brain_output(out, client=make_client(FakeTransport()))
        self.assertEqual(result.escalation_route, "human_review")
        self.assertEqual(result.escalation_reason, "sensitive_signal")


class FailClosedTests(unittest.TestCase):
    def test_unknown_business_raises_before_any_http(self):
        transport = FakeTransport()
        with self.assertRaises(UnknownBusinessError):
            route_for_brain_output(dict(BRAIN_OUTPUT, business_id="acme"),
                                   client=make_client(transport))
        self.assertEqual(transport.calls, [])

    def test_missing_business_id_raises_before_any_http(self):
        # This is the public webhook response shape: RESPOND strips
        # business_id. The bridge must refuse, never default to Zmart.
        out = {k: v for k, v in BRAIN_OUTPUT.items() if k != "business_id"}
        transport = FakeTransport()
        with self.assertRaises(MissingBusinessContextError):
            route_for_brain_output(out, client=make_client(transport))
        self.assertEqual(transport.calls, [])

    def test_blank_business_id_raises(self):
        with self.assertRaises(MissingBusinessContextError):
            route_for_brain_output(dict(BRAIN_OUTPUT, business_id="  "),
                                   client=make_client(FakeTransport()))

    def test_missing_gate_field_raises_before_any_http(self):
        out = {k: v for k, v in BRAIN_OUTPUT.items() if k != "escalation_route"}
        transport = FakeTransport()
        with self.assertRaises(BrainContractError):
            route_for_brain_output(out, client=make_client(transport))
        self.assertEqual(transport.calls, [])

    def test_unknown_escalation_route_value_raises(self):
        with self.assertRaises(BrainContractError):
            route_for_brain_output(dict(BRAIN_OUTPUT, escalation_route="sideways"),
                                   client=make_client(FakeTransport()))

    def test_omar_400_is_rejection_not_a_route(self):
        transport = FakeTransport(status=400, payload={"detail": "unknown business_id: x"})
        with self.assertRaises(OmarRejectedError):
            route_for_brain_output(BRAIN_OUTPUT, client=make_client(transport))

    def test_omar_401_is_auth_error(self):
        transport = FakeTransport(status=401, payload={"detail": "Unauthorized"})
        with self.assertRaises(OmarAuthError):
            route_for_brain_output(BRAIN_OUTPUT, client=make_client(transport))

    def test_omar_500_is_response_error(self):
        transport = FakeTransport(status=500, payload=b"boom")
        with self.assertRaises(OmarResponseError):
            route_for_brain_output(BRAIN_OUTPUT, client=make_client(transport))

    def test_unreachable_omar_raises_and_invents_nothing(self):
        transport = FakeTransport(error=OSError("connection refused"))
        with self.assertRaises(OmarUnreachableError):
            route_for_brain_output(BRAIN_OUTPUT, client=make_client(transport))

    def test_non_json_200_is_response_error(self):
        transport = FakeTransport(status=200, payload=b"<html>not json</html>")
        with self.assertRaises(OmarResponseError):
            route_for_brain_output(BRAIN_OUTPUT, client=make_client(transport))

    def test_ok_false_200_is_response_error(self):
        transport = FakeTransport(payload={"ok": False, "route": dict(OMAR_ROUTE)})
        with self.assertRaises(OmarResponseError):
            route_for_brain_output(BRAIN_OUTPUT, client=make_client(transport))

    def test_route_business_mismatch_is_response_error(self):
        bad = dict(OMAR_ROUTE, business_id="scan")
        transport = FakeTransport(payload={"ok": True, "route": bad})
        with self.assertRaises(OmarResponseError):
            route_for_brain_output(BRAIN_OUTPUT, client=make_client(transport))

    def test_no_key_configured_raises_before_any_http(self):
        transport = FakeTransport()
        client = OmarClient(base_url="https://omar.example.test", api_key=None,
                            transport=transport)
        with self.assertRaises(OmarConfigError):
            route_for_brain_output(BRAIN_OUTPUT, client=client)
        self.assertEqual(transport.calls, [])

    def test_client_route_rejects_unknown_omar_id_without_http(self):
        transport = FakeTransport()
        with self.assertRaises(UnknownBusinessError):
            make_client(transport).route("no-existe")
        self.assertEqual(transport.calls, [])


class ConfigTests(unittest.TestCase):
    def test_key_repr_never_leaks(self):
        client = make_client(FakeTransport())
        self.assertNotIn("test-key", repr(client))

    def test_from_env_reads_key_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "key"
            key_path.write_text("file-key\n", encoding="utf-8")
            transport = FakeTransport()
            client = OmarClient.from_env(
                {"OMAR_API_KEY_FILE": str(key_path),
                 "OMAR_CORE_BASE_URL": "https://omar.example.test"},
                transport=transport)
            route_for_brain_output(BRAIN_OUTPUT, client=client)
            self.assertEqual(transport.calls[0]["headers"]["X-Omar-Key"], "file-key")
            self.assertTrue(transport.calls[0]["url"].startswith("https://omar.example.test"))

    def test_from_env_prefers_direct_key(self):
        transport = FakeTransport()
        client = OmarClient.from_env({"OMAR_API_KEY": "direct-key"}, transport=transport)
        route_for_brain_output(BRAIN_OUTPUT, client=client)
        self.assertEqual(transport.calls[0]["headers"]["X-Omar-Key"], "direct-key")


if __name__ == "__main__":
    unittest.main()
