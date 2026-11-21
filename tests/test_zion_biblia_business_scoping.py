"""Regression tests: active commercial context must stay within its tenant."""
import unittest
from pathlib import Path

from zion_core.biblia import retrieve_biblia


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "zmart360" / "san_pedro_registry.json"


class LosDurosActiveContextIsolationTests(unittest.TestCase):
    def test_los_duros_receives_updated_sales_context(self):
        ctx = retrieve_biblia("los-duros", root=ROOT, registry_path=REGISTRY)
        self.assertIn("Philadelphia sales, 2026-11-21", ctx.text)
        self.assertIn("authentic official logo", ctx.text)
        self.assertIn("MEDIANO $300", ctx.text)

    def test_no_other_tenant_receives_philadelphia_sales_context(self):
        for business_id in (
            "zmart-consumer-rights",
            "scan-water-intelligence",
            "zero-lag-wifi",
            "zmart-ai-jessica",
        ):
            with self.subTest(business_id=business_id):
                ctx = retrieve_biblia(business_id, root=ROOT, registry_path=REGISTRY)
                self.assertNotIn("Philadelphia sales, 2026-11-21", ctx.text)
                self.assertNotIn("Ellio (Elliot) Martinez", ctx.text)
                self.assertNotIn("Video Express $299 redline proposed", ctx.text)

    def test_unrelated_tenant_cannot_read_los_duros_brand_document(self):
        for business_id in ("scan-water-intelligence", "zmart-consumer-rights"):
            with self.subTest(business_id=business_id):
                ctx = retrieve_biblia(business_id, root=ROOT, registry_path=REGISTRY)
                self.assertNotIn(
                    "Branded sales documents and outbound communication",
                    ctx.text,
                )


if __name__ == "__main__":
    unittest.main()
