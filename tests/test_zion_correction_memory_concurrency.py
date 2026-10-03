import tempfile
import threading
import unittest
from pathlib import Path

from zion_core.persistence import PersistentCorrectionMemory


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


if __name__=="__main__":
    unittest.main()
