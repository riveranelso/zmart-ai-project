import json
import tempfile
import unittest
from pathlib import Path

from zion_core import LearningIntent, OmarRuntime, apokrisis


class LearningRecoveryTests(unittest.TestCase):
    def test_retry_completes_learning_without_duplicate_angel_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            root=base/"biblia"
            root.mkdir()
            outside=base/"WORKFLOWS.md"
            outside.write_text("# Outside\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,
                "isolation_key":"zmart-consumer-rights",
                "context_refs":["../WORKFLOWS.md"]
            }}}),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,
                registry_path=registry,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            rule="RECOVERED_LEARNING_RULE"
            response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",
                mission_id="recover-learning-1",
                status="SUCCESS",
                summary="done",
                business_id="zmart-consumer-rights",
                correction_signals=(rule,),
            )
            intent=LearningIntent(scope_hint="WORKFLOW",repeated_correction=True)

            with self.assertRaisesRegex(ValueError,"BIBLIA_DESTINATION_OUTSIDE_ROOT"):
                runtime.close(response,learning=intent)

            self.assertEqual(len(runtime.history(event_type="ANGEL_RESPONSE")),1)
            self.assertEqual(runtime.history(event_type="BIBLIA_MUTATION"),())

            target=root/"WORKFLOWS.md"
            target.write_text("# Workflows\n",encoding="utf-8")
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,
                "isolation_key":"zmart-consumer-rights",
                "context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")

            recovered=runtime.close(response,learning=intent)
            self.assertTrue(recovered.processed)
            self.assertEqual(recovered.reason,"APOKRISIS_LEARNING_RECOVERED")
            self.assertIsNone(recovered.event)
            self.assertIn(rule,target.read_text(encoding="utf-8"))
            self.assertEqual(len(runtime.history(event_type="ANGEL_RESPONSE")),1)
            mutations=runtime.history(event_type="BIBLIA_MUTATION")
            self.assertEqual(len(mutations),1)
            self.assertEqual(mutations[0].status,"CHANGED")

            retry=runtime.close(response,learning=intent)
            self.assertFalse(retry.processed)
            self.assertEqual(retry.reason,"APOKRISIS_ALREADY_PROCESSED")
            self.assertEqual(len(runtime.history(event_type="ANGEL_RESPONSE")),1)
            self.assertEqual(len(runtime.history(event_type="BIBLIA_MUTATION")),1)


if __name__=="__main__":
    unittest.main()
