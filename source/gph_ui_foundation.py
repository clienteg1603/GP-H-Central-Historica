"""Fundação visual do GP-H — Etapa 1.

Tipografia, espaçamento e estilos da janela principal. O acabamento automático
adicionado na Etapa 9 para Toplevels foi retirado no hotfix v0.48.17 para
preservar integralmente o comportamento nativo dos ttk.Combobox no Windows.
Sem alterações em banco, Meta, métodos, geradores ou auditoria.
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

# A Etapa 9 continua registrada historicamente, mas o polimento dinâmico de
# Toplevels fica desativado. Não instalamos bind_all/bind_class em <Map>.
# Isso devolve ao Tk o controle exclusivo dos popups internos do Combobox.
DIALOG_VERSION = "9.2"
DIALOG_INFO = {
    "stage": 9,
    "visual_only": True,
    "runtime_polish_enabled": False,
    "changes_business_logic": False,
    "changes_database": False,
    "changes_profile": False,
    "changes_updater": False,
}

# O popup interno do ttk.Combobox deve permanecer 100% nativo. Em Tk 8.6/Windows,
# inserir uma fonte como texto simples no option database (ex.: "Segoe UI 10")
# pode ser interpretado como lista Tcl inválida ao postar o menu e quebrar a seleção.
COMBOBOX_POPUP_NATIVE = True

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
    """Mantido para compatibilidade/testes da Etapa 9; sem binding automático."""
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


def _install_dialog_polish(app, central):
    """Hotfix v0.48.17: não toca em bindings globais ou de classe do Tk.

    A v0.48.15 introduziu observação de <Map> para estilizar Toplevels. Como os
    popups internos de ttk.Combobox pertencem ao mesmo mecanismo de janelas do
    Tk no Windows, qualquer observador desse ciclo pode interferir na seleção.
    Até a Etapa 10 revisar diálogos com uma estratégia explícita, o polimento
    dinâmico fica desativado e o Tk mantém controle nativo integral.
    """
    try:
        app._gph_dialog_binding_installed = False
        app._gph_dialog_runtime_polish_enabled = False
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

    # Estilos da Etapa 9 permanecem disponíveis para uso explícito por janelas,
    # mas não são aplicados por observação automática de eventos do Tk.
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

    # Não usamos option_add em *TCombobox*Listbox. O Listbox é parte interna
    # do popup nativo e deve ficar sob controle integral do ttk/Tk do Windows.
    _install_dialog_polish(app, central)
    return FOUNDATION_INFO
