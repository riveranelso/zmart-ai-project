import unittest
from zion_core.holy_ghost import LearningSignal, evaluate_learning

class HolyGhostEvaluationTests(unittest.TestCase):
    def signal(self):
        return LearningSignal("m1","ANGEL-001","zmart-consumer-rights",None,True,(),("correction",))

    def test_one_off_defaults_temporary(self):
        p=evaluate_learning(self.signal())
        self.assertEqual(p.scope,"TEMPORARY")
        self.assertFalse(p.reusable)

    def test_locked_asset_is_brand(self):
        p=evaluate_learning(self.signal(),locked_asset=True)
        self.assertEqual(p.scope,"BRAND")

    def test_stable_workflow_is_workflow(self):
        p=evaluate_learning(self.signal(),stable_workflow=True)
        self.assertEqual(p.scope,"WORKFLOW")

    def test_campaign_context_is_campaign(self):
        p=evaluate_learning(self.signal(),active_campaign=True)
        self.assertEqual(p.scope,"CAMPAIGN")

    def test_explicit_scope_hint_wins(self):
        p=evaluate_learning(self.signal(),scope_hint="project",locked_asset=True)
        self.assertEqual(p.scope,"PROJECT")
        self.assertEqual(p.reason,"EXPLICIT_SCOPE_HINT")

    def test_invalid_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_learning(self.signal(),scope_hint="everything")

if __name__=="__main__":
    unittest.main()
