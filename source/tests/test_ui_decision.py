import unittest

import gph_ui_decision as ui


class DecisionVisualTests(unittest.TestCase):
    def test_stage_is_visual_only(self):
        spec = ui.decision_spec()
        self.assertTrue(spec["visual_only"])
        self.assertEqual(tuple(spec["views"]), ("summary", "analysis", "audit", "lab"))
        self.assertFalse(ui.DECISION_INFO["changes_meta"])
        self.assertFalse(ui.DECISION_INFO["changes_database"])
        self.assertFalse(ui.DECISION_INFO["changes_generators"])
        self.assertFalse(ui.DECISION_INFO["changes_methods"])
        self.assertFalse(ui.DECISION_INFO["changes_audit"])

    def test_navigation_role_marks_only_current_view_active(self):
        self.assertEqual(ui.button_role("Resumo", "summary"), "nav_active")
        self.assertEqual(ui.button_role("Análise", "summary"), "nav")
        self.assertEqual(ui.button_role("Auditoria", "audit"), "nav_active")
        self.assertEqual(ui.button_role("Laboratório", "lab"), "nav_active")

    def test_action_hierarchy(self):
        self.assertEqual(ui.button_role("ATUALIZAR AUDITORIA"), "primary")
        self.assertEqual(ui.button_role("TESTAR NO HISTÓRICO"), "primary")
        self.assertEqual(ui.button_role("COPIAR RESUMO"), "quiet")
        self.assertEqual(ui.button_role("EXPORTAR CSV"), "quiet")
        self.assertEqual(ui.button_role("Fechar"), "normal")


if __name__ == "__main__":
    unittest.main()
