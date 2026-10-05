import unittest
from zion_core.cronicas import CronicasMemorySink
from zion_core.router import exapostello

class ZionCronicasTests(unittest.TestCase):
    def mission(self, **changes):
        data = {
            "mission_id": "cronicas-1",
            "intent": "threat_detection",
            "requested_by": "OMAR",
            "scope": "zmart",
            "business_id": "zmart-consumer-rights",
            "risk_level": "low",
            "angel_count_max": 1,
            "correlation_id": "corr-1",
            "payload_ref": "PRIVATE-PAYLOAD-REF"
        }
        data.update(changes)
        return data

    def test_dispatch_appends_one_privacy_bounded_event(self):
        sink = CronicasMemorySink()
        decision = exapostello(self.mission(), cronicas_sink=sink)
        self.assertEqual(decision.action, "DISPATCH")
        self.assertEqual(len(sink.events), 1)
        event = sink.events[0]
        self.assertEqual(event.event_type, "MISSION_DECISION")
        self.assertEqual(event.mission_id, "cronicas-1")
        self.assertEqual(event.correlation_id, "corr-1")
        self.assertEqual(event.angel_ids, ("SANMIGUEL.HOST-01.ANGEL-001",))
        serialized = event.to_dict()
        self.assertNotIn("payload_ref", serialized)
        self.assertNotIn("context_refs", serialized)

    def test_routing_event_canonicalizes_correlation_id(self):
        sink = CronicasMemorySink()
        exapostello(self.mission(correlation_id="  corr-1  "), cronicas_sink=sink)
        self.assertEqual(sink.events[0].correlation_id, "corr-1")

    def test_routing_event_rejects_non_string_correlation_id(self):
        sink = CronicasMemorySink()
        with self.assertRaisesRegex(ValueError, "INVALID_STRING:correlation_id"):
            exapostello(self.mission(correlation_id=123), cronicas_sink=sink)
        self.assertEqual(sink.events, ())

    def test_gate_denial_is_recorded(self):
        sink = CronicasMemorySink()
        decision = exapostello(self.mission(kill_switch=True), cronicas_sink=sink)
        self.assertEqual(decision.reason, "KILL_SWITCH_ACTIVE")
        self.assertEqual(len(sink.events), 1)
        self.assertEqual(sink.events[0].denied_by, "POWERS")

    def test_sink_is_append_only_from_public_interface(self):
        sink = CronicasMemorySink()
        exapostello(self.mission(mission_id="m1"), cronicas_sink=sink)
        exapostello(self.mission(mission_id="m2"), cronicas_sink=sink)
        self.assertEqual(tuple(e.mission_id for e in sink.events), ("m1", "m2"))
        self.assertIsInstance(sink.events, tuple)

if __name__ == "__main__":
    unittest.main()
