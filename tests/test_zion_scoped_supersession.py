import json
import tempfile
import unittest
from pathlib import Path

from zion_core import LearningIntent, apokrisis, receive_apokrisis, retrieve_biblia


class ScopedSupersessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.brand=self.root/"BRANDS.md"
        self.campaign=self.root/"ACTIVE_CONTEXT.md"
        self.brand_rule="Use the permanent brand CTA."
        self.campaign_old="Use the October campaign CTA."
        self.brand.write_text(
            "# Brands\n\n## zmart-consumer-rights\n- "+self.brand_rule+"\n",
            encoding="utf-8",
        )
        self.campaign.write_text(
            "# Active Context\n\n## zmart-consumer-rights\n- "+self.campaign_old+"\n",
            encoding="utf-8",
        )
        self.registry=self.root/"registry.json"
        self.registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
            "enabled":True,
            "isolation_key":"zmart-consumer-rights",
            "context_refs":["ACTIVE_CONTEXT.md","BRANDS.md"]
        }}}),encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_campaign_override_is_more_specific_without_deleting_brand_rule(self):
        context=retrieve_biblia(
            "zmart-consumer-rights",root=self.root,registry_path=self.registry
        )
        self.assertEqual(context.precedence,("BRAND","CAMPAIGN"))
        self.assertLess(context.text.index(self.brand_rule),context.text.index(self.campaign_old))
        self.assertIn(self.brand_rule,self.brand.read_text(encoding="utf-8"))

    def test_campaign_supersession_only_mutates_campaign_destination(self):
        new="Use the November campaign CTA."
        response=apokrisis(
            angel_id="OMAR.OWNER-INPUT",mission_id="scope-replace-1",status="SUCCESS",
            summary="Owner changed active campaign rule",
            business_id="zmart-consumer-rights",correction_signals=(new,),
        )
        brand_before=self.brand.read_text(encoding="utf-8")
        _,cycle=receive_apokrisis(
            response,biblia_root=self.root,registry_path=self.registry,
            learning=LearningIntent(
                scope_hint="CAMPAIGN",
                existing_rule_candidates=(self.campaign_old,),
                supersede=True,
            ),
        )
        self.assertEqual(cycle.promotion.action,"SUPERSEDE")
        self.assertEqual(cycle.destination.destination_ref,"ACTIVE_CONTEXT.md")
        self.assertEqual(self.brand.read_text(encoding="utf-8"),brand_before)
        campaign_text=self.campaign.read_text(encoding="utf-8")
        self.assertIn(new,campaign_text)
        self.assertNotIn(self.campaign_old,campaign_text)
        context=retrieve_biblia(
            "zmart-consumer-rights",root=self.root,registry_path=self.registry
        )
        self.assertIn(self.brand_rule,context.text)
        self.assertIn(new,context.text)
        self.assertLess(context.text.index(self.brand_rule),context.text.index(new))


if __name__=="__main__":
    unittest.main()
