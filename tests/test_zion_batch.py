import json
import tempfile
import unittest
from pathlib import Path

from zion_core.batch import PatternObservation, assess_pattern_reuse, dispatch_pending, pending_items, plan_batch
from zion_core.runtime import OmarRuntime


class BatchMissionTests(unittest.TestCase):
    def test_plan_is_deterministic_and_tenant_bound(self):
        first=plan_batch(batch_id="scan-zip-2026q4",business_id="scan-water-intelligence",intent="resolve_zip",requested_by="OMAR",scope="WORKFLOW",item_keys=("32744","32807"))
        second=plan_batch(batch_id="scan-zip-2026q4",business_id="scan-water-intelligence",intent="resolve_zip",requested_by="OMAR",scope="WORKFLOW",item_keys=("32744","32807"))
        self.assertEqual(first,second)
        self.assertEqual(first.items[0].mission["business_id"],"scan-water-intelligence")
        self.assertEqual(first.items[0].mission["payload_ref"],"32744")
        self.assertNotEqual(first.items[0].mission_id,first.items[1].mission_id)

    def test_duplicate_item_keys_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"BATCH_ITEM_KEY_DUPLICATE"):
            plan_batch(batch_id="scan-zip",business_id="scan-water-intelligence",intent="resolve_zip",requested_by="OMAR",scope="WORKFLOW",item_keys=("32744","32744"))

    def test_defaults_cannot_override_batch_identity(self):
        with self.assertRaisesRegex(ValueError,"BATCH_DEFAULTS_OVERRIDE_IDENTITY"):
            plan_batch(batch_id="scan-zip",business_id="scan-water-intelligence",intent="resolve_zip",requested_by="OMAR",scope="WORKFLOW",item_keys=("32744",),mission_defaults={"business_id":"zmart-consumer-rights"})

    def test_pending_items_resume_from_durable_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"scan-water-intelligence":{"enabled":True,"isolation_key":"scan-water-intelligence","context_refs":["GLOBAL.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            plan=plan_batch(batch_id="scan-zip",business_id="scan-water-intelligence",intent="unknown_batch_intent",requested_by="OMAR",scope="WORKFLOW",item_keys=("32744","32807"))
            runtime.dispatch(plan.items[0].mission)
            remaining=pending_items(plan,runtime)
            self.assertEqual(tuple(item.item_key for item in remaining),("32807",))



    def test_dispatch_pending_is_bounded_and_resumable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"scan-water-intelligence":{"enabled":True,"isolation_key":"scan-water-intelligence","context_refs":["GLOBAL.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            plan=plan_batch(batch_id="scan-zip-run",business_id="scan-water-intelligence",intent="unknown_batch_intent",requested_by="OMAR",scope="WORKFLOW",item_keys=("32744","32807","32822"))
            first=dispatch_pending(plan,runtime,limit=2)
            self.assertEqual(first.attempted,("32744","32807"))
            self.assertEqual(first.remaining,("32822",))
            second=dispatch_pending(plan,runtime,limit=2)
            self.assertEqual(second.attempted,("32822",))
            self.assertEqual(second.remaining,())
            self.assertEqual(len(runtime.history(business_id="scan-water-intelligence",event_type="MISSION_DECISION")),3)


    def test_dispatch_pending_isolates_one_item_failure_and_continues(self):
        class Decision:
            def __init__(self,key):
                self.decision="ok:"+key
        class Runtime:
            def __init__(self):
                self.done=set()
            def history(self,*,business_id,event_type,mission_id=None):
                if mission_id is None:
                    return ()
                return ("done",) if mission_id in self.done else ()
            def dispatch(self,mission,*,security_context=None):
                if mission["payload_ref"]=="bad":
                    raise ValueError("ZIP_LOOKUP_FAILED")
                self.done.add(mission["mission_id"])
                return Decision(mission["payload_ref"])
        runtime=Runtime()
        plan=plan_batch(batch_id="scan-fault",business_id="scan-water-intelligence",intent="resolve_zip",requested_by="OMAR",scope="WORKFLOW",item_keys=("good-1","bad","good-2"))
        result=dispatch_pending(plan,runtime,limit=3)
        self.assertEqual(result.attempted,("good-1","bad","good-2"))
        self.assertEqual(result.remaining,("bad",))
        self.assertEqual(tuple(x.decision for x in result.decisions),("ok:good-1","ok:good-2"))
        self.assertEqual(len(result.failures),1)
        self.assertEqual(result.failures[0].item_key,"bad")
        self.assertEqual(result.failures[0].error_code,"ZIP_LOOKUP_FAILED")

    def test_dispatch_failure_does_not_copy_arbitrary_exception_text(self):
        class Runtime:
            def history(self,**kwargs):
                return ()
            def dispatch(self,mission,*,security_context=None):
                raise RuntimeError("customer secret "+mission["payload_ref"],"extra")
        plan=plan_batch(batch_id="scan-private",business_id="scan-water-intelligence",intent="resolve_zip",requested_by="OMAR",scope="WORKFLOW",item_keys=("32744",))
        result=dispatch_pending(plan,Runtime())
        self.assertEqual(result.failures[0].error_code,"RuntimeError")
        self.assertNotIn("32744",result.failures[0].error_code)

    def test_dispatch_pending_rejects_invalid_limit(self):
        plan=plan_batch(batch_id="scan-zip-run",business_id="scan-water-intelligence",intent="resolve_zip",requested_by="OMAR",scope="WORKFLOW",item_keys=("32744",))
        with self.assertRaisesRegex(ValueError,"BATCH_LIMIT_INVALID"):
            dispatch_pending(plan,object(),limit=0)

    def test_pattern_reuse_requires_repeated_same_tenant_evidence(self):
        candidate=assess_pattern_reuse((
            PatternObservation("scan-water-intelligence","zip+county","PWSID-123",("epa:1",)),
            PatternObservation("scan-water-intelligence","zip+county","PWSID-123",("epa:2",)),
        ))
        self.assertTrue(candidate.reusable)
        self.assertTrue(candidate.requires_review)
        self.assertEqual(candidate.reason,"PATTERN_REPEATED_EVIDENCE")

    def test_pattern_conflict_never_becomes_reusable(self):
        candidate=assess_pattern_reuse((
            PatternObservation("scan-water-intelligence","zip+county","PWSID-123"),
            PatternObservation("scan-water-intelligence","zip+county","PWSID-999"),
        ))
        self.assertFalse(candidate.reusable)
        self.assertTrue(candidate.requires_review)
        self.assertEqual(candidate.reason,"PATTERN_OUTCOME_CONFLICT")

    def test_pattern_evidence_cannot_cross_businesses(self):
        with self.assertRaisesRegex(ValueError,"PATTERN_CROSS_TENANT_CONFLICT"):
            assess_pattern_reuse((
                PatternObservation("scan-water-intelligence","zip+county","PWSID-123"),
                PatternObservation("zmart-consumer-rights","zip+county","PWSID-123"),
            ))


if __name__=="__main__":
    unittest.main()
