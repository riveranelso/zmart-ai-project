"""Tests for the Los Duros human approval queue (zion_core.approval_queue).

Covers: ROUTINE draft -> PENDING record, idempotent re-enqueue, tenant
isolation, MAIN_BRAIN/HUMAN_REVIEW (no draft -> no record, route preserved),
approve / edit+approve / reject, invalid transitions, unknown ids, the
APPROVED-never-publishes invariant (static + dynamic), no action creation,
no secrets/PII in logs or records, webhook wiring (enqueue, duplicates,
store failure keeps deliveries retryable), and durability across instances.

All secrets/tokens/ids here are synthetic.
"""
import hashlib
import hmac
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path

from zion_core import approval_queue as aq
from zion_core.approval_queue import (
    APPROVED,
    EDITED,
    PENDING,
    REJECTED,
    ApprovalError,
    ApprovalQueue,
    ApprovalRecord,
    ApprovalStore,
    ApprovalStoreError,
    approval_id_for_fingerprint,
)
from zion_core.glossolalia import (
    GlossolaliaError,
    process_meta_event,
    resolve_integration,
)
from zion_core.meta_webhook import (
    MetaWebhookReceiver,
    build_los_duros_instagram_integration,
    translate_instagram_payload,
)

# Synthetic-only values. Never real credentials.
VERIFY_TOKEN = "synthetic-verify-token-approval-queue"
APP_SECRET = "synthetic-app-secret-approval-queue-00"
ACCOUNT_ID = "17841409999999999"

ROUTINE_TEXT = "esto está duro, me encanta"  # classifies ROUTINE (draftable)
REVIEW_TEXT = "ese chota habló con los federales"  # safety gate -> HUMAN_REVIEW


def _sign(body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


def _payload(
    text=ROUTINE_TEXT,
    comment_id="cmt-9001",
    sender="user-5150",
    entry_id=ACCOUNT_ID,
):
    return {
        "object": "instagram",
        "entry": [
            {
                "id": entry_id,
                "time": 1759530000,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": comment_id,
                            "from": {"id": sender, "username": "fanpr"},
                            "text": text,
                            "media": {"id": "media-777", "media_product_type": "FEED"},
                        },
                    }
                ],
            }
        ],
    }


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


class ApprovalFixture(unittest.TestCase):
    def setUp(self):
        self._saved_env = dict(os.environ)
        os.environ["LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN"] = VERIFY_TOKEN
        os.environ["META_APP_SECRET"] = APP_SECRET
        os.environ["LOS_DUROS_IG_ACCOUNT_ID"] = ACCOUNT_ID
        self._tmp = tempfile.TemporaryDirectory()
        self.registry_path = _registry_with_los_duros(self._tmp.name)
        self.integration = build_los_duros_instagram_integration(
            instagram_account_id=ACCOUNT_ID
        )
        self.store_path = Path(self._tmp.name) / "approvals.json"
        self.store = ApprovalStore(self.store_path)
        self.queue = ApprovalQueue(self.store)

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.clear()
        os.environ.update(self._saved_env)

    # -- helpers ------------------------------------------------------
    def _result(self, text=ROUTINE_TEXT, comment_id="cmt-9001", sender="user-5150",
                seen=None):
        raw = translate_instagram_payload(
            _payload(text=text, comment_id=comment_id, sender=sender)
        ).accepted[0].raw
        return process_meta_event(
            raw,
            integration=self.integration,
            registry_path=self.registry_path,
            attempt_action=False,
            seen_fingerprints=set() if seen is None else seen,
        )

    def _receiver(self, with_store=True):
        return MetaWebhookReceiver(
            integration=self.integration,
            registry_path=self.registry_path,
            approval_store_path=self.store_path if with_store else None,
        )

    def _posted(self, receiver, text=ROUTINE_TEXT, comment_id="cmt-9001"):
        body = json.dumps(
            _payload(text=text, comment_id=comment_id)
        ).encode("utf-8")
        return receiver.ingest_post(body, _sign(body))

    def _events(self, report, name):
        return [e for e in report.events if e.get("event") == name]


