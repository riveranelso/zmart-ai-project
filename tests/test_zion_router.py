import unittest
import tempfile
from pathlib import Path
from zion_core.router import MissionValidationError, validate_mission, route_mission, load_derekh

class ZionRouterTests(unittest.TestCase):
    def mission(self,**changes):
        data={"mission_id":"m1","intent":"threat_detection","requested_by":"OMAR","scope":"zmart",
              "business_id":"zmart-consumer-rights","risk_level":"low","angel_count_max":2}
        data.update(changes); return data

    def test_clean_registered_mission_dispatches(self):
        r=route_mission(self.mission())
        self.assertEqual(r.action,"DISPATCH")
        self.assertEqual(r.reason,"ANGELS_ALLOCATED")

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

    def test_optional_string_fields_reject_whitespace_only_values(self):
        mission=self.mission()
        for field in ("project_id","target_command","target_host","payload_ref","correlation_id","isolation_key"):
            malformed=dict(mission)
            malformed[field]="   "
            with self.subTest(field=field):
                with self.assertRaisesRegex(MissionValidationError,"INVALID_STRING:"+field):
                    validate_mission(malformed)

    def test_required_and_optional_identity_strings_must_be_canonical(self):
        mission=self.mission()
        for field in ("mission_id","intent","requested_by","scope","business_id"):
            malformed=dict(mission)
            malformed[field]=" "+mission[field]+" "
            with self.subTest(required=field):
                with self.assertRaisesRegex(MissionValidationError,"NONCANONICAL_REQUIRED_FIELDS"):
                    validate_mission(malformed)
        for field,value in (
            ("target_command","SANGABRIEL"),("target_host","SANGABRIEL.HOST-01"),
            ("payload_ref","payload-1"),("isolation_key","zmart-consumer-rights"),
            ("project_id","project-1"),
        ):
            malformed=dict(mission)
            malformed[field]=" "+value+" "
            with self.subTest(optional=field):
                with self.assertRaisesRegex(MissionValidationError,"INVALID_STRING:"+field):
                    validate_mission(malformed)


    def test_derekh_ignores_route_like_entries_outside_routes_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"derekh.yaml"
            path.write_text(
                "defaults:\n"
                "  - intent: injected_before_routes\n"
                "    command: SANMIGUEL\n"
                "    host: SANMIGUEL.HOST-01\n"
                "routes:\n"
                "  - intent: legitimate\n"
                "    command: SANGABRIEL\n"
                "    host: SANGABRIEL.HOST-01\n"
                "fallback:\n"
                "  action: REQUIRE_HUMAN_REVIEW\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_derekh(path),
                {"legitimate":("SANGABRIEL","SANGABRIEL.HOST-01")},
            )

if __name__=="__main__": unittest.main()
