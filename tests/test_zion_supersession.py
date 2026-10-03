import json
import tempfile
import unittest
from pathlib import Path

from zion_core import LearningIntent, apokrisis, receive_apokrisis


class SupersessionTests(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory()
        root=Path(tmp.name)
        target=root/"WORKFLOWS.md"
        old="Use the old approved workflow."
        target.write_text("# Workflows\n\n## zmart-consumer-rights\n- "+old+"\n",encoding="utf-8")
        registry=root/"registry.json"
        registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
            "enabled":True,"isolation_key":"zmart-consumer-rights",
            "context_refs":["WORKFLOWS.md"]
        }}}),encoding="utf-8")
        return tmp,root,target,registry,old

    def response(self,new):
        return apokrisis(
            angel_id="OMAR.OWNER-INPUT",mission_id="replace-1",status="SUCCESS",
            summary="Owner changed canonical workflow",business_id="zmart-consumer-rights",
            correction_signals=(new,),
        )

    def test_explicit_supersession_replaces_exact_candidate(self):
        tmp,root,target,registry,old=self.fixture()
        try:
            new="Use the new approved workflow."
            _,cycle=receive_apokrisis(
                self.response(new),biblia_root=root,registry_path=registry,
                learning=LearningIntent(
                    scope_hint="WORKFLOW",existing_rule_candidates=(old,),supersede=True
                ),
            )
            self.assertEqual(cycle.promotion.action,"SUPERSEDE")
            text=target.read_text(encoding="utf-8")
            self.assertIn(new,text)
            self.assertNotIn(old,text)
            self.assertTrue(cycle.grapho.changed)
            self.assertEqual(cycle.grapho.reason,"RULES_SUPERSEDED")
        finally:
            tmp.cleanup()

    def test_supersession_without_candidate_becomes_conflict_and_does_not_write(self):
        tmp,root,target,registry,old=self.fixture()
        try:
            before=target.read_text(encoding="utf-8")
            _,cycle=receive_apokrisis(
                self.response("Use a different workflow."),biblia_root=root,registry_path=registry,
                learning=LearningIntent(scope_hint="WORKFLOW",supersede=True),
            )
            self.assertEqual(cycle.promotion.action,"CONFLICT")
            self.assertEqual(cycle.promotion.reason,"SUPERSESSION_CANDIDATE_REQUIRED")
            self.assertEqual(target.read_text(encoding="utf-8"),before)
        finally:
            tmp.cleanup()

    def test_ambiguous_conflict_never_writes(self):
        tmp,root,target,registry,old=self.fixture()
        try:
            before=target.read_text(encoding="utf-8")
            _,cycle=receive_apokrisis(
                self.response("Maybe use another workflow."),biblia_root=root,registry_path=registry,
                learning=LearningIntent(
                    scope_hint="WORKFLOW",existing_rule_candidates=(old,),conflict=True
                ),
            )
            self.assertEqual(cycle.promotion.action,"CONFLICT")
            self.assertEqual(target.read_text(encoding="utf-8"),before)
        finally:
            tmp.cleanup()


if __name__=="__main__":
    unittest.main()
