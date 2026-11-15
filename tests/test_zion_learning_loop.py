import unittest
from zion_core.apokrisis import apokrisis, close_apokrisis
from zion_core.cronicas import CronicasMemorySink

class ZionLearningLoopTests(unittest.TestCase):
    def test_response_records_history_and_learning_signal(self):
        sink = CronicasMemorySink()
        response = apokrisis(
            angel_id="SANMIGUEL.HOST-01.ANGEL-001",
            mission_id="m1",
            status="PARTIAL",
            summary="Completed with one correction.",
            business_id="zmart-consumer-rights",
            uncertainty=("source needs verification",),
            correction_signals=("reuse approved workflow next time",),
        )
        event, learning = close_apokrisis(response, sink)
        self.assertEqual(event.event_type, "ANGEL_RESPONSE")
        self.assertEqual(len(sink.events), 1)
        self.assertTrue(learning.needs_learning_review)
        self.assertEqual(learning.business_id, "zmart-consumer-rights")

    def test_clean_success_does_not_request_learning_review(self):
        response = apokrisis(
            angel_id="SANMIGUEL.HOST-01.ANGEL-001",
            mission_id="m2",
            status="SUCCESS",
            summary="Completed.",
            business_id="zmart-consumer-rights",
        )
        _, learning = close_apokrisis(response)
        self.assertFalse(learning.needs_learning_review)

if __name__ == "__main__":
    unittest.main()
