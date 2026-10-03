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

if __name__ == "__main__":
    unittest.main()
