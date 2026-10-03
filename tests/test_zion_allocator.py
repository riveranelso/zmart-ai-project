import unittest
from zion_core.allocator import allocate_angels

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

if __name__=="__main__": unittest.main()
