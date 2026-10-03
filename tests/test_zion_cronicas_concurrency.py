import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from zion_core.cronicas import CronicaEvent
from zion_core.persistence import CronicasJsonlSink, read_cronicas


class CronicasConcurrencyTests(unittest.TestCase):
    def test_concurrent_appends_remain_complete_jsonl_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"cronicas.jsonl"
            sink=CronicasJsonlSink(path)
            workers=16
            each=40
            barrier=threading.Barrier(workers)
            errors=[]
            guard=threading.Lock()

            def writer(worker):
                try:
                    barrier.wait()
                    for index in range(each):
                        sink(CronicaEvent(
                            event_id=f"{worker}-{index}",
                            occurred_at=datetime.now(timezone.utc).isoformat(),
                            event_type="MISSION_DECISION",
                            mission_id=f"m-{worker}-{index}",
                            action="DISPATCH",reason="TEST",
                            business_id="zmart-consumer-rights",
                        ))
                except Exception as exc:
                    with guard: errors.append(exc)

            threads=[threading.Thread(target=writer,args=(i,)) for i in range(workers)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()

            self.assertEqual(errors,[])
            events=read_cronicas(path)
            self.assertEqual(len(events),workers*each)
            self.assertEqual(len({event.event_id for event in events}),workers*each)


if __name__=="__main__":
    unittest.main()
