import tempfile
import unittest
from pathlib import Path

from zion_core import OmarRuntime
from zion_core.holy_ghost import PromotionDecision


class ReconciliationAuthorizationTests(unittest.TestCase):
    def decision(self, destination_ref):
        return PromotionDecision(
            mission_id="reconcile-auth-001",
            business_id="zmart-consumer-rights",
            scope="WORKFLOW", destination_ref=destination_ref, action="ADD",
            proposed_rules=("AUTHORIZED_RULE",), matched_rules=(),
            reason="NEW_RULE", requires_review=True,
        )

    def runtime(self, root):
        return OmarRuntime(
            biblia_root=root, cronicas_path=root/"cronicas.jsonl",
            correction_memory_path=root/"corrections.json",
        )

    def test_traversal_destination_is_rejected_even_if_file_looks_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp); root=parent/"biblia"; root.mkdir()
            outside=parent/"WORKFLOWS.md"
            outside.write_text("# Workflows\n\n## zmart-consumer-rights\n- AUTHORIZED_RULE\n",encoding="utf-8")
            runtime=self.runtime(root)
            with self.assertRaisesRegex(ValueError,"RECONCILIATION_DESTINATION_NOT_AUTHORIZED"):
                runtime.reconcile_biblia_mutation(self.decision("../WORKFLOWS.md"))
            self.assertEqual(runtime.history(),())

    def test_unregistered_in_root_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); target=root/"UNAUTHORIZED.md"
            target.write_text("# Other\n\n## zmart-consumer-rights\n- AUTHORIZED_RULE\n",encoding="utf-8")
            runtime=self.runtime(root)
            with self.assertRaisesRegex(ValueError,"RECONCILIATION_DESTINATION_NOT_AUTHORIZED"):
                runtime.reconcile_biblia_mutation(self.decision("UNAUTHORIZED.md"))
            self.assertEqual(runtime.history(),())

    def test_registered_short_ref_remains_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); target=root/"WORKFLOWS.md"
            target.write_text("# Workflows\n\n## zmart-consumer-rights\n- AUTHORIZED_RULE\n",encoding="utf-8")
            runtime=self.runtime(root)
            result=runtime.reconcile_biblia_mutation(self.decision("WORKFLOWS.md"))
            self.assertEqual(result.reason,"RECONCILED_ALREADY_COMMITTED")
            events=runtime.history(
                business_id="zmart-consumer-rights",event_type="BIBLIA_MUTATION",
                mission_id="reconcile-auth-001",
            )
            self.assertEqual(len(events),1)

    def test_scope_destination_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"WORKFLOWS.md"
            target.write_text("# Workflows\n\n## zmart-consumer-rights\n- AUTHORIZED_RULE\n",encoding="utf-8")
            runtime=self.runtime(root)
            decision=PromotionDecision(
                mission_id="reconcile-scope-mismatch",
                business_id="zmart-consumer-rights",
                scope="BRAND", destination_ref="WORKFLOWS.md", action="ADD",
                proposed_rules=("AUTHORIZED_RULE",), matched_rules=(),
                reason="NEW_RULE", requires_review=True,
            )
            with self.assertRaisesRegex(ValueError,"RECONCILIATION_SCOPE_DESTINATION_MISMATCH"):
                runtime.reconcile_biblia_mutation(decision)
            self.assertEqual(runtime.history(),())

    def test_temporary_scope_cannot_be_reconciled_into_biblia(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            runtime=self.runtime(root)
            decision=PromotionDecision(
                mission_id="reconcile-temporary",
                business_id="zmart-consumer-rights",
                scope="TEMPORARY", destination_ref="WORKFLOWS.md", action="ADD",
                proposed_rules=("AUTHORIZED_RULE",), matched_rules=(),
                reason="NEW_RULE", requires_review=True,
            )
            with self.assertRaisesRegex(ValueError,"RECONCILIATION_SCOPE_DESTINATION_MISMATCH"):
                runtime.reconcile_biblia_mutation(decision)
            self.assertEqual(runtime.history(),())


if __name__=="__main__":
    unittest.main()
