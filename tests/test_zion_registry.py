import json
import tempfile
import unittest
from pathlib import Path

from zion_core.biblia import retrieve_biblia
from zion_core.cronicas import CronicaEvent, CronicasMemorySink
from zion_core.omar import prepare_mission
from zion_core.paradosis import (
    MissionPacket,
    TenantBindingError,
    bind_tenant,
    build_mission_packet,
)
from zion_core.persistence import (
    CronicasJsonlSink,
    PersistentCorrectionMemory,
    read_cronicas,
)
from zion_core.router import route_mission
from zion_core.registry import (
    BUSINESS_ID_ALIASES,
    RegistryError,
    SanPedroError,
    resolve_business,
    sanpedro_business_ids,
    sanpedro_resolve,
)


ROOT = Path(__file__).resolve().parents[1]


class SanPedroRegistryTests(unittest.TestCase):
    def test_known_business_resolves_context(self):
        ctx = resolve_business("zmart-consumer-rights")
        self.assertEqual(ctx.isolation_key, "zmart-consumer-rights")
        self.assertTrue(ctx.context_refs)

    def test_unknown_business_fails(self):
        with self.assertRaisesRegex(RegistryError, "BUSINESS_NOT_REGISTERED"):
            resolve_business("unknown-business")

    def test_disabled_business_fails(self):
        data = {"businesses":{"x":{"enabled":False,"context_refs":["x"],"isolation_key":"x"}}}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"registry.json"
            p.write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaisesRegex(RegistryError,"BUSINESS_DISABLED"):
                resolve_business("x",p)

    def test_missing_context_fails(self):
        data = {"businesses":{"x":{"enabled":True,"context_refs":[],"isolation_key":"x"}}}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"registry.json"
            p.write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaisesRegex(RegistryError,"BUSINESS_CONTEXT_MISSING"):
                resolve_business("x",p)


    def test_registry_rejects_noncanonical_and_duplicate_context_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"registry.json"
            for refs,reason in [
                ([" BIBLIA.md "],"BUSINESS_CONTEXT_MISSING"),
                (["BIBLIA.md","BIBLIA.md"],"BUSINESS_CONTEXT_DUPLICATE"),
            ]:
                with self.subTest(refs=refs):
                    path.write_text(json.dumps({"businesses":{"zmart":{
                        "enabled":True,"isolation_key":"zmart","context_refs":refs
                    }}}),encoding="utf-8")
                    with self.assertRaisesRegex(SanPedroError,reason):
                        sanpedro_resolve("zmart",path)

    def test_registry_rejects_noncanonical_identity_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"registry.json"
            path.write_text(json.dumps({"businesses":{"zmart":{
                "enabled":True,"isolation_key":" zmart ","context_refs":["BIBLIA.md"]
            }}}),encoding="utf-8")
            with self.assertRaisesRegex(SanPedroError,"BUSINESS_ID_REQUIRED"):
                sanpedro_resolve(" zmart ",path)
            with self.assertRaisesRegex(SanPedroError,"ISOLATION_KEY_MISSING"):
                sanpedro_resolve("zmart",path)

