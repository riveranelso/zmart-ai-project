import json
import tempfile
import unittest
from pathlib import Path

from zion_core.router import MissionValidationError, route_mission


class ZionRouterTests(unittest.TestCase):
    def mission(self, **overrides):
        base = {
            "mission_id": "mission-001",
            "intent": "threat_detection",
            "requested_by": "OMAR",
            "scope": "zmart",
            "risk_level": "low",
            "angel_count_max": 2,
        }
        base.update(overrides)
        return base

    def test_routes_known_intent(self):
        result = route_mission(self.mission())
        self.assertEqual(result.action, "DISPATCH")
        self.assertEqual(result.command, "MICHAEL")
        self.assertEqual(result.host, "MICHAEL.HOST-01")
        self.assertEqual(result.angel_prefix, "MICHAEL.HOST-01.ANGEL-")

    def test_unknown_route_requires_human_review(self):
        result = route_mission(self.mission(intent="unknown"))
        self.assertEqual(result.action, "REQUIRE_HUMAN_REVIEW")
        self.assertEqual(result.reason, "ROUTE_NOT_FOUND")

    def test_explicit_human_gate_is_respected(self):
        result = route_mission(self.mission(human_approval_required=True))
        self.assertEqual(result.action, "REQUIRE_HUMAN_REVIEW")
        self.assertEqual(result.reason, "HUMAN_APPROVAL_REQUIRED")

    def test_high_risk_never_auto_dispatches(self):
        result = route_mission(self.mission(risk_level="high"))
        self.assertEqual(result.action, "REQUIRE_HUMAN_REVIEW")
        self.assertEqual(result.reason, "RISK_GATE")

    def test_target_override_cannot_redirect_command(self):
        result = route_mission(self.mission(target_command="GABRIEL"))
        self.assertEqual(result.reason, "TARGET_COMMAND_CONFLICT")

    def test_target_override_cannot_redirect_host(self):
        result = route_mission(self.mission(target_host="MICHAEL.HOST-02"))
        self.assertEqual(result.reason, "TARGET_HOST_CONFLICT")

    def test_missing_required_field_rejected(self):
        mission = self.mission()
        del mission["scope"]
        with self.assertRaises(MissionValidationError):
            route_mission(mission)

    def test_invalid_angel_count_rejected(self):
        with self.assertRaises(MissionValidationError):
            route_mission(self.mission(angel_count_max=0))

    def test_duplicate_route_registry_fails_closed(self):
        data = """routes:
  - intent: x
    command: MICHAEL
    host: MICHAEL.HOST-01
  - intent: x
    command: GABRIEL
    host: GABRIEL.HOST-01
fallback:
  action: REQUIRE_HUMAN_REVIEW
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "routes.yaml"
            path.write_text(data, encoding="utf-8")
            with self.assertRaises(RuntimeError):
                route_mission(self.mission(intent="x"), path)


if __name__ == "__main__":
    unittest.main()
