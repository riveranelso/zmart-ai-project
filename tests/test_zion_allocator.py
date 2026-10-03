import unittest
from zion_core.allocator import allocate_angels, diatasso

class AngelAllocatorTests(unittest.TestCase):
    def test_allocates_bounded_deterministic_ids(self):
        mission={"mission_id":"m1","scope":"zmart","angel_count_max":2}
        a=allocate_angels(mission=mission,command="SANMIGUEL",host="SANMIGUEL.HOST-01",
                          business_id="zmart-consumer-rights",isolation_key="zmart-consumer-rights",
                          context_refs=("zmart360/BIBLIA/GLOBAL.md",))
        self.assertEqual([x.angel_id for x in a],[
            "SANMIGUEL.HOST-01.ANGEL-001","SANMIGUEL.HOST-01.ANGEL-002"])
        self.assertTrue(all(x.isolation_key=="zmart-consumer-rights" for x in a))

    def test_defaults_to_one(self):
        a=allocate_angels(mission={"mission_id":"m1","scope":"x"},command="SANGABRIEL",
                          host="SANGABRIEL.HOST-01",business_id="b",isolation_key="b",context_refs=("x",))
        self.assertEqual(len(a),1)

    def test_allocator_enforces_router_angel_ceiling_when_called_directly(self):
        mission={"mission_id":"m2","scope":"PROJECT","angel_count_max":101}
        with self.assertRaisesRegex(ValueError,"INVALID_ANGEL_COUNT"):
            diatasso(mission=mission,command="BUILD",host="BUILD.HOST-01",
                     business_id="zmart-consumer-rights",isolation_key="zmart",
                     context_refs=("zmart360/BIBLIA/GLOBAL.md",))

    def test_allocator_rejects_missing_identity_when_called_directly(self):
        mission={"mission_id":"","scope":"PROJECT","angel_count_max":1}
        with self.assertRaisesRegex(ValueError,"MISSION_ID_REQUIRED"):
            diatasso(mission=mission,command="BUILD",host="BUILD.HOST-01",
                     business_id="zmart-consumer-rights",isolation_key="zmart",
                     context_refs=("zmart360/BIBLIA/GLOBAL.md",))

    def test_allocator_rejects_noncanonical_context_ref(self):
        mission={"mission_id":"m3","scope":"PROJECT"}
        with self.assertRaisesRegex(ValueError,"CONTEXT_REFS_REQUIRED"):
            diatasso(mission=mission,command="BUILD",host="BUILD.HOST-01",
                     business_id="zmart-consumer-rights",isolation_key="zmart",
                     context_refs=(" BIBLIA.md ",))

    def test_allocator_canonicalizes_payload_ref(self):
        mission={"mission_id":"m4","scope":"PROJECT","payload_ref":"  payload-1  "}
        commissions=diatasso(mission=mission,command="BUILD",host="BUILD.HOST-01",
                     business_id="zmart-consumer-rights",isolation_key="zmart",
                     context_refs=("BIBLIA.md",))
        self.assertEqual(commissions[0].payload_ref,"payload-1")

    def test_direct_allocator_rejects_noncanonical_boundary_identities(self):
        mission={"mission_id":"m5","scope":"PROJECT","angel_count_max":1}
        base=dict(mission=mission,command="SANGABRIEL",host="SANGABRIEL.HOST-01",
                  business_id="zmart-consumer-rights",isolation_key="zmart-consumer-rights",
                  context_refs=("BIBLIA.md",))
        for field in ("command","host","business_id","isolation_key"):
            malformed=dict(base)
            malformed[field]=" "+str(base[field])+" "
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    diatasso(**malformed)

if __name__=="__main__": unittest.main()
