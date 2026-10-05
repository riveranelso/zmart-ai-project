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


class OwnerCorrectionAliasTests(unittest.TestCase):
    """The public receive_owner_correction entrypoint must canonicalize the
    business identity at ingress: the legacy alias and the canonical id share
    one correction-memory partition, and unknown ids fail closed."""

    def fixture(self):
        tmp=tempfile.TemporaryDirectory()
        root=Path(tmp.name)
        target=root/"zmart360"/"BIBLIA"/"WORKFLOWS.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Workflows\n",encoding="utf-8")
        registry=root/"registry.json"
        registry.write_text(json.dumps({"businesses":{"zero-lag-wifi":{
            "enabled":True,
            "isolation_key":"zero-lag-wifi",
            "context_refs":["zmart360/BIBLIA/WORKFLOWS.md"]
        }}}),encoding="utf-8")
        return tmp,root,registry

    def test_alias_and_canonical_share_one_memory_partition(self):
        from zion_core import CorrectionMemory
        tmp,root,registry=self.fixture()
        try:
            mem=CorrectionMemory()
            rule="Always close YouTube replies with the subscribed CTA."
            receive_owner_correction(
                rule,business_id="zerolag",biblia_root=root,
                registry_path=registry,correction_memory=mem,
                correction_id="nelson-alias-001",
            )
            receive_owner_correction(
                rule,business_id="zero-lag-wifi",biblia_root=root,
                registry_path=registry,correction_memory=mem,
                correction_id="nelson-alias-002",
            )
            # One shared canonical partition: the second identical correction
            # is observed as a repetition, and no alias-keyed partition exists.
            self.assertEqual(mem.count("zero-lag-wifi",rule),2)
            self.assertEqual(mem.count("zerolag",rule),0)
        finally:
            tmp.cleanup()

    def test_unknown_business_id_fails_closed(self):
        from zion_core import CorrectionMemory
        from zion_core.registry import SanPedroError
        tmp,root,registry=self.fixture()
        try:
            with self.assertRaises(SanPedroError):
                receive_owner_correction(
                    "Some correction.",business_id="no-such-business",
                    biblia_root=root,registry_path=registry,
                    correction_memory=CorrectionMemory(),
                    correction_id="nelson-alias-003",
                )
        finally:
            tmp.cleanup()


if __name__=="__main__":
    unittest.main()
