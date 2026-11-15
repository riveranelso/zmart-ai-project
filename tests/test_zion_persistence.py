import json
import tempfile
import unittest
from pathlib import Path

from zion_core import (
    CronicasJsonlSink,
    PersistentCorrectionMemory,
    prepare_mission,
    receive_owner_correction,
)


class PersistenceTests(unittest.TestCase):
    def test_correction_count_survives_new_memory_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"corrections.json"
            first=PersistentCorrectionMemory(path)
            self.assertEqual(first.observe("zmart-consumer-rights","Usa el formato aprobado."),1)
            restarted=PersistentCorrectionMemory(path)
            self.assertEqual(restarted.count("zmart-consumer-rights","Usa el formato aprobado."),1)
            self.assertEqual(restarted.observe("zmart-consumer-rights","Usa el formato aprobado."),2)
            self.assertEqual(restarted.count("scan-water-intelligence","Usa el formato aprobado."),0)
            raw=path.read_text(encoding="utf-8")
            self.assertNotIn("Usa el formato aprobado.",raw)

    def test_restart_promotes_second_correction_and_cronicas_persists_metadata(self):
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
            memory_path=root/"runtime"/"corrections.json"
            cronicas_path=root/"runtime"/"cronicas.jsonl"
            rule="Usa el formato aprobado."

            receive_owner_correction(
                rule,business_id="zmart-consumer-rights",biblia_root=root,
                registry_path=registry,correction_memory=PersistentCorrectionMemory(memory_path),
                cronicas_sink=CronicasJsonlSink(cronicas_path),correction_id="before-restart"
            )
            _,cycle=receive_owner_correction(
                rule,business_id="zmart-consumer-rights",biblia_root=root,
                registry_path=registry,correction_memory=PersistentCorrectionMemory(memory_path),
                cronicas_sink=CronicasJsonlSink(cronicas_path),correction_id="after-restart"
            )
            self.assertEqual(cycle.promotion.action,"ADD")
            future=prepare_mission("zmart-consumer-rights",biblia_root=root,registry_path=registry)
            self.assertIn(rule,future.knowledge)

            lines=cronicas_path.read_text(encoding="utf-8").splitlines()
            self.assertGreaterEqual(len(lines),3)
            self.assertNotIn(rule,cronicas_path.read_text(encoding="utf-8"))
            events=[json.loads(line) for line in lines]
            self.assertTrue(all(e["business_id"]=="zmart-consumer-rights" for e in events))


if __name__=="__main__":
    unittest.main()
