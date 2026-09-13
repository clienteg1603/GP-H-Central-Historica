from types import SimpleNamespace
import unittest

import gph_ui_foundation as ui


class FakeStyle:
    def __init__(self):
        self.configured = {}
        self.mapped = {}

    def configure(self, name, **kwargs):
        self.configured.setdefault(name, {}).update(kwargs)

    def map(self, name, **kwargs):
        self.mapped.setdefault(name, {}).update(kwargs)


class FakeApp:
    def __init__(self):
        self.colors = {
            "bg": "#01", "card": "#02", "card2": "#03", "entry": "#04",
            "divider": "#05", "text": "#06", "muted": "#07", "border": "#08",
            "accent": "#09", "accent_hover": "#10", "hover": "#11", "band": "#12",
            "tree": "#13", "selection": "#14", "success": "#15",
            "warning": "#16", "danger": "#17",
        }
        self.options = {}
        self.bindings = {}

    def option_add(self, key, value):
        self.options[key] = value

    def bind_class(self, tag, sequence, callback, add=None):
        self.bindings[(tag, sequence)] = (callback, add)


class FakeTop:
    def __init__(self, class_name="Toplevel"):
        self.config = {}
        self.class_name = class_name

    def winfo_toplevel(self):
        return self

    def winfo_children(self):
        return []

    def winfo_class(self):
        return self.class_name

    def after_idle(self, callback):
        callback()

    def configure(self, **kwargs):
        self.config.update(kwargs)


class FakeComboboxPopup:
    def __init__(self):
        self.class_name = "ComboboxPopdown"

    def winfo_toplevel(self):
        return self

    def winfo_class(self):
        return self.class_name


class UIFoundationTests(unittest.TestCase):
    def make_central(self):
        style = FakeStyle()
        central = SimpleNamespace(
            UI_FONT_SIZES={"page": 17, "hero": 18, "kpi": 15, "section": 11, "body": 9, "secondary": 8, "table": 9, "table_heading": 9},
            UI_SPACING={"micro": 4, "small": 8, "normal": 12, "large": 16, "section": 24},
            UI_TABLE_ROWHEIGHT=28,
            UI_FONT_FAMILY="Segoe UI",
            UI_FONT_SEMIBOLD="Segoe UI Semibold",
            UI_TEXT_ON_ACCENT="#FFFFFF",
            ttk=SimpleNamespace(Style=lambda _app: style),
            tk=SimpleNamespace(Toplevel=FakeTop),
            computation_sentinel=object(),
        )
        return central, style

    def test_prepare_changes_only_visual_tokens(self):
        central, _ = self.make_central()
        sentinel = central.computation_sentinel
        info = ui.prepare_ui_foundation(central)
        self.assertEqual(central.UI_FONT_SIZES["body"], 10)
        self.assertEqual(central.UI_FONT_SIZES["secondary"], 9)
        self.assertEqual(central.UI_FONT_SIZES["page"], 18)
        self.assertEqual(central.UI_SPACING["large"], 18)
        self.assertEqual(central.UI_TABLE_ROWHEIGHT, 30)
        self.assertIs(central.computation_sentinel, sentinel)
        self.assertTrue(info["visual_only"])
        self.assertFalse(info["changes_meta"])
        self.assertFalse(info["changes_database"])
        self.assertFalse(info["changes_generators"])

    def test_apply_registers_semantic_styles(self):
        central, style = self.make_central()
        ui.prepare_ui_foundation(central)
        app = FakeApp()
        ui.apply_ui_foundation(app, central)
        for name in ("PageTitle.TLabel", "Panel.TFrame", "Primary.TButton", "Secondary.TButton", "Danger.TButton", "Treeview"):
            self.assertIn(name, style.configured)
        self.assertEqual(style.configured["Treeview"]["rowheight"], 30)
        self.assertEqual(style.configured["TButton"]["padding"], (12, 7))
        self.assertIn("*TCombobox*Listbox.background", app.options)

    def test_stage9_is_visual_only(self):
        self.assertEqual(ui.DIALOG_INFO["stage"], 9)
        self.assertTrue(ui.DIALOG_INFO["visual_only"])
        self.assertFalse(ui.DIALOG_INFO["changes_business_logic"])
        self.assertFalse(ui.DIALOG_INFO["changes_database"])
        self.assertFalse(ui.DIALOG_INFO["changes_profile"])
        self.assertFalse(ui.DIALOG_INFO["changes_updater"])

    def test_dialog_button_hierarchy(self):
        self.assertEqual(ui.dialog_button_role("Salvar"), "primary")
        self.assertEqual(ui.dialog_button_role("Confirmar"), "primary")
        self.assertEqual(ui.dialog_button_role("Fechar"), "quiet")
        self.assertEqual(ui.dialog_button_role("Cancelar"), "quiet")
        self.assertEqual(ui.dialog_button_role("Excluir", "Danger.TButton"), "danger")
        self.assertEqual(ui.dialog_button_role("Outra ação"), "normal")

    def test_dialog_styles_use_toplevel_class_binding_only(self):
        central, style = self.make_central()
        ui.prepare_ui_foundation(central)
        app = FakeApp()
        ui.apply_ui_foundation(app, central)
        for name in ("DialogCard.TFrame", "DialogPrimary.TButton", "DialogQuiet.TButton", "Dialog.Treeview"):
            self.assertIn(name, style.configured)
        key = ("Toplevel", "<Map>")
        self.assertIn(key, app.bindings)
        top = FakeTop()
        callback, add = app.bindings[key]
        callback(SimpleNamespace(widget=top))
        self.assertEqual(add, "+")
        self.assertTrue(top._gph_dialog_polished)
        self.assertEqual(top._gph_dialog_version, "9.1")
        self.assertEqual(top.config.get("background"), app.colors["bg"])
        self.assertEqual(central.GPH_UI_DIALOG_VERSION, "9.1")

    def test_combobox_popup_is_not_a_dialog(self):
        central, _ = self.make_central()
        app = FakeApp()
        popup = FakeComboboxPopup()
        self.assertFalse(ui._is_real_dialog_toplevel(popup, app, central))


if __name__ == "__main__":
    unittest.main()
