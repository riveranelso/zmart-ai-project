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


    def test_dispatch_history_with_missing_fingerprint_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            runtime.dispatch({"mission_id":"m-missing-fingerprint","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights"})
            from zion_core.cronicas import CronicaEvent
            from zion_core.persistence import CronicasJsonlSink
            first=runtime.history(business_id="zmart-consumer-rights",event_type="MISSION_DECISION",mission_id="m-missing-fingerprint")[0]
            CronicasJsonlSink(root/"cronicas.jsonl")(CronicaEvent(event_id="missing-fingerprint",occurred_at="2026-10-03T00:00:00+00:00",event_type="MISSION_DECISION",mission_id="m-missing-fingerprint",business_id="zmart-consumer-rights",action="DISPATCH",reason="AUTHORIZED",command=first.command,host=first.host,angel_ids=first.angel_ids,dispatch_fingerprint=None))
            response=apokrisis(angel_id=first.angel_ids[0],mission_id="m-missing-fingerprint",status="SUCCESS",summary="must fail closed",business_id="zmart-consumer-rights")
            with self.assertRaisesRegex(ValueError,"APOKRISIS_CONFLICTING_DISPATCH_FINGERPRINTS"):
                runtime.close(response,learning=LearningIntent())


    def test_response_history_for_other_angel_does_not_block_valid_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            dispatch=runtime.dispatch({"mission_id":"m-other-angel-history","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights","angel_count_max":2})
            first,second=(item.angel_id for item in dispatch.decision.angels)
            runtime.close(apokrisis(angel_id=first,mission_id="m-other-angel-history",status="SUCCESS",summary="first",business_id="zmart-consumer-rights"),learning=LearningIntent())
            result=runtime.close(apokrisis(angel_id=second,mission_id="m-other-angel-history",status="SUCCESS",summary="second",business_id="zmart-consumer-rights"),learning=LearningIntent())
            self.assertTrue(result.processed)
            self.assertEqual(len(runtime.history(business_id="zmart-consumer-rights",event_type="ANGEL_RESPONSE",mission_id="m-other-angel-history")),2)


    def test_prior_response_record_with_empty_angel_identity_does_not_authorize_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            dispatch=runtime.dispatch({"mission_id":"m-empty-response-identity","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights"})
            aid=dispatch.decision.angels[0].angel_id
            response=apokrisis(angel_id=aid,mission_id="m-empty-response-identity",status="SUCCESS",summary="good",business_id="zmart-consumer-rights")
            from zion_core.cronicas import CronicaEvent, build_apokrisis_fingerprint
            from zion_core.persistence import CronicasJsonlSink
            CronicasJsonlSink(root/"cronicas.jsonl")(CronicaEvent(event_id="empty-response-identity",occurred_at="2026-10-03T00:00:00+00:00",event_type="ANGEL_RESPONSE",mission_id="m-empty-response-identity",business_id="zmart-consumer-rights",action="APOKRISIS",reason="SUCCESS",angel_ids=(),status="SUCCESS",response_fingerprint=build_apokrisis_fingerprint(response)))
            result=runtime.close(response,learning=LearningIntent())
            self.assertTrue(result.processed)
            self.assertEqual(len(runtime.history(business_id="zmart-consumer-rights",event_type="ANGEL_RESPONSE",mission_id="m-empty-response-identity")),2)


    def test_prior_response_record_for_multiple_angels_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            dispatch=runtime.dispatch({"mission_id":"m-multi-angel-response-record","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights","angel_count_max":2})
            aid=dispatch.decision.angels[0].angel_id
            other=dispatch.decision.angels[1].angel_id
            good=apokrisis(angel_id=aid,mission_id="m-multi-angel-response-record",status="SUCCESS",summary="good",business_id="zmart-consumer-rights")
            from zion_core.cronicas import CronicaEvent, build_apokrisis_fingerprint
            from zion_core.persistence import CronicasJsonlSink
            CronicasJsonlSink(root/"cronicas.jsonl")(CronicaEvent(event_id="multi-angel-response",occurred_at="2026-10-03T00:00:00+00:00",event_type="ANGEL_RESPONSE",mission_id="m-multi-angel-response-record",business_id="zmart-consumer-rights",action="APOKRISIS",reason="SUCCESS",angel_ids=(aid,other),status="SUCCESS",response_fingerprint=build_apokrisis_fingerprint(good)))
            with self.assertRaisesRegex(ValueError,"APOKRISIS_RESPONSE_IDENTITY_INVALID"):
                runtime.close(good,learning=LearningIntent())


    def test_mixed_missing_response_fingerprint_history_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            dispatch=runtime.dispatch({"mission_id":"m-missing-response-fingerprint","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights"})
            aid=dispatch.decision.angels[0].angel_id
            good=apokrisis(angel_id=aid,mission_id="m-missing-response-fingerprint",status="SUCCESS",summary="good",business_id="zmart-consumer-rights")
            runtime.close(good,learning=LearningIntent())
            recorded=runtime.history(business_id="zmart-consumer-rights",event_type="ANGEL_RESPONSE",mission_id="m-missing-response-fingerprint")[0]
            from zion_core.cronicas import CronicaEvent
            from zion_core.persistence import CronicasJsonlSink
            CronicasJsonlSink(root/"cronicas.jsonl")(CronicaEvent(event_id="missing-response-fingerprint",occurred_at="2026-10-03T00:00:00+00:00",event_type="ANGEL_RESPONSE",mission_id="m-missing-response-fingerprint",business_id="zmart-consumer-rights",action=recorded.action,reason=recorded.reason,angel_ids=(aid,),status=recorded.status,correlation_id=recorded.correlation_id,evidence_refs=recorded.evidence_refs,uncertainty_count=recorded.uncertainty_count,correction_count=recorded.correction_count,response_fingerprint=None))
            with self.assertRaisesRegex(ValueError,"APOKRISIS_CONFLICTING_RESPONSE_HISTORY"):
                runtime.close(good,learning=LearningIntent())


    def test_conflicting_prior_response_history_fails_closed_even_when_latest_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            dispatch=runtime.dispatch({"mission_id":"m-response-history","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights"})
            aid=dispatch.decision.angels[0].angel_id
            good=apokrisis(angel_id=aid,mission_id="m-response-history",status="SUCCESS",summary="good",business_id="zmart-consumer-rights")
            runtime.close(good,learning=LearningIntent())
            from zion_core.cronicas import CronicaEvent
            from zion_core.persistence import CronicasJsonlSink
            from zion_core.cronicas import build_apokrisis_fingerprint
            bad=apokrisis(angel_id=aid,mission_id="m-response-history",status="FAILED",summary="bad",business_id="zmart-consumer-rights",error_code="FORGED")
            CronicasJsonlSink(root/"cronicas.jsonl")(CronicaEvent(event_id="bad-response",occurred_at="2026-10-03T00:00:00+00:00",event_type="ANGEL_RESPONSE",mission_id="m-response-history",business_id="zmart-consumer-rights",action="APOKRISIS",reason="FORGED",angel_ids=(aid,),status="FAILED",response_fingerprint=build_apokrisis_fingerprint(bad)))
            with self.assertRaisesRegex(ValueError,"APOKRISIS_CONFLICTING_RESPONSE_HISTORY"):
                runtime.close(good,learning=LearningIntent())


    def test_multiple_dispatch_records_with_different_routes_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            dispatch=runtime.dispatch({"mission_id":"m-conflicting-route","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights"})
            original=runtime.history(business_id="zmart-consumer-rights",event_type="MISSION_DECISION",mission_id="m-conflicting-route")[0]
            from zion_core.cronicas import CronicaEvent
            from zion_core.persistence import CronicasJsonlSink
            CronicasJsonlSink(root/"cronicas.jsonl")(CronicaEvent(event_id="conflict-route",occurred_at="2026-10-03T00:00:00+00:00",event_type="MISSION_DECISION",mission_id="m-conflicting-route",business_id="zmart-consumer-rights",action="DISPATCH",reason="AUTHORIZED",command="SANRAFAEL",host="SANRAFAEL.HOST-01",angel_ids=original.angel_ids,dispatch_fingerprint=original.dispatch_fingerprint))
            response=apokrisis(angel_id=dispatch.decision.angels[0].angel_id,mission_id="m-conflicting-route",status="SUCCESS",summary="must fail closed",business_id="zmart-consumer-rights")
            with self.assertRaisesRegex(ValueError,"APOKRISIS_CONFLICTING_ROUTE_HISTORY"):
                runtime.close(response,learning=LearningIntent())


    def test_multiple_dispatch_records_with_missing_fingerprint_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["WORKFLOWS.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            runtime.dispatch({"mission_id":"m-missing-fingerprint","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights"})
            from zion_core.cronicas import CronicaEvent
            from zion_core.persistence import CronicasJsonlSink
            CronicasJsonlSink(root/"cronicas.jsonl")(CronicaEvent(event_id="missing-fingerprint",occurred_at="2026-10-03T00:00:00+00:00",event_type="MISSION_DECISION",mission_id="m-missing-fingerprint",business_id="zmart-consumer-rights",action="DISPATCH",reason="AUTHORIZED",command="SANGABRIEL",host="SANGABRIEL.HOST-01",angel_ids=("SANGABRIEL.HOST-01.ANGEL-001",),dispatch_fingerprint=None))
            response=apokrisis(angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="m-missing-fingerprint",status="SUCCESS",summary="must fail closed",business_id="zmart-consumer-rights")
            with self.assertRaisesRegex(ValueError,"APOKRISIS_CONFLICTING_DISPATCH_FINGERPRINT"):
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
            runtime.dispatch({"mission_id":"m-fingerprint-conflict","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights"})
            from zion_core.cronicas import CronicaEvent
            from zion_core.persistence import CronicasJsonlSink
            first=runtime.history(business_id="zmart-consumer-rights",event_type="MISSION_DECISION",mission_id="m-fingerprint-conflict")[0]
            CronicasJsonlSink(root/"cronicas.jsonl")(CronicaEvent(event_id="fingerprint-conflict",occurred_at="2026-10-03T00:00:00+00:00",event_type="MISSION_DECISION",mission_id="m-fingerprint-conflict",business_id="zmart-consumer-rights",action="DISPATCH",reason="AUTHORIZED",command=first.command,host=first.host,angel_ids=first.angel_ids,dispatch_fingerprint="0"*64))
            response=apokrisis(angel_id=first.angel_ids[0],mission_id="m-fingerprint-conflict",status="SUCCESS",summary="must fail closed",business_id="zmart-consumer-rights")
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
