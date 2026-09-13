"""Fundação visual do GP-H — Etapas 1 e 9.

Tipografia, espaçamento e estilos. A Etapa 9 acrescenta acabamento visual às
janelas secundárias existentes, sem alterar banco, Meta, métodos ou geradores.
"""
from __future__ import annotations

FOUNDATION_VERSION = "1.0"
FOUNDATION_INFO = {
    "stage": 1,
    "visual_only": True,
    "changes_meta": False,
    "changes_database": False,
    "changes_generators": False,
}

DIALOG_VERSION = "9.0"
DIALOG_INFO = {
    "stage": 9,
    "visual_only": True,
    "changes_business_logic": False,
    "changes_database": False,
    "changes_profile": False,
    "changes_updater": False,
}

FONT_SIZES = {
    "page": 18,
    "hero": 20,
    "kpi": 16,
    "section": 12,
    "body": 10,
    "secondary": 9,
    "table": 10,
    "table_heading": 10,
}
SPACING = {"micro": 4, "small": 8, "normal": 12, "large": 18, "section": 24}
TABLE_ROWHEIGHT = 30


def prepare_ui_foundation(central):
    """Ajusta tokens antes da criação da janela principal."""
    central.UI_FONT_SIZES.update(FONT_SIZES)
    central.UI_SPACING.update(SPACING)
    central.UI_TABLE_ROWHEIGHT = TABLE_ROWHEIGHT
    central.GPH_UI_FOUNDATION_VERSION = FOUNDATION_VERSION
    return FOUNDATION_INFO


def _cfg(style, name, **kwargs):
    try:
        style.configure(name, **kwargs)
    except Exception:
        pass


def _map(style, name, **kwargs):
    try:
        style.map(name, **kwargs)
    except Exception:
        pass


def dialog_button_role(text, current_style=""):
    value = str(text or "").strip().upper()
    if str(current_style or "") == "Danger.TButton":
        return "danger"
    if any(word in value for word in (
        "SALVAR", "CONFIRMAR", "APLICAR", "CONTINUAR", "REGISTRAR", "IMPORTAR",
        "GERAR", "ATUALIZAR", "EXECUTAR", "TESTAR", "BUSCAR", "OK",
    )):
        return "primary"
    if any(word in value for word in (
        "CANCELAR", "FECHAR", "VOLTAR", "COPIAR", "DETALH", "AJUDA", "LOG",
        "EXPORTAR", "ABRIR PASTA",
    )):
        return "quiet"
    return "normal"


def _widget_text(widget, key):
    try:
        return str(widget.cget(key) or "")
    except Exception:
        return ""


def _polish_dialog_tree(root):
    try:
        children = list(root.winfo_children())
    except Exception:
        return
    for child in children:
        try:
            kind = str(child.winfo_class() or "")
            current = _widget_text(child, "style")
            text = _widget_text(child, "text")
            if kind == "TFrame" and current == "Card.TFrame":
                child.configure(style="DialogCard.TFrame")
            elif kind == "TFrame" and current == "Card2.TFrame":
                child.configure(style="DialogInset.TFrame")
            elif kind == "TLabelframe":
                child.configure(style="Dialog.TLabelframe")
            elif kind == "TLabel" and current in {"CardTitle.TLabel", "Section.TLabel"}:
                child.configure(style="DialogTitle.TLabel")
            elif kind == "TLabel" and current in {"CardMuted.TLabel", "Sub.TLabel"}:
                child.configure(style="DialogMuted.TLabel")
            elif kind == "Treeview":
                child.configure(style="Dialog.Treeview")
            elif kind == "TButton":
                role = dialog_button_role(text, current)
                if role == "primary":
                    child.configure(style="DialogPrimary.TButton")
                elif role == "quiet":
                    child.configure(style="DialogQuiet.TButton")
        except Exception:
            pass
        _polish_dialog_tree(child)


def _polish_toplevel(win, app, central):
    try:
        win.configure(background=app.colors["bg"])
    except Exception:
        pass
    _polish_dialog_tree(win)
    try:
        win._gph_dialog_polished = True
        win._gph_dialog_version = DIALOG_VERSION
    except Exception:
        pass
    central.GPH_UI_DIALOG_VERSION = DIALOG_VERSION


def _install_dialog_polish(app, central):
    if getattr(app, "_gph_dialog_binding_installed", False):
        return DIALOG_INFO

    def on_map(event):
        win = getattr(event, "widget", None)
        if win is None or win is app:
            return
        try:
            if win.winfo_toplevel() is not win:
                return
            if getattr(win, "_gph_dialog_polished", False):
                return
            win._gph_dialog_polished = True
            win.after_idle(lambda: _polish_toplevel(win, app, central))
        except Exception:
            return

    try:
        app.bind_all("<Map>", on_map, add="+")
        app._gph_dialog_binding_installed = True
        central.GPH_UI_DIALOG_VERSION = DIALOG_VERSION
    except Exception:
        pass
    return DIALOG_INFO


