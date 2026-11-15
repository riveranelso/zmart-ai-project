import unittest

from zion_core import assess_durability


class DurabilityTests(unittest.TestCase):
    def test_explicit_spanish_language_is_durable(self):
        for text in (
            "Siempre usa el asset aprobado.",
            "De ahora en adelante hazlo asi.",
            "Que no vuelva a pasar.",
        ):
            self.assertTrue(assess_durability(text).durable)

    def test_explicit_english_language_is_durable(self):
        self.assertTrue(assess_durability("Always use the approved workflow.").durable)
        self.assertTrue(assess_durability("From now on use this rule.").durable)

    def test_ambiguous_instruction_stays_temporary(self):
        self.assertFalse(assess_durability("Hazlo azul esta vez.").durable)

    def test_confirmed_repetition_and_stable_workflow_are_durable(self):
        self.assertTrue(assess_durability("Use this.",repeated_correction=True).durable)
        self.assertTrue(assess_durability("Use this.",stable_workflow=True).durable)


if __name__=="__main__":
    unittest.main()
