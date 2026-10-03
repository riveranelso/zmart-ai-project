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

    def test_duplicate_angel_commission_is_rejected(self):
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
            mission={"mission_id":"m-duplicate","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(
                mission,biblia_root=root,routes_path=routes,registry_path=registry
            )
            original=dispatch.decision.angels[0]
            tampered=replace(dispatch.decision,angels=(original,original))
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_DUPLICATE_ANGEL"):
                execution_contexts(replace(dispatch,decision=tampered))




    def test_removed_commission_from_multi_angel_dispatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n"
                "    host: SANGABRIEL.HOST-01\n",encoding="utf-8"
            )
            mission={"mission_id":"m-count","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights","angel_count_max":2}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            tampered=replace(dispatch.decision,angels=(dispatch.decision.angels[0],))
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_COUNT_MISMATCH"):
                execution_contexts(replace(dispatch,decision=tampered))


    def test_tampered_single_angel_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n"
                "    host: SANGABRIEL.HOST-01\n",encoding="utf-8"
            )
            mission={"mission_id":"m-angel-id","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            bad=replace(dispatch.decision.angels[0],angel_id="SANGABRIEL.HOST-01.ANGEL-099")
            tampered=replace(dispatch.decision,angels=(bad,))
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_ID_MISMATCH"):
                execution_contexts(replace(dispatch,decision=tampered))


    def test_tampered_commission_scope_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n"
                "    host: SANGABRIEL.HOST-01\n",encoding="utf-8"
            )
            mission={"mission_id":"m-scope","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            bad=replace(dispatch.decision.angels[0],scope="GLOBAL")
            tampered=replace(dispatch.decision,angels=(bad,))
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_SCOPE_MISMATCH"):
                execution_contexts(replace(dispatch,decision=tampered))

    def test_tampered_commission_payload_ref_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n"
                "    host: SANGABRIEL.HOST-01\n",encoding="utf-8"
            )
            mission={"mission_id":"m-payload","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights","payload_ref":"payload-a"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            bad=replace(dispatch.decision.angels[0],payload_ref="payload-b")
            tampered=replace(dispatch.decision,angels=(bad,))
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_PAYLOAD_MISMATCH"):
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
