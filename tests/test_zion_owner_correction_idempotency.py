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

            second_human_event=runtime.owner_correction(
                rule,business_id="zmart-consumer-rights",correction_id="human-2"
            )
            self.assertTrue(second_human_event.processed)
            self.assertEqual(second_human_event.cycle.promotion.action,"ADD")
            self.assertEqual(runtime.correction_memory.count("zmart-consumer-rights",rule),2)
            self.assertIn(rule,(root/"WORKFLOWS.md").read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
