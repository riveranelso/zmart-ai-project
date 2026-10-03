import tempfile
import multiprocessing
import threading
import unittest
from pathlib import Path

from zion_core.persistence import PersistentCorrectionMemory


def _observe_process(path_text,queue):
    memory=PersistentCorrectionMemory(Path(path_text))
    try:
        queue.put(("ok",memory.observe("zmart-consumer-rights","Preserve this reusable workflow.")))
    except Exception as exc:
        queue.put(("error",type(exc).__name__+":"+str(exc)))


class CorrectionMemoryConcurrencyTests(unittest.TestCase):
    def test_concurrent_distinct_human_events_do_not_lose_repetition_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory=PersistentCorrectionMemory(Path(tmp)/"corrections.json")
            barrier=threading.Barrier(8)
            counts=[]
            errors=[]
            guard=threading.Lock()
            rule="Preserve this reusable workflow."

            def worker():
                try:
                    barrier.wait()
                    count=memory.observe("zmart-consumer-rights",rule)
                    with guard: counts.append(count)
                except Exception as exc:
                    with guard: errors.append(exc)

            threads=[threading.Thread(target=worker) for _ in range(8)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()

            self.assertEqual(errors,[])
            self.assertEqual(sorted(counts),list(range(1,9)))
            self.assertEqual(memory.count("zmart-consumer-rights",rule),8)



    def test_multiprocess_observe_does_not_lose_repetition_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"corrections.json"
            ctx=multiprocessing.get_context("spawn")
            queue=ctx.Queue()
            processes=[ctx.Process(target=_observe_process,args=(str(path),queue)) for _ in range(6)]
            for process in processes: process.start()
            for process in processes:
                process.join(20)
                self.assertFalse(process.is_alive(),"correction-memory child process hung")
                self.assertEqual(process.exitcode,0)
            results=[queue.get(timeout=5) for _ in processes]
            self.assertFalse([item for item in results if item[0]=="error"],results)
            self.assertEqual(sorted(item[1] for item in results),list(range(1,7)))
            memory=PersistentCorrectionMemory(path)
            self.assertEqual(
                memory.count("zmart-consumer-rights","Preserve this reusable workflow."),6
            )

if __name__=="__main__":
    unittest.main()