class EnqueueTests(ApprovalFixture):
    def test_routine_creates_pending_approval(self):
        result = self._result()
        self.assertEqual(result.decision.route, "ROUTINE")
        self.assertIsNotNone(result.draft)
        self.assertIsNone(result.action)

        record, created = self.queue.enqueue_from_result(result, self.integration)
        self.assertTrue(created)
        self.assertEqual(record.status, PENDING)
        self.assertEqual(record.approval_id, approval_id_for_fingerprint(result.fingerprint))
        self.assertTrue(record.approval_id.startswith("appr_"))
        # Tenant fixed from the integration, never the payload.
        self.assertEqual(record.business_id, "los-duros")
        self.assertEqual(record.brand_id, "los-duros")
        self.assertEqual(record.integration_id, self.integration.integration_id)
        self.assertEqual(record.channel, "instagram")
        self.assertEqual(record.event_type, "comment")
        self.assertEqual(record.event_fingerprint, result.fingerprint)
        self.assertEqual(record.draft_text, result.draft.text)
        self.assertEqual(record.processing_route, "ROUTINE")
        self.assertTrue(record.created_at)
        self.assertTrue(record.updated_at)
        self.assertIsNone(record.reviewed_at)
        # Source identifiers are opaque hashes, never raw ids.
        self.assertNotIn("cmt-9001", record.comment_id_hash)
        self.assertNotIn("user-5150", record.sender_id_hash)
        self.assertEqual(len(record.comment_id_hash), 12)
        # History starts with the enqueue transition.
        self.assertEqual(len(record.history), 1)
        self.assertEqual(record.history[0].to_status, PENDING)

    def test_duplicate_event_reuses_same_approval(self):
        result = self._result()
        first, created_first = self.queue.enqueue_from_result(result, self.integration)
        second, created_second = self.queue.enqueue_from_result(result, self.integration)
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.approval_id, second.approval_id)
        self.assertEqual(len(self.store.list_by_status(PENDING)), 1)

    def test_main_brain_creates_no_record(self):
        # No text -> MAIN_BRAIN (insufficient context), no draft.
        result = self._result(text=None)
        self.assertEqual(result.decision.route, "MAIN_BRAIN")
        self.assertIsNone(result.draft)
        self.assertIsNone(self.queue.enqueue_from_result(result, self.integration))
        self.assertEqual(self.store.list_by_status(PENDING), ())

    def test_human_review_creates_no_record(self):
        result = self._result(text=REVIEW_TEXT)
        self.assertEqual(result.decision.route, "HUMAN_REVIEW")
        self.assertIsNone(result.draft)
        self.assertIsNone(self.queue.enqueue_from_result(result, self.integration))
        self.assertEqual(self.store.list_by_status(PENDING), ())

    def test_tenant_isolation(self):
        result = self._result()
        record, _ = self.queue.enqueue_from_result(result, self.integration)
        self.assertEqual(record.business_id, "los-duros")
        # A spoofed business_id claim in the identity never overrides.
        with self.assertRaises(GlossolaliaError) as ctx:
            resolve_integration(
                {
                    "channel": "instagram",
                    "identity": ACCOUNT_ID,
                    "business_id": "zmart",
                },
                [self.integration],
            )
        self.assertIn("TENANT_MISMATCH", str(ctx.exception))
        # Same comment under a different tenant: the fingerprint (and thus
        # the approval id) is tenant-scoped -- no cross-tenant collision.
        from dataclasses import replace
        from zion_core.glossolalia import intake_meta_event, meta_event_fingerprint
        other = replace(self.integration, business_id="other-biz",
                        brand_id="other-brand", integration_id="ig-other-1")
        raw = translate_instagram_payload(_payload()).accepted[0].raw
        fp_mine = meta_event_fingerprint(intake_meta_event(raw, self.integration))
        fp_other = meta_event_fingerprint(intake_meta_event(raw, other))
        self.assertNotEqual(fp_mine, fp_other)
        self.assertNotEqual(
            approval_id_for_fingerprint(fp_mine),
            approval_id_for_fingerprint(fp_other),
        )

    def test_list_pending_fifo(self):
        self.queue.enqueue_from_result(self._result(comment_id="cmt-a"), self.integration)
        self.queue.enqueue_from_result(self._result(comment_id="cmt-b"), self.integration)
        pending = self.queue.list_pending()
        self.assertEqual(len(pending), 2)
        self.assertLessEqual(pending[0].created_at, pending[1].created_at)

    def test_durable_across_instances(self):
        result = self._result()
        record, _ = self.queue.enqueue_from_result(result, self.integration)
        fresh = ApprovalQueue(ApprovalStore(self.store_path))
        self.assertEqual(fresh.inspect(record.approval_id).draft_text, record.draft_text)
        self.assertEqual(len(fresh.list_pending()), 1)


