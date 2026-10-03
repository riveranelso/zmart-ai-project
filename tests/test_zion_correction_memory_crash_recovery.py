import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zion_core.persistence import PersistentCorrectionMemory


class CorrectionMemoryCrashRecoveryTests(unittest.TestCase):
    def test_failed_replace_preserves_count_and_retry_advances_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"corrections.json"
            memory=PersistentCorrectionMemory(path)
            business="zmart-consumer-rights"
            correction="Use the official locked logo."

            self.assertEqual(memory.observe(business,correction),1)
            canonical_before=path.read_bytes()
            temp=path.with_suffix(path.suffix+".tmp")

            real_replace=Path.replace
            def fail_replace(self,target):
                if self == temp:
                    raise OSError("SIMULATED_REPLACE_FAILURE")
                return real_replace(self,target)

            with patch.object(Path,"replace",fail_replace):
                with self.assertRaisesRegex(OSError,"SIMULATED_REPLACE_FAILURE"):
                    memory.observe(business,correction)

            self.assertEqual(path.read_bytes(),canonical_before)
            self.assertEqual(memory.count(business,correction),1)
            self.assertTrue(temp.exists())

            self.assertEqual(memory.observe(business,correction),2)
            self.assertEqual(memory.count(business,correction),2)
            self.assertFalse(temp.exists())

    def test_post_replace_directory_fsync_failure_does_not_report_false_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"corrections.json"
            memory=PersistentCorrectionMemory(path)
            real_fsync=os.fsync
            calls=0

            def fail_second_fsync(fd):
                nonlocal calls
                calls+=1
                if calls==2:
                    raise OSError("SIMULATED_DIRECTORY_FSYNC_FAILURE")
                return real_fsync(fd)

            with patch("zion_core.persistence.os.fsync",side_effect=fail_second_fsync):
                count=memory.observe("zmart-consumer-rights","Same durable rule.")

            self.assertEqual(count,1)
            self.assertEqual(memory.count("zmart-consumer-rights","Same durable rule."),1)


if __name__=="__main__":
    unittest.main()
