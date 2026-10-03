import tempfile
import json
import unittest
import threading
import time
from pathlib import Path

from zion_core import CronicaEvent, CronicasJsonlSink, CronicasReadError, read_cronicas
from zion_core.persistence import LocalOperationLock


class CronicasReaderTests(unittest.TestCase):
    def event(self,event_id,business,event_type,mission):
        return CronicaEvent(
            event_id=event_id,occurred_at="2026-10-03T00:00:00+00:00",
            event_type=event_type,mission_id=mission,action="TEST",reason="TEST",
            business_id=business,
        )

    def test_filters_preserve_append_order_and_business_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"cronicas.jsonl"
            sink=CronicasJsonlSink(path)
            sink(self.event("1","zmart-consumer-rights","MISSION_DECISION","m1"))
            sink(self.event("2","scan-water-intelligence","MISSION_DECISION","m2"))
            sink(self.event("3","zmart-consumer-rights","BIBLIA_MUTATION","m1"))
            events=read_cronicas(path,business_id="zmart-consumer-rights")
            self.assertEqual(tuple(e.event_id for e in events),("1","3"))
            mutations=read_cronicas(
                path,business_id="zmart-consumer-rights",event_type="BIBLIA_MUTATION"
            )
            self.assertEqual(tuple(e.event_id for e in mutations),("3",))
            mission=read_cronicas(path,mission_id="m1")
            self.assertEqual(tuple(e.event_id for e in mission),("1","3"))

    def test_missing_history_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(read_cronicas(Path(tmp)/"missing.jsonl"),())

    def test_corrupt_line_fails_closed_with_line_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"cronicas.jsonl"
            path.write_text('{"broken":\n',encoding="utf-8")
            with self.assertRaisesRegex(CronicasReadError,"INVALID_CRONICAS_LINE:1"):
                read_cronicas(path)


    def test_semantically_malformed_metadata_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"cronicas.jsonl"
            base={
                "event_id":"1","occurred_at":"2026-10-03T00:00:00+00:00",
                "event_type":"MISSION_DECISION","mission_id":"m1",
                "action":"DISPATCH","reason":"TEST","business_id":"zmart-consumer-rights",
                "angel_ids":[],"evidence_refs":[],
            }
            malformed_rows=(
                dict(base,mission_id=123),
                dict(base,angel_ids="SANMIGUEL.HOST-01.ANGEL-001"),
                dict(base,uncertainty_count=True),
                dict(base,dispatch_fingerprint="not-a-sha256"),
                dict(base,response_fingerprint="not-a-sha256"),
            )
            for row in malformed_rows:
                with self.subTest(row=row):
                    path.write_text(json.dumps(row)+"\n",encoding="utf-8")
                    with self.assertRaisesRegex(CronicasReadError,"INVALID_CRONICAS_LINE:1"):
                        read_cronicas(path)

    def test_reader_waits_for_active_append_lock_before_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"cronicas.jsonl"
            sink=CronicasJsonlSink(path)
            sink(self.event("1","zmart-consumer-rights","MISSION_DECISION","m1"))
            lock=LocalOperationLock(path.parent/(path.name+".append-locks"))
            results=[]
            errors=[]

            with lock.hold("CRONICAS","JSONL_APPEND",str(path.resolve())):
                thread=threading.Thread(
                    target=lambda: self._capture_read(path,results,errors)
                )
                thread.start()
                time.sleep(0.1)
                self.assertTrue(thread.is_alive())
                self.assertEqual(results,[])
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors,[])
            self.assertEqual(len(results),1)
            self.assertEqual(results[0][0].event_id,"1")

    @staticmethod
    def _capture_read(path,results,errors):
        try:
            results.append(read_cronicas(path))
        except Exception as exc:
            errors.append(exc)


if __name__=="__main__":
    unittest.main()
