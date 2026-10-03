import json
import tempfile
import threading
import unittest
from pathlib import Path

from zion_core import OmarRuntime


class RuntimeDispatchConcurrencyTests(unittest.TestCase):
    def test_concurrent_duplicate_dispatch_records_one_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
                encoding="utf-8",
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json",
            )
            mission={"mission_id":"race-1","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            barrier=threading.Barrier(8)
            actions=[]
            errors=[]
            guard=threading.Lock()

            def worker():
                try:
                    barrier.wait()
                    result=runtime.dispatch(dict(mission))
                    with guard:
                        actions.append(result.decision.action)
                except Exception as exc:
                    with guard:
                        errors.append(exc)

            threads=[threading.Thread(target=worker) for _ in range(8)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()

            self.assertEqual(errors,[])
            self.assertEqual(actions.count("DISPATCH"),1)
            self.assertEqual(actions.count("IDEMPOTENT_NOOP"),7)
            events=runtime.history(
                business_id="zmart-consumer-rights",event_type="MISSION_DECISION",mission_id="race-1"
            )
            self.assertEqual(len(events),1)


if __name__=="__main__":
    unittest.main()