class ZeroLagIdentityTests(unittest.TestCase):
    """zerolag (contractual in Omar Core) vs zero-lag-wifi (ZION canonical).

    Decision: zerolag is conserved (Omar Core's brain/BUSINESS-REGISTRY.json,
    router, and tests on main depend on it) and mapped once at ingress to the
    single canonical ZION identity zero-lag-wifi. Every downstream artifact
    carries only the canonical identity.
    """

    def test_canonical_zero_lag_wifi_resolves(self):
        ctx = sanpedro_resolve("zero-lag-wifi")
        self.assertEqual(ctx.business_id, "zero-lag-wifi")
        self.assertEqual(ctx.display_name, "Zero Lag WiFi")
        self.assertEqual(ctx.isolation_key, "zero-lag-wifi")
        self.assertTrue(ctx.context_refs)

    def test_legacy_zerolag_alias_resolves_to_canonical(self):
        canonical = sanpedro_resolve("zero-lag-wifi")
        legacy = sanpedro_resolve("zerolag")
        self.assertEqual(legacy.business_id, "zero-lag-wifi")
        self.assertEqual(legacy.display_name, canonical.display_name)
        self.assertEqual(legacy.isolation_key, canonical.isolation_key)
        self.assertEqual(legacy.context_refs, canonical.context_refs)

    def test_alias_is_declared_explicitly(self):
        self.assertEqual(BUSINESS_ID_ALIASES.get("zerolag"), "zero-lag-wifi")

    def test_alias_does_not_create_a_second_registered_identity(self):
        ids = sanpedro_business_ids()
        self.assertIn("zero-lag-wifi", ids)
        self.assertNotIn("zerolag", ids)

    def test_zerolag_never_resolves_another_brands_context(self):
        ctx = sanpedro_resolve("zerolag")
        for other in ("los-duros", "zmart-consumer-rights",
                      "scan-water-intelligence", "yek-family",
                      "zmart-home-solutions", "full-nelson-ai"):
            other_ctx = sanpedro_resolve(other)
            self.assertNotEqual(ctx.isolation_key, other_ctx.isolation_key)
            self.assertNotIn(other, ctx.context_refs)

    def test_zero_lag_biblia_resolves_real_knowledge(self):
        biblia = retrieve_biblia("zero-lag-wifi", root=ROOT)
        self.assertEqual(biblia.business_id, "zero-lag-wifi")
        by_ref = {doc.ref: doc.text for doc in biblia.documents}
        brand_text = by_ref.get("zmart360/BIBLIA/BRANDS.md", "")
        project_text = by_ref.get("zmart360/BIBLIA/PROJECTS.md", "")
        self.assertIn("Zero Lag WiFi", brand_text)
        # Brand file points to the project file for funnel detail (no dupes).
        self.assertIn("PROJECTS.md", brand_text)
        self.assertIn("UNRESOLVED", brand_text)
        self.assertIn("Meta Instant Forms", project_text)
        self.assertIn("preserve, do not redesign", project_text)
        # Confirmed sales funnel, distinct from the /fiber-leads webhook.
        self.assertIn("ZeroLag Connect", project_text)
        self.assertIn("New Internet Package Requested", project_text)
        # Brand isolation at retrieval: no other brand's section leaks in.
        self.assertNotIn("## los-duros", brand_text)
        self.assertNotIn("## los-duros", project_text)

    def test_legacy_zerolag_biblia_matches_canonical(self):
        canonical = retrieve_biblia("zero-lag-wifi", root=ROOT)
        legacy = retrieve_biblia("zerolag", root=ROOT)
        # The envelope carries the canonical identity, not the legacy alias.
        self.assertEqual(legacy.business_id, "zero-lag-wifi")
        self.assertEqual(
            [d.text for d in legacy.documents],
            [d.text for d in canonical.documents],
        )
        self.assertIn("Zero Lag WiFi", legacy.text)

    def test_fiber_leads_ownership_confirmed_others_stay_por_confirmar(self):
        biblia = retrieve_biblia("zero-lag-wifi", root=ROOT)
        by_ref = {doc.ref: doc.text for doc in biblia.documents}
        brand_text = by_ref.get("zmart360/BIBLIA/BRANDS.md", "")
        # /fiber-leads ownership is CONFIRMED (Nelson, 2026-10-04): it is
        # Zero Lag WiFi's fiber-lead funnel webhook, workflow nsZgiapaMOy1IYLI.
        self.assertIn("OWNERSHIP CONFIRMADO", brand_text)
        self.assertIn("/fiber-leads", brand_text)
        self.assertIn("nsZgiapaMOy1IYLI", brand_text)
        self.assertIn("New Fiber Lead", brand_text)
        self.assertNotIn("no verificada por Nelson", brand_text)
        # Security state stays separate from ownership: known pending risk,
        # no hardening claimed.
        self.assertIn("SIN autenticación ni validación", brand_text)
        # Everything else remains explicitly unconfirmed, never invented.
        self.assertIn("POR CONFIRMAR", brand_text)
        self.assertIn("recruiting", brand_text)
        # Nelson-supplied editorial/compliance boundary is present verbatim.
        self.assertIn("PROHIBIDO inventar", brand_text)
        self.assertIn("velocidades, cobertura, precios, comisiones, roles o ingresos", brand_text)

    def test_invalid_zero_lag_lookalikes_fail_closed(self):
        for bad, reason in [
            ("", "BUSINESS_ID_REQUIRED"),
            ("   ", "BUSINESS_ID_REQUIRED"),
            ("zerolag ", "BUSINESS_ID_REQUIRED"),
            (" zerolag", "BUSINESS_ID_REQUIRED"),
            ("ZeroLag", "BUSINESS_NOT_REGISTERED"),
            ("ZEROLAG", "BUSINESS_NOT_REGISTERED"),
            ("zero_lag_wifi", "BUSINESS_NOT_REGISTERED"),
            ("zero-lag", "BUSINESS_NOT_REGISTERED"),
            ("zero-lag-wif", "BUSINESS_NOT_REGISTERED"),
        ]:
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(SanPedroError, reason):
                    sanpedro_resolve(bad)

