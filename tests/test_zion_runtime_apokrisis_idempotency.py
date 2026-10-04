import json
import tempfile
import unittest
from pathlib import Path

from zion_core import LearningIntent, OmarRuntime, apokrisis


class RuntimeApokrisisIdempotencyTests(unittest.TestCase):
    def test_same_angel_response_is_processed_once_but_second_angel_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text(
                "# Workflows\n\n## zmart-consumer-rights\n",encoding="utf-8"
            )
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            first_response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m1",
                status="SUCCESS",summary="done",business_id="zmart-consumer-rights",
            )
            first=runtime.close(first_response,learning=LearningIntent())
            self.assertTrue(first.processed)
            before=(root/"cronicas.jsonl").read_bytes()

            retry=runtime.close(first_response,learning=LearningIntent())
            self.assertFalse(retry.processed)
            self.assertEqual(retry.reason,"APOKRISIS_ALREADY_PROCESSED")
            self.assertEqual((root/"cronicas.jsonl").read_bytes(),before)

            second_response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-002",mission_id="m1",
                status="SUCCESS",summary="also done",business_id="zmart-consumer-rights",
            )
            second=runtime.close(second_response,learning=LearningIntent())
            self.assertTrue(second.processed)
            events=runtime.history(
                business_id="zmart-consumer-rights",
                event_type="ANGEL_RESPONSE",mission_id="m1",
            )
            self.assertEqual(len(events),2)
            self.assertEqual(
                tuple(event.angel_ids[0] for event in events),
                ("SANGABRIEL.HOST-01.ANGEL-001","SANGABRIEL.HOST-01.ANGEL-002"),
            )


    def test_dispatched_mission_cannot_accept_response_for_uncommissioned_angel_when_other_commissions_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            runtime.dispatch({"mission_id":"m-commission-bound","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights","angel_count_max":1})
            forged=apokrisis(angel_id="SANGABRIEL.HOST-01.ANGEL-002",mission_id="m-commission-bound",status="SUCCESS",summary="forged",business_id="zmart-consumer-rights")
            with self.assertRaisesRegex(ValueError,"APOKRISIS_ANGEL_NOT_COMMISSIONED"):
                runtime.close(forged,learning=LearningIntent())


    def test_multiple_dispatch_records_with_different_fingerprints_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            runtime.dispatch({"mission_id":"m-fingerprint-history","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights"})
            original=runtime.history(business_id="zmart-consumer-rights",event_type="MISSION_DECISION",mission_id="m-fingerprint-history")[0]
            from dataclasses import replace
            from zion_core.persistence import CronicasJsonlSink
            CronicasJsonlSink(root/"cronicas.jsonl")(replace(original,event_id="conflicting-fingerprint",dispatch_fingerprint="0"*64))
            response=apokrisis(angel_id=original.angel_ids[0],mission_id="m-fingerprint-history",status="SUCCESS",summary="must fail closed",business_id="zmart-consumer-rights")
            with self.assertRaisesRegex(ValueError,"APOKRISIS_CONFLICTING_DISPATCH_FINGERPRINTS"):
                runtime.close(response,learning=LearningIntent())


    def test_multiple_dispatch_records_with_different_fingerprints_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            runtime.dispatch({"mission_id":"m-conflicting-fingerprint","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights"})
            from zion_core.cronicas import CronicaEvent
            from zion_core.persistence import CronicasJsonlSink
            CronicasJsonlSink(root/"cronicas.jsonl")(CronicaEvent(event_id="conflict-fingerprint",occurred_at="2026-10-03T00:00:00+00:00",event_type="MISSION_DECISION",mission_id="m-conflicting-fingerprint",business_id="zmart-consumer-rights",action="DISPATCH",reason="AUTHORIZED",command="SANGABRIEL",host="SANGABRIEL.HOST-01",angel_ids=("SANGABRIEL.HOST-01.ANGEL-001",),dispatch_fingerprint="forged-fingerprint"))
            response=apokrisis(angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m-conflicting-fingerprint",status="SUCCESS",summary="must fail closed",business_id="zmart-consumer-rights")
            with self.assertRaisesRegex(ValueError,"APOKRISIS_CONFLICTING_DISPATCH_FINGERPRINT"):
                runtime.close(response,learning=LearningIntent())


    def test_multiple_dispatch_records_with_different_commissions_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            runtime.dispatch({"mission_id":"m-conflicting-commissions","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights","angel_count_max":1})
            from zion_core.cronicas import CronicaEvent
            from zion_core.persistence import CronicasJsonlSink
            original=runtime.history(business_id="zmart-consumer-rights",event_type="MISSION_DECISION",mission_id="m-conflicting-commissions")[0]
            from dataclasses import replace
            CronicasJsonlSink(root/"cronicas.jsonl")(replace(original,event_id="conflict-commission",angel_ids=("SANGABRIEL.HOST-01.ANGEL-002",)))
            response=apokrisis(angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m-conflicting-commissions",status="SUCCESS",summary="must fail closed",business_id="zmart-consumer-rights")
            with self.assertRaisesRegex(ValueError,"APOKRISIS_CONFLICTING_COMMISSION_HISTORY"):
                runtime.close(response,learning=LearningIntent())


    def test_conflicting_durable_mission_decisions_fail_closed_at_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            runtime.dispatch({"mission_id":"m-conflicting-history","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights"})
            from zion_core.cronicas import CronicaEvent
            from zion_core.persistence import CronicasJsonlSink
            CronicasJsonlSink(root/"cronicas.jsonl")(CronicaEvent(event_id="conflict",occurred_at="2026-10-03T00:00:00+00:00",event_type="MISSION_DECISION",mission_id="m-conflicting-history",business_id="zmart-consumer-rights",action="REQUIRE_HUMAN_REVIEW",reason="POLICY_CONFLICT",angel_ids=()))
            response=apokrisis(angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m-conflicting-history",status="SUCCESS",summary="must fail closed",business_id="zmart-consumer-rights")
            with self.assertRaisesRegex(ValueError,"APOKRISIS_CONFLICTING_MISSION_HISTORY"):
                runtime.close(response,learning=LearningIntent())


    def test_dispatched_mission_with_empty_commission_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            from zion_core.cronicas import CronicaEvent
            from zion_core.persistence import CronicasJsonlSink
            CronicasJsonlSink(root/"cronicas.jsonl")(CronicaEvent(event_id="test-empty",occurred_at="2026-10-03T00:00:00+00:00",event_type="MISSION_DECISION",mission_id="m-empty-commission",business_id="zmart-consumer-rights",action="DISPATCH",reason="AUTHORIZED",angel_ids=()))
            forged=apokrisis(angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m-empty-commission",status="SUCCESS",summary="forged",business_id="zmart-consumer-rights")
            with self.assertRaisesRegex(ValueError,"APOKRISIS_COMMISSION_EVIDENCE_MISSING"):
                runtime.close(forged,learning=LearningIntent())


    def test_denied_mission_cannot_accept_angel_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\\n",encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json",
            )
            denied=runtime.dispatch({
                "mission_id":"m-denied-response","intent":"unknown","requested_by":"OMAR",
                "scope":"WORKFLOW","business_id":"zmart-consumer-rights",
            })
            self.assertEqual(denied.decision.action,"REQUIRE_HUMAN_REVIEW")
            forged=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m-denied-response",
                status="SUCCESS",summary="should not execute",business_id="zmart-consumer-rights",
            )
            with self.assertRaisesRegex(ValueError,"APOKRISIS_MISSION_NOT_DISPATCHED"):
                runtime.close(forged,learning=LearningIntent())


    def test_response_must_match_dispatched_angel_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\n\n## zmart-consumer-rights\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
                encoding="utf-8",
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json",
            )
            runtime.dispatch({
                "mission_id":"m-bound","intent":"internal_dispatch","requested_by":"OMAR",
                "scope":"WORKFLOW","business_id":"zmart-consumer-rights","angel_count_max":1,
            })
            forged=apokrisis(
                angel_id="SANMIGUEL.HOST-01.ANGEL-001",mission_id="m-bound",
                status="SUCCESS",summary="forged",business_id="zmart-consumer-rights",
            )
            with self.assertRaisesRegex(ValueError,"APOKRISIS_ANGEL_NOT_COMMISSIONED"):
                runtime.close(forged,learning=LearningIntent())



    def test_same_angel_cannot_replay_changed_response_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\n\n## zmart-consumer-rights\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,
                cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json",
            )
            first=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m-replay",
                status="SUCCESS",summary="done",business_id="zmart-consumer-rights",
                correlation_id="corr-1",evidence_refs=("proof-a",),
            )
            runtime.close(first,learning=LearningIntent())
            changed=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m-replay",
                status="PARTIAL",summary="changed",business_id="zmart-consumer-rights",
                correlation_id="corr-2",evidence_refs=("proof-b",),
            )
            with self.assertRaisesRegex(ValueError,"APOKRISIS_REUSE_CONFLICT"):
                runtime.close(changed,learning=LearningIntent())




    def test_changed_summary_is_not_silent_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\n\n## zmart-consumer-rights\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,
                cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json",
            )
            first=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m-summary-replay",
                status="SUCCESS",summary="first result",business_id="zmart-consumer-rights",
            )
            runtime.close(first,learning=LearningIntent(auto_write=False))
            changed=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m-summary-replay",
                status="SUCCESS",summary="different result",business_id="zmart-consumer-rights",
            )
            with self.assertRaisesRegex(ValueError,"APOKRISIS_REUSE_CONFLICT"):
                runtime.close(changed,learning=LearningIntent(auto_write=False))


    def test_same_count_changed_correction_signal_is_not_silent_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\n\n## zmart-consumer-rights\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,
                cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json",
            )
            first=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m-signal-replay",
                status="SUCCESS",summary="done",business_id="zmart-consumer-rights",
                correction_signals=("keep original rule",),
            )
            runtime.close(first,learning=LearningIntent(auto_write=False))
            changed=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m-signal-replay",
                status="SUCCESS",summary="done",business_id="zmart-consumer-rights",
                correction_signals=("replace with different rule",),
            )
            with self.assertRaisesRegex(ValueError,"APOKRISIS_REUSE_CONFLICT"):
                runtime.close(changed,learning=LearningIntent(auto_write=False))



if __name__=="__main__":
    unittest.main()
