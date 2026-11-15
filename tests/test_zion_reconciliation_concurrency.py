import tempfile
import threading
import unittest
from pathlib import Path

from zion_core import OmarRuntime
from zion_core.holy_ghost import PromotionDecision


class ReconciliationConcurrencyTests(unittest.TestCase):
    def test_concurrent_reconciliation_records_exactly_one_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"WORKFLOWS.md"
            rule="Persist this exact durable rule."
            target.write_text(
                "# Workflows\n\n## zmart-consumer-rights\n- "+rule+"\n",
                encoding="utf-8",
            )
            before=target.read_bytes()
            runtime=OmarRuntime(
                biblia_root=root,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            decision=PromotionDecision(
                mission_id="gap-concurrent-001",
                business_id="zmart-consumer-rights",
                scope="WORKFLOW",destination_ref="WORKFLOWS.md",action="ADD",
                proposed_rules=(rule,),matched_rules=(),reason="NEW_RULE",
                requires_review=True,
            )
            results=[]
            errors=[]
            guard=threading.Lock()

            def worker():
                try:
                    value=runtime.reconcile_biblia_mutation(decision)
                    with guard:
                        results.append(value)
                except Exception as exc:
                    with guard:
                        errors.append(exc)

            threads=[threading.Thread(target=worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(10)
                self.assertFalse(thread.is_alive())

            self.assertEqual(errors,[])
            reconciled=[x for x in results if x is not None]
            self.assertEqual(len(reconciled),1)
            self.assertEqual(reconciled[0].reason,"RECONCILED_ALREADY_COMMITTED")
            self.assertEqual(sum(x is None for x in results),7)
            self.assertEqual(target.read_bytes(),before)
            events=runtime.history(
                business_id="zmart-consumer-rights",
                event_type="BIBLIA_MUTATION",mission_id="gap-concurrent-001",
            )
            self.assertEqual(len(events),1)
            self.assertEqual(events[0].status,"RECONCILED")


if __name__=="__main__":
    unittest.main()