def _packet_for(business_id: str) -> MissionPacket:
    return MissionPacket(
        mission_id="m", repo="r", branch="b", current_head="h",
        business_id=business_id, brand_id=business_id, objective="o",
        allowed_scope=(), forbidden_scope=(), relevant_modules=(),
        canonical_context_refs=(), security_boundaries=(),
        production_boundary="", test_requirements=(),
        write_permissions=(), current_known_state="",
    )


class ZeroLagAdversarialTests(unittest.TestCase):
    """Try to break Zero Lag tenant isolation. Everything must fail closed."""

    def test_casing_variants_fail_closed(self):
        for bad in ("ZeroLag", "ZEROLAG", "ZERO-LAG-WIFI", "Zero-Lag-Wifi",
                    "zErOlAg", "ZERO-lag-WIFI"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(SanPedroError, "BUSINESS_NOT_REGISTERED"):
                    sanpedro_resolve(bad)

    def test_whitespace_variants_fail_closed(self):
        for bad in ("\tzerolag", "zerolag\n", "zerolag\r\n", " zerolag",
                    "\tzero-lag-wifi", "zero-lag-wifi\n"):
            with self.subTest(bad=repr(bad)):
                with self.assertRaisesRegex(SanPedroError, "BUSINESS_ID_REQUIRED"):
                    sanpedro_resolve(bad)

    def test_punctuation_variants_fail_closed(self):
        for bad in ("zero--lag-wifi", "zero-lag-wifi!", "-zero-lag-wifi",
                    "zero-lag-wifi-", ".zero-lag-wifi", "zero-lag-wifi.",
                    "zero_lag_wifi", "zero lag wifi", "zero-lag_wifi"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(SanPedroError, "BUSINESS_NOT_REGISTERED"):
                    sanpedro_resolve(bad)

    def test_near_match_ids_fail_closed(self):
        for bad in ("zero-lag-wif", "zero-lag-wifii", "azero-lag-wifi",
                    "zero-lag-wifia", "zero-lag", "zerola", "zerolagg",
                    "zero-lag-wifі"):  # cyrillic і lookalike
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(SanPedroError, "BUSINESS_NOT_REGISTERED"):
                    sanpedro_resolve(bad)

    def test_explicit_registry_entry_wins_over_alias(self):
        # If the registry ever defines "zerolag" itself, the alias must not
        # silently merge that tenant into zero-lag-wifi.
        data = {"businesses": {
            "zerolag": {"enabled": True, "isolation_key": "zerolag-own",
                        "context_refs": ["x.md"], "display_name": "Other"},
            "zero-lag-wifi": {"enabled": True, "isolation_key": "zero-lag-wifi",
                              "context_refs": ["y.md"]},
        }}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "registry.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            ctx = sanpedro_resolve("zerolag", p)
            self.assertEqual(ctx.business_id, "zerolag")
            self.assertEqual(ctx.isolation_key, "zerolag-own")

    def test_post_resolution_checks_use_canonical_id_only(self):
        # build_mission_packet canonicalizes at ingress, so a packet created
        # from a "zerolag" claim carries "zero-lag-wifi" downstream.
        p = _packet_for("zero-lag-wifi")
        self.assertIs(bind_tenant(p, "zero-lag-wifi", "zero-lag-wifi"), p)
        # The legacy id no longer matches once canonicalized: fail closed.
        with self.assertRaises(TenantBindingError):
            bind_tenant(p, "zerolag")
        # A foreign tenant claim fails closed too.
        with self.assertRaises(TenantBindingError):
            bind_tenant(p, "los-duros")
        with self.assertRaises(TenantBindingError):
            bind_tenant(p, "zero-lag-wifi", "los-duros")

    def test_legacy_alias_retrieval_contains_no_foreign_brand_sections(self):
        legacy = retrieve_biblia("zerolag", root=ROOT)
        for oid in sanpedro_business_ids():
            if oid != "zero-lag-wifi":
                self.assertNotIn(f"## {oid}", legacy.text)

    def test_alias_does_not_weaken_other_tenants(self):
        # Every other registered tenant still resolves to itself, unaffected
        # by the alias table.
        for oid in sanpedro_business_ids():
            if oid == "zero-lag-wifi":
                continue
            ctx = sanpedro_resolve(oid)
            self.assertEqual(ctx.business_id, oid)
            self.assertEqual(ctx.isolation_key, oid)


class ZeroLagMissionAssemblyTests(unittest.TestCase):
    """prepare_mission must emit one canonical identity.

    Regression: the legacy alias used to survive in the MissionContext and
    BibliaContext envelopes while exapostello already canonicalized the
    dispatch decision, so execution_contexts raised
    ANGEL_CONTEXT_DECISION_BUSINESS_MISMATCH for zerolag missions.
    """

    def test_prepare_mission_canonicalizes_legacy_alias(self):
        ctx = prepare_mission("zerolag", biblia_root=ROOT)
        self.assertEqual(ctx.business_id, "zero-lag-wifi")
        self.assertEqual(ctx.biblia.business_id, "zero-lag-wifi")
        self.assertEqual(ctx.isolation_key, "zero-lag-wifi")
        self.assertIn("Zero Lag WiFi", ctx.knowledge)

    def test_prepare_mission_legacy_matches_canonical(self):
        legacy = prepare_mission("zerolag", biblia_root=ROOT)
        canonical = prepare_mission("zero-lag-wifi", biblia_root=ROOT)
        self.assertEqual(legacy.business_id, canonical.business_id)
        self.assertEqual(legacy.isolation_key, canonical.isolation_key)
        self.assertEqual(legacy.knowledge, canonical.knowledge)
        self.assertEqual(legacy.biblia.refs, canonical.biblia.refs)

    def test_prepare_mission_canonical_id_unchanged(self):
        ctx = prepare_mission("zero-lag-wifi", biblia_root=ROOT)
        self.assertEqual(ctx.business_id, "zero-lag-wifi")
        self.assertEqual(ctx.biblia.business_id, "zero-lag-wifi")

    def test_prepare_mission_still_fails_closed_for_unknown(self):
        with self.assertRaises(SanPedroError):
            prepare_mission("ZeroLag", biblia_root=ROOT)

    def test_router_dispatch_canonicalizes_legacy_alias(self):
        mission = {"mission_id": "m1", "intent": "threat_detection",
                   "requested_by": "OMAR", "scope": "zerolag",
                   "business_id": "zerolag", "risk_level": "low",
                   "angel_count_max": 2}
        decision = route_mission(mission)
        self.assertEqual(decision.action, "DISPATCH")
        self.assertEqual(decision.business_id, "zero-lag-wifi")
        self.assertEqual(decision.isolation_key, "zero-lag-wifi")

    def test_router_rejects_spoofed_legacy_alias_combination(self):
        # Claimed zerolag with another tenant's isolation key fails closed.
        mission = {"mission_id": "m1", "intent": "threat_detection",
                   "requested_by": "OMAR", "scope": "zerolag",
                   "business_id": "zerolag", "isolation_key": "los-duros",
                   "risk_level": "low", "angel_count_max": 2}
        decision = route_mission(mission)
        self.assertNotEqual(decision.action, "DISPATCH")

    def test_paradosis_packet_canonicalizes_legacy_alias(self):
        packet = build_mission_packet(
            mission_id="m1", objective="zero lag audit",
            business_id="zerolag", repo_root=ROOT,
        )
        self.assertEqual(packet.business_id, "zero-lag-wifi")
        self.assertEqual(packet.brand_id, "zero-lag-wifi")
        # Post-resolution tenant checks use the canonical id only.
        self.assertIs(bind_tenant(packet, "zero-lag-wifi"), packet)
        with self.assertRaises(TenantBindingError):
            bind_tenant(packet, "zerolag")


def _zerolag_runtime(root: Path):
    from zion_core import OmarRuntime
    (root / "GLOBAL.md").write_text("# Global\n", encoding="utf-8")
    registry = root / "registry.json"
    registry.write_text(json.dumps({"businesses": {
        "zero-lag-wifi": {
            "enabled": True, "isolation_key": "zero-lag-wifi",
            "context_refs": ["GLOBAL.md"],
        },
        "los-duros": {
            "enabled": True, "isolation_key": "los-duros",
            "context_refs": ["GLOBAL.md"],
        },
    }}), encoding="utf-8")
    routes = root / "derekh.yaml"
    routes.write_text(
        "routes:\n  - intent: internal_dispatch\n"
        "    command: SANGABRIEL\n    host: SANGABRIEL.HOST-01\n",
        encoding="utf-8",
    )
    return OmarRuntime(
        biblia_root=root, registry_path=registry, routes_path=routes,
        cronicas_path=root / "cronicas.jsonl",
        correction_memory_path=root / "corrections.json",
    )


def _zerolag_mission(business_id: str, mission_id: str = "m1") -> dict:
    return {
        "mission_id": mission_id, "intent": "internal_dispatch",
        "requested_by": "OMAR", "scope": "WORKFLOW",
        "business_id": business_id,
    }


class ZeroLagCronicasPartitionTests(unittest.TestCase):
    """CRONICAS history must share one partition per canonical tenant.

    Regression: the legacy alias 'zerolag' and the canonical 'zero-lag-wifi'
    used to create separate history partitions (and separate operation
    locks), so a retry under the other spelling duplicated the dispatch
    instead of returning IDEMPOTENT_NOOP.
    """

    def test_alias_and_canonical_share_one_history_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _zerolag_runtime(Path(tmp))
            first = runtime.dispatch(_zerolag_mission("zerolag"))
            self.assertEqual(first.decision.action, "DISPATCH")
            via_alias = runtime.history(
                business_id="zerolag", event_type="MISSION_DECISION",
                mission_id="m1",
            )
            via_canonical = runtime.history(
                business_id="zero-lag-wifi", event_type="MISSION_DECISION",
                mission_id="m1",
            )
            self.assertEqual(len(via_alias), 1)
            self.assertEqual(len(via_canonical), 1)
            self.assertEqual(via_alias[0].business_id, "zero-lag-wifi")
            self.assertEqual(
                via_alias[0].event_id, via_canonical[0].event_id,
            )

    def test_cross_spelling_retry_is_idempotent_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = _zerolag_runtime(root)
            first = runtime.dispatch(_zerolag_mission("zerolag"))
            self.assertEqual(first.decision.action, "DISPATCH")
            before = (root / "cronicas.jsonl").read_bytes()
            second = runtime.dispatch(_zerolag_mission("zero-lag-wifi"))
            self.assertEqual(second.decision.action, "IDEMPOTENT_NOOP")
            self.assertEqual(second.decision.reason, "MISSION_ALREADY_DECIDED")
            self.assertEqual((root / "cronicas.jsonl").read_bytes(), before)

    def test_other_brand_cannot_read_zero_lag_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _zerolag_runtime(Path(tmp))
            runtime.dispatch(_zerolag_mission("zerolag"))
            foreign = runtime.history(
                business_id="los-duros", mission_id="m1",
            )
            self.assertEqual(foreign, ())

    def test_invalid_business_id_fails_closed_on_history_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _zerolag_runtime(Path(tmp))
            for bad in ("nope", "ZeroLag", "zero-lag-wif"):
                with self.subTest(bad=bad):
                    with self.assertRaises(SanPedroError):
                        runtime.history(business_id=bad)

    def test_jsonl_sink_normalizes_alias_on_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.json"
            registry.write_text(json.dumps({"businesses": {
                "zero-lag-wifi": {
                    "enabled": True, "isolation_key": "zero-lag-wifi",
                    "context_refs": ["x.md"],
                },
            }}), encoding="utf-8")
            sink = CronicasJsonlSink(
                root / "c.jsonl", registry_path=registry,
            )
            event = CronicaEvent(
                event_id="e1", occurred_at="2026-10-04T00:00:00+00:00",
                event_type="MISSION_DECISION", mission_id="m1",
                action="DISPATCH", reason="ok", business_id="zerolag",
            )
            sink(event)
            stored = read_cronicas(
                root / "c.jsonl", registry_path=registry,
            )
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0].business_id, "zero-lag-wifi")
            bad = CronicaEvent(
                event_id="e2", occurred_at="2026-10-04T00:00:00+00:00",
                event_type="MISSION_DECISION", mission_id="m2",
                action="DISPATCH", reason="ok", business_id="nope",
            )
            with self.assertRaises(SanPedroError):
                sink(bad)

    def test_memory_sink_normalizes_alias_on_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.json"
            registry.write_text(json.dumps({"businesses": {
                "zero-lag-wifi": {
                    "enabled": True, "isolation_key": "zero-lag-wifi",
                    "context_refs": ["x.md"],
                },
            }}), encoding="utf-8")
            sink = CronicasMemorySink(registry_path=registry)
            sink(CronicaEvent(
                event_id="e1", occurred_at="2026-10-04T00:00:00+00:00",
                event_type="MISSION_DECISION", mission_id="m1",
                action="DISPATCH", reason="ok", business_id="zerolag",
            ))
            self.assertEqual(sink.events[0].business_id, "zero-lag-wifi")

    def test_correction_memory_shares_partition_across_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.json"
            registry.write_text(json.dumps({"businesses": {
                "zero-lag-wifi": {
                    "enabled": True, "isolation_key": "zero-lag-wifi",
                    "context_refs": ["x.md"],
                },
            }}), encoding="utf-8")
            memory = PersistentCorrectionMemory(
                root / "corrections.json", registry_path=registry,
            )
            self.assertEqual(memory.observe("zerolag", "fix the cta"), 1)
            self.assertEqual(memory.observe("zero-lag-wifi", "fix the cta"), 2)
            self.assertEqual(memory.count("zerolag", "fix the cta"), 2)
            with self.assertRaises(SanPedroError):
                memory.observe("nope", "fix the cta")

if __name__ == "__main__":
    unittest.main()
