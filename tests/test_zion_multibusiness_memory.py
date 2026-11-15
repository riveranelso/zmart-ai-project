import json
import tempfile
import unittest
from pathlib import Path

from zion_core import LearningIntent, apokrisis, prepare_mission, receive_apokrisis


class MultiBusinessMemoryIsolationTests(unittest.TestCase):
    def test_learned_rule_never_leaks_to_another_business(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            zmart=root/"zmart360"/"BIBLIA"/"zmart"/"WORKFLOWS.md"
            scan=root/"zmart360"/"BIBLIA"/"scan"/"WORKFLOWS.md"
            zmart.parent.mkdir(parents=True)
            scan.parent.mkdir(parents=True)
            zmart.write_text("# Zmart Workflows\n",encoding="utf-8")
            scan.write_text("# SCAN Workflows\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({
                "businesses":{
                    "zmart-consumer-rights":{
                        "enabled":True,
                        "isolation_key":"zmart-consumer-rights",
                        "context_refs":["zmart360/BIBLIA/zmart/WORKFLOWS.md"]
                    },
                    "scan-water-intelligence":{
                        "enabled":True,
                        "isolation_key":"scan-water-intelligence",
                        "context_refs":["zmart360/BIBLIA/scan/WORKFLOWS.md"]
                    }
                }
            }),encoding="utf-8")

            zmart_only="Use Zmart's approved intake workflow."
            response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",
                mission_id="m-isolation",
                status="SUCCESS",
                summary="Zmart correction",
                business_id="zmart-consumer-rights",
                correction_signals=(zmart_only,),
            )
            receive_apokrisis(
                response,
                biblia_root=root,
                registry_path=registry,
                learning=LearningIntent(stable_workflow=True),
            )

            zmart_context=prepare_mission(
                "zmart-consumer-rights",biblia_root=root,registry_path=registry
            )
            scan_context=prepare_mission(
                "scan-water-intelligence",biblia_root=root,registry_path=registry
            )
            self.assertIn(zmart_only,zmart_context.knowledge)
            self.assertNotIn(zmart_only,scan_context.knowledge)
            self.assertNotIn(zmart_only,scan.read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
