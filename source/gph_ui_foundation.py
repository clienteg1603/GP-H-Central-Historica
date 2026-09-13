"""Fundação visual do GP-H — Etapa 1.

Apenas tipografia, espaçamento e estilos. Sem alterações em banco, Meta, métodos,
geradores ou auditoria.
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

    try:
        app.option_add("*TCombobox*Listbox.font", f"{font} {body}")
        app.option_add("*TCombobox*Listbox.background", c["entry"])
        app.option_add("*TCombobox*Listbox.foreground", c["text"])
        app.option_add("*TCombobox*Listbox.selectBackground", c["selection"])
        app.option_add("*TCombobox*Listbox.selectForeground", c["text"])
    except Exception:
        pass
    return FOUNDATION_INFO
