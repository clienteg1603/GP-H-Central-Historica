import unittest
from types import SimpleNamespace

import gph_ui_home as home


class HomePolishTests(unittest.TestCase):
    def test_stage_is_visual_only(self):
        self.assertEqual(home.HOME_POLISH_INFO["stage"], 3)
        self.assertTrue(home.HOME_POLISH_INFO["visual_only"])
        self.assertFalse(home.HOME_POLISH_INFO["changes_meta"])
        self.assertFalse(home.HOME_POLISH_INFO["changes_database"])
        self.assertFalse(home.HOME_POLISH_INFO["changes_generators"])
        self.assertFalse(home.HOME_POLISH_INFO["changes_methods"])

    def test_target_text_has_safe_fallback(self):
        app = SimpleNamespace()
        target = {"data": "2026-09-13", "sorteio": "PTM", "hora": "11h"}
        text = home._target_text(app, target)
        self.assertIn("2026-09-13", text)
        self.assertIn("PTM", text)
        self.assertIn("11h", text)

    def test_recommendation_snapshot_marks_stale_target(self):
        app = SimpleNamespace(
            _round_advisor_recommendation={
                "target": {"data": "2026-09-12", "sorteio": "PTN", "hora": "18h"},
                "selector": "Similaridade",
                "kind": "Centena",
            }
        )
        target = {"data": "2026-09-13", "sorteio": "PPT", "hora": "09h"}
        snap = home._recommendation_snapshot(app, target)
        self.assertIn("antiga", snap["value"].lower())

    def test_recommendation_snapshot_exposes_method_without_recalculating(self):
        app = SimpleNamespace(
            _round_advisor_recommendation={
                "target": {"data": "2026-09-13", "sorteio": "PPT", "hora": "09h"},
                "selector": "Similaridade",
                "kind": "Centena",
                "confidence": "SINAL HISTÓRICO POSITIVO",
                "n": 43,
            }
        )
        target = {"data": "2026-09-13", "sorteio": "PPT", "hora": "09h"}
        snap = home._recommendation_snapshot(app, target)
        self.assertIn("Similaridade", snap["value"])
        self.assertIn("Centena", snap["value"])
        self.assertIn("n=43", snap["subtitle"])

    def test_install_is_idempotent_and_preserves_original_home(self):
        class FakeApp:
            def show_home(self):
                self.called = True
                return "legacy-home"

        fake_central = SimpleNamespace(App=FakeApp)
        first = home.install_home_polish(fake_central)
        patched = FakeApp.show_home
        second = home.install_home_polish(fake_central)
        self.assertEqual(first, home.HOME_POLISH_INFO)
        self.assertEqual(second, home.HOME_POLISH_INFO)
        self.assertIs(FakeApp.show_home, patched)

        app = FakeApp()
        self.assertEqual(app.show_home(), "legacy-home")
        self.assertTrue(app.called)


if __name__ == "__main__":
    unittest.main()
