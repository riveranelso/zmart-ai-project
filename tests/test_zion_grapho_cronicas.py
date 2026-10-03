import unittest
from types import SimpleNamespace
from zion_core.cronicas import CronicasMemorySink
from zion_core.grapho import grapho_render
from zion_core.cronicas import cronicas_emit_grapho

class GraphoCronicasTests(unittest.TestCase):
    def test_mutation_event_contains_metadata_not_rule_text(self):
        decision=SimpleNamespace(mission_id="m1",business_id="los-duros",
            proposed_rules=("private rule text",))
        result=SimpleNamespace(action="ADD",reason="RULES_APPENDED",changed=True,
            destination_ref="zmart360/BIBLIA/BRANDS.md")
        sink=CronicasMemorySink()
        event=cronicas_emit_grapho(decision,result,sink)
        self.assertEqual(event.event_type,"BIBLIA_MUTATION")
        self.assertEqual(event.status,"CHANGED")
        self.assertEqual(event.correction_count,1)
        self.assertNotIn("private rule text",str(event.to_dict()))

if __name__=="__main__":
    unittest.main()
