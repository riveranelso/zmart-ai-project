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
    def test_idempotent_add_retry_is_recorded_as_unchanged_not_changed(self):
        decision=SimpleNamespace(
            mission_id="m-retry",business_id="los-duros",
            action="ADD",destination_ref="zmart360/BIBLIA/BRANDS.md",
            proposed_rules=("Use approved logo only.",),matched_rules=(),
        )
        existing="# BIBLIA\n\n## los-duros\n- Use approved logo only.\n"
        result=grapho_render(existing,decision)
        sink=CronicasMemorySink()
        event=cronicas_emit_grapho(decision,result,sink)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"RULES_ALREADY_PRESENT")
        self.assertEqual(event.status,"UNCHANGED")
        self.assertEqual(event.reason,"RULES_ALREADY_PRESENT")


if __name__=="__main__":
    unittest.main()
