import unittest
from zion_core.gates import SecurityContext, evaluate_gates

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


    def test_cherubim_rejects_whitespace_only_principal(self):
        mission=self.base(business_id="zmart-consumer-rights")
        security=SecurityContext(
            authenticated=True,principal_id="   ",
            allowed_business_ids=("zmart-consumer-rights",),
        )
        denied=[
            x for x in evaluate_gates(mission,"zmart",("BIBLIA",),security)
            if not x.allowed
        ]
        self.assertEqual(denied[0].gate,"CHERUBIM")
        self.assertEqual(denied[0].reason,"AUTHENTICATION_REQUIRED")



    def test_cherubim_rejects_non_string_principal(self):
        mission=self.base(business_id="zmart-consumer-rights")
        security=SecurityContext(
            authenticated=True,principal_id=123,
            allowed_business_ids=("zmart-consumer-rights",),
        )
        denied=[
            x for x in evaluate_gates(mission,"zmart",("BIBLIA",),security)
            if not x.allowed
        ]
        self.assertEqual(denied[0].gate,"CHERUBIM")
        self.assertEqual(denied[0].reason,"AUTHENTICATION_REQUIRED")


    def test_thrones_blocks_policy_conflict(self):
        self.assertEqual(self.denied(policy_conflict=True)[0].gate,"THRONES")

    def test_thrones_fails_closed_when_approval_required_without_security_context(self):
        denied=self.denied(human_approval_required=True)
        self.assertEqual(denied[0].gate,"THRONES")
        self.assertEqual(denied[0].reason,"HUMAN_APPROVAL_REQUIRED")


    def test_thrones_rejects_truthy_non_boolean_human_approval(self):
        mission=self.base(human_approval_required=True,business_id="zmart-consumer-rights")
        for value in (1,"yes"):
            with self.subTest(value=value):
                security=SecurityContext(
                    authenticated=True,principal_id="owner",
                    allowed_business_ids=("zmart-consumer-rights",),
                    human_approval_granted=value,
                )
                denied=[
                    x for x in evaluate_gates(mission,"zmart",("BIBLIA",),security)
                    if not x.allowed
                ]
                self.assertEqual(denied[0].gate,"THRONES")
                self.assertEqual(denied[0].reason,"HUMAN_APPROVAL_REQUIRED")


    def test_thrones_accepts_explicit_human_approval(self):
        mission=self.base(human_approval_required=True,business_id="zmart-consumer-rights")
        security=SecurityContext(
            authenticated=True,principal_id="owner",
            allowed_business_ids=("zmart-consumer-rights",),
            human_approval_granted=True,
        )
        denied=[x for x in evaluate_gates(mission,"zmart",("BIBLIA",),security) if not x.allowed]
        self.assertEqual(denied,[])

    def test_powers_blocks_high_risk(self):
        self.assertEqual(self.denied(risk_level="high")[0].gate,"POWERS")

    def test_powers_honors_kill_switch(self):
        self.assertEqual(self.denied(kill_switch=True)[0].reason,"KILL_SWITCH_ACTIVE")

if __name__=="__main__":
    unittest.main()
