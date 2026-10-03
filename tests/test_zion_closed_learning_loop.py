import json
import tempfile
import unittest
from pathlib import Path

from zion_core import (
    CronicasJsonlSink,
    PersistentCorrectionMemory,
    apokrisis,
    dispatch_mission,
    execution_contexts,
    prepare_mission,
    receive_apokrisis,
)


class ClosedLearningLoopTests(unittest.TestCase):
    def test_dispatch_response_learning_and_next_mission_use_new_knowledge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            biblia=root/"WORKFLOWS.md"
            biblia.write_text("# Workflows\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,
                "isolation_key":"zmart-consumer-rights",
                "context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n"
                "  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n"
                "    host: SANGABRIEL.HOST-01\n"
                "fallback:\n"
                "  action: REQUIRE_HUMAN_REVIEW\n",
                encoding="utf-8",
            )
            cronicas_path=root/"runtime"/"cronicas.jsonl"
            sink=CronicasJsonlSink(cronicas_path)
            memory=PersistentCorrectionMemory(root/"runtime"/"corrections.json")
            mission={
                "mission_id":"loop-001",
                "intent":"internal_dispatch",
                "requested_by":"OMAR",
                "scope":"WORKFLOW",
                "business_id":"zmart-consumer-rights",
            }

            first_dispatch=dispatch_mission(
                mission,biblia_root=root,routes_path=routes,
                registry_path=registry,cronicas_sink=sink,
            )
            first_execution=execution_contexts(first_dispatch)
            self.assertEqual(len(first_execution),1)
            self.assertNotIn("Use the approved close format.",first_execution[0].knowledge)

            rule="Use the approved close format."
            memory.observe("zmart-consumer-rights",rule)
            repeated=memory.observe("zmart-consumer-rights",rule)>=2
            response=apokrisis(
                angel_id=first_execution[0].commission.angel_id,
                mission_id=mission["mission_id"],
                status="SUCCESS",
                summary="Mission completed with owner correction",
                business_id="zmart-consumer-rights",
                correction_signals=(rule,),
            )
            from zion_core import LearningIntent
            _,cycle=receive_apokrisis(
                response,biblia_root=root,registry_path=registry,
                cronicas_sink=sink,
                learning=LearningIntent(repeated_correction=repeated),
            )
            self.assertEqual(cycle.promotion.action,"ADD")

            next_mission=dict(mission,mission_id="loop-002")
            second_dispatch=dispatch_mission(
                next_mission,biblia_root=root,routes_path=routes,
                registry_path=registry,cronicas_sink=sink,
            )
            second_execution=execution_contexts(second_dispatch)
            self.assertIn(rule,second_execution[0].knowledge)

            events=[
                json.loads(line)
                for line in cronicas_path.read_text(encoding="utf-8").splitlines()
            ]
            types=[event["event_type"] for event in events]
            self.assertIn("MISSION_DECISION",types)
            self.assertIn("ANGEL_RESPONSE",types)
            self.assertIn("BIBLIA_MUTATION",types)
            self.assertNotIn(rule,cronicas_path.read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
