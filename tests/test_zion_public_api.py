import unittest
import zion_core


class ZionPublicApiTests(unittest.TestCase):
    def test_all_exports_exist(self):
        missing=[name for name in zion_core.__all__ if not hasattr(zion_core,name)]
        self.assertEqual(missing,[])

    def test_learning_entrypoints_are_public(self):
        for name in (
            "omar_close_and_learn",
            "prepare_learning_cycle",
            "persist_learning_cycle",
            "grapho_write",
            "exapostello",
            "diatasso",
        ):
            self.assertIn(name,zion_core.__all__)


if __name__=="__main__":
    unittest.main()
