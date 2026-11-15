import multiprocessing
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from zion_core.cronicas import CronicaEvent
from zion_core.persistence import CronicasJsonlSink, read_cronicas


def _cronicas_process_writer(path_text,process_index,count):
    sink=CronicasJsonlSink(Path(path_text))
    for item_index in range(count):
        event_id=f"p{process_index}-e{item_index}"
        sink(CronicaEvent(
            event_id=event_id,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            event_type="MISSION_DECISION",
            mission_id=event_id,
            action="DISPATCH",
            reason="MULTIPROCESS_TEST",
            business_id="zmart-consumer-rights",
        ))


class CronicasMultiprocessTests(unittest.TestCase):
    def test_multiple_processes_append_complete_unique_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"cronicas.jsonl"
            ctx=multiprocessing.get_context("spawn")
            process_count=4
            events_per_process=25
            processes=[
                ctx.Process(
                    target=_cronicas_process_writer,
                    args=(str(path),index,events_per_process),
                )
                for index in range(process_count)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(20)
                self.assertFalse(process.is_alive(),"CRONICAS child process hung")
                self.assertEqual(process.exitcode,0)

            events=read_cronicas(path)
            expected=process_count*events_per_process
            self.assertEqual(len(events),expected)
            ids=[event.event_id for event in events]
            self.assertEqual(len(set(ids)),expected)


if __name__=="__main__":
    unittest.main()
