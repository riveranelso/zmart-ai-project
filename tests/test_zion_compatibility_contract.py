import json
import unittest
from pathlib import Path

from zion_core.router import load_derekh, load_routes


ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"zmart360"


class CompatibilityContractTests(unittest.TestCase):
    def test_legacy_routes_match_canonical_derekh_semantics(self):
        canonical=load_derekh(CONFIG/"derekh.yaml")
        legacy=load_routes(CONFIG/"dispatch_routes.yaml")
        self.assertEqual(legacy,canonical)

    def test_legacy_mission_schema_matches_megillah_contract(self):
        canonical=json.loads((CONFIG/"megillah.schema.json").read_text(encoding="utf-8"))
        legacy=json.loads((CONFIG/"mission_envelope.schema.json").read_text(encoding="utf-8"))
        canonical=dict(canonical)
        legacy=dict(legacy)
        canonical.pop("title",None)
        legacy.pop("title",None)
        self.assertEqual(legacy,canonical)

    def test_legacy_names_are_not_default_runtime_authorities(self):
        import inspect
        from zion_core import router
        source=inspect.getsource(router.load_derekh)
        self.assertIn('"derekh.yaml"',source)
        self.assertNotIn('"dispatch_routes.yaml"',source)


if __name__=="__main__":
    unittest.main()
