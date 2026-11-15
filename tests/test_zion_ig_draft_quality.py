"""IG draft quality gate: platform-aware drafting + username context.

Covers the two upstream quality gaps fixed before production deployment:

GAP A -- Instagram drafts must never receive the YouTube subscribe/share
         CTA automatically; YouTube behavior is preserved.
GAP B -- Meta `from.username` is preserved through normalization as
         contextual metadata only (never tenant identity, never the stable
         sender_id, never in the dedupe fingerprint, never logged).

Publication remains impossible: no transport exists anywhere in this path.
"""

import ast
import logging
import unittest
from pathlib import Path

from zion_core import antiphon
from zion_core import glossolalia
from zion_core.meta_webhook import (
    build_los_duros_instagram_integration,
    translate_instagram_payload,
)

ROUTINE_TEXT = "Ese tema esta duro, lo tengo en repeat todo el dia"
YT_CTA_MARKERS = ("Suscribete pa que no te pierdas", "🔔")


def _integration():
    return build_los_duros_instagram_integration(
        instagram_account_id="1409195987990807"
    )


def _raw_event(*, sender_id="987654", username="elbichote_pr",
               comment_id="cmt_q1", text=ROUTINE_TEXT):
    raw = {
        "channel": "instagram",
        "event_type": "comment",
        "sender_id": sender_id,
        "message_id": comment_id,
        "parent_id": None,
        "conversation_id": "media_1",
        "timestamp": "2026-10-06T05:00:00+00:00",
        "text": text,
        "raw_event_ref": f"meta:instagram:comments:{comment_id}",
    }
    if username is not None:
        raw["sender_username"] = username
    return raw


def _routine_draft(text=ROUTINE_TEXT):
    event = glossolalia.intake_meta_event(_raw_event(text=text), _integration())
    decision = glossolalia.route_meta_event(event)
    assert decision.route == antiphon.ROUTINE, decision.route
    draft = glossolalia.draft_meta_reply(event, decision)
    assert draft is not None
    return event, draft


class PlatformAwareDraftingTests(unittest.TestCase):
    def test_ig_routine_draft_has_no_youtube_cta(self):
        _, draft = _routine_draft()
        for marker in YT_CTA_MARKERS:
            self.assertNotIn(marker, draft.text)
        self.assertIsNone(draft.cta_variant)

    def test_ig_draft_body_is_real_reply(self):
        _, draft = _routine_draft()
        # Body still present and non-empty without the CTA.
        self.assertTrue(len(draft.text.strip()) > 20)

    def test_youtube_behavior_unchanged_explicit_platform(self):
        comment = antiphon.NormalizedComment(
            comment_id="yt_explicit", video_id="v1", author="a",
            text=ROUTINE_TEXT, business_id="los-duros",
            platform=antiphon.PLATFORM_YOUTUBE,
        )
        brand = antiphon.resolve_brand(comment)
        classification = antiphon.classify_comment(comment)
        self.assertEqual(classification.route, antiphon.ROUTINE)
        draft = antiphon.draft_reply(comment, classification, brand=brand)
        self.assertIn("Suscribete pa que no te pierdas", draft.text)
        self.assertIsNotNone(draft.cta_variant)

    def test_youtube_behavior_unchanged_legacy_no_platform(self):
        # Callers that never set platform keep the historical behavior.
        comment = antiphon.NormalizedComment(
            comment_id="yt_legacy", video_id="v1", author="a",
            text=ROUTINE_TEXT, business_id="los-duros",
        )
        self.assertIsNone(comment.platform)
        brand = antiphon.resolve_brand(comment)
        classification = antiphon.classify_comment(comment)
        self.assertEqual(classification.route, antiphon.ROUTINE)
        draft = antiphon.draft_reply(comment, classification, brand=brand)
        self.assertIn("Suscribete pa que no te pierdas", draft.text)

    def test_channel_reaches_drafting_from_event(self):
        event, _ = _routine_draft()
        self.assertEqual(event.channel, "instagram")
        comment = glossolalia._as_antiphon_comment(event)
        self.assertEqual(comment.platform, "instagram")


