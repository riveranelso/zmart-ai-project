import json
import tempfile
import unittest
from pathlib import Path

from zion_core import CronicaEvent, OmarRuntime


class RuntimeRecoveryTests(unittest.TestCase):
    def test_runtime_history_is_read_only_and_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cronicas=root/"cronicas.jsonl"
            runtime=OmarRuntime(
                biblia_root=root,
                cronicas_path=cronicas,
                correction_memory_path=root/"corrections.json",
            )
            sink=runtime.cronicas_sink
            sink(CronicaEvent(
                event_id="1",occurred_at="2026-10-03T00:00:00+00:00",
                event_type="MISSION_DECISION",mission_id="m1",action="DISPATCH",
                reason="TEST",business_id="zmart-consumer-rights",
            ))
            sink(CronicaEvent(
                event_id="2",occurred_at="2026-10-03T00:00:01+00:00",
                event_type="ANGEL_RESPONSE",mission_id="m1",action="APOKRISIS",
                reason="SUCCESS",business_id="zmart-consumer-rights",
            ))
            sink(CronicaEvent(
                event_id="3",occurred_at="2026-10-03T00:00:02+00:00",
                event_type="MISSION_DECISION",mission_id="m2",action="DISPATCH",
                reason="TEST",business_id="scan-water-intelligence",
            ))
            before=cronicas.read_bytes()
            history=runtime.mission_history("m1",business_id="zmart-consumer-rights")
            self.assertEqual(tuple(e.event_id for e in history),("1","2"))
            self.assertEqual(cronicas.read_bytes(),before)
            self.assertFalse((root/"corrections.json").exists())

    def test_empty_mission_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            runtime=OmarRuntime(
                biblia_root=root,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            with self.assertRaisesRegex(ValueError,"MISSION_ID_REQUIRED"):
                runtime.mission_history("   ")


if __name__=="__main__":
    unittest.main()
