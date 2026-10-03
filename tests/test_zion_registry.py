import json
import tempfile
import unittest
from pathlib import Path

from zion_core.registry import RegistryError, resolve_business


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


if __name__ == "__main__":
    unittest.main()
