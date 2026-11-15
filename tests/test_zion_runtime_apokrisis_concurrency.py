import json
import tempfile
import threading
import unittest
from pathlib import Path

from zion_core import LearningIntent, OmarRuntime, apokrisis


class RuntimeApokrisisConcurrencyTests(unittest.TestCase):
    def test_concurrent_same_angel_response_is_processed_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text(
                "# Workflows\n\n## zmart-consumer-rights\n",encoding="utf-8"
            )
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="race-close-1",
                status="SUCCESS",summary="done",business_id="zmart-consumer-rights",
            )
            barrier=threading.Barrier(8)
            processed=[]
            errors=[]
            guard=threading.Lock()

            def worker():
                try:
                    barrier.wait()
                    result=runtime.close(response,learning=LearningIntent())
                    with guard: processed.append(result.processed)
                except Exception as exc:
                    with guard: errors.append(exc)

            threads=[threading.Thread(target=worker) for _ in range(8)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()

            self.assertEqual(errors,[])
            self.assertEqual(processed.count(True),1)
            self.assertEqual(processed.count(False),7)
            events=runtime.history(
                business_id="zmart-consumer-rights",
                event_type="ANGEL_RESPONSE",mission_id="race-close-1",
            )
            self.assertEqual(len(events),1)

    def test_distinct_angels_same_mission_remain_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text(
                "# Workflows\n\n## zmart-consumer-rights\n",encoding="utf-8"
            )
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            responses=[
                apokrisis(
                    angel_id=f"SANGABRIEL.HOST-01.ANGEL-00{i}",mission_id="shared-mission",
                    status="SUCCESS",summary="done",business_id="zmart-consumer-rights",
                ) for i in (1,2)
            ]
            results=[runtime.close(x,learning=LearningIntent()) for x in responses]
            self.assertEqual([x.processed for x in results],[True,True])


if __name__=="__main__":
    unittest.main()
