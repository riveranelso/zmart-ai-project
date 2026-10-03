import tempfile
import unittest
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from zion_core import CronicasJsonlSink, read_cronicas
from zion_core.grapho import grapho_reconcile_committed_mutation
from zion_core.persistence import LocalOperationLock


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

    def test_reconciliation_does_not_accept_prefixed_business_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"WORKFLOWS.md"
            rule="Persist this exact durable rule."
            original="# Workflows\n\n## zmart-consumer-rights-extra\n- "+rule+"\n"
            target.write_text(original,encoding="utf-8")
            cronicas=root/"cronicas.jsonl"

            result=grapho_reconcile_committed_mutation(
                target,self.decision(rule),CronicasJsonlSink(cronicas),
            )

            self.assertFalse(result.changed)
            self.assertEqual(result.reason,"RECONCILIATION_BUSINESS_SECTION_NOT_FOUND")
            self.assertEqual(target.read_text(encoding="utf-8"),original)
            self.assertFalse(cronicas.exists())

    def test_reconciliation_requires_complete_rule_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"WORKFLOWS.md"
            original="# Workflows\n\n## zmart-consumer-rights\n- Persist this exact durable rule. extended\n"
            target.write_text(original,encoding="utf-8")
            cronicas=root/"cronicas.jsonl"

            result=grapho_reconcile_committed_mutation(
                target,self.decision("Persist this exact durable rule."),CronicasJsonlSink(cronicas),
            )

            self.assertFalse(result.changed)
            self.assertEqual(result.reason,"RECONCILIATION_RULES_NOT_PROVEN")
            self.assertEqual(target.read_text(encoding="utf-8"),original)
            self.assertFalse(cronicas.exists())

    def test_direct_reconciliation_rejects_non_mutating_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"WORKFLOWS.md"
            rule="Persist this exact durable rule."
            original="# Workflows\n\n## zmart-consumer-rights\n- "+rule+"\n"
            target.write_text(original,encoding="utf-8")
            cronicas=Path(tmp)/"cronicas.jsonl"
            decision=self.decision(rule)
            decision.action="NO_CHANGE"
            result=grapho_reconcile_committed_mutation(
                target,decision,CronicasJsonlSink(cronicas),
            )
            self.assertEqual(result.reason,"RECONCILIATION_ACTION_NOT_WRITABLE")
            self.assertFalse(cronicas.exists())

    def test_direct_reconciliation_rejects_multiline_rule_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"WORKFLOWS.md"
            target.write_text(
                "# Workflows\n\n## zmart-consumer-rights\n- Safe rule.\n- Injected rule.\n",
                encoding="utf-8",
            )
            cronicas=Path(tmp)/"cronicas.jsonl"
            decision=self.decision("Safe rule.\n- Injected rule.")
            result=grapho_reconcile_committed_mutation(
                target,decision,CronicasJsonlSink(cronicas),
            )
            self.assertEqual(result.reason,"RECONCILIATION_INVALID_RULES")
            self.assertFalse(cronicas.exists())

    def test_direct_reconciliation_rejects_destination_path_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"WORKFLOWS.md"
            rule="Persist this exact durable rule."
            target.write_text(
                "# Workflows\n\n## zmart-consumer-rights\n- "+rule+"\n",
                encoding="utf-8",
            )
            cronicas=root/"cronicas.jsonl"
            decision=self.decision(rule)
            decision.destination_ref="BRANDS.md"
            result=grapho_reconcile_committed_mutation(
                target,decision,CronicasJsonlSink(cronicas),
            )
            self.assertEqual(result.reason,"RECONCILIATION_DESTINATION_MISMATCH")
            self.assertFalse(cronicas.exists())

    def test_reconciliation_waits_for_active_biblia_writer_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"WORKFLOWS.md"
            rule="Persist this exact durable rule."
            target.write_text("# Workflows\n\n## zmart-consumer-rights\n- "+rule+"\n",encoding="utf-8")
            cronicas=root/"cronicas.jsonl"
            lock=LocalOperationLock(target.parent/".zion-biblia-locks")
            identity=str(target.resolve())
            results=[]

            with lock.hold("BIBLIA","GRAPHO_WRITE",identity):
                thread=threading.Thread(target=lambda: results.append(
                    grapho_reconcile_committed_mutation(
                        target,self.decision(rule),CronicasJsonlSink(cronicas)
                    )
                ))
                thread.start()
                time.sleep(0.1)
                self.assertTrue(thread.is_alive())
                self.assertEqual(results,[])
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(results),1)
            self.assertEqual(results[0].reason,"RECONCILED_ALREADY_COMMITTED")


if __name__=="__main__":
    unittest.main()
