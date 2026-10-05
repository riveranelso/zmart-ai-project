import json
import tempfile
import unittest
from pathlib import Path

from zion_core.apokrisis import apokrisis, omar_close_and_learn
from zion_core.cronicas import CronicasMemorySink


class OmarLearningCycleTests(unittest.TestCase):
    def _fixture(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        biblia = root / "zmart360" / "BIBLIA"
        biblia.mkdir(parents=True)
        target = biblia / "WORKFLOWS.md"
        target.write_text("# Workflows\n", encoding="utf-8")
        registry = root / "registry.json"
        registry.write_text(json.dumps({
            "defaults": {
                "deny_unknown_business": True,
                "deny_disabled_business": True,
                "require_context_refs": True
            },
            "businesses": {
                "zmart-consumer-rights": {
                    "enabled": True,
                    "isolation_key": "zmart-consumer-rights",
                    "context_refs": ["zmart360/BIBLIA/WORKFLOWS.md"]
                }
            }
        }), encoding="utf-8")
        return temp, root, target, registry

    def test_durable_correction_flows_into_biblia_and_cronicas(self):
        temp, root, target, registry = self._fixture()
        self.addCleanup(temp.cleanup)
        sink = CronicasMemorySink()
        response = apokrisis(
            angel_id="SANGABRIEL.HOST-01.ANGEL-001",
            mission_id="m-omar-1",
            status="SUCCESS",
            summary="Correction captured",
            business_id="zmart-consumer-rights",
            correction_signals=("Always preserve the approved workflow.",),
        )
        event, cycle = omar_close_and_learn(
            response,
            biblia_root=root,
            registry_path=registry,
            cronicas_sink=sink,
            stable_workflow=True,
        )
        self.assertEqual(event.event_type, "ANGEL_RESPONSE")
        self.assertEqual(cycle.promotion.action, "ADD")
        self.assertTrue(cycle.grapho.changed)
        self.assertIn("Always preserve the approved workflow.", target.read_text(encoding="utf-8"))
        self.assertEqual([x.event_type for x in sink.events], ["ANGEL_RESPONSE", "BIBLIA_MUTATION"])

    def test_temporary_learning_does_not_write_biblia(self):
        temp, root, target, registry = self._fixture()
        self.addCleanup(temp.cleanup)
        before = target.read_text(encoding="utf-8")
        response = apokrisis(
            angel_id="SANGABRIEL.HOST-01.ANGEL-001",
            mission_id="m-omar-2",
            status="SUCCESS",
            summary="One-off correction",
            business_id="zmart-consumer-rights",
            correction_signals=("Use this only once.",),
        )
        _, cycle = omar_close_and_learn(
            response,
            biblia_root=root,
            registry_path=registry,
        )
        self.assertEqual(cycle.promotion.action, "NOT_READY")
        self.assertEqual(target.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
