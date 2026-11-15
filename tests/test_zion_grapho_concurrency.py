import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from zion_core.grapho import grapho_write


class GraphoConcurrencyTests(unittest.TestCase):
    def decision(self,business,rule):
        return SimpleNamespace(
            action="ADD",destination_ref="WORKFLOWS.md",business_id=business,
            proposed_rules=(rule,),matched_rules=(),
        )

    def test_concurrent_business_writes_to_same_biblia_file_preserve_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"WORKFLOWS.md"
            path.write_text(
                "# Workflows\n\n## zmart-consumer-rights\n- ZMART_BASE\n\n"
                "## scan-water-intelligence\n- SCAN_BASE\n",
                encoding="utf-8",
            )
            barrier=threading.Barrier(2)
            errors=[]
            guard=threading.Lock()

            def writer(decision):
                try:
                    barrier.wait()
                    grapho_write(path,decision)
                except Exception as exc:
                    with guard: errors.append(exc)

            threads=[
                threading.Thread(target=writer,args=(self.decision("zmart-consumer-rights","ZMART_CONCURRENT"),)),
                threading.Thread(target=writer,args=(self.decision("scan-water-intelligence","SCAN_CONCURRENT"),)),
            ]
            for thread in threads: thread.start()
            for thread in threads: thread.join()

            self.assertEqual(errors,[])
            final=path.read_text(encoding="utf-8")
            zsection=final.split("## zmart-consumer-rights",1)[1].split("## scan-water-intelligence",1)[0]
            scansection=final.split("## scan-water-intelligence",1)[1]
            self.assertIn("ZMART_CONCURRENT",zsection)
            self.assertNotIn("SCAN_CONCURRENT",zsection)
            self.assertIn("SCAN_CONCURRENT",scansection)
            self.assertNotIn("ZMART_CONCURRENT",scansection)


if __name__=="__main__":
    unittest.main()
