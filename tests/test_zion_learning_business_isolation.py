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

    def test_learning_rejects_registry_traversal_outside_biblia_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); root=base/"biblia"; root.mkdir()
            outside=base/"WORKFLOWS.md"
            original="# Outside\n\n## zmart-consumer-rights\n- BASE\n"
            outside.write_text(original,encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["../WORKFLOWS.md"]
            }}}),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="traversal-learn",
                status="SUCCESS",summary="done",business_id="zmart-consumer-rights",
                correction_signals=("MUST_NOT_ESCAPE",),
            )
            with self.assertRaisesRegex(ValueError,"BIBLIA_DESTINATION_OUTSIDE_ROOT"):
                runtime.close(response,learning=LearningIntent(
                    scope_hint="WORKFLOW",repeated_correction=True))
            self.assertEqual(outside.read_text(encoding="utf-8"),original)
            self.assertEqual(len(runtime.history(event_type="ANGEL_RESPONSE")),1)
            self.assertEqual(runtime.history(event_type="BIBLIA_MUTATION"),())

    def test_learning_rejects_authorized_symlink_outside_biblia_root(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root=Path(tmp)
            outside=Path(outside_tmp)/"WORKFLOWS.md"
            original="# Outside\n\n## zmart-consumer-rights\n- BASE\n"
            outside.write_text(original,encoding="utf-8")
            link=root/"WORKFLOWS.md"
            try:
                link.symlink_to(outside)
            except (OSError,NotImplementedError):
                self.skipTest("symlink not supported by test platform")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",mission_id="symlink-learn",
                status="SUCCESS",summary="done",business_id="zmart-consumer-rights",
                correction_signals=("MUST_NOT_ESCAPE",),
            )
            with self.assertRaisesRegex(ValueError,"BIBLIA_DESTINATION_OUTSIDE_ROOT"):
                runtime.close(response,learning=LearningIntent(
                    scope_hint="WORKFLOW",repeated_correction=True))
            self.assertEqual(outside.read_text(encoding="utf-8"),original)
            self.assertEqual(len(runtime.history(event_type="ANGEL_RESPONSE")),1)
            self.assertEqual(runtime.history(event_type="BIBLIA_MUTATION"),())


if __name__=="__main__":
    unittest.main()
