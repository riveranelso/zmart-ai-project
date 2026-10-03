import unittest
from zion_core.router import MissionValidationError, route_mission

class ZionRouterTests(unittest.TestCase):
    def mission(self, **overrides):
        data = {"mission_id":"m1","intent":"threat_detection","requested_by":"OMAR",
                "scope":"zmart","business_id":"zmart-consumer-rights","risk_level":"low",
                "angel_count_max":2}
        data.update(overrides)
        return data

    def test_registered_business_dispatches(self):
        result = route_mission(self.mission())
        self.assertEqual(result.action, "DISPATCH")
        self.assertEqual(result.command, "MICHAEL")
        self.assertEqual(result.host, "MICHAEL.HOST-01")
        self.assertEqual(result.isolation_key, "zmart-consumer-rights")
        self.assertTrue(result.context_refs)

    def test_unknown_business_requires_review(self):
        result = route_mission(self.mission(business_id="unknown"))
        self.assertEqual(result.action, "REQUIRE_HUMAN_REVIEW")
        self.assertEqual(result.reason, "BUSINESS_NOT_REGISTERED")

    def test_unknown_intent_requires_review(self):
        self.assertEqual(route_mission(self.mission(intent="unknown")).reason, "ROUTE_NOT_FOUND")

    def test_high_risk_requires_review(self):
        self.assertEqual(route_mission(self.mission(risk_level="high")).reason, "RISK_GATE")

    def test_explicit_human_approval_requires_review(self):
        self.assertEqual(route_mission(self.mission(human_approval_required=True)).reason,
                         "HUMAN_APPROVAL_REQUIRED")

    def test_command_conflict_requires_review(self):
        self.assertEqual(route_mission(self.mission(target_command="GABRIEL")).reason,
                         "TARGET_COMMAND_CONFLICT")

    def test_host_conflict_requires_review(self):
        self.assertEqual(route_mission(self.mission(target_host="MICHAEL.HOST-02")).reason,
                         "TARGET_HOST_CONFLICT")

    def test_missing_business_is_invalid(self):
        data = self.mission()
        del data["business_id"]
        with self.assertRaises(MissionValidationError):
            route_mission(data)

if __name__ == "__main__":
    unittest.main()
