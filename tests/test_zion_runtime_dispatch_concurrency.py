import json
import multiprocessing
import tempfile
import threading
import unittest
from pathlib import Path

from zion_core import OmarRuntime


def _dispatch_process(root_text,registry_text,routes_text,queue):
    root=Path(root_text)
    runtime=OmarRuntime(
        biblia_root=root,registry_path=Path(registry_text),routes_path=Path(routes_text),
        cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json",
    )
    mission={"mission_id":"process-race-1","intent":"internal_dispatch","requested_by":"OMAR",
             "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
    try:
        queue.put(("ok",runtime.dispatch(mission).decision.action))
    except Exception as exc:
        queue.put(("error",type(exc).__name__+":"+str(exc)))


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


    def test_same_mission_id_with_different_route_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n"
                "  - intent: first\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n"
                "  - intent: second\n    command: SANMIGUEL\n    host: SANMIGUEL.HOST-01\n",
                encoding="utf-8",
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json",
            )
            base={"mission_id":"reuse-1","requested_by":"OMAR","scope":"WORKFLOW",
                  "business_id":"zmart-consumer-rights"}
            first=runtime.dispatch(dict(base,intent="first"))
            self.assertEqual(first.decision.action,"DISPATCH")
            with self.assertRaisesRegex(ValueError,"MISSION_ID_REUSE_CONFLICT"):
                runtime.dispatch(dict(base,intent="second"))


    def test_multiprocess_duplicate_dispatch_records_one_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
                encoding="utf-8",
            )
            ctx=multiprocessing.get_context("spawn")
            queue=ctx.Queue()
            processes=[
                ctx.Process(target=_dispatch_process,args=(str(root),str(registry),str(routes),queue))
                for _ in range(4)
            ]
            for process in processes: process.start()
            for process in processes:
                process.join(20)
                self.assertFalse(process.is_alive(),"dispatch child process hung")
                self.assertEqual(process.exitcode,0)
            results=[queue.get(timeout=5) for _ in processes]
            self.assertFalse([item for item in results if item[0]=="error"],results)
            actions=[item[1] for item in results]
            self.assertEqual(actions.count("DISPATCH"),1)
            self.assertEqual(actions.count("IDEMPOTENT_NOOP"),3)
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json",
            )
            events=runtime.history(
                business_id="zmart-consumer-rights",event_type="MISSION_DECISION",
                mission_id="process-race-1",
            )
            self.assertEqual(len(events),1)

if __name__=="__main__":
    unittest.main()
