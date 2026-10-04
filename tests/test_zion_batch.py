import json
import tempfile
import unittest
from pathlib import Path

from zion_core.batch import pending_items, plan_batch
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
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=root/"derekh.yaml",cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            plan=plan_batch(batch_id="scan-zip",business_id="scan-water-intelligence",intent="unknown_batch_intent",requested_by="OMAR",scope="WORKFLOW",item_keys=("32744","32807"))
            runtime.dispatch(plan.items[0].mission)
            remaining=pending_items(plan,runtime)
            self.assertEqual(tuple(item.item_key for item in remaining),("32807",))


if __name__=="__main__":
    unittest.main()
