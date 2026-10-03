import unittest
from zion_core.holy_ghost import LearningProposal, LearningDestination, propose_biblia_promotion

class PromotionTests(unittest.TestCase):
    def proposal(self, rules=("Use approved logo only.",)):
        return LearningProposal("m1","los-duros","BRAND",True,"TEST",rules,(),True)

    def destination(self, ready=True):
        return LearningDestination("m1","los-duros","BRAND","zmart360/BIBLIA/BRANDS.md" if ready else None,ready,"DESTINATION_RESOLVED" if ready else "DESTINATION_NOT_REGISTERED")

    def test_new_rule_is_add(self):
        d=propose_biblia_promotion(self.proposal(),self.destination(),"existing unrelated text")
        self.assertEqual(d.action,"ADD")

    def test_existing_rule_is_no_change(self):
        d=propose_biblia_promotion(self.proposal(),self.destination(),"- Use approved logo only.\n")
        self.assertEqual(d.action,"NO_CHANGE")

    def test_rule_substring_in_prose_is_not_treated_as_existing_rule(self):
        d=propose_biblia_promotion(
            self.proposal(),self.destination(),
            "Narrative says use approved logo only. during review",
        )
        self.assertEqual(d.action,"ADD")

    def test_rule_prefix_in_longer_bullet_is_not_treated_as_exact_rule(self):
        d=propose_biblia_promotion(
            self.proposal(),self.destination(),
            "- Use approved logo only. during campaign review\n",
        )
        self.assertEqual(d.action,"ADD")

    def test_duplicate_semantic_rules_are_collapsed_before_add(self):
        d=propose_biblia_promotion(
            self.proposal(("Keep this rule.","  KEEP   this rule.  ")),
            self.destination(),"",
        )
        self.assertEqual(d.action,"ADD")
        self.assertEqual(d.proposed_rules,("Keep this rule.",))

    def test_duplicate_semantic_rules_do_not_create_false_update_count_mismatch(self):
        d=propose_biblia_promotion(
            self.proposal(("New rule."," new   rule. ")),
            self.destination(),"- Old rule.\n",
            existing_rule_candidates=("Old rule.",),
        )
        self.assertEqual(d.action,"UPDATE")
        self.assertEqual(d.proposed_rules,("New rule.",))
        self.assertEqual(d.matched_rules,("Old rule.",))

    def test_candidate_rule_is_update(self):
        d=propose_biblia_promotion(self.proposal(),self.destination(),"- Old logo rule\n",existing_rule_candidates=("Old logo rule",))
        self.assertEqual(d.action,"UPDATE")

    def test_explicit_conflict_stops_promotion(self):
        d=propose_biblia_promotion(self.proposal(),self.destination(),"old rule",existing_rule_candidates=("Opposite rule",),conflict=True)
        self.assertEqual(d.action,"CONFLICT")

    def test_missing_destination_is_not_ready(self):
        d=propose_biblia_promotion(self.proposal(),self.destination(False),"")
        self.assertEqual(d.action,"NOT_READY")

if __name__=="__main__":
    unittest.main()
