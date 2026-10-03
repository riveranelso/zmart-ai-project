import unittest
from zion_core.apokrisis import apokrisis

class ZionApokrisisTests(unittest.TestCase):
    def test_success(self):
        result = apokrisis(
            angel_id="SANMIGUEL.HOST-01.ANGEL-001",
            mission_id="m1",
            status="SUCCESS",
            summary="Completed.",
            business_id="zmart-consumer-rights",
        )
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.mission_id, "m1")

    def test_failed_requires_error_code(self):
        with self.assertRaises(ValueError):
            apokrisis(
                angel_id="SANMIGUEL.HOST-01.ANGEL-001",
                mission_id="m2",
                status="FAILED",
                summary="Failed.",
                business_id="zmart-consumer-rights",
            )

    def test_blank_summary_rejected(self):
        with self.assertRaises(ValueError):
            apokrisis(
                angel_id="SANMIGUEL.HOST-01.ANGEL-001",
                mission_id="m3",
                status="SUCCESS",
                summary=" ",
                business_id="zmart-consumer-rights",
            )

    def test_non_string_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"APOKRISIS_IDENTITY_REQUIRED"):
            apokrisis(
                angel_id=123,mission_id="m4",status="SUCCESS",
                summary="Completed.",business_id="zmart-consumer-rights",
            )

    def test_string_is_not_accepted_as_correction_signal_collection(self):
        with self.assertRaisesRegex(ValueError,"INVALID_APOKRISIS_CORRECTION_SIGNALS"):
            apokrisis(
                angel_id="ANGEL-1",mission_id="m5",status="SUCCESS",
                summary="Completed.",business_id="zmart-consumer-rights",
                correction_signals="not-a-tuple",
            )

if __name__ == "__main__":
    unittest.main()
