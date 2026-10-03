import json
import tempfile
import unittest
from pathlib import Path

from zion_core import LearningIntent, OmarRuntime, apokrisis


class LearningBusinessIsolationTests(unittest.TestCase):
    def test_apokrisis_learning_writes_only_target_business_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            workflows=root/"WORKFLOWS.md"
            workflows.write_text(
                "# Workflows\n\n## zmart-consumer-rights\n\n- ZMART_BASE\n\n"
                "## scan-water-intelligence\n\n- SCAN_BASE\n",
                encoding="utf-8",
            )
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{
                "zmart-consumer-rights":{
                    "enabled":True,"isolation_key":"zmart-consumer-rights",
                    "context_refs":["WORKFLOWS.md"]
                },
                "scan-water-intelligence":{
                    "enabled":True,"isolation_key":"scan-water-intelligence",
                    "context_refs":["WORKFLOWS.md"]
                }
            }}),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )

            zrule="ZMART_ONLY_LEARNED_RULE"
            zresp=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="z-learn",
                status="SUCCESS",summary="done",business_id="zmart-consumer-rights",
                correction_signals=(zrule,),
            )
            zresult=runtime.close(
                zresp,
                learning=LearningIntent(scope_hint="WORKFLOW",repeated_correction=True),
            )
            self.assertTrue(zresult.processed)
            self.assertEqual(zresult.cycle.promotion.action,"ADD")

            after_z=workflows.read_text(encoding="utf-8")
            zsection=after_z.split("## zmart-consumer-rights",1)[1].split("## scan-water-intelligence",1)[0]
            scansection=after_z.split("## scan-water-intelligence",1)[1]
            self.assertIn(zrule,zsection)
            self.assertNotIn(zrule,scansection)

            srule="SCAN_ONLY_LEARNED_RULE"
            sresp=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="s-learn",
                status="SUCCESS",summary="done",business_id="scan-water-intelligence",
                correction_signals=(srule,),
            )
            sresult=runtime.close(
                sresp,
                learning=LearningIntent(scope_hint="WORKFLOW",repeated_correction=True),
            )
            self.assertTrue(sresult.processed)
            self.assertEqual(sresult.cycle.promotion.action,"ADD")

            final=workflows.read_text(encoding="utf-8")
            zsection=final.split("## zmart-consumer-rights",1)[1].split("## scan-water-intelligence",1)[0]
            scansection=final.split("## scan-water-intelligence",1)[1]
            self.assertIn(zrule,zsection)
            self.assertNotIn(srule,zsection)
            self.assertIn(srule,scansection)
            self.assertNotIn(zrule,scansection)

            zevents=runtime.history(business_id="zmart-consumer-rights")
            sevents=runtime.history(business_id="scan-water-intelligence")
            self.assertTrue(zevents)
            self.assertTrue(sevents)
            self.assertTrue(all(e.business_id=="zmart-consumer-rights" for e in zevents))
            self.assertTrue(all(e.business_id=="scan-water-intelligence" for e in sevents))


if __name__=="__main__":
    unittest.main()
