import unittest
from zion_core.holy_ghost import LearningProposal, resolve_learning_destination

class LearningDestinationTests(unittest.TestCase):
    def proposal(self, scope, business="zmart-consumer-rights", reusable=True):
        return LearningProposal("m1",business,scope,reusable,"TEST",("correction",),(),True)

    def test_brand_resolves_registered_biblia(self):
        d=resolve_learning_destination(self.proposal("BRAND"))
        self.assertTrue(d.ready_for_review)
        self.assertTrue(d.destination_ref.endswith("BRANDS.md"))

    def test_workflow_resolves_registered_biblia(self):
        d=resolve_learning_destination(self.proposal("WORKFLOW"))
        self.assertTrue(d.destination_ref.endswith("WORKFLOWS.md"))

    def test_unregistered_scope_destination_stays_pending(self):
        d=resolve_learning_destination(self.proposal("WORKFLOW","los-duros"))
        self.assertFalse(d.ready_for_review)
        self.assertEqual(d.reason,"DESTINATION_NOT_REGISTERED")

    def test_temporary_has_no_canonical_destination(self):
        d=resolve_learning_destination(self.proposal("TEMPORARY",reusable=False))
        self.assertFalse(d.ready_for_review)
        self.assertEqual(d.reason,"TEMPORARY_NOT_CANONICAL")

if __name__=="__main__":
    unittest.main()
