import unittest
from types import SimpleNamespace

import gph_ui_play as ui


class PlayPolishTests(unittest.TestCase):
    def test_stage_is_visual_only(self):
        self.assertEqual(ui.PLAY_POLISH_INFO["stage"], 4)
        self.assertTrue(ui.PLAY_POLISH_INFO["visual_only"])
        self.assertFalse(ui.PLAY_POLISH_INFO["changes_meta"])
        self.assertFalse(ui.PLAY_POLISH_INFO["changes_database"])
        self.assertFalse(ui.PLAY_POLISH_INFO["changes_generators"])
        self.assertFalse(ui.PLAY_POLISH_INFO["changes_methods"])

    def test_kind_label_is_compact(self):
        self.assertEqual(ui._short_kind("Terno de Grupo"), "Terno")
        self.assertEqual(ui._short_kind("Centena"), "Centena")

    def test_install_is_idempotent(self):
        advisor = SimpleNamespace(_build_advisor_card=lambda app: "legacy")
        first = ui.install_play_polish(advisor, "0.48.10")
        patched = advisor._build_advisor_card
        second = ui.install_play_polish(advisor, "0.48.10")
        self.assertEqual(first, ui.PLAY_POLISH_INFO)
        self.assertEqual(second, ui.PLAY_POLISH_INFO)
        self.assertIs(advisor._build_advisor_card, patched)
        self.assertTrue(advisor._gph_ui_play_stage4_installed)


if __name__ == "__main__":
    unittest.main()
