import json
import tempfile
import unittest
from pathlib import Path

from zion_core import OmarRuntime


class BusinessIsolationRetryTests(unittest.TestCase):
    def test_same_mission_id_is_isolated_by_business_across_dispatch_history_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"ZMARK.md").write_text("# Zmart\n",encoding="utf-8")
            (root/"SCAN.md").write_text("# Scan\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{
                "zmart-consumer-rights":{
                    "enabled":True,"isolation_key":"zmart-consumer-rights",
                    "context_refs":["ZMARK.md"]
                },
                "scan-water-intelligence":{
                    "enabled":True,"isolation_key":"scan-water-intelligence",
                    "context_refs":["SCAN.md"]
                }
            }}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
                encoding="utf-8",
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            base={
                "mission_id":"shared-id","intent":"internal_dispatch",
                "requested_by":"OMAR","scope":"WORKFLOW",
            }
            zmart=runtime.dispatch({**base,"business_id":"zmart-consumer-rights"})
            scan=runtime.dispatch({**base,"business_id":"scan-water-intelligence"})
            self.assertEqual(zmart.decision.action,"DISPATCH")
            self.assertEqual(scan.decision.action,"DISPATCH")
            self.assertEqual(zmart.context.business_id,"zmart-consumer-rights")
            self.assertEqual(scan.context.business_id,"scan-water-intelligence")
            self.assertIn("# Zmart",zmart.context.knowledge)
            self.assertNotIn("# Scan",zmart.context.knowledge)
            self.assertIn("# Scan",scan.context.knowledge)
            self.assertNotIn("# Zmart",scan.context.knowledge)

            zhist=runtime.mission_history("shared-id",business_id="zmart-consumer-rights")
            shist=runtime.mission_history("shared-id",business_id="scan-water-intelligence")
            self.assertEqual(len(zhist),1)
            self.assertEqual(len(shist),1)
            self.assertEqual(zhist[0].business_id,"zmart-consumer-rights")
            self.assertEqual(shist[0].business_id,"scan-water-intelligence")

            zretry=runtime.dispatch({**base,"business_id":"zmart-consumer-rights"})
            sretry=runtime.dispatch({**base,"business_id":"scan-water-intelligence"})
            self.assertEqual(zretry.decision.action,"IDEMPOTENT_NOOP")
            self.assertEqual(sretry.decision.action,"IDEMPOTENT_NOOP")
            self.assertEqual(len(runtime.history(event_type="MISSION_DECISION",mission_id="shared-id")),2)


    def test_same_mission_and_angel_identity_remains_isolated_at_close(self):
        from zion_core import LearningIntent, apokrisis
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"ZMARK.md").write_text("# Zmart\\n",encoding="utf-8")
            (root/"SCAN.md").write_text("# Scan\\n",encoding="utf-8")
            (root/"WORKFLOWS.md").write_text("# Workflows\\n\\n## zmart-consumer-rights\\n\\n## scan-water-intelligence\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{
                "zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["ZMARK.md","WORKFLOWS.md"]},
                "scan-water-intelligence":{"enabled":True,"isolation_key":"scan-water-intelligence","context_refs":["SCAN.md","WORKFLOWS.md"]}
            }}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\\n  - intent: internal_dispatch\\n    command: SANGABRIEL\\n    host: SANGABRIEL.HOST-01\\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            base={"mission_id":"shared-close","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW"}
            zdispatch=runtime.dispatch({**base,"business_id":"zmart-consumer-rights"})
            sdispatch=runtime.dispatch({**base,"business_id":"scan-water-intelligence"})
            self.assertEqual(zdispatch.decision.action,"DISPATCH")
            self.assertEqual(sdispatch.decision.action,"DISPATCH")
            for business in ("zmart-consumer-rights","scan-water-intelligence"):
                response=apokrisis(angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="shared-close",status="SUCCESS",summary=business,business_id=business)
                self.assertTrue(runtime.close(response,learning=LearningIntent()).processed)
            self.assertEqual(len(runtime.history(business_id="zmart-consumer-rights",event_type="ANGEL_RESPONSE",mission_id="shared-close")),1)
            self.assertEqual(len(runtime.history(business_id="scan-water-intelligence",event_type="ANGEL_RESPONSE",mission_id="shared-close")),1)


if __name__=="__main__":
    unittest.main()
