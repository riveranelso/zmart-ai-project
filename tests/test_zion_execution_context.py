import json
import tempfile
import unittest
from pathlib import Path

from dataclasses import replace

from zion_core import dispatch_mission, execution_contexts
from zion_core.biblia import BibliaContext, BibliaDocument


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





    def test_injected_commission_beyond_authorized_count_is_rejected(self):
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
            mission={"mission_id":"m-extra","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            original=dispatch.decision.angels[0]
            injected=replace(original,angel_id="SANGABRIEL.HOST-01.ANGEL-002")
            tampered=replace(dispatch.decision,angels=(original,injected))
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_COUNT_MISMATCH"):
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



    def test_boolean_angel_count_authority_is_rejected(self):
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
            mission={"mission_id":"m-bool-count","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            tampered=replace(dispatch.decision,angel_count=True)
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



    def test_mismatched_biblia_business_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["BIBLIA.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            mission={"mission_id":"m-biblia-business","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            other=BibliaContext("other-business",dispatch.context.biblia.refs,(BibliaDocument("BIBLIA.md","Other knowledge","GLOBAL",10),))
            changed=replace(dispatch.context,biblia=other)
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_BIBLIA_BUSINESS_MISMATCH"):
                execution_contexts(replace(dispatch,context=changed))


    def test_tampered_decision_count_cannot_expand_authorized_commissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            mission={"mission_id":"m-count","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights","angel_count_max":1}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            first=dispatch.decision.angels[0]
            second=replace(first,angel_id="SANGABRIEL.HOST-01.ANGEL-002")
            tampered=replace(dispatch.decision,angels=(first,second),angel_count=2)
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_DECISION_COUNT_MISMATCH"):
                execution_contexts(replace(dispatch,decision=tampered))


    def test_tampered_decision_angel_prefix_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            mission={"mission_id":"m-prefix","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            tampered=replace(dispatch.decision,angel_prefix="ATTACKER.ANGEL-")
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_PREFIX_MISMATCH"):
                execution_contexts(replace(dispatch,decision=tampered))


    def test_tampered_prepared_route_authority_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            mission={"mission_id":"m-route-context","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            tampered_context=replace(dispatch.context,command="SANRAFAEL",host="SANRAFAEL.HOST-01")
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_DECISION_ROUTE_MISMATCH"):
                execution_contexts(replace(dispatch,context=tampered_context))


    def test_tampered_decision_route_is_rejected_even_when_commissions_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            mission={"mission_id":"m-route","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            bad_decision=replace(dispatch.decision,command="SANRAFAEL",host="SANRAFAEL.HOST-01")
            bad_angels=tuple(replace(item,command="SANRAFAEL",host="SANRAFAEL.HOST-01",angel_id="SANRAFAEL.HOST-01.ANGEL-001") for item in bad_decision.angels)
            tampered=replace(bad_decision,angels=bad_angels,angel_prefix="SANRAFAEL.HOST-01.ANGEL-")
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_DECISION_ROUTE_MISMATCH"):
                execution_contexts(replace(dispatch,decision=tampered))


    def test_tampered_prepared_isolation_authority_is_rejected_by_biblia_registry_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"tenant-zmart-001","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            mission={"mission_id":"m-context-isolation","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            tampered_context=replace(dispatch.context,isolation_key="attacker-key")
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_DECISION_ISOLATION_MISMATCH"):
                execution_contexts(replace(dispatch,context=tampered_context))


    def test_custom_registry_isolation_key_is_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"tenant-zmart-001","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            mission={"mission_id":"m-custom-isolation","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            contexts=execution_contexts(dispatch)
            self.assertEqual(contexts[0].commission.isolation_key,"tenant-zmart-001")


    def test_tampered_decision_payload_is_rejected_even_when_commissions_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            mission={"mission_id":"m-payload","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights","payload_ref":"payload://original"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            bad_decision=replace(dispatch.decision,payload_ref="payload://substituted")
            bad_angels=tuple(replace(item,payload_ref="payload://substituted") for item in bad_decision.angels)
            tampered=replace(bad_decision,angels=bad_angels)
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_DECISION_PAYLOAD_MISMATCH"):
                execution_contexts(replace(dispatch,decision=tampered))


    def test_tampered_decision_scope_is_rejected_even_when_commissions_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Approved.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            mission={"mission_id":"m-scope","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            bad_decision=replace(dispatch.decision,scope="GLOBAL")
            bad_angels=tuple(replace(item,scope="GLOBAL") for item in bad_decision.angels)
            tampered=replace(bad_decision,angels=bad_angels)
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_DECISION_SCOPE_MISMATCH"):
                execution_contexts(replace(dispatch,decision=tampered))


    def test_tampered_decision_mission_id_is_rejected_before_commission(self):
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
            mission={"mission_id":"m-original","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            bad_decision=replace(dispatch.decision,mission_id="m-substituted")
            bad_angels=tuple(replace(item,mission_id="m-substituted") for item in bad_decision.angels)
            tampered=replace(bad_decision,angels=bad_angels)
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_DECISION_MISSION_MISMATCH"):
                execution_contexts(replace(dispatch,decision=tampered))


    def test_tampered_decision_isolation_key_is_rejected(self):
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
            mission={"mission_id":"m-decision-isolation","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            bad_decision=replace(dispatch.decision,isolation_key="other-business")
            bad_angels=tuple(replace(item,isolation_key="other-business") for item in bad_decision.angels)
            tampered=replace(bad_decision,angels=bad_angels)
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_DECISION_ISOLATION_MISMATCH"):
                execution_contexts(replace(dispatch,decision=tampered))


    def test_tampered_decision_context_refs_are_rejected(self):
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
            mission={"mission_id":"m-decision-refs","intent":"internal_dispatch","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            dispatch=dispatch_mission(mission,biblia_root=root,routes_path=routes,registry_path=registry)
            tampered=replace(dispatch.decision,context_refs=("OTHER.md",))
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_DECISION_REFS_MISMATCH"):
                execution_contexts(replace(dispatch,decision=tampered))


    def test_cross_business_dispatch_decision_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"BIBLIA.md").write_text("Shared knowledge.",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{
                "zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["BIBLIA.md"]},
                "scan-water-intelligence":{"enabled":True,"isolation_key":"scan-water-intelligence","context_refs":["BIBLIA.md"]}
            }}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n"
                "    host: SANGABRIEL.HOST-01\n",encoding="utf-8"
            )
            zmart=dispatch_mission(
                {"mission_id":"m-zmart","intent":"internal_dispatch","requested_by":"OMAR",
                 "scope":"WORKFLOW","business_id":"zmart-consumer-rights"},
                biblia_root=root,routes_path=routes,registry_path=registry,
            )
            scan=dispatch_mission(
                {"mission_id":"m-scan","intent":"internal_dispatch","requested_by":"OMAR",
                 "scope":"WORKFLOW","business_id":"scan-water-intelligence"},
                biblia_root=root,routes_path=routes,registry_path=registry,
            )
            tampered=replace(zmart,decision=scan.decision)
            with self.assertRaisesRegex(ValueError,"ANGEL_CONTEXT_DECISION_BUSINESS_MISMATCH"):
                execution_contexts(tampered)


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