class UsernameContextTests(unittest.TestCase):
    def test_username_preserved_when_present(self):
        event = glossolalia.intake_meta_event(
            _raw_event(username="elbichote_pr"), _integration())
        self.assertEqual(event.sender_username, "elbichote_pr")
        self.assertEqual(event.sender_id, "987654")

    def test_missing_username_works(self):
        event = glossolalia.intake_meta_event(
            _raw_event(username=None), _integration())
        self.assertIsNone(event.sender_username)
        decision = glossolalia.route_meta_event(event)
        draft = glossolalia.draft_meta_reply(event, decision)
        self.assertIsNotNone(draft)

    def test_username_not_tenant_identity(self):
        cfg = _integration()
        e1 = glossolalia.intake_meta_event(
            _raw_event(username="alice"), cfg)
        e2 = glossolalia.intake_meta_event(
            _raw_event(username="bob"), cfg)
        # Tenant still comes only from the resolved integration config.
        self.assertEqual(e1.business_id_internal, "los-duros")
        self.assertEqual(e2.business_id_internal, "los-duros")
        self.assertEqual(e1.brand_id_internal, e2.brand_id_internal)
        # resolve_integration matches on (channel, entry identity), not username.
        ident = {"channel": "instagram", "identity": "1409195987990807"}
        self.assertEqual(
            glossolalia.resolve_integration(ident, [cfg]).integration_id,
            cfg.integration_id,
        )

    def test_username_not_in_dedupe_fingerprint(self):
        fp1 = glossolalia.meta_event_fingerprint(
            glossolalia.intake_meta_event(_raw_event(username="alice"),
                                          _integration()))
        fp2 = glossolalia.meta_event_fingerprint(
            glossolalia.intake_meta_event(_raw_event(username="bob"),
                                          _integration()))
        fp3 = glossolalia.meta_event_fingerprint(
            glossolalia.intake_meta_event(_raw_event(username=None),
                                          _integration()))
        self.assertEqual(fp1, fp2)
        self.assertEqual(fp1, fp3)

    def test_username_exposed_at_brain_boundary(self):
        event = glossolalia.intake_meta_event(
            _raw_event(username="elbichote_pr"), _integration())
        comment = glossolalia._as_antiphon_comment(event)
        self.assertEqual(comment.author_username, "elbichote_pr")
        # Stable identifier unchanged.
        self.assertEqual(comment.author, "987654")

    def test_username_absent_from_structured_logs(self):
        import hashlib
        import hmac
        import json as json_mod
        import os
        from zion_core.meta_webhook import MetaWebhookReceiver

        os.environ["LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN"] = "verify-token-synth"
        os.environ["META_APP_SECRET"] = "app-secret-synth"
        os.environ["LOS_DUROS_IG_ACCOUNT_ID"] = "17841409999999999"
        try:
            receiver = MetaWebhookReceiver(
                integration=_integration(), approval_store_path=None)
            body = json_mod.dumps({
                "object": "instagram",
                "entry": [{
                    "id": "1409195987990807",
                    "time": 1759530000,
                    "changes": [{
                        "field": "comments",
                        "value": {
                            "id": "cmt_log1",
                            "from": {"id": "user-9",
                                     "username": "elbichote_pr"},
                            "text": ROUTINE_TEXT,
                            "media": {"id": "media_9"},
                        },
                    }],
                }],
            }).encode("utf-8")
            sig = ("sha256=" + hmac.new(
                b"app-secret-synth", body, hashlib.sha256).hexdigest())
            report = receiver.ingest_post(body, sig)
        finally:
            for key in ("LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN",
                        "META_APP_SECRET", "LOS_DUROS_IG_ACCOUNT_ID"):
                os.environ.pop(key, None)
        self.assertEqual(report.status, 200)
        blob = json_mod.dumps(report.events, sort_keys=True)
        self.assertNotIn("elbichote_pr", blob)

    def test_webhook_extraction_preserves_username(self):
        payload = {
            "object": "instagram",
            "entry": [{
                "id": "1409195987990807",
                "time": 1720000000,
                "changes": [{
                    "field": "comments",
                    "value": {
                        "id": "cmt_w1",
                        "text": ROUTINE_TEXT,
                        "from": {"id": "user-9", "username": "otro"},
                        "media": {"id": "media_9"},
                    },
                }],
            }],
        }
        result = translate_instagram_payload(payload)
        self.assertEqual(len(result.accepted), 1)
        self.assertEqual(result.accepted[0].raw["sender_username"], "otro")
        self.assertEqual(result.accepted[0].raw["sender_id"], "user-9")

    def test_webhook_extraction_missing_username(self):
        payload = {
            "object": "instagram",
            "entry": [{
                "id": "1409195987990807",
                "time": 1720000000,
                "changes": [{
                    "field": "comments",
                    "value": {
                        "id": "cmt_w2",
                        "text": ROUTINE_TEXT,
                        "from": {"id": "user-9"},
                        "media": {"id": "media_9"},
                    },
                }],
            }],
        }
        result = translate_instagram_payload(payload)
        self.assertEqual(len(result.accepted), 1)
        self.assertIsNone(result.accepted[0].raw["sender_username"])


class SafetyInvariantTests(unittest.TestCase):
    def test_human_review_still_fail_closed(self):
        event = glossolalia.intake_meta_event(
            _raw_event(text="te voy a matar cuando te vea",
                       comment_id="cmt_hr"),
            _integration())
        decision = glossolalia.route_meta_event(event)
        self.assertEqual(decision.route, antiphon.HUMAN_REVIEW)
        self.assertIsNone(glossolalia.draft_meta_reply(event, decision))

    def test_no_publication_transport_in_new_code(self):
        # AST-level: the touched modules define/import/call no network
        # transport for replies. APPROVED stays internal-only.
        for path in (
            Path("zion_core/antiphon.py"),
            Path("zion_core/glossolalia.py"),
            Path("zion_core/meta_webhook.py"),
            Path("zion_core/approval_queue.py"),
        ):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            hits = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module in (
                    "requests", "urllib.request", "http.client"):
                    hits.append(ast.dump(node)[:80])
                if isinstance(node, ast.Call):
                    target = ast.dump(node.func)
                    if "urlopen" in target or "requests." in target:
                        hits.append(target[:80])
            self.assertEqual(hits, [], f"{path}: {hits}")

    def test_attempt_action_stays_off_in_webhook_wiring(self):
        import inspect
        from zion_core import meta_webhook
        src = inspect.getsource(meta_webhook.MetaWebhookReceiver.ingest_post)
        self.assertIn("attempt_action=False", src)

    def test_process_meta_event_builds_no_action_by_default(self):
        result = glossolalia.process_meta_event(
            _raw_event(), integration=_integration(), biblia_root=None,
            attempt_action=False, seen_fingerprints=set())
        self.assertIsNone(result.action)


if __name__ == "__main__":
    unittest.main()
