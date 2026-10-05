import json
import tempfile
import unittest
from pathlib import Path

from zion_core.biblia import retrieve_biblia
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
        self.assertIn("Meta Instant Forms", brand_text)
        self.assertIn("UNRESOLVED", brand_text)
        self.assertIn("Meta Instant Forms", project_text)
        self.assertIn("preserve, do not redesign", project_text)
        # Brand isolation at retrieval: no other brand's section leaks in.
        self.assertNotIn("## los-duros", brand_text)
        self.assertNotIn("## los-duros", project_text)

    def test_legacy_zerolag_biblia_matches_canonical(self):
        canonical = retrieve_biblia("zero-lag-wifi", root=ROOT)
        legacy = retrieve_biblia("zerolag", root=ROOT)
        self.assertEqual(legacy.business_id, "zerolag")
        self.assertEqual(
            [d.text for d in legacy.documents],
            [d.text for d in canonical.documents],
        )
        self.assertIn("Zero Lag WiFi", legacy.text)

    def test_unconfirmed_items_stay_marked_por_confirmar(self):
        biblia = retrieve_biblia("zero-lag-wifi", root=ROOT)
        by_ref = {doc.ref: doc.text for doc in biblia.documents}
        brand_text = by_ref.get("zmart360/BIBLIA/BRANDS.md", "")
        self.assertIn("POR CONFIRMAR", brand_text)
        self.assertIn("/fiber-leads", brand_text)
        self.assertIn("recruiting vertical", brand_text)

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

if __name__ == "__main__":
    unittest.main()