class TransitionTests(ApprovalFixture):
    def _pending(self):
        record, _ = self.queue.enqueue_from_result(self._result(), self.integration)
        return record

    def test_approve(self):
        record = self._pending()
        approved = self.queue.approve(record.approval_id, reviewer="panda")
        self.assertEqual(approved.status, APPROVED)
        self.assertEqual(approved.reviewer, "panda")
        self.assertEqual(approved.decision, APPROVED)
        self.assertTrue(approved.reviewed_at)
        self.assertTrue(approved.updated_at >= record.updated_at)
        self.assertEqual(len(approved.history), 2)
        self.assertEqual(approved.history[-1].from_status, PENDING)
        self.assertEqual(approved.history[-1].to_status, APPROVED)
        self.assertEqual(approved.history[-1].reviewer, "panda")
        self.assertEqual(self.queue.list_pending(), ())

    def test_edit_and_approve(self):
        record = self._pending()
        edited = self.queue.edit_and_approve(
            record.approval_id, reviewer="panda", edited_text="Duro, gracias por el apoyo."
        )
        self.assertEqual(edited.status, EDITED)
        self.assertEqual(edited.edited_text, "Duro, gracias por el apoyo.")
        self.assertEqual(edited.reviewer, "panda")
        self.assertEqual(edited.history[-1].to_status, EDITED)

    def test_reject(self):
        record = self._pending()
        rejected = self.queue.reject(record.approval_id, reviewer="panda",
                                     reason="off-brand")
        self.assertEqual(rejected.status, REJECTED)
        self.assertEqual(rejected.history[-1].note, "off-brand")
        self.assertIsNone(rejected.edited_text)

    def test_invalid_state_transitions(self):
        record = self._pending()
        self.queue.approve(record.approval_id, reviewer="panda")
        for op in (
            lambda: self.queue.approve(record.approval_id, reviewer="panda"),
            lambda: self.queue.reject(record.approval_id, reviewer="panda"),
            lambda: self.queue.edit_and_approve(
                record.approval_id, reviewer="panda", edited_text="x"),
        ):
            with self.assertRaises(ApprovalError) as ctx:
                op()
            self.assertIn("INVALID_TRANSITION", str(ctx.exception))
        # Terminal state is unchanged.
        self.assertEqual(self.queue.inspect(record.approval_id).status, APPROVED)

    def test_unknown_approval_id(self):
        with self.assertRaises(ApprovalError) as ctx:
            self.queue.inspect("appr_doesnotexist00")
        self.assertIn("APPROVAL_NOT_FOUND", str(ctx.exception))
        with self.assertRaises(ApprovalError):
            self.queue.approve("appr_doesnotexist00", reviewer="panda")
        with self.assertRaises(ApprovalError):
            self.queue.reject("appr_doesnotexist00", reviewer="panda")
        with self.assertRaises(ApprovalError):
            self.queue.edit_and_approve("appr_doesnotexist00", reviewer="panda",
                                        edited_text="x")

    def test_reviewer_required(self):
        record = self._pending()
        with self.assertRaises(ApprovalError):
            self.queue.approve(record.approval_id, reviewer="  ")

    def test_edit_requires_text(self):
        record = self._pending()
        with self.assertRaises(ApprovalError):
            self.queue.edit_and_approve(record.approval_id, reviewer="panda",
                                        edited_text="   ")

    def test_corrupt_store_fails_closed(self):
        self._pending()
        self.store_path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ApprovalStoreError):
            self.queue.list_pending()