def apply_ui_foundation(app, central):
    """Finaliza o acabamento ttk depois que App criou o tema base."""
    style = central.ttk.Style(app)
    c = app.colors
    sizes = central.UI_FONT_SIZES
    font = central.UI_FONT_FAMILY
    semibold = central.UI_FONT_SEMIBOLD
    body = sizes["body"]
    secondary = sizes["secondary"]

    for name, background in (
        ("Surface.TFrame", c["bg"]),
        ("Panel.TFrame", c["card"]),
        ("PanelAlt.TFrame", c["card2"]),
        ("Inset.TFrame", c["entry"]),
        ("Divider.TFrame", c["divider"]),
    ):
        _cfg(style, name, background=background)

    _cfg(style, "PageTitle.TLabel", background=c["bg"], foreground=c["text"], font=(semibold, sizes["page"]))
    _cfg(style, "PageSubtitle.TLabel", background=c["bg"], foreground=c["muted"], font=(font, body))
    _cfg(style, "SectionTitle.TLabel", background=c["card"], foreground=c["text"], font=(semibold, sizes["section"]))
    _cfg(style, "Eyebrow.TLabel", background=c["card"], foreground=c["muted"], font=(semibold, secondary))
    _cfg(style, "Metric.TLabel", background=c["card"], foreground=c["text"], font=(semibold, sizes["kpi"]))

    _cfg(style, "TButton", font=(semibold, body), padding=(12, 7), background=c["card2"], foreground=c["text"], bordercolor=c["border"], relief="flat")
    _cfg(style, "Accent.TButton", font=(semibold, body), padding=(14, 8), background=c["accent"], foreground=central.UI_TEXT_ON_ACCENT, bordercolor=c["accent"], relief="flat")
    _cfg(style, "Primary.TButton", font=(semibold, body), padding=(14, 8), background=c["accent"], foreground=central.UI_TEXT_ON_ACCENT, bordercolor=c["accent"], relief="flat")
    _map(style, "Primary.TButton", background=[("active", c["accent_hover"]), ("pressed", c["accent"])])
    _cfg(style, "Secondary.TButton", font=(semibold, body), padding=(12, 7), background=c["card2"], foreground=c["text"], bordercolor=c["border"], relief="flat")
    _map(style, "Secondary.TButton", background=[("active", c["hover"]), ("pressed", c["band"])])
    _cfg(style, "Quiet.TButton", font=(font, body), padding=(10, 6), background=c["card2"], foreground=c["muted"], bordercolor=c["border"])
    _cfg(style, "Danger.TButton", font=(semibold, body), padding=(12, 7), background=c["card2"], foreground=c["danger"], bordercolor=c["danger"], relief="flat")

    for name in ("Subnav.TButton", "SubnavActive.TButton"):
        _cfg(style, name, font=(semibold, body), padding=(12, 7))

    _cfg(style, "Treeview", font=(font, sizes["table"]), rowheight=central.UI_TABLE_ROWHEIGHT)
    _cfg(style, "Treeview.Heading", font=(semibold, sizes["table_heading"]), padding=(8, 7))
    _cfg(style, "TEntry", font=(font, body), padding=6)
    _cfg(style, "TCombobox", font=(font, body), padding=5)
    _cfg(style, "TSpinbox", font=(font, body), padding=5)
    _cfg(style, "TCheckbutton", font=(font, body), padding=(0, 3))
    _cfg(style, "TRadiobutton", font=(font, body), padding=(0, 3))

    for name, color in (
        ("StatusInfo.TLabel", c["accent_hover"]),
        ("StatusSuccess.TLabel", c["success"]),
        ("StatusWarning.TLabel", c["warning"]),
        ("StatusDanger.TLabel", c["danger"]),
    ):
        _cfg(style, name, background=c["card"], foreground=color, font=(semibold, secondary))

    _cfg(style, "DialogCard.TFrame", background=c["card"], bordercolor=c["border"], borderwidth=1, relief="solid")
    _cfg(style, "DialogInset.TFrame", background=c["card2"], bordercolor=c["border"], borderwidth=1, relief="solid")
    _cfg(style, "Dialog.TLabelframe", background=c["card"], bordercolor=c["border"], borderwidth=1, relief="solid")
    _cfg(style, "Dialog.TLabelframe.Label", background=c["card"], foreground=c["text"], font=(semibold, body))
    _cfg(style, "DialogTitle.TLabel", background=c["card"], foreground=c["text"], font=(semibold, sizes["section"]))
    _cfg(style, "DialogMuted.TLabel", background=c["card"], foreground=c["muted"], font=(font, secondary))
    _cfg(style, "DialogPrimary.TButton", font=(semibold, body), padding=(14, 8), background=c["accent"], foreground=central.UI_TEXT_ON_ACCENT, bordercolor=c["accent"], relief="flat")
    _map(style, "DialogPrimary.TButton", background=[("active", c["accent_hover"])])
    _cfg(style, "DialogQuiet.TButton", font=(font, body), padding=(10, 7), background=c["card2"], foreground=c["muted"], bordercolor=c["border"], relief="flat")
    _map(style, "DialogQuiet.TButton", background=[("active", c["hover"])], foreground=[("active", c["text"])])
    _cfg(style, "Dialog.Treeview", background=c["entry"], fieldbackground=c["entry"], foreground=c["text"], bordercolor=c["border"], borderwidth=1, relief="flat", font=(font, sizes["table"]), rowheight=central.UI_TABLE_ROWHEIGHT)
    _cfg(style, "Dialog.Treeview.Heading", background=c["card2"], foreground=c["text"], bordercolor=c["border"], font=(semibold, sizes["table_heading"]), padding=(9, 8), relief="flat")
    _map(style, "Dialog.Treeview", background=[("selected", c["selection"])], foreground=[("selected", c["text"])])

    try:
        app.option_add("*TCombobox*Listbox.font", f"{font} {body}")
        app.option_add("*TCombobox*Listbox.background", c["entry"])
        app.option_add("*TCombobox*Listbox.foreground", c["text"])
        app.option_add("*TCombobox*Listbox.selectBackground", c["selection"])
        app.option_add("*TCombobox*Listbox.selectForeground", c["text"])
    except Exception:
        pass

    _install_dialog_polish(app, central)
    return FOUNDATION_INFO
