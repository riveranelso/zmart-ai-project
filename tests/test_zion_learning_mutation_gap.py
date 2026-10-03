import json
import tempfile
import unittest
from pathlib import Path

from zion_core import CronicasJsonlSink, LearningIntent, OmarRuntime, apokrisis


class _FailMutationSink:
    def __init__(self,delegate):
        self.delegate=delegate
    def __call__(self,event):
        if event.event_type=="BIBLIA_MUTATION":
            raise OSError("SIMULATED_MUTATION_LOG_FAILURE")
        self.delegate(event)


class LearningMutationGapTests(unittest.TestCase):
    def test_biblia_can_commit_before_mutation_history_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            workflows=root/"WORKFLOWS.md"
            workflows.write_text("# Workflows\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["WORKFLOWS.md"]
            }}}),encoding="utf-8")
            cronicas=root/"cronicas.jsonl"
            response=apokrisis(
                angel_id="SANGABRIEL.HOST-01.ANGEL-001",
                mission_id="gap-001",status="SUCCESS",summary="done",
                business_id="zmart-consumer-rights",
                correction_signals=("Persist this exact durable rule.",),
            )
            from zion_core.apokrisis import omar_close_and_learn
            with self.assertRaisesRegex(OSError,"SIMULATED_MUTATION_LOG_FAILURE"):
                omar_close_and_learn(
                    response,biblia_root=root,registry_path=registry,
                    cronicas_sink=_FailMutationSink(CronicasJsonlSink(cronicas)),
                    learning if False else None,
                    scope_hint="WORKFLOW",
                )

            self.assertIn("Persist this exact durable rule.",workflows.read_text(encoding="utf-8"))
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,
                cronicas_path=cronicas,correction_memory_path=root/"corrections.json",
            )
            self.assertEqual(len(runtime.history(
                business_id="zmart-consumer-rights",
                event_type="ANGEL_RESPONSE",mission_id="gap-001",
            )),1)
            self.assertEqual(len(runtime.history(
                business_id="zmart-consumer-rights",
                event_type="BIBLIA_MUTATION",mission_id="gap-001",
            )),0)


if __name__=="__main__":
    unittest.main()
