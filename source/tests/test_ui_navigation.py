import unittest
from types import SimpleNamespace

import gph_ui_navigation as nav


class NavigationSpecTests(unittest.TestCase):
    def test_stage_is_visual_only(self):
        self.assertEqual(nav.NAVIGATION_INFO["stage"], 2)
        self.assertTrue(nav.NAVIGATION_INFO["visual_only"])
        self.assertFalse(nav.NAVIGATION_INFO["changes_meta"])
        self.assertFalse(nav.NAVIGATION_INFO["changes_database"])
        self.assertFalse(nav.NAVIGATION_INFO["changes_generators"])
        self.assertFalse(nav.NAVIGATION_INFO["changes_methods"])

    def test_navigation_has_single_clear_home_for_every_destination(self):
        spec = nav.navigation_spec()
        items = spec["operation"] + spec["analysis"] + spec["bottom"]
        labels = [item[0] for item in items]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(
            labels,
            [
                "Início", "Jogos do dia", "Jogar", "Decisão",
                "Pesquisa", "Estatísticas", "Puxadas", "Métodos",
                "Resultados", "Configurações",
            ],
        )
        self.assertEqual(spec["bottom"][0][0], "Resultados")
        self.assertEqual(spec["bottom"][1][0], "Configurações")
        self.assertGreaterEqual(spec["width"], 210)

    def test_pages_resolve_to_visible_navigation(self):
        labels = {
            item[0]
            for group in (nav.OPERATION_ITEMS, nav.ANALYSIS_ITEMS, nav.BOTTOM_ITEMS)
            for item in group
        }
        for page, label in nav.PAGE_TO_NAV.items():
            with self.subTest(page=page):
                self.assertIn(label, labels)

    def test_install_is_idempotent_and_keeps_original_fallback(self):
        class FakeApp:
            def _build_ui(self):
                self.built = True
                return "ok"

            def _set_active_nav(self, label):
                self.old_active = label
                return "legacy"

        fake_central = SimpleNamespace(App=FakeApp)
        first = nav.install_navigation_polish(fake_central)
        patched_build = FakeApp._build_ui
        second = nav.install_navigation_polish(fake_central)

        self.assertEqual(first, nav.NAVIGATION_INFO)
        self.assertEqual(second, nav.NAVIGATION_INFO)
        self.assertIs(FakeApp._build_ui, patched_build)

        app = FakeApp()
        self.assertEqual(app._build_ui(), "ok")
        self.assertTrue(app.built)
        self.assertEqual(app._set_active_nav("Início"), "legacy")
        self.assertEqual(app.old_active, "Início")


if __name__ == "__main__":
    unittest.main()
