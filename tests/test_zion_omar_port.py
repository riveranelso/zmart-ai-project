import json
import tempfile
import unittest
from pathlib import Path

from zion_core import LearningIntent, apokrisis, receive_apokrisis


class OmarPortTests(unittest.TestCase):
    def test_receive_apokrisis_runs_durable_learning(self):
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
                mission_id="m-port-1",
                status="SUCCESS",
                summary="Learned workflow correction",
                business_id="zmart-consumer-rights",
                correction_signals=("Keep this workflow rule.",),
            )
            _,cycle=receive_apokrisis(
                response,
                biblia_root=root,
                registry_path=registry,
                learning=LearningIntent(stable_workflow=True),
            )
            self.assertEqual(cycle.promotion.action,"ADD")
            self.assertTrue(cycle.grapho.changed)
            self.assertIn("Keep this workflow rule.",target.read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
