"""Adversarial tests (layer: UNIT) for the Brain -> Omar bridge + service.

Written by the independent reviewer in the builder/reviewer loop
(2026-11-20). The author of this file did NOT write the code under
test. Every test encodes the CONTRACT the bridge must satisfy:

- business_id translation 'zmart' -> 'zmart-consumer'; anything
  unmapped fails closed with a typed error, never a raw exception.
- The Omar key lives only in the environment; a caller with no key or
  a wrong key is rejected (401); unknown business_id -> 400.
- Malformed input (bad types, bad Content-Length, pathological JSON,
  wrong HTTP method) gets a typed/JSON rejection — never a dropped
  connection, a pinned handler thread, or a stdlib HTML error page.

Against the current build these tests are EXPECTED TO FAIL: each
failure is a confirmed defect, listed in the reviewer's report. All
HTTP to Omar is faked through an injected transport; the service runs
on an ephemeral loopback port, like tests/test_brain_omar_bridge_service.py.
"""
import json
import socket
import threading
import unittest
import urllib.error
import urllib.request

from brain_omar_bridge import (
    BrainContractError,
    OmarClient,
    OmarConfigError,
    UnknownBusinessError,
    route_for_brain_output,
)
from brain_omar_bridge_service.service import create_server

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

OMAR_ROUTE = {"business_id": "zmart-consumer", "name": "Zmart Consumer Rights"}


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


def make_client(transport, **kwargs):
    return OmarClient(base_url="https://omar.example.test", api_key="test-key",
                      transport=transport, **kwargs)


class BridgeTypeSafetyTests(unittest.TestCase):
    """Wrong-typed gate fields must raise typed bridge errors, not TypeError."""

    def test_unhashable_escalation_route_list_raises_contract_error(self):
        # bridge.py validate_brain_output: `x not in ESCALATION_ROUTES`
        # raises TypeError (unhashable) for a list value instead of the
        # promised BrainContractError.
        with self.assertRaises(BrainContractError):
            route_for_brain_output(dict(BRAIN_OUTPUT, escalation_route=["routine"]),
                                   client=make_client(FakeTransport()))

    def test_unhashable_escalation_route_dict_raises_contract_error(self):
        with self.assertRaises(BrainContractError):
            route_for_brain_output(dict(BRAIN_OUTPUT, escalation_route={"r": 1}),
                                   client=make_client(FakeTransport()))

    def test_non_mapping_payload_raises_contract_error(self):
        # route_for_brain_output promises "a BridgeError subclass on any
        # doubt"; a list payload crashes with AttributeError instead.
        with self.assertRaises(BrainContractError):
            route_for_brain_output([1, 2, 3], client=make_client(FakeTransport()))

    def test_client_route_unhashable_business_id_raises_unknown_business(self):
        # OmarClient.route: `business_id not in OMAR_BUSINESS_IDS` raises
        # TypeError for an unhashable id instead of UnknownBusinessError.
        with self.assertRaises(UnknownBusinessError):
            make_client(FakeTransport()).route(["zmart-consumer"])


class ConfigRobustnessTests(unittest.TestCase):
    """A bad key-file path must surface as OmarConfigError, not a raw OSError."""

    def test_missing_key_file_raises_config_error(self):
        # bridge.py OmarClient.from_env: Path.read_text raises
        # FileNotFoundError, which in service.main() kills the process
        # before /health ever comes up.
        with self.assertRaises(OmarConfigError):
            OmarClient.from_env({"OMAR_API_KEY_FILE": "/nonexistent/missing-key"})

    def test_key_file_pointing_at_directory_raises_config_error(self):
        with self.assertRaises(OmarConfigError):
            OmarClient.from_env({"OMAR_API_KEY_FILE": "/tmp"})


