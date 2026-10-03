import json
import tempfile
import unittest
from pathlib import Path

from dataclasses import replace

from zion_core import dispatch_mission, execution_contexts


class AngelExecutionContextTests(unittest.TestCase):
    def test_authorized_angels_receive_same_isolated_knowledge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved Zmart knowledge.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,
                "isolation_key":"zmart-consumer-rights",
                "context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n"
                "  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n"
                "    host: SANGABRIEL.HOST-01\n"
                "fallback:\n"
                "  action: REQUIRE_HUMAN_REVIEW\n",
                encoding="utf-8",
            )
            mission={
                "mission_id":"m-exec",
                "intent":"internal_dispatch",
                "requested_by":"OMAR",
                "scope":"WORKFLOW",
                "business_id":"zmart-consumer-rights",
                "angel_count_max":2,
            }
            dispatch=dispatch_mission(
                mission,biblia_root=root,routes_path=routes,registry_path=registry
            )
            contexts=execution_contexts(dispatch)
            self.assertEqual(len(contexts),2)
            self.assertTrue(all(c.knowledge=="Approved Zmart knowledge." for c in contexts))
            self.assertTrue(all(c.commission.business_id=="zmart-consumer-rights" for c in contexts))

    def test_tampered_commission_isolation_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved Zmart knowledge.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n"
                "    host: SANGABRIEL.HOST-01\nfallback:\n  action: REQUIRE_HUMAN_REVIEW\n",
                encoding="utf-8",
            )
            mission={"mission_id":"m-tamper","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(
                mission,biblia_root=root,routes_path=routes,registry_path=registry
            )
            bad=replace(dispatch.decision.angels[0],isolation_key="other-business")
            tampered=replace(dispatch.decision,angels=(bad,))
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_ISOLATION_MISMATCH"):
                execution_contexts(replace(dispatch,decision=tampered))

    def test_no_execution_context_when_dispatch_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Knowledge.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,
                "isolation_key":"zmart-consumer-rights",
                "context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\nfallback:\n  action: REQUIRE_HUMAN_REVIEW\n",encoding="utf-8")
            mission={
                "mission_id":"m-denied","intent":"unknown","requested_by":"OMAR",
                "scope":"WORKFLOW","business_id":"zmart-consumer-rights",
            }
            dispatch=dispatch_mission(
                mission,biblia_root=root,routes_path=routes,registry_path=registry
            )
            self.assertEqual(execution_contexts(dispatch),())


if __name__=="__main__":
    unittest.main()
