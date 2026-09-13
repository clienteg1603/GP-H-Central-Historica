import unittest

import gph_ui_analysis as ui


class FakeStyle:
    def __init__(self):
        self.configured = {}
        self.mapped = {}

    def configure(self, name, **kwargs):
        self.configured[name] = kwargs

    def map(self, name, **kwargs):
        self.mapped[name] = kwargs


class FakeTTK:
    style = FakeStyle()

    @classmethod
    def Style(cls, _app):
        return cls.style


class FakeCentral:
    ttk = FakeTTK
    UI_FONT_FAMILY = "Segoe UI"
    UI_FONT_SEMIBOLD = "Segoe UI Semibold"
    UI_FONT_SIZES = {
        "body": 10, "secondary": 9, "table": 10, "table_heading": 10,
        "section": 12, "kpi": 16,
    }
    UI_TABLE_ROWHEIGHT = 30
    UI_TEXT_ON_ACCENT = "#ffffff"


class EmptyContent:
    def winfo_children(self):
        return []


class FakeTree:
    def __init__(self):
        self.style = None

    def configure(self, **kwargs):
        self.style = kwargs.get("style")


class FakeApp:
    def __init__(self):
        self.colors = {
            "card": "#111111", "border": "#222222", "entry": "#090909",
            "text": "#eeeeee", "card2": "#161616", "selection": "#25364a",
            "hover": "#1f2933", "muted": "#999999", "accent": "#2374e1",
            "accent_hover": "#4b91ef", "success": "#39b980", "warning": "#e5b94c",
            "danger": "#e06470",
        }
        self.content = EmptyContent()
        self.method_tree = FakeTree()


class AnalysisPolishTests(unittest.TestCase):
    def setUp(self):
        FakeTTK.style = FakeStyle()

    def test_stage_is_visual_only(self):
        spec = ui.analysis_spec()
        self.assertEqual(spec["pages"], ("search", "statistics", "pulls", "methods"))
        self.assertTrue(spec["visual_only"])
        self.assertFalse(ui.ANALYSIS_INFO["changes_meta"])
        self.assertFalse(ui.ANALYSIS_INFO["changes_methods"])

    def test_methods_tree_receives_analysis_style(self):
        app = FakeApp()
        ui.polish_analysis_page(app, FakeCentral, "methods")
        self.assertEqual(app.method_tree.style, "Analysis.Treeview")
        self.assertTrue(app._gph_analysis_polished)
        self.assertIn("Analysis.Treeview", FakeTTK.style.configured)
        self.assertIn("AnalysisPrimary.TButton", FakeTTK.style.configured)


class ResultsPolishTests(unittest.TestCase):
    def setUp(self):
        FakeTTK.style = FakeStyle()

    def test_stage7_is_visual_only(self):
        spec = ui.results_spec()
        self.assertEqual(spec["pages"], ("results", "games_day"))
        self.assertTrue(spec["visual_only"])
        self.assertFalse(ui.RESULTS_INFO["changes_database"])
        self.assertFalse(ui.RESULTS_INFO["changes_audit"])
        self.assertFalse(ui.RESULTS_INFO["changes_results"])
        self.assertFalse(ui.RESULTS_INFO["changes_frozen_games"])

    def test_status_hierarchy(self):
        self.assertEqual(ui.status_role("PENDENTE"), "pending")
        self.assertEqual(ui.status_role("AUDITADO"), "success")
        self.assertEqual(ui.status_role("EM AUDITORIA"), "warning")
        self.assertEqual(ui.status_role("ERRO"), "danger")
        self.assertEqual(ui.status_role("CONGELADO"), "info")
        self.assertIsNone(ui.status_role("sem status"))

    def test_action_hierarchy(self):
        self.assertEqual(ui.results_button_role("ATUALIZAR"), "primary")
        self.assertEqual(ui.results_button_role("AUDITAR JOGOS"), "primary")
        self.assertEqual(ui.results_button_role("DETALHES"), "quiet")
        self.assertEqual(ui.results_button_role("EXPORTAR"), "quiet")
        self.assertEqual(ui.results_button_role("OUTRA AÇÃO"), "normal")

    def test_results_styles_are_registered(self):
        app = FakeApp()
        ui.polish_results_page(app, FakeCentral, "results")
        self.assertTrue(app._gph_results_polished)
        self.assertEqual(app._gph_results_page, "results")
        self.assertIn("ResultsCard.TFrame", FakeTTK.style.configured)
        self.assertIn("Results.Treeview", FakeTTK.style.configured)
        self.assertIn("ResultsPrimary.TButton", FakeTTK.style.configured)
        self.assertIn("ResultsStatusPending.TLabel", FakeTTK.style.configured)


class SettingsPolishTests(unittest.TestCase):
    def setUp(self):
        FakeTTK.style = FakeStyle()

    def test_stage8_is_visual_only(self):
        spec = ui.settings_spec()
        self.assertTrue(spec["visual_only"])
        self.assertEqual(tuple(spec["sections"]), ("account", "appearance", "updates", "data"))
        self.assertFalse(ui.SETTINGS_INFO["changes_profile"])
        self.assertFalse(ui.SETTINGS_INFO["changes_sync"])
        self.assertFalse(ui.SETTINGS_INFO["changes_updater"])
        self.assertFalse(ui.SETTINGS_INFO["changes_database"])

    def test_settings_navigation(self):
        self.assertEqual(ui.settings_button_role("Conta e Sync", "account"), "nav_active")
        self.assertEqual(ui.settings_button_role("Aparência", "account"), "nav")
        self.assertEqual(ui.settings_button_role("Atualizações", "updates"), "nav_active")
        self.assertEqual(ui.settings_button_role("Base de dados", "data"), "nav_active")

    def test_settings_status(self):
        self.assertEqual(ui.settings_status_role("Perfil conectado"), "ok")
        self.assertEqual(ui.settings_status_role("Atualizado"), "ok")
        self.assertEqual(ui.settings_status_role("Sync pendente"), "wait")
        self.assertEqual(ui.settings_status_role("Não configurado"), "wait")
        self.assertIsNone(ui.settings_status_role("Informação comum"))

    def test_settings_styles_are_registered(self):
        app = FakeApp()
        ui.polish_settings_page(app, FakeCentral, "updates")
        self.assertTrue(app._gph_settings_polished)
        self.assertEqual(app._gph_settings_section, "updates")
        self.assertIn("SettingsCard.TFrame", FakeTTK.style.configured)
        self.assertIn("SettingsNavActive.TButton", FakeTTK.style.configured)
        self.assertIn("SettingsPrimary.TButton", FakeTTK.style.configured)
        self.assertIn("SettingsStatusOk.TLabel", FakeTTK.style.configured)


if __name__ == "__main__":
    unittest.main()
