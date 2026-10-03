import json
import tempfile
import unittest
from pathlib import Path

from zion_core import retrieve_biblia


class BibliaPrecedenceTests(unittest.TestCase):
    def test_more_specific_scope_is_later_even_if_registry_order_is_scrambled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,text in (
                ("GLOBAL.md","GLOBAL RULE"),
                ("WORKFLOWS.md","WORKFLOW RULE"),
                ("BRANDS.md","BRAND RULE"),
                ("PROJECTS.md","PROJECT RULE"),
                ("ACTIVE_CONTEXT.md","CAMPAIGN RULE"),
            ):
                (root/name).write_text(text,encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"zmart-consumer-rights":{
                "enabled":True,
                "isolation_key":"zmart-consumer-rights",
                "context_refs":[
                    "ACTIVE_CONTEXT.md","GLOBAL.md","PROJECTS.md","BRANDS.md","WORKFLOWS.md"
                ]
            }}}),encoding="utf-8")
            context=retrieve_biblia(
                "zmart-consumer-rights",root=root,registry_path=registry
            )
            self.assertEqual(
                context.precedence,
                ("GLOBAL","WORKFLOW","BRAND","PROJECT","CAMPAIGN"),
            )
            text=context.text
            positions=[text.index(rule) for rule in (
                "GLOBAL RULE","WORKFLOW RULE","BRAND RULE","PROJECT RULE","CAMPAIGN RULE"
            )]
            self.assertEqual(positions,sorted(positions))

    def test_unknown_compatibility_document_defaults_to_global(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"LEGACY.md").write_text("legacy",encoding="utf-8")
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"x":{
                "enabled":True,"isolation_key":"x","context_refs":["LEGACY.md"]
            }}}),encoding="utf-8")
            context=retrieve_biblia("x",root=root,registry_path=registry)
            self.assertEqual(context.precedence,("GLOBAL",))


if __name__=="__main__":
    unittest.main()
