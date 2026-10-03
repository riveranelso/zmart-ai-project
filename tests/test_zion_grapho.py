import unittest
from types import SimpleNamespace
from zion_core.grapho import grapho_render

class GraphoTests(unittest.TestCase):
    def decision(self, action, matched=()):
        return SimpleNamespace(action=action,destination_ref="BIBLIA.md",business_id="los-duros",
            proposed_rules=("Use approved logo only.",),matched_rules=matched)

    def test_add(self):
        result=grapho_render("# BIBLIA\n",self.decision("ADD"))
        self.assertTrue(result.changed)
        self.assertIn("## los-duros",result.content)

    def test_blocked_actions_do_not_write(self):
        for action in ("NO_CHANGE","CONFLICT","NOT_READY"):
            original="# BIBLIA\n"
            result=grapho_render(original,self.decision(action))
            self.assertFalse(result.changed)
            self.assertEqual(result.content,original)

    def test_update(self):
        original="# BIBLIA\n\n## los-duros\n- Old logo rule.\n"
        result=grapho_render(original,self.decision("UPDATE",("Old logo rule.",)))
        self.assertTrue(result.changed)
        self.assertIn("- Use approved logo only.",result.content)
        self.assertNotIn("- Old logo rule.",result.content)

if __name__=="__main__":
    unittest.main()
