import json
import tempfile
import unittest
from pathlib import Path

from zion_core.registry import RegistryError, SanPedroError, resolve_business, sanpedro_resolve


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
                (["../outside.md"],"BUSINESS_CONTEXT_INVALID_REF"),
                (["/tmp/outside.md"],"BUSINESS_CONTEXT_INVALID_REF"),
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

if __name__ == "__main__":
    unittest.main()
