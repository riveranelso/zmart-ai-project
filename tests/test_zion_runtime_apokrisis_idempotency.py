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



if __name__=="__main__":
    unittest.main()
