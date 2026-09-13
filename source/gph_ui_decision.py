"""Etapa 6 da cura visual: Decisão, Meta, Auditoria e Laboratório.

Somente apresentação. Não altera Meta, pesos, features, banco, métodos,
auditoria, geradores ou critérios de decisão.
"""
from __future__ import annotations

DECISION_VERSION = "6.0"
DECISION_INFO = {
    "stage": 6,
    "visual_only": True,
    "changes_meta": False,
    "changes_database": False,
    "changes_generators": False,
    "changes_methods": False,
    "changes_audit": False,
}

DECISION_VIEWS = {
    "summary": "Resumo",
    "analysis": "Análise",
    "audit": "Auditoria",
    "lab": "Laboratório",
}


def decision_spec():
    return {
        "version": DECISION_VERSION,
        "views": dict(DECISION_VIEWS),
        "visual_only": True,
    }


def button_role(text, current_view=None):
    text = str(text or "").strip()
    upper = text.upper()
    for key, label in DECISION_VIEWS.items():
        if text == label:
            return "nav_active" if key == current_view else "nav"
    if any(word in upper for word in ("ATUALIZAR", "AUDITAR", "GERAR", "TESTAR", "EXECUTAR", "PESQUISAR")):
        return "primary"
    if any(word in upper for word in ("COPIAR", "EXPORTAR", "DETALH", "TÉCNIC", "TECNIC", "VOLTAR", "OCULTAR")):
        return "quiet"
    return "normal"


def _read(widget, key):
    try:
        return str(widget.cget(key) or "")
    except Exception:
        return ""


def configure_decision_styles(app, central):
    style = central.ttk.Style(app)
    c = app.colors
    font = central.UI_FONT_FAMILY
    semi = central.UI_FONT_SEMIBOLD
    sizes = central.UI_FONT_SIZES

    style.configure(
        "DecisionCard.TFrame", background=c["card"], bordercolor=c["border"],
        borderwidth=1, relief="solid"
    )
    style.configure(
        "DecisionInset.TFrame", background=c["card2"], bordercolor=c["border"],
        borderwidth=1, relief="solid"
    )
    style.configure(
        "DecisionNav.TButton", font=(semi, sizes["body"]), padding=(14, 8),
        background=c["card2"], foreground=c["muted"], bordercolor=c["border"], relief="flat"
    )
    style.configure(
        "DecisionNavActive.TButton", font=(semi, sizes["body"]), padding=(14, 8),
        background=c["selection"], foreground=c["text"], bordercolor=c["accent"], relief="flat"
    )
    style.map("DecisionNav.TButton", background=[("active", c["hover"])], foreground=[("active", c["text"])])
    style.map("DecisionNavActive.TButton", background=[("active", c["selection"])])

    style.configure(
        "DecisionPrimary.TButton", font=(semi, sizes["body"]), padding=(14, 8),
        background=c["accent"], foreground=central.UI_TEXT_ON_ACCENT,
        bordercolor=c["accent"], relief="flat"
    )
    style.configure(
        "DecisionQuiet.TButton", font=(font, sizes["body"]), padding=(10, 6),
        background=c["card2"], foreground=c["muted"], bordercolor=c["border"], relief="flat"
    )

    style.configure(
        "DecisionSection.TLabel", background=c["card"], foreground=c["text"],
        font=(semi, sizes["section"])
    )
    style.configure(
        "DecisionKpi.TLabel", background=c["card"], foreground=c["text"],
        font=(semi, max(17, sizes["kpi"]))
    )
    style.configure(
        "DecisionKpiCaption.TLabel", background=c["card"], foreground=c["muted"],
        font=(semi, sizes["secondary"])
    )
    style.configure(
        "DecisionMuted.TLabel", background=c["card"], foreground=c["muted"],
        font=(font, sizes["secondary"])
    )
    style.configure(
        "Decision.Treeview", background=c["entry"], fieldbackground=c["entry"],
        foreground=c["text"], bordercolor=c["border"], borderwidth=1, relief="flat",
        font=(font, sizes["table"]), rowheight=max(31, int(central.UI_TABLE_ROWHEIGHT))
    )
    style.configure(
        "Decision.Treeview.Heading", background=c["card2"], foreground=c["text"],
        bordercolor=c["border"], font=(semi, sizes["table_heading"]), padding=(9, 8), relief="flat"
    )
    style.map("Decision.Treeview", background=[("selected", c["selection"])], foreground=[("selected", c["text"])])
    style.map("Decision.Treeview.Heading", background=[("active", c["hover"])])


def _polish_children(root, current_view):
    try:
        children = list(root.winfo_children())
    except Exception:
        return

    for child in children:
        try:
            kind = str(child.winfo_class() or "")
            current = _read(child, "style")
            text = _read(child, "text")

            if kind == "TFrame":
                if current == "Card.TFrame":
                    child.configure(style="DecisionCard.TFrame")
                elif current == "Card2.TFrame":
                    child.configure(style="DecisionInset.TFrame")
            elif kind == "Treeview":
                child.configure(style="Decision.Treeview")
            elif kind == "TLabel":
                if current in {"CardTitle.TLabel", "Section.TLabel"}:
                    child.configure(style="DecisionSection.TLabel")
                elif current == "Kpi.TLabel":
                    child.configure(style="DecisionKpi.TLabel")
                elif current == "KpiCaption.TLabel":
                    child.configure(style="DecisionKpiCaption.TLabel")
                elif current == "CardMuted.TLabel":
                    child.configure(style="DecisionMuted.TLabel")
            elif kind == "TButton":
                role = button_role(text, current_view)
                if role == "nav_active":
                    child.configure(style="DecisionNavActive.TButton")
                elif role == "nav":
                    child.configure(style="DecisionNav.TButton")
                elif role == "primary" and current not in {"Danger.TButton"}:
                    child.configure(style="DecisionPrimary.TButton")
                elif role == "quiet" and current not in {"Danger.TButton"}:
                    child.configure(style="DecisionQuiet.TButton")
        except Exception:
            pass
        _polish_children(child, current_view)


def polish_decision_page(app, central, current_view="summary"):
    current_view = current_view if current_view in DECISION_VIEWS else "summary"
    configure_decision_styles(app, central)
    content = getattr(app, "content", None)
    if content is not None:
        _polish_children(content, current_view)
    app._gph_decision_view = current_view
    app._gph_decision_polished = True
    central.GPH_UI_DECISION_VERSION = DECISION_VERSION
    return DECISION_INFO


def install_decision_polish(central):
    """Envolve a tela existente sem alterar sua lógica ou seus dados."""
    app_cls = central.App
    if getattr(app_cls, "_gph_ui_decision_installed", False):
        return DECISION_INFO

    original = app_cls.show_decision_page

    def show_decision_page(self, open_lab=False, view=None, *args, **kwargs):
        requested = view or ("lab" if open_lab else "summary")
        if requested not in DECISION_VIEWS:
            requested = "summary"
        result = original(self, open_lab=open_lab, view=view, *args, **kwargs)
        try:
            polish_decision_page(self, central, requested)
        except Exception as exc:
            self._gph_decision_polish_error = str(exc)
        return result

    app_cls.show_decision_page = show_decision_page
    app_cls._gph_ui_decision_installed = True
    central.GPH_UI_DECISION_VERSION = DECISION_VERSION
    return DECISION_INFO
