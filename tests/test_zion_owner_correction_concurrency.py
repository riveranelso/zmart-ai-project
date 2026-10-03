import json
import tempfile
import threading
import unittest
from pathlib import Path

from zion_core import OmarRuntime


class OwnerCorrectionConcurrencyTests(unittest.TestCase):
    def test_same_correction_id_concurrently_counts_once(self):
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
            rule="Always preserve this exact workflow."
            barrier=threading.Barrier(8)
            results=[]
            errors=[]
            guard=threading.Lock()

            def worker():
                try:
                    barrier.wait()
                    result=runtime.owner_correction(
                        rule,business_id="zmart-consumer-rights",
                        correction_id="human-race-1",
                    )
                    with guard: results.append(result)
                except Exception as exc:
                    with guard: errors.append(exc)

            threads=[threading.Thread(target=worker) for _ in range(8)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()

            self.assertEqual(errors,[])
            self.assertEqual(sum(x.processed for x in results),1)
            self.assertEqual(
                sum(x.reason=="OWNER_CORRECTION_ALREADY_PROCESSED" for x in results),7
            )
            self.assertEqual(
                runtime.correction_memory.count("zmart-consumer-rights",rule),1
            )
            events=runtime.history(
                business_id="zmart-consumer-rights",
                event_type="ANGEL_RESPONSE",mission_id="human-race-1",
            )
            self.assertEqual(len(events),1)

    def test_distinct_human_correction_ids_still_count_as_distinct_events(self):
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
            rule="Use the locked workflow."
            first=runtime.owner_correction(
                rule,business_id="zmart-consumer-rights",correction_id="human-1"
            )
            second=runtime.owner_correction(
                rule,business_id="zmart-consumer-rights",correction_id="human-2"
            )
            self.assertTrue(first.processed)
            self.assertTrue(second.processed)
            self.assertEqual(runtime.correction_memory.count("zmart-consumer-rights",rule),2)


if __name__=="__main__":
    unittest.main()
