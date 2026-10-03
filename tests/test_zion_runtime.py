import json
import tempfile
import unittest
from pathlib import Path

from zion_core import OmarRuntime


class OmarRuntimeTests(unittest.TestCase):
    def test_runtime_persists_repetition_and_future_knowledge_without_manual_wiring(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            workflows=root/"WORKFLOWS.md"
            workflows.write_text("# Workflows\n\n## zmart-consumer-rights\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,
                "isolation_key":"zmart-consumer-rights",
                "context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,
                registry_path=registry,
                cronicas_path=root/"runtime"/"cronicas.jsonl",
                correction_memory_path=root/"runtime"/"corrections.json",
            )
            rule="Use the approved owner close format."
            _,first=runtime.owner_correction(rule,business_id="zmart-consumer-rights")
            self.assertEqual(first.promotion.action,"NOT_READY")
            _,second=runtime.owner_correction(rule,business_id="zmart-consumer-rights")
            self.assertEqual(second.promotion.action,"ADD")
            self.assertIn(rule,workflows.read_text(encoding="utf-8"))

            restarted=OmarRuntime(
                biblia_root=root,
                registry_path=registry,
                cronicas_path=root/"runtime"/"cronicas.jsonl",
                correction_memory_path=root/"runtime"/"corrections.json",
            )
            self.assertEqual(
                restarted.correction_memory.count("zmart-consumer-rights",rule),2
            )
            from zion_core import prepare_mission
            context=prepare_mission(
                "zmart-consumer-rights",biblia_root=root,registry_path=registry
            )
            self.assertIn(rule,context.knowledge)
            cronicas=(root/"runtime"/"cronicas.jsonl").read_text(encoding="utf-8")
            self.assertNotIn(rule,cronicas)


if __name__=="__main__":
    unittest.main()
