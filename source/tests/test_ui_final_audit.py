from types import SimpleNamespace
import unittest

import gph_ui_final_audit as final_ui


class FakeStyle:
    def __init__(self):
        self.maps = {}

    def map(self, name, **kwargs):
        self.maps.setdefault(name, {}).update(kwargs)


class FakeContent:
    def __init__(self):
        self.kwargs = {}

    def configure(self, **kwargs):
        self.kwargs.update(kwargs)


class FakeApp:
    def __init__(self):
        self.colors = {"muted": "#777", "entry": "#111", "text": "#eee"}
        self.content = FakeContent()
        self._gph_dialog_binding_installed = False


class FinalAuditTests(unittest.TestCase):
    def make_central(self):
        style = FakeStyle()
        app_cls = type("App", (), {
            "_gph_ui_navigation_installed": True,
            "_gph_ui_results_installed": True,
        })
        central = SimpleNamespace(ttk=SimpleNamespace(Style=lambda _app: style), App=app_cls)
        return central, style

    def test_stage10_is_visual_only(self):
        info = final_ui.FINAL_AUDIT_INFO
        self.assertEqual(info["stage"], 10)
        self.assertTrue(info["visual_only"])
        self.assertFalse(info["changes_meta"])
        self.assertFalse(info["changes_database"])
        self.assertFalse(info["changes_generators"])
        self.assertFalse(info["changes_methods"])
        self.assertFalse(info["changes_financial"])
        self.assertFalse(info["changes_round_audit"])

    def test_runtime_audit_requires_native_combobox_and_no_dialog_hook(self):
        central, _ = self.make_central()
        app = FakeApp()
        audit = final_ui.runtime_audit(app, central)
        self.assertTrue(audit["combobox_popup_native"])
        self.assertTrue(audit["dialog_runtime_hook_disabled"])
        self.assertTrue(audit["no_dialog_map_binding"])
        self.assertTrue(audit["passed"])

    def test_apply_keeps_consistent_content_padding_and_safe_widget_maps(self):
        central, style = self.make_central()
        app = FakeApp()
        result = final_ui.apply_final_audit(app, central)
        self.assertEqual(app.content.kwargs["padding"], final_ui.FINAL_CONTENT_PADDING)
        self.assertIn("TButton", style.maps)
        self.assertIn("TCombobox", style.maps)
        self.assertTrue(app._gph_final_visual_audit["passed"])
        self.assertEqual(central.GPH_UI_FINAL_AUDIT_VERSION, "10.0")
        self.assertTrue(result["visual_only"])


if __name__ == "__main__":
    unittest.main()
