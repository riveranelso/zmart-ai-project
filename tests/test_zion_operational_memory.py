import json
import tempfile
import unittest
from pathlib import Path

from zion_core import LearningIntent, apokrisis, prepare_mission, receive_apokrisis


class OmarOperationalMemoryTests(unittest.TestCase):
    def test_future_mission_loads_rule_learned_by_omar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"zmart360"/"BIBLIA"/"WORKFLOWS.md"
            target.parent.mkdir(parents=True)
            target.write_text("# Workflows\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({
                "businesses":{"zmart-consumer-rights":{
                    "enabled":True,
                    "isolation_key":"zmart-consumer-rights",
                    "context_refs":["zmart360/BIBLIA/WORKFLOWS.md"]
                }}
            }),encoding="utf-8")

            learned="Always load the approved workflow before future execution."
            response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",
                mission_id="m-operational-memory",
                status="SUCCESS",
                summary="Correction learned",
                business_id="zmart-consumer-rights",
                correction_signals=(learned,),
            )
            receive_apokrisis(
                response,
                biblia_root=root,
                registry_path=registry,
                learning=LearningIntent(stable_workflow=True),
            )

            next_mission=prepare_mission(
                "zmart-consumer-rights",
                biblia_root=root,
                registry_path=registry,
            )
            self.assertIn(learned,next_mission.knowledge)
            self.assertEqual(next_mission.business_id,"zmart-consumer-rights")


if __name__=="__main__":
    unittest.main()
