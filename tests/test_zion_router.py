import unittest
from zion_core.router import MissionValidationError, route_mission

class ZionRouterTests(unittest.TestCase):
    def mission(self,**changes):
        data={"mission_id":"m1","intent":"threat_detection","requested_by":"OMAR","scope":"zmart",
              "business_id":"zmart-consumer-rights","risk_level":"low","angel_count_max":2}
        data.update(changes); return data

    def test_clean_registered_mission_dispatches(self):
        r=route_mission(self.mission())
        self.assertEqual(r.action,"DISPATCH")
        self.assertEqual(r.reason,"ANGELS_ALLOCATED")
        self.assertEqual(r.host,"SANMIGUEL.HOST-01")\n        self.assertEqual([a.angel_id for a in r.angels],["SANMIGUEL.HOST-01.ANGEL-001","SANMIGUEL.HOST-01.ANGEL-002"])

    def test_unknown_business_stops_before_dispatch(self):
        self.assertEqual(route_mission(self.mission(business_id="unknown")).reason,"BUSINESS_NOT_REGISTERED")

    def test_unknown_route_stops(self):
        self.assertEqual(route_mission(self.mission(intent="unknown")).reason,"ROUTE_NOT_FOUND")

    def test_seraphim_denial_is_reported(self):
        r=route_mission(self.mission(integrity_conflict=True))
        self.assertEqual((r.denied_by,r.reason),("SERAPHIM","INTEGRITY_CONFLICT"))

    def test_cherubim_denial_is_reported(self):
        r=route_mission(self.mission(isolation_key="other-business"))
        self.assertEqual((r.denied_by,r.reason),("CHERUBIM","ISOLATION_BOUNDARY_VIOLATION"))

    def test_thrones_denial_is_reported(self):
        r=route_mission(self.mission(policy_conflict=True))
        self.assertEqual((r.denied_by,r.reason),("THRONES","POLICY_CONFLICT"))

    def test_powers_denial_is_reported(self):
        r=route_mission(self.mission(kill_switch=True))
        self.assertEqual((r.denied_by,r.reason),("POWERS","KILL_SWITCH_ACTIVE"))

    def test_high_risk_is_powers_gate(self):
        r=route_mission(self.mission(risk_level="high"))
        self.assertEqual((r.denied_by,r.reason),("POWERS","RISK_GATE"))

    def test_missing_business_is_invalid(self):
        data=self.mission(); del data["business_id"]
        with self.assertRaises(MissionValidationError): route_mission(data)

if __name__=="__main__": unittest.main()
