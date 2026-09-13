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
    UI_FONT_SIZES = {"body": 10, "secondary": 9, "table": 10, "table_heading": 10}
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
        }
        self.content = EmptyContent()
        self.method_tree = FakeTree()


class AnalysisPolishTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
