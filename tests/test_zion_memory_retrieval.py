import json
import tempfile
import unittest
from pathlib import Path

from zion_core import LearningIntent, apokrisis, receive_apokrisis, retrieve_biblia


class ZionMemoryRetrievalTests(unittest.TestCase):
    def test_learned_rule_is_retrievable_for_future_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"zmart360"/"BIBLIA"/"WORKFLOWS.md"
            target.parent.mkdir(parents=True)
            target.write_text("# Workflows\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({
                "defaults":{"deny_unknown_business":True,"deny_disabled_business":True,"require_context_refs":True},
                "businesses":{"zmart-consumer-rights":{
                    "enabled":True,
                    "isolation_key":"zmart-consumer-rights",
                    "context_refs":["zmart360/BIBLIA/WORKFLOWS.md"]
                }}
            }),encoding="utf-8")

            response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",
                mission_id="m-memory-1",
                status="SUCCESS",
                summary="Durable correction",
                business_id="zmart-consumer-rights",
                correction_signals=("Future missions must load this learned rule.",),
            )
            receive_apokrisis(
                response,
                biblia_root=root,
                registry_path=registry,
                learning=LearningIntent(stable_workflow=True),
            )

            future_context=retrieve_biblia(
                "zmart-consumer-rights",
                root=root,
                registry_path=registry,
            )
            self.assertIn("Future missions must load this learned rule.",future_context.text)
            self.assertEqual(future_context.business_id,"zmart-consumer-rights")


if __name__=="__main__":
    unittest.main()
