import json
import tempfile
import unittest
from pathlib import Path

from zion_core import OmarRuntime
from zion_core.gates import SecurityContext


class RuntimeIdempotencyTests(unittest.TestCase):
    def test_duplicate_mission_does_not_dispatch_or_append_second_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
                encoding="utf-8",
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            mission={
                "mission_id":"same-1","intent":"internal_dispatch","requested_by":"OMAR",
                "scope":"WORKFLOW","business_id":"zmart-consumer-rights",
            }
            first=runtime.dispatch(mission)
            self.assertEqual(first.decision.action,"DISPATCH")
            before=(root/"cronicas.jsonl").read_bytes()
            second=runtime.dispatch(dict(mission))
            self.assertEqual(second.decision.action,"IDEMPOTENT_NOOP")
            self.assertEqual(second.decision.reason,"MISSION_ALREADY_DECIDED")
            self.assertEqual((root/"cronicas.jsonl").read_bytes(),before)
            events=runtime.history(
                business_id="zmart-consumer-rights",
                event_type="MISSION_DECISION",mission_id="same-1",
            )
            self.assertEqual(len(events),1)


    def test_retry_fails_closed_on_conflicting_durable_mission_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{"enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["GLOBAL.md"]}}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n  - intent: internal_dispatch\n    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8")
            runtime=OmarRuntime(biblia_root=root,registry_path=registry,routes_path=routes,cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json")
            mission={"mission_id":"retry-conflict","intent":"internal_dispatch","requested_by":"OMAR","scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            runtime.dispatch(mission)
            original=runtime.history(business_id="zmart-consumer-rights",event_type="MISSION_DECISION",mission_id="retry-conflict")[0]
            from zion_core.cronicas import CronicaEvent
            from zion_core.persistence import CronicasJsonlSink
            CronicasJsonlSink(root/"cronicas.jsonl")(CronicaEvent(event_id="conflicting-decision",occurred_at="2026-10-03T00:00:00+00:00",event_type="MISSION_DECISION",mission_id="retry-conflict",business_id="zmart-consumer-rights",action="REQUIRE_HUMAN_REVIEW",reason="FORGED",dispatch_fingerprint=original.dispatch_fingerprint))
            with self.assertRaisesRegex(ValueError,"MISSION_CONFLICTING_HISTORY"):
                runtime.dispatch(dict(mission))


    def test_same_mission_id_cannot_change_from_routed_to_unknown_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
                encoding="utf-8",
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            base={"mission_id":"same-route-unknown","requested_by":"OMAR",
                  "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            self.assertEqual(
                runtime.dispatch(dict(base,intent="internal_dispatch")).decision.action,
                "DISPATCH",
            )
            with self.assertRaisesRegex(ValueError,"MISSION_ID_REUSE_CONFLICT"):
                runtime.dispatch(dict(base,intent="unknown-now"))

    def test_same_unknown_intent_retry_remains_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text("routes:\n",encoding="utf-8")
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            mission={"mission_id":"unknown-retry","intent":"unknown","requested_by":"OMAR",
                     "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            first=runtime.dispatch(mission)
            self.assertEqual(first.decision.reason,"ROUTE_NOT_FOUND")
            second=runtime.dispatch(dict(mission))
            self.assertEqual(second.decision.action,"IDEMPOTENT_NOOP")


    def test_same_mission_id_cannot_change_dispatch_affecting_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
                encoding="utf-8",
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            base={"mission_id":"identity-reuse","intent":"internal_dispatch",
                  "requested_by":"OMAR","scope":"WORKFLOW",
                  "business_id":"zmart-consumer-rights","payload_ref":"payload-a"}
            self.assertEqual(runtime.dispatch(dict(base)).decision.action,"DISPATCH")
            for changed in (
                dict(base,payload_ref="payload-b"),
                dict(base,kill_switch=True),
                dict(base,scope="BUSINESS"),
            ):
                with self.subTest(changed=changed):
                    with self.assertRaisesRegex(ValueError,"MISSION_ID_REUSE_CONFLICT"):
                        runtime.dispatch(changed)



    def test_omitted_gate_defaults_match_explicit_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8"
            )
            defaults={
                "risk_level":"low","human_approval_required":False,
                "integrity_conflict":False,"policy_conflict":False,
                "kill_switch":False,"runtime_enabled":True,
            }
            for index,(key,value) in enumerate(defaults.items()):
                with self.subTest(key=key):
                    runtime=OmarRuntime(
                        biblia_root=root,registry_path=registry,routes_path=routes,
                        cronicas_path=root/f"cronicas-{index}.jsonl",
                        correction_memory_path=root/f"corrections-{index}.json",
                    )
                    base={"mission_id":f"default-{key}","intent":"internal_dispatch",
                          "requested_by":"OMAR","scope":"WORKFLOW",
                          "business_id":"zmart-consumer-rights"}
                    self.assertEqual(runtime.dispatch(dict(base)).decision.action,"DISPATCH")
                    self.assertEqual(
                        runtime.dispatch(dict(base,**{key:value})).decision.action,
                        "IDEMPOTENT_NOOP",
                    )


    def test_omitted_default_angel_count_matches_explicit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8"
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json",
            )
            base={"mission_id":"default-count","intent":"internal_dispatch","requested_by":"OMAR",
                  "scope":"WORKFLOW","business_id":"zmart-consumer-rights"}
            self.assertEqual(runtime.dispatch(dict(base)).decision.action,"DISPATCH")
            self.assertEqual(
                runtime.dispatch(dict(base,angel_count_max=1)).decision.action,
                "IDEMPOTENT_NOOP",
            )


    def test_correlation_id_whitespace_remains_same_dispatch_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
                encoding="utf-8",
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            base={"mission_id":"corr-canonical","intent":"internal_dispatch",
                  "requested_by":"OMAR","scope":"WORKFLOW",
                  "business_id":"zmart-consumer-rights"}
            self.assertEqual(
                runtime.dispatch(dict(base,correlation_id="  corr-1  ")).decision.action,
                "DISPATCH",
            )
            self.assertEqual(
                runtime.dispatch(dict(base,correlation_id="corr-1")).decision.action,
                "IDEMPOTENT_NOOP",
            )

    def test_allowed_business_order_does_not_change_security_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
                encoding="utf-8",
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json",
            )
            mission={"mission_id":"security-order","intent":"internal_dispatch",
                     "requested_by":"OMAR","scope":"WORKFLOW",
                     "business_id":"zmart-consumer-rights"}
            first=SecurityContext(
                authenticated=True,principal_id="owner",
                allowed_business_ids=("zmart-consumer-rights","scan-water-intelligence"),
            )
            reordered=SecurityContext(
                authenticated=True,principal_id="owner",
                allowed_business_ids=("scan-water-intelligence","zmart-consumer-rights"),
            )
            self.assertEqual(runtime.dispatch(dict(mission),security_context=first).decision.action,"DISPATCH")
            self.assertEqual(
                runtime.dispatch(dict(mission),security_context=reordered).decision.action,
                "IDEMPOTENT_NOOP",
            )


    def test_duplicate_allowed_business_ids_do_not_change_security_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights","context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",encoding="utf-8"
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",correction_memory_path=root/"corrections.json",
            )
            mission={"mission_id":"security-duplicates","intent":"internal_dispatch",
                     "requested_by":"OMAR","scope":"WORKFLOW",
                     "business_id":"zmart-consumer-rights"}
            duplicated=SecurityContext(
                authenticated=True,principal_id="owner",
                allowed_business_ids=("zmart-consumer-rights","zmart-consumer-rights"),
            )
            canonical=SecurityContext(
                authenticated=True,principal_id="owner",
                allowed_business_ids=("zmart-consumer-rights",),
            )
            self.assertEqual(runtime.dispatch(dict(mission),security_context=duplicated).decision.action,"DISPATCH")
            self.assertEqual(
                runtime.dispatch(dict(mission),security_context=canonical).decision.action,
                "IDEMPOTENT_NOOP",
            )


    def test_same_mission_id_cannot_change_security_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text("# Global\n",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,"isolation_key":"zmart-consumer-rights",
                "context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            routes=root/"derekh.yaml"
            routes.write_text(
                "routes:\n  - intent: internal_dispatch\n"
                "    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
                encoding="utf-8",
            )
            runtime=OmarRuntime(
                biblia_root=root,registry_path=registry,routes_path=routes,
                cronicas_path=root/"cronicas.jsonl",
                correction_memory_path=root/"corrections.json",
            )
            mission={"mission_id":"security-reuse","intent":"internal_dispatch",
                     "requested_by":"OMAR","scope":"WORKFLOW",
                     "business_id":"zmart-consumer-rights"}
            first=SecurityContext(
                authenticated=True,principal_id="owner-a",
                allowed_business_ids=("zmart-consumer-rights",),
            )
            second=SecurityContext(
                authenticated=True,principal_id="owner-b",
                allowed_business_ids=("zmart-consumer-rights",),
            )
            self.assertEqual(
                runtime.dispatch(dict(mission),security_context=first).decision.action,
                "DISPATCH",
            )
            with self.assertRaisesRegex(ValueError,"MISSION_ID_REUSE_CONFLICT"):
                runtime.dispatch(dict(mission),security_context=second)

if __name__=="__main__":
    unittest.main()