class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        client = OmarClient(base_url="https://omar.example.test",
                            api_key="test-key", transport=self.transport)
        self.server = create_server("127.0.0.1", 0, client)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path, body=None, headers=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        for name, value in (headers or {}).items():
            req.add_header(name, value)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def raw_exchange(self, request_bytes, timeout=4.0):
        """Send raw bytes; return whatever comes back ('' if the server
        drops the connection or never answers within `timeout`)."""
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=timeout)
        try:
            sock.sendall(request_bytes)
            chunks = []
            try:
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
            except socket.timeout:
                pass
            return b"".join(chunks).decode("utf-8", "replace")
        finally:
            sock.close()


class ServiceAuthTests(ServiceTestCase):
    def test_route_rejects_caller_with_no_credential(self):
        # Contract: no key -> 401. The handler never reads any caller
        # credential, so a completely unauthenticated POST is routed
        # with the bridge's own Omar key (service is a public Fly
        # http_service per brain_omar_bridge_service/fly.toml).
        status, _ = self.request("POST", "/bridge/route", BRAIN_OUTPUT)
        self.assertEqual(status, 401)
        self.assertEqual(self.transport.calls, [])

    def test_unknown_business_id_is_400(self):
        # Contract: unknown business_id -> 400. The service maps
        # UnknownBusinessError to 422 (its README documents 422 as a
        # deliberate choice — contract conflict for the owner to settle).
        status, _ = self.request("POST", "/bridge/route",
                                 dict(BRAIN_OUTPUT, business_id="acme"))
        self.assertEqual(status, 400)


class ServiceMalformedInputTests(ServiceTestCase):
    def test_negative_content_length_gets_400_not_dropped_connection(self):
        # service.py do_POST: rfile.read(-5) raises ValueError inside the
        # handler; the caller gets an empty reply (connection dropped)
        # instead of the documented JSON error.
        response = self.raw_exchange(
            b"POST /bridge/route HTTP/1.0\r\nHost: x\r\n"
            b"Content-Type: application/json\r\nContent-Length: -5\r\n\r\n")
        self.assertTrue(response.startswith("HTTP/"), repr(response[:80]))
        self.assertIn(" 400 ", response.split("\r\n", 1)[0])
        self.assertIn('"ok": false', response)

    def test_content_length_minus_one_does_not_pin_the_handler(self):
        # Content-Length: -1 makes rfile.read(-1) block until EOF: one
        # request pins a handler thread indefinitely (thread-exhaustion
        # DoS against ThreadingHTTPServer). A timely 400 is required.
        response = self.raw_exchange(
            b"POST /bridge/route HTTP/1.0\r\nHost: x\r\n"
            b"Content-Type: application/json\r\nContent-Length: -1\r\n\r\n",
            timeout=3.0)
        self.assertIn(" 400 ", response.split("\r\n", 1)[0] if response else "")

    def test_deeply_nested_json_gets_400_not_dropped_connection(self):
        # 120 KB of nesting fits under MAX_BODY_BYTES (256 KB) but blows
        # the JSON decoder's recursion limit; RecursionError is not in
        # do_POST's except (ValueError, UnicodeDecodeError), so the
        # connection drops with no response at all.
        nested = b"[" * 60000 + b"]" * 60000
        response = self.raw_exchange(
            b"POST /bridge/route HTTP/1.0\r\nHost: x\r\n"
            b"Content-Type: application/json\r\nContent-Length: "
            + str(len(nested)).encode() + b"\r\n\r\n" + nested)
        self.assertTrue(response.startswith("HTTP/"), repr(response[:80]))
        self.assertIn(" 400 ", response.split("\r\n", 1)[0])
        self.assertIn("InvalidJsonBody", response)

    def test_unsupported_method_gets_json_error_not_stdlib_501(self):
        # The service defines only do_GET/do_POST; BaseHTTPRequestHandler
        # answers PUT with its own 501 HTML page, breaking the service's
        # documented "non-200 -> {"ok": false, "error": ...}" contract.
        status, raw = self.request("PUT", "/bridge/route", BRAIN_OUTPUT)
        self.assertIn(status, (404, 405))
        self.assertEqual(json.loads(raw)["ok"], False)


if __name__ == "__main__":
    unittest.main()
