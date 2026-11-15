import json
import tempfile
import unittest
from pathlib import Path

from zion_core import OmarRuntime


class OwnerCorrectionIdempotencyTests(unittest.TestCase):
    def runtime(self,root):
        (root/"WORKFLOWS.md").write_text(
            "# Workflows\n\n## zmart-consumer-rights\n",encoding="utf-8"
        )
        registry=root/"registry.json"
        registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
            "enabled":True,"isolation_key":"zmart-consumer-rights",
            "context_refs":["WORKFLOWS.md"]
        }}}),encoding="utf-8")
        return OmarRuntime(
            biblia_root=root,registry_path=registry,
            cronicas_path=root/"cronicas.jsonl",
            correction_memory_path=root/"corrections.json",
        )

    def test_retry_same_correction_id_does_not_fake_repetition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            runtime=self.runtime(root)
            rule="Use this exact workflow."
            first=runtime.owner_correction(
                rule,business_id="zmart-consumer-rights",correction_id="human-1"
            )
            self.assertTrue(first.processed)
            self.assertEqual(first.cycle.promotion.action,"NOT_READY")
            self.assertEqual(runtime.correction_memory.count("zmart-consumer-rights",rule),1)
            before=(root/"cronicas.jsonl").read_bytes()

            retry=runtime.owner_correction(
                rule,business_id="zmart-consumer-rights",correction_id="human-1"
            )
            self.assertFalse(retry.processed)
            self.assertEqual(retry.reason,"OWNER_CORRECTION_ALREADY_PROCESSED")
            self.assertEqual(runtime.correction_memory.count("zmart-consumer-rights",rule),1)
            self.assertEqual((root/"cronicas.jsonl").read_bytes(),before)
            self.assertNotIn(rule,(root/"WORKFLOWS.md").read_text(encoding="utf-8"))

            restarted=OmarRuntime(
                biblia_root=root,registry_path=root/"registry.json",
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            retry_after_restart=restarted.owner_correction(
                rule,business_id="zmart-consumer-rights",correction_id="human-1"
            )
            self.assertFalse(retry_after_restart.processed)
            self.assertEqual(retry_after_restart.reason,"OWNER_CORRECTION_ALREADY_PROCESSED")
            self.assertEqual(restarted.correction_memory.count("zmart-consumer-rights",rule),1)

            second_human_event=restarted.owner_correction(
                rule,business_id="zmart-consumer-rights",correction_id="human-2"
            )
            self.assertTrue(second_human_event.processed)
            self.assertEqual(second_human_event.cycle.promotion.action,"ADD")
            self.assertEqual(runtime.correction_memory.count("zmart-consumer-rights",rule),2)
            self.assertIn(rule,(root/"WORKFLOWS.md").read_text(encoding="utf-8"))

    def test_durable_owner_retry_recovers_learning_without_fake_repetition(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            root=base/"biblia"
            root.mkdir()
            outside=base/"GLOBAL.md"
            outside.write_text("# Outside\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["../GLOBAL.md"]
            }}}),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            rule="From now on preserve this durable owner rule."
            with self.assertRaisesRegex(ValueError,"BIBLIA_DESTINATION_OUTSIDE_ROOT"):
                runtime.owner_correction(
                    rule,business_id="zmart-consumer-rights",
                    correction_id="owner-recovery-1",
                )
            self.assertEqual(
                runtime.correction_memory.count("zmart-consumer-rights",rule),1
            )
            self.assertEqual(len(runtime.history(event_type="ANGEL_RESPONSE")),1)
            self.assertEqual(runtime.history(event_type="BIBLIA_MUTATION"),())

            target=root/"GLOBAL.md"
            target.write_text("# Global\n",encoding="utf-8")
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")

            restarted=OmarRuntime(
                biblia_root=root,registry_path=registry,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            recovered=restarted.owner_correction(
                rule,business_id="zmart-consumer-rights",
                correction_id="owner-recovery-1",
            )
            self.assertTrue(recovered.processed)
            self.assertEqual(
                recovered.reason,"OWNER_CORRECTION_LEARNING_RECOVERED"
            )
            self.assertIsNone(recovered.event)
            self.assertEqual(
                runtime.correction_memory.count("zmart-consumer-rights",rule),1
            )
            self.assertEqual(len(runtime.history(event_type="ANGEL_RESPONSE")),1)
            mutations=runtime.history(event_type="BIBLIA_MUTATION")
            self.assertEqual(len(mutations),1)
            self.assertEqual(mutations[0].angel_ids,("OMAR.OWNER-INPUT",))
            self.assertIn(rule,target.read_text(encoding="utf-8"))

            retry=runtime.owner_correction(
                rule,business_id="zmart-consumer-rights",
                correction_id="owner-recovery-1",
            )
            self.assertFalse(retry.processed)
            self.assertEqual(retry.reason,"OWNER_CORRECTION_ALREADY_PROCESSED")
            self.assertEqual(
                runtime.correction_memory.count("zmart-consumer-rights",rule),1
            )

    def test_non_owner_mutation_with_same_id_does_not_suppress_owner_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            root=base/"biblia"
            root.mkdir()
            workflow=root/"WORKFLOWS.md"
            workflow.write_text("# Workflows\n",encoding="utf-8")
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
            from zion_core import LearningIntent, apokrisis
            shared_id="shared-owner-id"
            angel=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id=shared_id,
                status="SUCCESS",summary="angel",business_id="zmart-consumer-rights",
                correction_signals=("ANGEL_RULE",),
            )
            self.assertTrue(runtime.close(
                angel,learning=LearningIntent(
                    scope_hint="WORKFLOW",repeated_correction=True
                )
            ).processed)

            outside=base/"GLOBAL.md"
            outside.write_text("# Outside\n",encoding="utf-8")
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["../GLOBAL.md"]
            }}}),encoding="utf-8")
            owner_rule="From now on preserve OWNER_RULE."
            with self.assertRaisesRegex(ValueError,"BIBLIA_DESTINATION_OUTSIDE_ROOT"):
                runtime.owner_correction(
                    owner_rule,business_id="zmart-consumer-rights",
                    correction_id=shared_id,
                )

            global_target=root/"GLOBAL.md"
            global_target.write_text("# Global\n",encoding="utf-8")
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            recovered=runtime.owner_correction(
                owner_rule,business_id="zmart-consumer-rights",
                correction_id=shared_id,
            )
            self.assertTrue(recovered.processed)
            self.assertEqual(
                recovered.reason,"OWNER_CORRECTION_LEARNING_RECOVERED"
            )
            self.assertIn(owner_rule,global_target.read_text(encoding="utf-8"))
            mutations=runtime.history(
                event_type="BIBLIA_MUTATION",mission_id=shared_id
            )
            self.assertEqual(len(mutations),2)
            self.assertEqual(mutations[0].angel_ids,("SANGABRIEL.HOST-01.ANGEL-001",))
            self.assertEqual(mutations[1].angel_ids,("OMAR.OWNER-INPUT",))


if __name__=="__main__":
    unittest.main()
