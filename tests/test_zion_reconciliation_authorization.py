import json
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
            root=Path(tmp)
            target=root/"WORKFLOWS.md"
            target.write_text("# Workflows\n\n## zmart-consumer-rights\n- AUTHORIZED_RULE\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({
                "businesses":{
                    "zmart-consumer-rights":{
                        "display_name":"Zmart Consumer Rights",
                        "enabled":True,
                        "context_refs":["zmart360/BIBLIA/GLOBAL.md"],
                        "isolation_key":"zmart-consumer-rights",
                    }
                }
            }),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",registry_path=registry,
            )
            with self.assertRaisesRegex(ValueError,"RECONCILIATION_DESTINATION_NOT_AUTHORIZED"):
                runtime.reconcile_biblia_mutation(self.decision("WORKFLOWS.md"))
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

    def test_unrelated_mutation_event_does_not_suppress_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); target=root/"WORKFLOWS.md"
            target.write_text("# Workflows\n\n## zmart-consumer-rights\n- AUTHORIZED_RULE\n",encoding="utf-8")
            runtime=self.runtime(root)
            from zion_core.cronicas import CronicaEvent
            runtime.cronicas_sink(CronicaEvent(
                event_id="unrelated",occurred_at="2026-10-03T00:00:00+00:00",
                event_type="BIBLIA_MUTATION",mission_id="reconcile-auth-001",
                action="ADD",reason="RULES_APPENDED",business_id="zmart-consumer-rights",
                status="CHANGED",evidence_refs=("BRANDS.md",),
            ))

            result=runtime.reconcile_biblia_mutation(self.decision("WORKFLOWS.md"))

            self.assertEqual(result.reason,"RECONCILED_ALREADY_COMMITTED")
            events=runtime.history(
                business_id="zmart-consumer-rights",event_type="BIBLIA_MUTATION",
                mission_id="reconcile-auth-001",
            )
            self.assertEqual(len(events),2)
            self.assertEqual(events[-1].evidence_refs,("WORKFLOWS.md",))

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

    def test_non_mutating_actions_cannot_create_reconciliation_evidence(self):
        for action in ("NO_CHANGE","CONFLICT","NOT_READY"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                target=root/"WORKFLOWS.md"
                target.write_text(
                    "# Workflows\n\n## zmart-consumer-rights\n- AUTHORIZED_RULE\n",
                    encoding="utf-8",
                )
                runtime=self.runtime(root)
                decision=PromotionDecision(
                    mission_id="reconcile-nonmutating-"+action.lower(),
                    business_id="zmart-consumer-rights",
                    scope="WORKFLOW",destination_ref="WORKFLOWS.md",action=action,
                    proposed_rules=("AUTHORIZED_RULE",),matched_rules=(),
                    reason="TEST",requires_review=True,
                )
                with self.assertRaisesRegex(ValueError,"RECONCILIATION_ACTION_NOT_MUTATING"):
                    runtime.reconcile_biblia_mutation(decision)
                self.assertEqual(runtime.history(),())

    def test_authorized_symlink_cannot_escape_biblia_root(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root=Path(tmp)
            outside=Path(outside_tmp)/"outside.md"
            original="# Outside\n\n## zmart-consumer-rights\n- AUTHORIZED_RULE\n"
            outside.write_text(original,encoding="utf-8")
            link=root/"WORKFLOWS.md"
            try:
                link.symlink_to(outside)
            except (OSError,NotImplementedError):
                self.skipTest("symlink not supported by test platform")
            runtime=self.runtime(root)
            with self.assertRaisesRegex(ValueError,"RECONCILIATION_DESTINATION_OUTSIDE_BIBLIA_ROOT"):
                runtime.reconcile_biblia_mutation(self.decision("WORKFLOWS.md"))
            self.assertEqual(runtime.history(),())
            self.assertEqual(outside.read_text(encoding="utf-8"),original)


if __name__=="__main__":
    unittest.main()
