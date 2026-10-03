import unittest
from zion_core.gates import evaluate_gates

class ZionGateTests(unittest.TestCase):
    def base(self, **changes):
        data={"risk_level":"low"}
        data.update(changes)
        return data

    def denied(self, **changes):
        return [x for x in evaluate_gates(self.base(**changes),"zmart",("BIBLIA",)) if not x.allowed]

    def test_clean_mission_passes_all_gates(self):
        self.assertEqual(self.denied(), [])

    def test_seraphim_blocks_integrity_conflict(self):
        self.assertEqual(self.denied(integrity_conflict=True)[0].gate,"SERAPHIM")

    def test_cherubim_blocks_cross_business_boundary(self):
        self.assertEqual(self.denied(isolation_key="other")[0].gate,"CHERUBIM")

    def test_thrones_blocks_policy_conflict(self):
        self.assertEqual(self.denied(policy_conflict=True)[0].gate,"THRONES")

    def test_powers_blocks_high_risk(self):
        self.assertEqual(self.denied(risk_level="high")[0].gate,"POWERS")

    def test_powers_honors_kill_switch(self):
        self.assertEqual(self.denied(kill_switch=True)[0].reason,"KILL_SWITCH_ACTIVE")

if __name__=="__main__":
    unittest.main()
