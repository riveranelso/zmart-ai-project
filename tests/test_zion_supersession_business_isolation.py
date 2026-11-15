import json
import tempfile
import unittest
from pathlib import Path

from zion_core import LearningIntent, OmarRuntime, apokrisis


class SupersessionBusinessIsolationTests(unittest.TestCase):
    def test_zmart_supersession_cannot_replace_scan_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            workflows=root/"WORKFLOWS.md"
            zold="Use ZMART old workflow."
            sold="Use SCAN old workflow."
            workflows.write_text(
                "# Workflows\n\n"
                "## zmart-consumer-rights\n\n- "+zold+"\n\n"
                "## scan-water-intelligence\n\n- "+sold+"\n",
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
            before=workflows.read_text(encoding="utf-8")
            scan_before=before.split("## scan-water-intelligence",1)[1]

            znew="Use ZMART new workflow."
            response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",
                mission_id="z-super-1",status="SUCCESS",summary="owner correction",
                business_id="zmart-consumer-rights",correction_signals=(znew,),
            )
            result=runtime.close(
                response,
                learning=LearningIntent(
                    scope_hint="WORKFLOW",
                    explicit_durable_instruction=True,
                    existing_rule_candidates=(zold,),
                    supersede=True,
                ),
            )
            self.assertTrue(result.processed)
            self.assertEqual(result.cycle.promotion.action,"SUPERSEDE")

            final=workflows.read_text(encoding="utf-8")
            zsection=final.split("## zmart-consumer-rights",1)[1].split("## scan-water-intelligence",1)[0]
            scan_after=final.split("## scan-water-intelligence",1)[1]
            self.assertIn(znew,zsection)
            self.assertNotIn(zold,zsection)
            self.assertEqual(scan_after,scan_before)
            self.assertIn(sold,scan_after)
            self.assertNotIn(znew,scan_after)


if __name__=="__main__":
    unittest.main()
