import unittest
from types import SimpleNamespace
from zion_core.grapho import grapho_render

class GraphoTests(unittest.TestCase):
    def decision(self, action, matched=()):
        return SimpleNamespace(action=action,destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("Use approved logo only.",),matched_rules=matched)

    def test_add(self):
        result=grapho_render("# BIBLIA\n",self.decision("ADD"))
        self.assertTrue(result.changed)
        self.assertIn("## los-duros",result.content)

    def test_blocked_actions_do_not_write(self):
        for action in ("NO_CHANGE","CONFLICT","NOT_READY"):
            original="# BIBLIA\n"
            result=grapho_render(original,self.decision(action))
            self.assertFalse(result.changed)
            self.assertEqual(result.content,original)

    def test_update(self):
        original="# BIBLIA\n\n## los-duros\n- Old logo rule.\n"
        result=grapho_render(original,self.decision("UPDATE",("Old logo rule.",)))
        self.assertTrue(result.changed)
        self.assertIn("- Use approved logo only.",result.content)
        self.assertNotIn("- Old logo rule.",result.content)


    def test_add_stays_inside_target_business_section(self):
        existing="# BIBLIA\n\n## los-duros\n- Existing Los Duros rule.\n\n## yek-family\n- Existing Yek rule.\n"
        result=grapho_render(existing,self.decision("ADD"))
        self.assertLess(result.content.index("- Use approved logo only."),result.content.index("## yek-family"))

    def test_update_rejects_rule_candidate_count_mismatch(self):
        decision=SimpleNamespace(action="UPDATE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("New one","New two"),matched_rules=("Old one",))
        result=grapho_render("- Old one\n",decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"UPDATE_RULE_COUNT_MISMATCH")
    def test_add_rejects_duplicate_proposed_rules(self):
        original="# BIBLIA\n"
        decision=SimpleNamespace(
            action="ADD",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("Same rule.","Same rule."),matched_rules=(),
        )
        result=grapho_render(original,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"DUPLICATE_PROPOSED_RULE")
        self.assertEqual(result.content,original)

    def test_add_retry_does_not_duplicate_rule_in_same_business_section(self):
        decision=SimpleNamespace(action="ADD",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("Keep this rule.",),matched_rules=())
        first=grapho_render("# BIBLIA\n",decision)
        second=grapho_render(first.content,decision)
        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(second.reason,"RULES_ALREADY_PRESENT")
        self.assertEqual(second.content.count("- Keep this rule."),1)

    def test_same_rule_in_other_business_does_not_suppress_target_add(self):
        existing="# BIBLIA\n\n## scan-water-intelligence\n- Shared wording.\n"
        decision=SimpleNamespace(action="ADD",destination_ref="BIBLIA.md",business_id="zmart-consumer-rights",
            proposed_rules=("Shared wording.",),matched_rules=())
        result=grapho_render(existing,decision)
        self.assertTrue(result.changed)
        self.assertIn("## zmart-consumer-rights\n- Shared wording.",result.content)
        self.assertEqual(result.content.count("- Shared wording."),2)

    def test_add_only_appends_missing_rules_on_partial_retry(self):
        existing="# BIBLIA\n\n## zmart-consumer-rights\n- Existing rule.\n"
        decision=SimpleNamespace(action="ADD",destination_ref="BIBLIA.md",business_id="zmart-consumer-rights",
            proposed_rules=("Existing rule.","New rule."),matched_rules=())
        result=grapho_render(existing,decision)
        self.assertTrue(result.changed)
        self.assertEqual(result.content.count("- Existing rule."),1)
        self.assertEqual(result.content.count("- New rule."),1)

    def test_multi_rule_update_is_all_or_nothing_when_candidate_missing(self):
        existing="# BIBLIA\n\n## los-duros\n- Old one\n"
        decision=SimpleNamespace(
            action="UPDATE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("New one","New two"),matched_rules=("Old one","Old two"),
        )
        result=grapho_render(existing,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"UPDATE_CANDIDATE_NOT_FOUND")
        self.assertEqual(result.content,existing)
        self.assertIn("- Old one",result.content)
        self.assertNotIn("- New one",result.content)

    def test_multi_rule_supersede_is_all_or_nothing_when_candidate_missing(self):
        existing="# BIBLIA\n\n## los-duros\n- Old one\n"
        decision=SimpleNamespace(
            action="SUPERSEDE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("New one","New two"),matched_rules=("Old one","Old two"),
        )
        result=grapho_render(existing,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"SUPERSESSION_CANDIDATE_NOT_FOUND")
        self.assertEqual(result.content,existing)

    def test_update_same_rule_is_exact_noop(self):
        original="# BIBLIA\n\n## los-duros\n- Keep same rule.\n"
        decision=SimpleNamespace(
            action="UPDATE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("Keep same rule.",),matched_rules=("Keep same rule.",),
        )
        result=grapho_render(original,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.content,original)
        self.assertEqual(result.reason,"RULES_ALREADY_PRESENT")

    def test_supersede_same_rule_is_exact_noop(self):
        original="# BIBLIA\n\n## los-duros\n- Keep same rule.\n"
        decision=SimpleNamespace(
            action="SUPERSEDE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("Keep same rule.",),matched_rules=("Keep same rule.",),
        )
        result=grapho_render(original,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.content,original)
        self.assertEqual(result.reason,"RULES_ALREADY_PRESENT")

    def test_identical_update_does_not_add_trailing_newline(self):
        original="# BIBLIA\n\n## los-duros\n- Keep same rule."
        decision=SimpleNamespace(
            action="UPDATE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("Keep same rule.",),matched_rules=("Keep same rule.",),
        )
        result=grapho_render(original,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.content,original)
        self.assertEqual(result.reason,"RULES_ALREADY_PRESENT")

    def test_update_rejects_candidate_that_is_only_line_prefix(self):
        original="# BIBLIA\n\n## los-duros\n- Rule extended.\n"
        decision=SimpleNamespace(
            action="UPDATE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("Replacement.",),matched_rules=("Rule",),
        )
        result=grapho_render(original,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"UPDATE_CANDIDATE_NOT_FOUND")
        self.assertEqual(result.content,original)

    def test_supersede_rejects_candidate_that_is_only_line_prefix(self):
        original="# BIBLIA\n\n## los-duros\n- Rule extended.\n"
        decision=SimpleNamespace(
            action="SUPERSEDE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("Replacement.",),matched_rules=("Rule",),
        )
        result=grapho_render(original,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"SUPERSESSION_CANDIDATE_NOT_FOUND")
        self.assertEqual(result.content,original)

    def test_duplicate_candidates_require_duplicate_exact_lines(self):
        original="# BIBLIA\n\n## los-duros\n- Same rule.\n"
        decision=SimpleNamespace(
            action="UPDATE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("First.","Second."),
            matched_rules=("Same rule.","Same rule."),
        )
        result=grapho_render(original,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"UPDATE_CANDIDATE_NOT_FOUND")
        self.assertEqual(result.content,original)

    def test_update_preserves_crlf_outside_replaced_rule(self):
        original="# BIBLIA\r\n\r\n## los-duros\r\n- Old rule.\r\n- Keep untouched.\r\n"
        decision=SimpleNamespace(
            action="UPDATE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("New rule.",),matched_rules=("Old rule.",),
        )
        result=grapho_render(original,decision)
        self.assertTrue(result.changed)
        self.assertEqual(
            result.content,
            "# BIBLIA\r\n\r\n## los-duros\r\n- New rule.\r\n- Keep untouched.\r\n",
        )

    def test_real_update_preserves_missing_final_newline(self):
        original="# BIBLIA\n\n## los-duros\n- Old rule."
        decision=SimpleNamespace(
            action="UPDATE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("New rule.",),matched_rules=("Old rule.",),
        )
        result=grapho_render(original,decision)
        self.assertTrue(result.changed)
        self.assertEqual(
            result.content,"# BIBLIA\n\n## los-duros\n- New rule."
        )

    def test_add_rejects_multiline_rule_injection(self):
        original="# BIBLIA\n"
        decision=SimpleNamespace(
            action="ADD",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("Safe text\n## scan-water-intelligence\n- injected",),
            matched_rules=(),
        )
        result=grapho_render(original,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"MULTILINE_RULE_REJECTED")
        self.assertEqual(result.content,original)

    def test_update_rejects_multiline_candidate_injection(self):
        original="# BIBLIA\n\n## los-duros\n- Old rule.\n"
        decision=SimpleNamespace(
            action="UPDATE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("New rule.",),
            matched_rules=("Old rule.\n## scan-water-intelligence",),
        )
        result=grapho_render(original,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"MULTILINE_RULE_REJECTED")
        self.assertEqual(result.content,original)

    def test_rejects_multiline_business_section_injection(self):
        original="# BIBLIA\n"
        decision=SimpleNamespace(
            action="ADD",destination_ref="BIBLIA.md",
            business_id="los-duros\n## scan-water-intelligence",
            proposed_rules=("Safe rule.",),matched_rules=(),
        )
        result=grapho_render(original,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"INVALID_BUSINESS_ID")
        self.assertEqual(result.content,original)

    def test_rejects_noncanonical_business_id_whitespace(self):
        original="# BIBLIA\n"
        decision=SimpleNamespace(
            action="ADD",destination_ref="BIBLIA.md",business_id=" los-duros ",
            proposed_rules=("Safe rule.",),matched_rules=(),
        )
        result=grapho_render(original,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"INVALID_BUSINESS_ID")
        self.assertEqual(result.content,original)

    def test_add_does_not_treat_prefixed_business_heading_as_target(self):
        original="# BIBLIA\n\n## los-duros-extra\n- Existing other rule.\n"
        decision=SimpleNamespace(
            action="ADD",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("Own rule.",),matched_rules=(),
        )
        result=grapho_render(original,decision)
        self.assertTrue(result.changed)
        self.assertIn("## los-duros-extra\n- Existing other rule.",result.content)
        self.assertIn("## los-duros\n- Own rule.",result.content)

    def test_update_does_not_match_prefixed_business_heading(self):
        original="# BIBLIA\n\n## los-duros-extra\n- Old rule.\n"
        decision=SimpleNamespace(
            action="UPDATE",destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("New rule.",),matched_rules=("Old rule.",),
        )
        result=grapho_render(original,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"BUSINESS_SECTION_NOT_FOUND")
        self.assertEqual(result.content,original)


    def test_render_rejects_malformed_proposed_rule_collection_without_partial_write(self):
        decision=self.decision(action="ADD",proposed_rules=("Valid rule",123))
        existing="## zmart-consumer-rights\n"
        result=grapho_render(existing,decision)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason,"INVALID_PROPOSED_RULES")
        self.assertEqual(result.content,existing)

if __name__=="__main__":
    unittest.main()
