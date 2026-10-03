import json
import tempfile
import unittest
from pathlib import Path

from zion_core import LearningIntent, prepare_mission, receive_owner_correction


class OwnerCorrectionTests(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory()
        root=Path(tmp.name)
        target=root/"zmart360"/"BIBLIA"/"WORKFLOWS.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Workflows\n",encoding="utf-8")
        registry=root/"registry.json"
        registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
            "enabled":True,
            "isolation_key":"zmart-consumer-rights",
            "context_refs":["zmart360/BIBLIA/WORKFLOWS.md"]
        }}}),encoding="utf-8")
        return tmp,root,target,registry

    def test_explicit_durable_owner_correction_is_learned_and_recalled(self):
        tmp,root,target,registry=self.fixture()
        try:
            rule="Always use the approved workflow for this business."
            _,cycle=receive_owner_correction(
                rule,
                business_id="zmart-consumer-rights",
                biblia_root=root,
                registry_path=registry,
                learning=LearningIntent(explicit_durable_instruction=True,scope_hint="WORKFLOW"),
                correction_id="nelson-001",
            )
            self.assertEqual(cycle.promotion.action,"ADD")
            future=prepare_mission("zmart-consumer-rights",biblia_root=root,registry_path=registry)
            self.assertIn(rule,future.knowledge)
        finally:
            tmp.cleanup()

    def test_one_off_owner_correction_does_not_become_canonical(self):
        tmp,root,target,registry=self.fixture()
        try:
            before=target.read_text(encoding="utf-8")
            _,cycle=receive_owner_correction(
                "Only do this once.",
                business_id="zmart-consumer-rights",
                biblia_root=root,
                registry_path=registry,
                learning=LearningIntent(),
                correction_id="nelson-002",
            )
            self.assertEqual(cycle.promotion.action,"NOT_READY")
            self.assertEqual(target.read_text(encoding="utf-8"),before)
        finally:
            tmp.cleanup()


if __name__=="__main__":
    unittest.main()
