import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from zion_core import CronicasJsonlSink, read_cronicas
from zion_core.grapho import grapho_reconcile_committed_mutation


class GraphoReconciliationTests(unittest.TestCase):
    def decision(self,rule):
        return SimpleNamespace(
            action="ADD",destination_ref="WORKFLOWS.md",
            business_id="zmart-consumer-rights",mission_id="gap-001",
            proposed_rules=(rule,),matched_rules=(),
        )

    def test_records_missing_evidence_when_rule_is_already_committed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"WORKFLOWS.md"
            rule="Persist this exact durable rule."
            original="# Workflows\n\n## zmart-consumer-rights\n- "+rule+"\n"
            target.write_text(original,encoding="utf-8")
            cronicas=root/"cronicas.jsonl"

            result=grapho_reconcile_committed_mutation(
                target,self.decision(rule),CronicasJsonlSink(cronicas),
            )

            self.assertFalse(result.changed)
            self.assertEqual(result.reason,"RECONCILED_ALREADY_COMMITTED")
            self.assertEqual(target.read_text(encoding="utf-8"),original)
            events=read_cronicas(cronicas,event_type="BIBLIA_MUTATION",mission_id="gap-001")
            self.assertEqual(len(events),1)
            self.assertEqual(events[0].status,"RECONCILED")
            self.assertEqual(events[0].reason,"RECONCILED_ALREADY_COMMITTED")

    def test_refuses_to_record_mutation_when_rule_is_not_proven(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"WORKFLOWS.md"
            original="# Workflows\n\n## zmart-consumer-rights\n- Different rule.\n"
            target.write_text(original,encoding="utf-8")
            cronicas=root/"cronicas.jsonl"

            result=grapho_reconcile_committed_mutation(
                target,self.decision("Missing rule."),CronicasJsonlSink(cronicas),
            )

            self.assertFalse(result.changed)
            self.assertEqual(result.reason,"RECONCILIATION_RULES_NOT_PROVEN")
            self.assertEqual(target.read_text(encoding="utf-8"),original)
            self.assertFalse(cronicas.exists())


if __name__=="__main__":
    unittest.main()
