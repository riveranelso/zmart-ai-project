import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from zion_core.grapho import grapho_write


class GraphoCrashRecoveryTests(unittest.TestCase):
    def decision(self,rule="ZMART_RECOVERED"):
        return SimpleNamespace(
            action="ADD",
            destination_ref="WORKFLOWS.md",
            business_id="zmart-consumer-rights",
            proposed_rules=(rule,),
            matched_rules=(),
            mission_id="mission-crash-recovery",
        )

    def test_failure_before_replace_preserves_canonical_biblia_and_retry_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"WORKFLOWS.md"
            original=(
                "# Workflows\n\n"
                "## zmart-consumer-rights\n"
                "- ZMART_BASE\n"
            )
            path.write_text(original,encoding="utf-8")
            temp=path.with_suffix(path.suffix+".grapho.tmp")

            real_replace=Path.replace
            def fail_replace(self,target):
                if self == temp:
                    raise OSError("SIMULATED_REPLACE_FAILURE")
                return real_replace(self,target)

            with patch.object(Path,"replace",fail_replace):
                with self.assertRaisesRegex(OSError,"SIMULATED_REPLACE_FAILURE"):
                    grapho_write(path,self.decision())

            self.assertEqual(path.read_text(encoding="utf-8"),original)
            self.assertTrue(temp.exists())
            self.assertIn("ZMART_RECOVERED",temp.read_text(encoding="utf-8"))

            result=grapho_write(path,self.decision())

            self.assertTrue(result.changed)
            final=path.read_text(encoding="utf-8")
            self.assertIn("ZMART_BASE",final)
            self.assertIn("ZMART_RECOVERED",final)
            self.assertFalse(temp.exists())

    def test_stale_temp_file_is_overwritten_by_current_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"WORKFLOWS.md"
            path.write_text(
                "# Workflows\n\n## zmart-consumer-rights\n- ZMART_BASE\n",
                encoding="utf-8",
            )
            temp=path.with_suffix(path.suffix+".grapho.tmp")
            temp.write_text("STALE_UNTRUSTED_CONTENT",encoding="utf-8")

            grapho_write(path,self.decision("CURRENT_RULE"))

            final=path.read_text(encoding="utf-8")
            self.assertIn("CURRENT_RULE",final)
            self.assertNotIn("STALE_UNTRUSTED_CONTENT",final)
            self.assertFalse(temp.exists())


if __name__=="__main__":
    unittest.main()
