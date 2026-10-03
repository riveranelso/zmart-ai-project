import tempfile
import threading
import unittest
from pathlib import Path

from zion_core.persistence import AtomicClaimStore


class AtomicClaimStoreTests(unittest.TestCase):
    def test_concurrent_same_identity_has_exactly_one_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=AtomicClaimStore(Path(tmp)/"claims")
            barrier=threading.Barrier(8)
            results=[]
            lock=threading.Lock()

            def contender():
                barrier.wait()
                won=store.claim("zmart-consumer-rights","MISSION_DISPATCH","same-1")
                with lock:
                    results.append(won)

            threads=[threading.Thread(target=contender) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(results.count(True),1)
            self.assertEqual(results.count(False),7)

    def test_claims_are_business_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=AtomicClaimStore(Path(tmp)/"claims")
            self.assertTrue(store.claim("zmart-consumer-rights","MISSION_DISPATCH","shared"))
            self.assertTrue(store.claim("scan-water-intelligence","MISSION_DISPATCH","shared"))
            self.assertFalse(store.claim("zmart-consumer-rights","MISSION_DISPATCH","shared"))


if __name__=="__main__":
    unittest.main()
