"""Adversarial tests for the Meta webhook receiver (zion_core.meta_webhook).

Covers: GET verification contract, POST signature security (official Meta
X-Hub-Signature-256 scheme over raw bytes), payload translation, tenant
fixing / cross-tenant spoof attempts, dedupe of Meta retries, the
never-publish invariant, secret hygiene (env: refs only, no leakage), and
a loopback smoke test of the real stdlib HTTP adapter.

All secrets/tokens/ids here are synthetic.
"""
import hashlib
import hmac
import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from zion_core import meta_webhook as mw
from zion_core.meta_webhook import (
    CALLBACK_PATH,
    MetaWebhookError,
    MetaWebhookReceiver,
    build_los_duros_instagram_integration,
    handle_verification_request,
    receiver_from_env,
    resolve_secret_ref,
    translate_instagram_payload,
    verify_post_signature,
)

# Synthetic-only values. Never real credentials.
VERIFY_TOKEN = "synthetic-verify-token-9f8e7d6c5b4a39281736"
APP_SECRET = "synthetic-app-secret-aaaabbbbccccdddd0000"
ACCOUNT_ID = "17841409999999999"
OTHER_ACCOUNT_ID = "17841408888888888"
CHALLENGE = "synthetic-challenge-12345"


def _sign(body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


def _payload(
    field="comments",
    entry_id=ACCOUNT_ID,
    comment_id="cmt-1001",
    text="esto está duro, me encanta",
    sender="user-4242",
    media="media-777",
    parent=None,
    obj="instagram",
    extra_value=None,
):
    value = {
        "id": comment_id,
        "from": {"id": sender, "username": "fanpr"},
        "text": text,
        "media": {"id": media, "media_product_type": "FEED"},
    }
    if parent is not None:
        value["parent_id"] = parent
    if extra_value:
        value.update(extra_value)
    return {
        "object": obj,
        "entry": [
            {
                "id": entry_id,
                "time": 1759530000,
                "changes": [{"field": field, "value": value}],
            }
        ],
    }


def _raw(payload) -> bytes:
    # ensure_ascii=True mirrors what Meta signs (escaped unicode).
    return json.dumps(payload, ensure_ascii=True).encode("utf-8")


def _registry_with_los_duros(tmp: str) -> Path:
    reg = Path(tmp) / "reg.json"
    reg.write_text(
        json.dumps(
            {
                "businesses": {
                    "los-duros": {
                        "display_name": "Los Duros",
                        "enabled": True,
                        "isolation_key": "los-duros",
                        "context_refs": ["biblia/los-duros"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return reg


class ReceiverFixture(unittest.TestCase):
    def setUp(self):
        self._saved_env = dict(os.environ)
        os.environ["LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN"] = VERIFY_TOKEN
        os.environ["META_APP_SECRET"] = APP_SECRET
        os.environ["LOS_DUROS_IG_ACCOUNT_ID"] = ACCOUNT_ID
        self._tmp = tempfile.TemporaryDirectory()
        self.registry_path = _registry_with_los_duros(self._tmp.name)
        self.receiver = MetaWebhookReceiver(
            integration=build_los_duros_instagram_integration(
                instagram_account_id=ACCOUNT_ID
            ),
            registry_path=self.registry_path,
        )

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved_env)
        self._tmp.cleanup()

    def _post(self, payload, secret=APP_SECRET, header="auto"):
        body = _raw(payload)
        sig = _sign(body, secret) if header == "auto" else header
        return self.receiver.ingest_post(body, sig), body


class GetVerificationTests(ReceiverFixture):
    def test_correct_token_returns_challenge_verbatim(self):
        status, body = self.receiver.verify_get(
            {
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": CHALLENGE,
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, CHALLENGE)

    def test_incorrect_token_fails_closed(self):
        status, body = self.receiver.verify_get(
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": CHALLENGE,
            }
        )
        self.assertEqual(status, 403)
        self.assertNotEqual(body, CHALLENGE)
        self.assertNotIn(VERIFY_TOKEN, body)

    def test_missing_token_fails_closed(self):
        status, _ = self.receiver.verify_get(
            {"hub.mode": "subscribe", "hub.challenge": CHALLENGE}
        )
        self.assertEqual(status, 403)

    def test_wrong_mode_fails_closed(self):
        status, body = self.receiver.verify_get(
            {
                "hub.mode": "unsubscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": CHALLENGE,
            }
        )
        self.assertEqual(status, 403)
        self.assertNotEqual(body, CHALLENGE)

    def test_missing_challenge_fails_closed(self):
        status, _ = self.receiver.verify_get(
            {"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN}
        )
        self.assertEqual(status, 403)

    def test_empty_query_fails_closed(self):
        status, _ = self.receiver.verify_get({})
        self.assertEqual(status, 403)

    def test_pure_function_rejects_unconfigured_token(self):
        with self.assertRaises(MetaWebhookError):
            handle_verification_request(
                {"hub.mode": "subscribe", "hub.verify_token": "x",
                 "hub.challenge": "y"},
                expected_verify_token="",
            )


class PostSignatureTests(ReceiverFixture):
    def test_valid_signature_accepted(self):
        body = _raw(_payload())
        verify_post_signature(body, _sign(body), app_secret=APP_SECRET)

    def test_invalid_signature_rejected(self):
        body = _raw(_payload())
        with self.assertRaises(MetaWebhookError) as ctx:
            verify_post_signature(body, _sign(body, "wrong-secret"),
                                  app_secret=APP_SECRET)
        self.assertEqual(str(ctx.exception), "SIGNATURE_INVALID")

    def test_missing_signature_rejected(self):
        with self.assertRaises(MetaWebhookError) as ctx:
            verify_post_signature(b"{}", None, app_secret=APP_SECRET)
        self.assertEqual(str(ctx.exception), "SIGNATURE_MISSING")

    def test_malformed_signature_rejected(self):
        for bad in ("sha256=zzz", "sha256=", "not-a-signature",
                    "md5=" + "a" * 32, "sha256=" + "g" * 64):
            with self.assertRaises(MetaWebhookError) as ctx:
                verify_post_signature(b"{}", bad, app_secret=APP_SECRET)
            self.assertEqual(str(ctx.exception), "SIGNATURE_MALFORMED")

    def test_empty_signature_treated_as_missing(self):
        with self.assertRaises(MetaWebhookError) as ctx:
            verify_post_signature(b"{}", "", app_secret=APP_SECRET)
        self.assertEqual(str(ctx.exception), "SIGNATURE_MISSING")

    def test_tampered_body_rejected(self):
        body = _raw(_payload())
        sig = _sign(body)
        tampered = body.replace(b"me encanta", b"me encanta!")
        with self.assertRaises(MetaWebhookError):
            verify_post_signature(tampered, sig, app_secret=APP_SECRET)

    def test_signature_is_over_raw_bytes_not_reserialized(self):
        # Emoji payload: re-serializing (key order / unicode escaping) must
        # NOT be what gets signed. Sign the exact bytes Meta would send.
        payload = _payload(text="esto está duro 🔥🇵🇷", comment_id="cmt-emoji-1")
        body = _raw(payload)
        report, _ = self._post(payload)
        self.assertEqual(report.status, 200)
        self.assertEqual(report.body["processed"], 1)

    def test_missing_signature_header_gives_401(self):
        report, _ = self._post(_payload(), header=None)
        self.assertEqual(report.status, 401)
        self.assertFalse(report.body["ok"])

    def test_invalid_signature_gives_401(self):
        report, _ = self._post(_payload(), secret="wrong-secret")
        self.assertEqual(report.status, 401)

    def test_malformed_json_gives_400(self):
        body = b'{"object": "instagram", "entry": ['
        report = self.receiver.ingest_post(body, _sign(body))
        self.assertEqual(report.status, 400)
        self.assertEqual(report.body["error"], "MALFORMED_JSON")

    def test_non_dict_json_gives_400(self):
        body = b"[1, 2, 3]"
        report = self.receiver.ingest_post(body, _sign(body))
        self.assertEqual(report.status, 400)


class TranslationTests(ReceiverFixture):
    def test_comments_field_translates_to_canonical_comment(self):
        result = translate_instagram_payload(_payload(comment_id="cmt-1"))
        self.assertEqual(len(result.accepted), 1)
        change = result.accepted[0]
        self.assertEqual(change.raw["event_type"], "comment")
        self.assertEqual(change.raw["channel"], "instagram")
        self.assertEqual(change.raw["message_id"], "cmt-1")
        self.assertEqual(change.raw["sender_id"], "user-4242")
        self.assertEqual(change.raw["conversation_id"], "media-777")
        self.assertEqual(change.native_field, "comments")
        self.assertIn("meta:instagram:comments:cmt-1", change.raw["raw_event_ref"])
        self.assertEqual(change.event_identity,
                         {"channel": "instagram", "identity": ACCOUNT_ID})
        # Caller claims are never forwarded.
        self.assertNotIn("business_id", change.raw)
        self.assertNotIn("brand_id", change.raw)

    def test_live_comments_field_accepted(self):
        result = translate_instagram_payload(
            _payload(field="live_comments", comment_id="live-9")
        )
        self.assertEqual(len(result.accepted), 1)
        self.assertEqual(result.accepted[0].native_field, "live_comments")
        self.assertEqual(result.accepted[0].raw["event_type"], "comment")

    def test_unsupported_field_skipped_safely(self):
        for field in ("mentions", "messages", "story_insights", "messaging_seen"):
            result = translate_instagram_payload(_payload(field=field))
            self.assertEqual(result.accepted, ())
            self.assertEqual(result.skipped_unsupported, 1)

    def test_non_instagram_object_rejected(self):
        with self.assertRaises(MetaWebhookError) as ctx:
            translate_instagram_payload(_payload(obj="page"))
        self.assertEqual(str(ctx.exception), "OBJECT_NOT_INSTAGRAM")

    def test_missing_identifiers_skipped_fail_safe(self):
        payload = _payload()
        del payload["entry"][0]["changes"][0]["value"]["id"]
        result = translate_instagram_payload(payload)
        self.assertEqual(result.accepted, ())
        self.assertEqual(result.skipped_invalid, 1)

    def test_missing_sender_skipped_fail_safe(self):
        payload = _payload()
        del payload["entry"][0]["changes"][0]["value"]["from"]
        result = translate_instagram_payload(payload)
        self.assertEqual(result.accepted, ())
        self.assertEqual(result.skipped_invalid, 1)

    def test_empty_entry_rejected(self):
        with self.assertRaises(MetaWebhookError):
            translate_instagram_payload({"object": "instagram", "entry": []})

    def test_reply_parent_id_preserved(self):
        result = translate_instagram_payload(
            _payload(comment_id="cmt-r1", parent="cmt-parent-0")
        )
        self.assertEqual(result.accepted[0].raw["parent_id"], "cmt-parent-0")

    def test_comment_id_alias_accepted(self):
        payload = _payload()
        value = payload["entry"][0]["changes"][0]["value"]
        value["comment_id"] = value.pop("id")
        result = translate_instagram_payload(payload)
        self.assertEqual(result.accepted[0].raw["message_id"], "cmt-1001")


class IngestPipelineTests(ReceiverFixture):
    def test_valid_comments_event_processed_tenant_fixed(self):
        report, _ = self._post(_payload(comment_id="cmt-a1"))
        self.assertEqual(report.status, 200)
        self.assertTrue(report.body["ok"])
        self.assertEqual(report.body["processed"], 1)
        self.assertEqual(report.body["duplicates"], 0)
        result = report.results[0]
        self.assertEqual(result.event.business_id_internal, "los-duros")
        self.assertEqual(result.event.brand_id_internal, "los-duros")
        self.assertEqual(result.event.channel, "instagram")
        self.assertFalse(result.duplicate)

    def test_valid_live_comments_event_processed(self):
        report, _ = self._post(
            _payload(field="live_comments", comment_id="live-a2")
        )
        self.assertEqual(report.status, 200)
        self.assertEqual(report.body["processed"], 1)
        result = report.results[0]
        self.assertEqual(result.event.business_id_internal, "los-duros")
        self.assertIn("live_comments", result.event.raw_event_ref or "")

    def test_routine_comment_drafts_but_builds_no_action(self):
        report, _ = self._post(
            _payload(comment_id="cmt-routine-1",
                     text="esto está duro, me encanta")
        )
        self.assertEqual(report.body["processed"], 1)
        result = report.results[0]
        self.assertEqual(result.decision.route, "ROUTINE")
        self.assertIsNotNone(result.draft)
        # The never-publish invariant: no transport intent is ever built.
        self.assertIsNone(result.action)

    def test_human_review_comment_holds_no_action(self):
        report, _ = self._post(
            _payload(comment_id="cmt-hr-1", text="ese tipo es un chota")
        )
        self.assertEqual(report.body["processed"], 1)
        result = report.results[0]
        self.assertEqual(result.decision.route, "HUMAN_REVIEW")
        self.assertIsNone(result.draft)
        self.assertIsNone(result.action)

    def test_no_automatic_publishing_across_batch(self):
        payload = _payload(comment_id="cmt-np-1")
        payload["entry"][0]["changes"].append(
            {"field": "comments",
             "value": {"id": "cmt-np-2",
                       "from": {"id": "user-7", "username": "otro"},
                       "text": "durísimo el tema nuevo",
                       "media": {"id": "media-1",
                                 "media_product_type": "REELS"}}}
        )
        report, _ = self._post(payload)
        self.assertEqual(report.body["received"], 2)
        for result in report.results:
            self.assertIsNone(result.action)
        records = self.receiver.decision_records(report)
        self.assertTrue(all(r["action_built"] is False for r in records))

    def test_duplicate_delivery_is_idempotent(self):
        payload = _payload(comment_id="cmt-dup-1")
        first, _ = self._post(payload)
        second, _ = self._post(payload)
        self.assertEqual(first.status, 200)
        self.assertEqual(first.body["processed"], 1)
        self.assertEqual(second.status, 200)
        self.assertEqual(second.body["processed"], 0)
        self.assertEqual(second.body["duplicates"], 1)
        self.assertTrue(second.results[0].duplicate)
        self.assertIsNone(second.results[0].draft)
        self.assertIsNone(second.results[0].action)

    def test_cross_tenant_spoof_wrong_account_rejected(self):
        report, _ = self._post(_payload(entry_id=OTHER_ACCOUNT_ID,
                                        comment_id="cmt-spoof-1"))
        self.assertEqual(report.status, 200)
        self.assertEqual(report.body["processed"], 0)
        self.assertEqual(report.body["rejected"], 1)
        self.assertEqual(report.results, ())

    def test_smuggled_business_claim_is_ignored(self):
        report, _ = self._post(
            _payload(comment_id="cmt-smug-1",
                     extra_value={"business_id": "zmart-consumer-rights",
                                  "brand_id": "zmart"})
        )
        self.assertEqual(report.body["processed"], 1)
        result = report.results[0]
        self.assertEqual(result.event.business_id_internal, "los-duros")
        self.assertEqual(result.event.brand_id_internal, "los-duros")

    def test_unsupported_field_never_reaches_pipeline(self):
        report, _ = self._post(_payload(field="mentions",
                                        comment_id="cmt-men-1"))
        self.assertEqual(report.status, 200)
        self.assertEqual(report.body["processed"], 0)
        self.assertEqual(report.body["skipped_unsupported"], 1)
        self.assertEqual(report.results, ())

    def test_missing_identifiers_never_reach_pipeline(self):
        payload = _payload(comment_id="cmt-bad-1")
        del payload["entry"][0]["changes"][0]["value"]["id"]
        report, _ = self._post(payload)
        self.assertEqual(report.status, 200)
        self.assertEqual(report.body["processed"], 0)
        self.assertEqual(report.body["skipped_invalid"], 1)

    def test_tenant_isolation_every_result_bound_to_los_duros(self):
        payload = _payload(comment_id="cmt-iso-1")
        payload["entry"].append(
            {"id": ACCOUNT_ID, "time": 1759530001,
             "changes": [{"field": "live_comments",
                          "value": {"id": "cmt-iso-2",
                                    "from": {"id": "user-9",
                                             "username": "fan2"},
                                    "text": "en vivo!",
                                    "media": {"id": "live-3",
                                              "media_product_type": "LIVE"}}}]}
        )
        report, _ = self._post(payload)
        self.assertEqual(report.body["processed"], 2)
        for result in report.results:
            self.assertEqual(result.event.business_id_internal, "los-duros")
            self.assertEqual(result.event.brand_id_internal, "los-duros")
            self.assertEqual(result.event.integration_id,
                             "ig-losduros-webhook-1")

    def test_decision_records_carry_no_text_no_secrets(self):
        report, _ = self._post(_payload(comment_id="cmt-rec-1"))
        records = self.receiver.decision_records(report)
        self.assertEqual(len(records), 1)
        blob = json.dumps(records)
        self.assertNotIn(VERIFY_TOKEN, blob)
        self.assertNotIn(APP_SECRET, blob)
        self.assertNotIn("me encanta", blob)

    def test_error_bodies_never_leak_secrets(self):
        bodies = []
        for query in ({}, {"hub.mode": "subscribe"}):
            _, body = self.receiver.verify_get(query)
            bodies.append(body)
        for sig in (None, "bad", _sign(b"{}", "wrong")):
            report = self.receiver.ingest_post(b"{}", sig)
            bodies.append(json.dumps(report.body))
        blob = "\n".join(bodies)
        self.assertNotIn(VERIFY_TOKEN, blob)
        self.assertNotIn(APP_SECRET, blob)


class SecretHygieneTests(unittest.TestCase):
    def test_env_ref_resolves(self):
        os.environ["MW_TEST_SECRET"] = "synthetic-value"
        try:
            self.assertEqual(resolve_secret_ref("env:MW_TEST_SECRET"),
                             "synthetic-value")
        finally:
            del os.environ["MW_TEST_SECRET"]

    def test_unset_env_fails_closed(self):
        os.environ.pop("MW_TEST_MISSING", None)
        with self.assertRaises(MetaWebhookError) as ctx:
            resolve_secret_ref("env:MW_TEST_MISSING")
        self.assertEqual(str(ctx.exception), "SECRET_ENV_UNSET")

    def test_unsupported_scheme_fails_closed(self):
        for ref in ("vault:some/path", "secret:my-secret", "config:meta",
                    "plain-token-value-12345678901234567890"):
            with self.assertRaises(MetaWebhookError):
                resolve_secret_ref(ref)

    def test_invalid_env_name_rejected(self):
        with self.assertRaises(MetaWebhookError):
            resolve_secret_ref("env:bad name!")

    def test_raw_secret_rejected_in_integration_config(self):
        from zion_core import validate_integration_config, GlossolaliaError
        cfg = {
            "integration_id": "ig-x",
            "business_id": "los-duros",
            "brand_id": "los-duros",
            "provider": "meta",
            "channel": "instagram",
            "instagram_account_id": "123",
            "credential_ref": "env:META_APP_SECRET",
            # 40-char opaque token without a scheme: raw secret.
            "webhook_verify_ref": "aB3dE5fG7hI9jK1lM2nO4pQ6rS8tU0vW2xY4",
        }
        with self.assertRaises(GlossolaliaError):
            validate_integration_config(cfg)

    def test_receiver_requires_verify_token_ref(self):
        os.environ["META_APP_SECRET"] = APP_SECRET
        try:
            integration = build_los_duros_instagram_integration(
                instagram_account_id=ACCOUNT_ID
            )
            bad = integration.__class__(
                **{**integration.__dict__, "webhook_verify_ref": None}
            )
            with self.assertRaises(MetaWebhookError):
                MetaWebhookReceiver(integration=bad)
        finally:
            del os.environ["META_APP_SECRET"]

    def test_receiver_requires_app_secret_ref(self):
        os.environ["LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN"] = VERIFY_TOKEN
        try:
            integration = build_los_duros_instagram_integration(
                instagram_account_id=ACCOUNT_ID
            )
            bad = integration.__class__(
                **{**integration.__dict__, "credential_ref": None}
            )
            with self.assertRaises(MetaWebhookError):
                MetaWebhookReceiver(integration=bad)
        finally:
            del os.environ["LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN"]

    def test_receiver_rejects_non_instagram_integration(self):
        from zion_core import validate_integration_config
        cfg = validate_integration_config({
            "integration_id": "wa-x",
            "business_id": "los-duros",
            "brand_id": "los-duros",
            "provider": "meta",
            "channel": "whatsapp",
            "whatsapp_phone_number_id": "phone-1",
            "credential_ref": "env:META_APP_SECRET",
            "webhook_verify_ref": "env:LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN",
        })
        with self.assertRaises(MetaWebhookError):
            MetaWebhookReceiver(integration=cfg)

    def test_missing_account_id_fails_closed(self):
        with self.assertRaises(MetaWebhookError):
            build_los_duros_instagram_integration(instagram_account_id="")
        with self.assertRaises(MetaWebhookError):
            build_los_duros_instagram_integration(instagram_account_id="   ")

    def test_receiver_from_env_fails_closed_without_account_id(self):
        saved = dict(os.environ)
        os.environ["LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN"] = VERIFY_TOKEN
        os.environ["META_APP_SECRET"] = APP_SECRET
        os.environ.pop("LOS_DUROS_IG_ACCOUNT_ID", None)
        try:
            with self.assertRaises(MetaWebhookError):
                receiver_from_env()
        finally:
            os.environ.clear()
            os.environ.update(saved)


class HttpAdapterSmokeTests(ReceiverFixture):
    """Real loopback server: proves the stdlib adapter captures raw bodies
    and routes GET/POST on CALLBACK_PATH."""

    def _serve(self):
        handler = mw._WebhookHandler
        handler.receiver = self.receiver
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server

    def test_get_verification_end_to_end(self):
        server = self._serve()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port,
                                              timeout=5)
            path = (f"{CALLBACK_PATH}?hub.mode=subscribe"
                    f"&hub.verify_token={VERIFY_TOKEN}"
                    f"&hub.challenge={CHALLENGE}")
            conn.request("GET", path)
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.read().decode("utf-8"), CHALLENGE)
        finally:
            server.shutdown()
            server.server_close()

    def test_get_wrong_path_404(self):
        server = self._serve()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port,
                                              timeout=5)
            conn.request("GET", "/wrong-path")
            self.assertEqual(conn.getresponse().status, 404)
        finally:
            server.shutdown()
            server.server_close()

    def test_post_end_to_end_with_raw_body_signature(self):
        server = self._serve()
        try:
            payload = _payload(comment_id="cmt-e2e-1",
                               text="saludos desde el live 🔥")
            body = _raw(payload)
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port,
                                              timeout=5)
            conn.request(
                "POST", CALLBACK_PATH, body=body,
                headers={"Content-Type": "application/json",
                         "X-Hub-Signature-256": _sign(body)},
            )
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["ok"])
            self.assertEqual(data["processed"], 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_post_bad_signature_end_to_end_401(self):
        server = self._serve()
        try:
            body = _raw(_payload(comment_id="cmt-e2e-2"))
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port,
                                              timeout=5)
            conn.request(
                "POST", CALLBACK_PATH, body=body,
                headers={"X-Hub-Signature-256": _sign(body, "wrong")},
            )
            self.assertEqual(conn.getresponse().status, 401)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
