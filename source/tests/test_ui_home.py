import unittest


class HomePolishDisabledTests(unittest.TestCase):
    def test_etapa_3_remains_disabled_in_v0489(self):
        import gph_bootstrap
        self.assertFalse(hasattr(gph_bootstrap, "install_home_polish"))


if __name__ == "__main__":
    unittest.main()
