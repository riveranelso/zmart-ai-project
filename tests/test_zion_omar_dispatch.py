import json
import tempfile
import unittest
from pathlib import Path

from zion_core import CronicasMemorySink, dispatch_mission


class OmarDispatchTests(unittest.TestCase):
    def test_omar_loads_isolated_biblia_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"BIBLIA.md"
            target.write_text("# Canon\nZmart learned workflow rule.\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,
                "isolation_key":"zmart-consumer-rights",
                "context_refs":["BIBLIA.md"]
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
            sink=CronicasMemorySink()
            mission={
                "mission_id":"mission-next",
                "intent":"internal_dispatch",
                "requested_by":"OMAR",
                "scope":"WORKFLOW",
                "business_id":"zmart-consumer-rights",
            }
            result=dispatch_mission(
                mission,biblia_root=root,routes_path=routes,
                registry_path=registry,cronicas_sink=sink,
            )

            self.assertIn("Zmart learned workflow rule.",result.context.knowledge)
            self.assertEqual(result.context.business_id,"zmart-consumer-rights")
            self.assertEqual(result.decision.action,"DISPATCH")
            self.assertEqual(result.decision.business_id,"zmart-consumer-rights")
            self.assertEqual(result.decision.angels[0].context_refs,("BIBLIA.md",))
            self.assertEqual(len(sink.events),1)
            self.assertEqual(sink.events[0].event_type,"MISSION_DECISION")

    def test_omar_does_not_dispatch_when_biblia_reference_escapes_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"biblia"
            root.mkdir()
            registry=Path(tmp)/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,
                "isolation_key":"zmart-consumer-rights",
                "context_refs":["../outside.md"]
            }}}),encoding="utf-8")
            mission={
                "mission_id":"mission-bad-ref",
                "intent":"internal_dispatch",
                "requested_by":"OMAR",
                "scope":"WORKFLOW",
                "business_id":"zmart-consumer-rights",
            }
            with self.assertRaises(ValueError):
                dispatch_mission(mission,biblia_root=root,registry_path=registry)


if __name__=="__main__":
    unittest.main()
