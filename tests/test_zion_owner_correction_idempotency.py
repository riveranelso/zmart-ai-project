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
            self.assertEqual(len(runtime.history(event_type="BIBLIA_MUTATION")),1)
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


if __name__=="__main__":
    unittest.main()
