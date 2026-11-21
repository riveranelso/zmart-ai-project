"""Unit tests for zion_core.meta_leadgen (ZeroLag Lead Ads ingestion).

All 13 mandatory tests. No network calls (urllib mocked), no secrets
(dummy values only), no PII in assertions beyond synthetic fixtures.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from zion_core.meta_leadgen import (
    LeadDedupeStore,
    MetaWebhookError,
    N8nForwarder,
    ZeroLagLeadReceiver,
    fetch_lead_graph,
    parse_form_allowlist,
    translate_lead_fields,
    translate_leadgen_payload,
)


# ---------------------------------------------------------------------------
# Fixtures (synthetic only)
# ---------------------------------------------------------------------------

_DUMMY_VERIFY_TOKEN = "dummy-verify-token-abc123"
_DUMMY_APP_SECRET = "dummy-app-secret-xyz789"
_DUMMY_PAGE_TOKEN = "dummy-page-token-000"
_DUMMY_N8N_URL = "https://n8n.example.test/webhook/meta-leads"
_DUMMY_LEADGEN_ID = "LG_SYNTHETIC_001"
_DUMMY_PAGE_ID = "1026212810584297"


def _leadgen_payload(**over):
    value = {
        "leadgen_id": _DUMMY_LEADGEN_ID,
        "form_id": "FORM_SYNTH_1",
        "page_id": _DUMMY_PAGE_ID,
        "ad_id": "AD_SYNTH_1",
        "adgroup_id": "ADSET_SYNTH_1",
        "created_time": "2026-10-07T04:00:00+0000",
    }
    value.update(over.get("value", {}))
    payload = {
        "object": over.get("object", "page"),
        "entry": [
            {
                "id": _DUMMY_PAGE_ID,
                "time": 1790000000,
                "changes": [
                    {"field": over.get("field", "leadgen"), "value": value}
                ],
            }
        ],
    }
    if "business_id" in over:  # spoof attempt injection
        payload["business_id"] = over["business_id"]
    return payload


def _sign(body: bytes, secret: str = _DUMMY_APP_SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class _FakeHTTPResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _graph_lead_json() -> bytes:
    return json.dumps({
        "id": _DUMMY_LEADGEN_ID,
        "form_id": "FORM_SYNTH_1",
        "ad_id": "AD_SYNTH_1",
        "created_time": "2026-10-07T04:00:00+0000",
        "field_data": [
            {"name": "full_name", "values": ["Test Lead Synthetic"]},
            {"name": "phone_number", "values": ["+15550100001"]},
            {"name": "email", "values": ["synthetic@example.test"]},
            {"name": "city", "values": ["Orlando"]},
            {"name": "what_service", "values": ["Fiber internet"]},
        ],
    }).encode()


class LeadgenTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._env_patch = mock.patch.dict(
            "os.environ",
            {
                "ZEROLAG_WEBHOOK_VERIFY_TOKEN": _DUMMY_VERIFY_TOKEN,
                "META_APP_SECRET": _DUMMY_APP_SECRET,
                "META_PAGE_TOKEN": _DUMMY_PAGE_TOKEN,
                "N8N_META_LEADS_URL": _DUMMY_N8N_URL,
            },
            clear=False,
        )
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)
        # No sleeping in retry/backoff paths.
        self._sleep_patch = mock.patch("time.sleep", return_value=None)
        self._sleep_patch.start()
        self.addCleanup(self._sleep_patch.stop)
        # Route the module's urllib.error catches to our fakes.
        import urllib.error as _urlerror

        self._http_err_patch = mock.patch.object(
            _urlerror, "HTTPError", _FakeHTTPError)
        self._url_err_patch = mock.patch.object(
            _urlerror, "URLError", _FakeURLError)
        self._http_err_patch.start()
        self._url_err_patch.start()
        self.addCleanup(self._http_err_patch.stop)
        self.addCleanup(self._url_err_patch.stop)

    def _receiver(self, **kw):
        store = Path(self._tmp.name) / "leadgen.db"
        return ZeroLagLeadReceiver(
            verify_token_ref="env:ZEROLAG_WEBHOOK_VERIFY_TOKEN",
            app_secret_ref="env:META_APP_SECRET",
            page_token_ref="env:META_PAGE_TOKEN",
            n8n_url_ref="env:N8N_META_LEADS_URL",
            store_path=store,
            **kw,
        )

    def _urlopen_mock(self, graph_ok=True, n8n_ok=True, n8n_fail_times=0):
        """Mock urlopen: records calls, dispatches by URL."""
        calls = {"graph": 0, "n8n": 0, "urls": []}
        n8n_failures = {"left": n8n_fail_times}

        def fake(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
            calls["urls"].append(url)
            if "graph.facebook.com" in url:
                calls["graph"] += 1
                if not graph_ok:
                    raise _FakeURLError("graph down")
                return _FakeHTTPResponse(_graph_lead_json())
            calls["n8n"] += 1
            if n8n_failures["left"] > 0:
                n8n_failures["left"] -= 1
                raise _FakeHTTPError(500)
            if not n8n_ok:
                raise _FakeHTTPError(500)
            return _FakeHTTPResponse(b'{"ok":true}', status=200)

        return calls, fake

    # -- 1. verification challenge -------------------------------------
    def test_01_verification_challenge_valid(self):
        r = self._receiver()
        status, body = r.verify_get({
            "hub.mode": "subscribe",
            "hub.verify_token": _DUMMY_VERIFY_TOKEN,
            "hub.challenge": "CHALLENGE_123",
        })
        self.assertEqual(status, 200)
        self.assertEqual(body, "CHALLENGE_123")

    def test_01b_verification_challenge_wrong_token(self):
        r = self._receiver()
        status, body = r.verify_get({
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "CHALLENGE_123",
        })
        self.assertEqual(status, 403)
        self.assertNotIn("CHALLENGE_123", body)

    # -- 2. signature valid --------------------------------------------
    def test_02_signature_valid_accepted(self):
        r = self._receiver()
        body = json.dumps(_leadgen_payload()).encode()
        calls, fake = self._urlopen_mock()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            report = r.ingest_post(body, _sign(body))
        self.assertEqual(report.status, 200)
        self.assertTrue(report.body.get("ok"))
        self.assertEqual(calls["graph"], 1)
        self.assertEqual(calls["n8n"], 1)

    # -- 3. signature invalid/missing/malformed -------------------------
    def test_03_signature_invalid_rejected(self):
        r = self._receiver()
        body = json.dumps(_leadgen_payload()).encode()
        report = r.ingest_post(body, _sign(body, secret="wrong-secret"))
        self.assertEqual(report.status, 401)

    def test_03b_signature_missing_rejected(self):
        r = self._receiver()
        body = json.dumps(_leadgen_payload()).encode()
        report = r.ingest_post(body, None)
        self.assertEqual(report.status, 401)

    def test_03c_signature_malformed_rejected(self):
        r = self._receiver()
        body = json.dumps(_leadgen_payload()).encode()
        report = r.ingest_post(body, "not-a-valid-signature")
        self.assertEqual(report.status, 401)

    # -- 4. leadgen payload translation --------------------------------
    def test_04_translate_leadgen_payload(self):
        events = translate_leadgen_payload(_leadgen_payload())
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e.leadgen_id, _DUMMY_LEADGEN_ID)
        self.assertEqual(e.page_id, _DUMMY_PAGE_ID)
        self.assertEqual(e.form_id, "FORM_SYNTH_1")
        self.assertEqual(e.ad_id, "AD_SYNTH_1")
        self.assertEqual(e.adgroup_id, "ADSET_SYNTH_1")
        self.assertEqual(e.business_id, "zerolag")  # FIXED, never from payload

    # -- 5. duplicate leadgen_id ---------------------------------------
    def test_05_duplicate_leadgen_id_no_second_processing(self):
        r = self._receiver()
        body = json.dumps(_leadgen_payload()).encode()
        sig = _sign(body)
        calls, fake = self._urlopen_mock()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            first = r.ingest_post(body, sig)
            second = r.ingest_post(body, sig)
        self.assertEqual(first.status, 200)
        self.assertEqual(second.status, 200)
        self.assertEqual(second.body.get("duplicates"), 1)
        # Graph + n8n each hit exactly once: no second processing.
        self.assertEqual(calls["graph"], 1)
        self.assertEqual(calls["n8n"], 1)

    # -- 6. Graph fetch success ----------------------------------------
    def test_06_graph_fetch_success_parsed(self):
        with mock.patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(_graph_lead_json()),
        ):
            data = fetch_lead_graph(
                _DUMMY_LEADGEN_ID, page_token=_DUMMY_PAGE_TOKEN
            )
        self.assertIn("field_data", data)
        names = [f["name"] for f in data["field_data"]]
        self.assertIn("full_name", names)

    def test_06b_translate_lead_fields(self):
        events = translate_leadgen_payload(_leadgen_payload())
        data = json.loads(_graph_lead_json().decode())
        out = translate_lead_fields(data["field_data"], event=events[0])
        self.assertEqual(out["full_name"], "Test Lead Synthetic")
        self.assertEqual(out["phone"], "+15550100001")
        self.assertEqual(out["email"], "synthetic@example.test")
        self.assertIn("Orlando", out["address"])
        self.assertEqual(out["business_id"], "zerolag")
        self.assertEqual(out["source"], "meta")
        self.assertEqual(out["custom_questions"][0]["question"], "what_service")

    # -- 7. Graph fetch failure -> pending ------------------------------
    def test_07_graph_fetch_failure_pending_no_loss(self):
        r = self._receiver()
        body = json.dumps(_leadgen_payload()).encode()
        calls, fake = self._urlopen_mock(graph_ok=False)
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            report = r.ingest_post(body, _sign(body))
        # Meta gets 200 (stops retrying); WE own the retry.
        self.assertEqual(report.status, 200)
        self.assertEqual(report.body.get("pending"), 1)
        self.assertEqual(r._store.status_of(_DUMMY_LEADGEN_ID), "fetch_pending")
        # Graph was attempted GRAPH_MAX_ATTEMPTS times (3), n8n never hit.
        self.assertEqual(calls["graph"], 3)
        self.assertEqual(calls["n8n"], 0)
        # Retry sweep recovers once Graph is back: no lead loss.
        calls2, fake2 = self._urlopen_mock(graph_ok=True, n8n_ok=True)
        with mock.patch("urllib.request.urlopen", side_effect=fake2):
            summary = r.retry_pending()
        self.assertEqual(summary["forwarded"], 1)
        self.assertEqual(r._store.status_of(_DUMMY_LEADGEN_ID), "forwarded")

    # -- 8. n8n forward success -----------------------------------------
    def test_08_n8n_forward_success(self):
        fwd = N8nForwarder(_DUMMY_N8N_URL)
        with mock.patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(b'{"ok":true}', status=200),
        ):
            self.assertTrue(fwd.post_lead({"leadgen_id": "X"}))

    # -- 9. n8n temporary failure -> retry -> pending --------------------
    def test_09_n8n_failure_pending_no_loss_no_dup(self):
        r = self._receiver()
        body = json.dumps(_leadgen_payload()).encode()
        # Graph OK, n8n always 500.
        calls, fake = self._urlopen_mock(graph_ok=True, n8n_ok=False)
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            report = r.ingest_post(body, _sign(body))
        self.assertEqual(report.status, 200)
        self.assertEqual(r._store.status_of(_DUMMY_LEADGEN_ID),
                         "forward_pending")
        n8n_calls_first = calls["n8n"]
        self.assertGreaterEqual(n8n_calls_first, 1)
        # Retry sweep recovers once n8n is back; exactly one success total.
        calls2, fake2 = self._urlopen_mock(graph_ok=True, n8n_ok=True)
        with mock.patch("urllib.request.urlopen", side_effect=fake2):
            summary = r.retry_pending()
        self.assertEqual(summary["forwarded"], 1)
        # Re-ingest after recovery is a duplicate: no second forward.
        with mock.patch("urllib.request.urlopen", side_effect=fake2):
            r.ingest_post(body, _sign(body))
        self.assertEqual(calls2["n8n"], 1)

    # -- 10. tenant isolation -------------------------------------------
    def test_10_wrong_object_rejected(self):
        r = self._receiver()
        body = json.dumps(_leadgen_payload(object="instagram")).encode()
        report = r.ingest_post(body, _sign(body))
        self.assertEqual(report.status, 400)

    def test_10b_wrong_field_safely_ignored(self):
        r = self._receiver()
        body = json.dumps(_leadgen_payload(field="comments")).encode()
        calls, fake = self._urlopen_mock()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            report = r.ingest_post(body, _sign(body))
        self.assertEqual(report.status, 200)
        self.assertEqual(report.body.get("accepted"), 0)
        self.assertEqual(calls["graph"], 0)
        self.assertEqual(calls["n8n"], 0)

    def test_10c_caller_business_id_spoof_never_trusted(self):
        spoofed = _leadgen_payload(business_id="los-duros")
        events = translate_leadgen_payload(spoofed)
        self.assertEqual(events[0].business_id, "zerolag")
        # End-to-end: forwarded payload also carries zerolag only.
        r = self._receiver()
        body = json.dumps(spoofed).encode()
        forwarded = {}
        calls, fake = self._urlopen_mock()
        orig = fake

        def capture(req, timeout=None):
            url = req.full_url
            if "graph.facebook.com" in url:
                return orig(req, timeout)
            forwarded.update(json.loads(req.data.decode()))
            return _FakeHTTPResponse(b'{"ok":true}', status=200)

        with mock.patch("urllib.request.urlopen", side_effect=capture):
            r.ingest_post(body, _sign(body))
        self.assertEqual(forwarded.get("business_id"), "zerolag")

    def test_10d_page_id_allowlist_enforced(self):
        r = self._receiver(expected_page_id="DIFFERENT_PAGE_ID")
        body = json.dumps(_leadgen_payload()).encode()
        calls, fake = self._urlopen_mock()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            report = r.ingest_post(body, _sign(body))
        self.assertEqual(report.status, 200)
        self.assertEqual(calls["graph"], 0)
        self.assertEqual(calls["n8n"], 0)

    def test_10e_form_allowlist_blocks_unauthorized_form(self):
        r = self._receiver(allowed_form_ids=frozenset({"FORM-AUTHORIZED"}))
        body = json.dumps(_leadgen_payload(value={"form_id": "FORM-RECRUITING"})).encode()
        calls, fake = self._urlopen_mock()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            report = r.ingest_post(body, _sign(body))
        self.assertEqual(report.status, 200)
        self.assertEqual(report.body.get("ignored_form"), 1)
        self.assertEqual(report.body.get("processed"), 0)
        self.assertEqual(calls["graph"], 0)  # no Graph fetch
        self.assertEqual(calls["n8n"], 0)    # no forward, no Gmail

    def test_10f_form_allowlist_allows_authorized_form(self):
        r = self._receiver(allowed_form_ids=frozenset({"FORM-AUTHORIZED"}))
        body = json.dumps(_leadgen_payload(value={"form_id": "FORM-AUTHORIZED"})).encode()
        calls, fake = self._urlopen_mock()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            report = r.ingest_post(body, _sign(body))
        self.assertEqual(report.status, 200)
        self.assertEqual(report.body.get("ignored_form"), 0)
        self.assertEqual(report.body.get("processed"), 1)
        self.assertEqual(calls["n8n"], 1)

    def test_10g_form_allowlist_unset_allows_all(self):
        r = self._receiver(allowed_form_ids=None)
        body = json.dumps(_leadgen_payload(value={"form_id": "FORM-ANYTHING"})).encode()
        calls, fake = self._urlopen_mock()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            report = r.ingest_post(body, _sign(body))
        self.assertEqual(report.body.get("processed"), 1)

    def test_10h_form_allowlist_missing_form_id_ignored(self):
        r = self._receiver(allowed_form_ids=frozenset({"FORM-AUTHORIZED"}))
        payload = _leadgen_payload()
        del payload["entry"][0]["changes"][0]["value"]["form_id"]
        body = json.dumps(payload).encode()
        calls, fake = self._urlopen_mock()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            report = r.ingest_post(body, _sign(body))
        self.assertEqual(report.status, 200)
        self.assertEqual(report.body.get("ignored_form"), 1)
        self.assertEqual(calls["n8n"], 0)

    def test_10i_parse_form_allowlist(self):
        self.assertIsNone(parse_form_allowlist(None))
        self.assertIsNone(parse_form_allowlist(""))
        self.assertIsNone(parse_form_allowlist("   "))
        self.assertEqual(
            parse_form_allowlist("A,B , C"), frozenset({"A", "B", "C"})
        )

    # -- 11. zero duplicate Gmail (dedupe prevents 2nd forward) ----------
    def test_11_zero_duplicate_forward(self):
        r = self._receiver()
        body = json.dumps(_leadgen_payload()).encode()
        sig = _sign(body)
        calls, fake = self._urlopen_mock()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            r.ingest_post(body, sig)
            r.ingest_post(body, sig)
            r.ingest_post(body, sig)
        self.assertEqual(calls["n8n"], 1)

    # -- 12. zero loops (no self-triggering) ------------------------------
    def test_12_zero_loops(self):
        r = self._receiver()
        body = json.dumps(_leadgen_payload()).encode()
        calls, fake = self._urlopen_mock()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            r.ingest_post(body, _sign(body))
        for url in calls["urls"]:
            self.assertNotIn("/meta/webhooks/leadgen", url)
            self.assertTrue(
                url.startswith("https://graph.facebook.com")
                or url == _DUMMY_N8N_URL
            )

    # -- 13. no secret/PII leakage in logs -------------------------------
    def test_13_no_secret_pii_in_logs(self):
        r = self._receiver()
        body = json.dumps(_leadgen_payload()).encode()
        calls, fake = self._urlopen_mock()
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        # _log_event is reused by import from meta_webhook: it writes to
        # the zion.meta_webhook logger. Capture there.
        zlog = logging.getLogger("zion.meta_webhook")
        zlog.addHandler(handler)
        zlog.setLevel(logging.INFO)
        try:
            with mock.patch("urllib.request.urlopen", side_effect=fake):
                r.ingest_post(body, _sign(body))
                r.verify_get({
                    "hub.mode": "subscribe",
                    "hub.verify_token": _DUMMY_VERIFY_TOKEN,
                    "hub.challenge": "CHALLENGE_XYZ",
                })
        finally:
            zlog.removeHandler(handler)
        logs = stream.getvalue()
        for secret in (
            _DUMMY_VERIFY_TOKEN, _DUMMY_APP_SECRET, _DUMMY_PAGE_TOKEN,
        ):
            self.assertNotIn(secret, logs)
        for pii in (
            "Test Lead Synthetic", "+15550100001", "synthetic@example.test",
            _DUMMY_LEADGEN_ID, "CHALLENGE_XYZ",
        ):
            self.assertNotIn(pii, logs)
        # Observability still works (events emitted, opaque hashes only).
        self.assertIn("webhook_received", logs)
        self.assertIn("webhook_complete", logs)


class _FakeURLError(Exception):
    pass


class _FakeHTTPError(Exception):
    def __init__(self, code: int):
        super().__init__(f"HTTP {code}")
        self.code = code


if __name__ == "__main__":
    unittest.main()
