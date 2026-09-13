import os
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
        self.bindings[("class", tag, sequence)] = (callback, add)

    def bind_all(self, sequence, callback, add=None):
        self.bindings[("all", sequence)] = (callback, add)


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

    def test_apply_registers_semantic_styles_without_touching_combobox_popup(self):
        central, style = self.make_central()
        ui.prepare_ui_foundation(central)
        app = FakeApp()
        ui.apply_ui_foundation(app, central)
        for name in ("PageTitle.TLabel", "Panel.TFrame", "Primary.TButton", "Secondary.TButton", "Danger.TButton", "Treeview"):
            self.assertIn(name, style.configured)
        self.assertEqual(style.configured["Treeview"]["rowheight"], 30)
        self.assertEqual(style.configured["TButton"]["padding"], (12, 7))
        self.assertTrue(ui.COMBOBOX_POPUP_NATIVE)
        self.assertFalse(any(str(key).startswith("*TCombobox*Listbox") for key in app.options))

    def test_stage9_runtime_polish_is_disabled(self):
        self.assertEqual(ui.DIALOG_INFO["stage"], 9)
        self.assertTrue(ui.DIALOG_INFO["visual_only"])
        self.assertFalse(ui.DIALOG_INFO["runtime_polish_enabled"])
        self.assertFalse(ui.DIALOG_INFO["changes_business_logic"])
        self.assertFalse(ui.DIALOG_INFO["changes_database"])
        self.assertFalse(ui.DIALOG_INFO["changes_profile"])
        self.assertFalse(ui.DIALOG_INFO["changes_updater"])

    def test_dialog_button_hierarchy_remains_available(self):
        self.assertEqual(ui.dialog_button_role("Salvar"), "primary")
        self.assertEqual(ui.dialog_button_role("Confirmar"), "primary")
        self.assertEqual(ui.dialog_button_role("Fechar"), "quiet")
        self.assertEqual(ui.dialog_button_role("Cancelar"), "quiet")
        self.assertEqual(ui.dialog_button_role("Excluir", "Danger.TButton"), "danger")
        self.assertEqual(ui.dialog_button_role("Outra ação"), "normal")

    def test_foundation_does_not_install_map_bindings(self):
        central, style = self.make_central()
        ui.prepare_ui_foundation(central)
        app = FakeApp()
        ui.apply_ui_foundation(app, central)
        for name in ("DialogCard.TFrame", "DialogPrimary.TButton", "DialogQuiet.TButton", "Dialog.Treeview"):
            self.assertIn(name, style.configured)
        self.assertEqual(app.bindings, {})
        self.assertFalse(app._gph_dialog_binding_installed)
        self.assertFalse(app._gph_dialog_runtime_polish_enabled)
        self.assertEqual(central.GPH_UI_DIALOG_VERSION, "9.2")

    @unittest.skipUnless(os.name == "nt", "Smoke real do ttk.Combobox é específico do build Windows")
    def test_real_windows_readonly_combobox_can_select_from_popup(self):
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
        root.geometry("320x120+20+20")
        try:
            root.colors = {
                "bg": "#101214", "card": "#181b1f", "card2": "#20242a", "entry": "#111417",
                "divider": "#303640", "text": "#f2f4f7", "muted": "#9ca6b3", "border": "#46505c",
                "accent": "#4d8df7", "accent_hover": "#6aa0fa", "hover": "#2a3038", "band": "#252b32",
                "tree": "#111417", "selection": "#315b8a", "success": "#35b96f",
                "warning": "#d6a23d", "danger": "#e85b5b",
            }
            central = SimpleNamespace(
                UI_FONT_SIZES=dict(ui.FONT_SIZES),
                UI_SPACING=dict(ui.SPACING),
                UI_TABLE_ROWHEIGHT=ui.TABLE_ROWHEIGHT,
                UI_FONT_FAMILY="Segoe UI",
                UI_FONT_SEMIBOLD="Segoe UI Semibold",
                UI_TEXT_ON_ACCENT="#FFFFFF",
                ttk=ttk,
            )
            ui.prepare_ui_foundation(central)
            ui.apply_ui_foundation(root, central)

            value = tk.StringVar(value="A")
            combo = ttk.Combobox(
                root,
                textvariable=value,
                values=("A", "B", "C"),
                state="readonly",
                width=18,
            )
            combo.pack(padx=20, pady=20)
            root.update_idletasks()
            root.update()

            root.tk.call("ttk::combobox::Post", str(combo))
            root.update()
            popdown = root.tk.call("ttk::combobox::PopdownWindow", str(combo))
            listbox = f"{popdown}.f.l"
            root.tk.call(listbox, "selection", "clear", 0, "end")
            root.tk.call(listbox, "selection", "set", 1)
            root.tk.call(listbox, "activate", 1)
            root.tk.call("ttk::combobox::LBSelected", listbox)
            root.update()

            self.assertEqual(value.get(), "B")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
