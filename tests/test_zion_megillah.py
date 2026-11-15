import unittest
from zion_core.router import MissionValidationError, validate_mission

class ZionMegillahTests(unittest.TestCase):
    def base(self, **changes):
        mission = {
            "mission_id": "m1",
            "intent": "threat_detection",
            "requested_by": "OMAR",
            "scope": "zmart",
            "business_id": "zmart-consumer-rights",
        }
        mission.update(changes)
        return mission

    def test_stable_core_is_valid(self):
        validate_mission(self.base())

    def test_runtime_extension_signal_is_allowed(self):
        validate_mission(self.base(custom_runtime_signal={"value": 1}))

    def test_blank_required_field_is_rejected(self):
        with self.assertRaises(MissionValidationError):
            validate_mission(self.base(intent=" "))

    def test_non_boolean_guardrail_signal_is_rejected(self):
        with self.assertRaises(MissionValidationError):
            validate_mission(self.base(kill_switch="yes"))

    def test_angel_count_has_practical_upper_bound(self):
        with self.assertRaises(MissionValidationError):
            validate_mission(self.base(angel_count_max=101))

if __name__ == "__main__":
    unittest.main()