class NoPublishTests(ApprovalFixture):
    def test_module_has_no_transport_symbols(self):
        # AST-level guard: the module must not define, import, or call any
        # transport/action symbol. (Docstring prose mentioning the invariant
        # in the negative is fine -- only code matters.)
        import ast
        tree = ast.parse(Path(aq.__file__).read_text(encoding="utf-8"))
        forbidden = {
            "build_action_intent", "route_meta_action", "publish_reply",
            "MetaActionIntent", "MetaActionResult", "urlopen", "httpx",
            "requests", "socket",
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.assertNotIn(node.name, forbidden, f"defined: {node.name}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0], forbidden)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    self.assertNotIn(alias.name, forbidden)
            elif isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else (
                    func.attr if isinstance(func, ast.Attribute) else "")
                self.assertNotIn(name, forbidden, f"called: {name}")
        for name in ("build_action_intent", "route_meta_action", "publish_reply"):
            self.assertFalse(hasattr(aq, name), name)

    def test_approval_never_creates_action(self):
        result = self._result()
        record, _ = self.queue.enqueue_from_result(result, self.integration)
        self.assertIsNone(result.action)
        approved = self.queue.approve(record.approval_id, reviewer="panda")
        self.assertIsNone(result.action)
        # The approved record carries no intent, no transport handle.
        self.assertFalse(hasattr(approved, "intent"))
        self.assertFalse(hasattr(approved, "action"))

    def test_no_secrets_or_pii_in_logs(self):
        with self.assertLogs("zion.approval_queue", level="INFO") as logs:
            result = self._result()
            record, _ = self.queue.enqueue_from_result(result, self.integration)
            self.queue.approve(record.approval_id, reviewer="panda")
            self.queue.reject(
                self.queue.enqueue_from_result(
                    self._result(comment_id="cmt-9002"), self.integration
                )[0].approval_id,
                reviewer="panda",
            )
        output = "\n".join(logs.output)
        for secret in (APP_SECRET, VERIFY_TOKEN):
            self.assertNotIn(secret, output)
        # No comment text, usernames, or raw ids in logs.
        for pii in (ROUTINE_TEXT, "fanpr", "cmt-9001", "cmt-9002",
                    "user-5150", ACCOUNT_ID):
            self.assertNotIn(pii, output)
        # But the structured events are present.
        for event in ("approval_created", "approval_approved", "approval_rejected"):
            self.assertIn(event, output)

    def test_source_text_not_persisted(self):
        record, _ = self.queue.enqueue_from_result(self._result(), self.integration)
        raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        stored = raw[record.approval_id]
        blob = json.dumps(stored, ensure_ascii=False)
        self.assertNotIn(ROUTINE_TEXT, blob)
        self.assertNotIn("fanpr", blob)
        # Draft text (ZION-generated) IS persisted.
        self.assertIn(record.draft_text, blob)


class WebhookWiringTests(ApprovalFixture):
    def test_webhook_enqueues_on_draft(self):
        receiver = self._receiver(with_store=True)
        self.assertIsNotNone(receiver.approval_queue)
        report = self._posted(receiver)
        self.assertEqual(report.status, 200)
        created = self._events(report, "approval_created")
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["status"], "PENDING")
        pending = receiver.approval_queue.list_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].approval_id, created[0]["approval_id"])
        self.assertEqual(pending[0].business_id, "los-duros")
        # Publishing still impossible: no action anywhere.
        self.assertTrue(all(r.action is None for r in report.results))
        processed_events = self._events(report, "event_processed")
        self.assertTrue(processed_events)
        self.assertTrue(all(e["action_created"] is False for e in processed_events))
        complete = self._events(report, "webhook_complete")
        self.assertEqual(complete[0]["actions_created"], 0)

    def test_webhook_duplicate_creates_no_second_record(self):
        receiver = self._receiver(with_store=True)
        first = self._posted(receiver)
        second = self._posted(receiver)  # Meta retry: same bytes
        self.assertEqual(first.status, 200)
        self.assertEqual(second.status, 200)
        self.assertEqual(second.body["duplicates"], 1)
        self.assertEqual(len(receiver.approval_queue.list_pending()), 1)
        # Only the first delivery emitted approval_created.
        total_created = self._events(first, "approval_created") + self._events(
            second, "approval_created")
        self.assertEqual(len(total_created), 1)

    def test_webhook_without_store_unchanged(self):
        receiver = self._receiver(with_store=False)
        self.assertIsNone(receiver.approval_queue)
        report = self._posted(receiver)
        self.assertEqual(report.status, 200)
        self.assertEqual(
            [e for e in report.events if e.get("event", "").startswith("approval_")],
            [],
        )
        # Draft still produced; nothing persisted.
        self.assertTrue(any(r.draft is not None for r in report.results))

    def test_non_routine_creates_no_record(self):
        receiver = self._receiver(with_store=True)
        report = self._posted(receiver, text=REVIEW_TEXT, comment_id="cmt-hr-1")
        self.assertEqual(report.status, 200)
        self.assertEqual(receiver.approval_queue.list_pending(), ())
        self.assertEqual(
            [e for e in report.events if e.get("event", "").startswith("approval_")],
            [],
        )

    def test_enqueue_failure_keeps_delivery_retryable(self):
        receiver = self._receiver(with_store=True)
        # Corrupt the store AFTER construction (construction validates).
        self.store_path.write_text("{corrupt", encoding="utf-8")
        failed = self._posted(receiver)
        self.assertEqual(failed.status, 500)
        self.assertEqual(failed.body["error"], "APPROVAL_STORE_FAILED")
        self.assertEqual(len(self._events(failed, "approval_failed")), 1)
        # Fix the store; the Meta retry must process normally (no silent loss).
        self.store_path.write_text("{}", encoding="utf-8")
        retried = self._posted(receiver)
        self.assertEqual(retried.status, 200)
        self.assertEqual(retried.body["duplicates"], 0)
        self.assertEqual(len(self._events(retried, "approval_created")), 1)
        self.assertEqual(len(receiver.approval_queue.list_pending()), 1)


if __name__ == "__main__":
    unittest.main()
