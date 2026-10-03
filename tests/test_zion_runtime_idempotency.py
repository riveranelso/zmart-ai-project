import json
import tempfile
import unittest
from pathlib import Path

from zion_core import OmarRuntime


class RuntimeIdempotencyTests(unittest.TestCase):
    def test_duplicate_mission_does_not_dispatch_or_append_second_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
                encoding="utf-8",
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            mission={
                "mission_id":"same-1","intent":"internal_dispatch","requested_by":"OMAR",
                "scope":"WORKFLOW","business_id":"zmart-consumer-rights",
            }
            first=runtime.dispatch(mission)
            self.assertEqual(first.decision.action,"DISPATCH")
            before=(root/"cronicas.jsonl").read_bytes()
            second=runtime.dispatch(dict(mission))
            self.assertEqual(second.decision.action,"IDEMPOTENT_NOOP")
            self.assertEqual(second.decision.reason,"MISSION_ALREADY_DECIDED")
            self.assertEqual((root/"cronicas.jsonl").read_bytes(),before)
            events=runtime.history(
                business_id="zmart-consumer-rights",
                event_type="MISSION_DECISION",mission_id="same-1",
            )
            self.assertEqual(len(events),1)


    def test_same_mission_id_cannot_change_from_routed_to_unknown_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
                encoding="utf-8",
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            base={"mission_id":"same-route-unknown","requested_by":"OMAR",
                  "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            self.assertEqual(
                runtime.dispatch(dict(base,intent="internal_dispatch")).decision.action,
                "DISPATCH",
            )
            with self.assertRaisesRegex(ValueError,"MISSION_ID_REUSE_CONFLICT"):
                runtime.dispatch(dict(base,intent="unknown-now"))

if __name__=="__main__":
    unittest.main()
