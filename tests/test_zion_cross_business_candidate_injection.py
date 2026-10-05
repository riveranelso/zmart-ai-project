import json
import tempfile
import unittest
from pathlib import Path

from zion_core import LearningIntent, OmarRuntime, apokrisis


class CrossBusinessCandidateInjectionTests(unittest.TestCase):
    def test_zmart_cannot_supersede_scan_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            workflows=root/"WORKFLOWS.md"
            zrule="ZMART protected rule."
            scanrule="SCAN protected rule."
            original=(
                "# Workflows\n\n"
                "## zmart-consumer-rights\n\n- "+zrule+"\n\n"
                "## scan-water-intelligence\n\n- "+scanrule+"\n"
            )
            workflows.write_text(original,encoding="utf-8")
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
            response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",
                mission_id="candidate-injection-1",
                status="SUCCESS",summary="attempted replacement",
                business_id="zmart-consumer-rights",
                correction_signals=("Injected replacement.",),
            )
            result=runtime.close(
                response,
                learning=LearningIntent(
                    scope_hint="WORKFLOW",
                    explicit_durable_instruction=True,
                    existing_rule_candidates=(scanrule,),
                    supersede=True,
                ),
            )
            self.assertTrue(result.processed)
            self.assertEqual(result.cycle.promotion.action,"CONFLICT")
            self.assertEqual(workflows.read_text(encoding="utf-8"),original)
            self.assertNotIn("Injected replacement.",workflows.read_text(encoding="utf-8"))


    def test_zmart_cannot_update_scan_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            workflows=root/"WORKFLOWS.md"
            original=(
                "# Workflows\n\n"
                "## zmart-consumer-rights\n\n- ZMART protected rule.\n\n"
                "## scan-water-intelligence\n\n- SCAN protected rule.\n"
            )
            workflows.write_text(original,encoding="utf-8")
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
            response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",
                mission_id="update-injection-1",status="SUCCESS",
                summary="attempted update",business_id="zmart-consumer-rights",
                correction_signals=("Injected update.",),
            )
            result=runtime.close(
                response,
                learning=LearningIntent(
                    scope_hint="WORKFLOW",
                    explicit_durable_instruction=True,
                    existing_rule_candidates=("SCAN protected rule.",),
                ),
            )
            self.assertTrue(result.processed)
            self.assertEqual(result.cycle.promotion.action,"CONFLICT")
            self.assertEqual(workflows.read_text(encoding="utf-8"),original)


if __name__=="__main__":
    unittest.main()
