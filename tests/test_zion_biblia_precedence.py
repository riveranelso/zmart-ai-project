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

    def test_segmented_document_never_falls_back_to_other_business(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text(
                "# Workflows\n\n## los-duros-extra\n- OTHER SECRET\n"
                "## scan-water-intelligence\n- SCAN ONLY\n",
                encoding="utf-8",
            )
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{
                "los-duros":{
                    "enabled":True,"isolation_key":"los-duros",
                    "context_refs":["WORKFLOWS.md"]
                },
                "los-duros-extra":{
                    "enabled":True,"isolation_key":"los-duros-extra",
                    "context_refs":["WORKFLOWS.md"]
                },
                "scan-water-intelligence":{
                    "enabled":True,"isolation_key":"scan-water-intelligence",
                    "context_refs":["WORKFLOWS.md"]
                }
            }}),encoding="utf-8")
            context=retrieve_biblia("los-duros",root=root,registry_path=registry)
            self.assertEqual(context.documents[0].text,"")
            self.assertNotIn("OTHER SECRET",context.text)
            self.assertNotIn("SCAN ONLY",context.text)

    def test_exact_business_heading_does_not_match_prefixed_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"WORKFLOWS.md").write_text(
                "# Workflows\n\n## los-duros-extra\n- WRONG\n"
                "## los-duros\n- RIGHT\n"
                "## scan-water-intelligence\n- SCAN\n",
                encoding="utf-8",
            )
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{
                "los-duros":{
                    "enabled":True,"isolation_key":"los-duros",
                    "context_refs":["WORKFLOWS.md"]
                },
                "los-duros-extra":{
                    "enabled":True,"isolation_key":"los-duros-extra",
                    "context_refs":["WORKFLOWS.md"]
                },
                "scan-water-intelligence":{
                    "enabled":True,"isolation_key":"scan-water-intelligence",
                    "context_refs":["WORKFLOWS.md"]
                }
            }}),encoding="utf-8")
            context=retrieve_biblia("los-duros",root=root,registry_path=registry)
            self.assertIn("## los-duros\n- RIGHT",context.text)
            self.assertNotIn("WRONG",context.text)
            self.assertNotIn("SCAN",context.text)

    def test_thematic_h2_in_unsegmented_document_remains_global_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"GLOBAL.md").write_text(
                "# Global\n\n## Repetition prevention\n- GLOBAL RULE\n",
                encoding="utf-8",
            )
            registry=root/"registry.json"
            registry.write_text(json.dumps({"businesses":{"los-duros":{
                "enabled":True,"isolation_key":"los-duros",
                "context_refs":["GLOBAL.md"]
            }}}),encoding="utf-8")
            context=retrieve_biblia("los-duros",root=root,registry_path=registry)
            self.assertIn("## Repetition prevention",context.text)
            self.assertIn("GLOBAL RULE",context.text)


if __name__=="__main__":
    unittest.main()
