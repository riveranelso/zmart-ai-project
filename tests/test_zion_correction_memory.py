import json
import tempfile
import unittest
from pathlib import Path

from zion_core import CorrectionMemory, prepare_mission, receive_owner_correction


class CorrectionRepetitionTests(unittest.TestCase):
    def test_second_same_correction_becomes_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"zmart360"/"BIBLIA"/"WORKFLOWS.md"
            target.parent.mkdir(parents=True)
            target.write_text("# Workflows\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,
                "isolation_key":"zmart-consumer-rights",
                "context_refs":["zmart360/BIBLIA/WORKFLOWS.md"]
            }}}),encoding="utf-8")
            memory=CorrectionMemory()
            rule="Usa el mismo formato aprobado."

            _,first=receive_owner_correction(
                rule,business_id="zmart-consumer-rights",biblia_root=root,
                registry_path=registry,correction_memory=memory,correction_id="c1"
            )
            self.assertEqual(first.promotion.action,"NOT_READY")

            _,second=receive_owner_correction(
                rule,business_id="zmart-consumer-rights",biblia_root=root,
                registry_path=registry,correction_memory=memory,correction_id="c2"
            )
            self.assertEqual(second.promotion.action,"ADD")
            future=prepare_mission("zmart-consumer-rights",biblia_root=root,registry_path=registry)
            self.assertIn(rule,future.knowledge)

    def test_repetition_is_isolated_by_business(self):
        memory=CorrectionMemory()
        rule="Usa el mismo formato aprobado."
        self.assertEqual(memory.observe("zmart-consumer-rights",rule),1)
        self.assertEqual(memory.observe("scan-water-intelligence",rule),1)
        self.assertEqual(memory.count("zmart-consumer-rights",rule),1)
        self.assertEqual(memory.count("scan-water-intelligence",rule),1)


if __name__=="__main__":
    unittest.main()
