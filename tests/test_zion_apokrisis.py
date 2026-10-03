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

if __name__ == "__main__":
    unittest.main()
