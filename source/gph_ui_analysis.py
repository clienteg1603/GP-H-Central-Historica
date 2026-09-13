"""Etapas 5 e 7 da cura visual.

Etapa 5: acabamento visual comum das telas da área Análise.
Etapa 7: acabamento visual de Resultados, Jogos do dia e histórico operacional.
Somente apresentação; consultas, cálculos, banco, auditoria e geração permanecem intactos.
"""
from __future__ import annotations

ANALYSIS_VERSION = "5.0"
ANALYSIS_INFO = {
    "stage": 5,
    "visual_only": True,
    "changes_meta": False,
    "changes_database": False,
    "changes_generators": False,
    "changes_methods": False,
}
TREE_BY_PAGE = {
    "search": "tree",
    "statistics": "stat_tree",
    "pulls": "pull_tree",
    "methods": "method_tree",
}

RESULTS_VERSION = "7.0"
RESULTS_INFO = {
    "stage": 7,
    "visual_only": True,
    "changes_database": False,
    "changes_audit": False,
    "changes_results": False,
    "changes_frozen_games": False,
    "changes_generators": False,
    "changes_methods": False,
}


def analysis_spec():
    return {"version": ANALYSIS_VERSION, "pages": tuple(TREE_BY_PAGE), "visual_only": True}


def results_spec():
    return {
        "version": RESULTS_VERSION,
        "pages": ("results", "games_day"),
        "visual_only": True,
    }


def configure_analysis_styles(app, central):
    style = central.ttk.Style(app)
    c = app.colors
    font = central.UI_FONT_FAMILY
    semi = central.UI_FONT_SEMIBOLD
    sizes = central.UI_FONT_SIZES
    style.configure("AnalysisCard.TFrame", background=c["card"], bordercolor=c["border"], borderwidth=1, relief="solid")
    style.configure("Analysis.Treeview", background=c["entry"], fieldbackground=c["entry"], foreground=c["text"], bordercolor=c["border"], borderwidth=1, relief="flat", font=(font, sizes["table"]), rowheight=max(30, int(central.UI_TABLE_ROWHEIGHT)))
    style.configure("Analysis.Treeview.Heading", background=c["card2"], foreground=c["text"], bordercolor=c["border"], font=(semi, sizes["table_heading"]), padding=(9, 8), relief="flat")
    style.map("Analysis.Treeview", background=[("selected", c["selection"])], foreground=[("selected", c["text"])])
    style.map("Analysis.Treeview.Heading", background=[("active", c["hover"])])
    style.configure("AnalysisPrimary.TButton", font=(semi, sizes["body"]), padding=(14, 8), background=c["accent"], foreground=central.UI_TEXT_ON_ACCENT, bordercolor=c["accent"], relief="flat")
    style.configure("AnalysisQuiet.TButton", font=(font, sizes["body"]), padding=(10, 6), background=c["card2"], foreground=c["muted"], bordercolor=c["border"], relief="flat")


def configure_results_styles(app, central):
    style = central.ttk.Style(app)
    c = app.colors
    font = central.UI_FONT_FAMILY
    semi = central.UI_FONT_SEMIBOLD
    sizes = central.UI_FONT_SIZES

    style.configure("ResultsCard.TFrame", background=c["card"], bordercolor=c["border"], borderwidth=1, relief="solid")
    style.configure("ResultsInset.TFrame", background=c["card2"], bordercolor=c["border"], borderwidth=1, relief="solid")
    style.configure("ResultsSection.TLabel", background=c["card"], foreground=c["text"], font=(semi, sizes["section"]))
    style.configure("ResultsKpi.TLabel", background=c["card"], foreground=c["text"], font=(semi, max(17, sizes["kpi"])))
    style.configure("ResultsKpiCaption.TLabel", background=c["card"], foreground=c["muted"], font=(semi, sizes["secondary"]))
    style.configure("ResultsMuted.TLabel", background=c["card"], foreground=c["muted"], font=(font, sizes["secondary"]))

    for name, color in (
        ("ResultsStatusSuccess.TLabel", c["success"]),
        ("ResultsStatusPending.TLabel", c["warning"]),
        ("ResultsStatusWarning.TLabel", c["warning"]),
        ("ResultsStatusDanger.TLabel", c["danger"]),
        ("ResultsStatusInfo.TLabel", c["accent_hover"]),
    ):
        style.configure(name, background=c["card"], foreground=color, font=(semi, sizes["secondary"]))

    style.configure("ResultsPrimary.TButton", font=(semi, sizes["body"]), padding=(14, 8), background=c["accent"], foreground=central.UI_TEXT_ON_ACCENT, bordercolor=c["accent"], relief="flat")
    style.map("ResultsPrimary.TButton", background=[("active", c["accent_hover"]), ("pressed", c["accent"])])
    style.configure("ResultsQuiet.TButton", font=(font, sizes["body"]), padding=(10, 6), background=c["card2"], foreground=c["muted"], bordercolor=c["border"], relief="flat")
    style.map("ResultsQuiet.TButton", background=[("active", c["hover"])], foreground=[("active", c["text"])])

    style.configure("Results.Treeview", background=c["entry"], fieldbackground=c["entry"], foreground=c["text"], bordercolor=c["border"], borderwidth=1, relief="flat", font=(font, sizes["table"]), rowheight=max(31, int(central.UI_TABLE_ROWHEIGHT)))
    style.configure("Results.Treeview.Heading", background=c["card2"], foreground=c["text"], bordercolor=c["border"], font=(semi, sizes["table_heading"]), padding=(9, 8), relief="flat")
    style.map("Results.Treeview", background=[("selected", c["selection"])], foreground=[("selected", c["text"])])
    style.map("Results.Treeview.Heading", background=[("active", c["hover"])])


def _read(widget, key):
    try:
        return str(widget.cget(key) or "")
    except Exception:
        return ""


def status_role(text):
    value = str(text or "").strip().upper()
    if not value:
        return None
    if any(token in value for token in ("FALHOU", "ERRO", "DERROTA", "CANCELADO")):
        return "danger"
    if any(token in value for token in ("AUDITADO", "CONCLUÍDO", "CONCLUIDO", "FECHADO", "VENCEU", "VENCEDOR", "POSITIVO", "PAGO")):
        return "success"
    if any(token in value for token in ("PENDENTE", "AGUARDANDO", "ABERTO", "SEM RESULTADO")):
        return "pending"
    if any(token in value for token in ("PARCIAL", "EM AUDITORIA", "AUDITANDO")):
        return "warning"
    if any(token in value for token in ("CONGELADO", "REGISTRADO")):
        return "info"
    return None


def results_button_role(text):
    value = str(text or "").strip().upper()
    if any(token in value for token in ("ATUALIZAR", "AUDITAR", "CONFERIR", "REGISTRAR", "SALVAR", "BUSCAR RESULTADO")):
        return "primary"
    if any(token in value for token in ("DETALH", "EXPORTAR", "COPIAR", "TÉCNIC", "TECNIC", "VOLTAR", "LIMPAR")):
        return "quiet"
    return "normal"


def polish_children(root):
    try:
        children = list(root.winfo_children())
    except Exception:
        return
    for child in children:
        try:
            kind = str(child.winfo_class() or "")
            current = _read(child, "style")
            text = _read(child, "text").upper()
            if kind == "TFrame" and current == "Card.TFrame":
                child.configure(style="AnalysisCard.TFrame", padding=(12, 10))
            elif kind == "TButton" and current not in {"Danger.TButton", "Primary.TButton", "Accent.TButton"}:
                if any(word in text for word in ("PESQUIS", "CALCULAR", "GERAR", "ATUALIZAR", "EXECUTAR", "APLICAR")):
                    child.configure(style="AnalysisPrimary.TButton")
                elif any(word in text for word in ("EXPORTAR", "LIMPAR", "DETALH", "TÉCNIC", "TECNIC", "VOLTAR")):
                    child.configure(style="AnalysisQuiet.TButton")
        except Exception:
            pass
        polish_children(child)


def _tag_results_tree(tree, app):
    c = app.colors
    try:
        tree.tag_configure("gph_success", foreground=c["success"])
        tree.tag_configure("gph_pending", foreground=c["warning"])
        tree.tag_configure("gph_warning", foreground=c["warning"])
        tree.tag_configure("gph_danger", foreground=c["danger"])
        tree.tag_configure("gph_info", foreground=c["accent_hover"])
        items = list(tree.get_children(""))
    except Exception:
        return

    for item in items:
        try:
            values = tree.item(item, "values") or ()
            role = status_role(" ".join(str(v) for v in values))
            if not role:
                continue
            tags = [x for x in (tree.item(item, "tags") or ()) if not str(x).startswith("gph_")]
            tags.append(f"gph_{role}")
            tree.item(item, tags=tuple(tags))
        except Exception:
            pass


def polish_results_children(root, app):
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
                    child.configure(style="ResultsCard.TFrame")
                elif current == "Card2.TFrame":
                    child.configure(style="ResultsInset.TFrame")
            elif kind == "Treeview":
                child.configure(style="Results.Treeview")
                _tag_results_tree(child, app)
            elif kind == "TLabel":
                role = status_role(text)
                if role:
                    child.configure(style=f"ResultsStatus{role.title()}.TLabel")
                elif current in {"CardTitle.TLabel", "Section.TLabel"}:
                    child.configure(style="ResultsSection.TLabel")
                elif current == "Kpi.TLabel":
                    child.configure(style="ResultsKpi.TLabel")
                elif current == "KpiCaption.TLabel":
                    child.configure(style="ResultsKpiCaption.TLabel")
                elif current == "CardMuted.TLabel":
                    child.configure(style="ResultsMuted.TLabel")
            elif kind == "TButton":
                role = results_button_role(text)
                if role == "primary" and current != "Danger.TButton":
                    child.configure(style="ResultsPrimary.TButton")
                elif role == "quiet" and current != "Danger.TButton":
                    child.configure(style="ResultsQuiet.TButton")
        except Exception:
            pass
        polish_results_children(child, app)


def polish_analysis_page(app, central, page_key):
    configure_analysis_styles(app, central)
    content = getattr(app, "content", None)
    if content is not None:
        polish_children(content)
    tree = getattr(app, TREE_BY_PAGE.get(page_key, ""), None)
    if tree is not None:
        try:
            tree.configure(style="Analysis.Treeview")
        except Exception:
            pass
    app._gph_analysis_page = page_key
    app._gph_analysis_polished = True
    central.GPH_UI_ANALYSIS_VERSION = ANALYSIS_VERSION
    return ANALYSIS_INFO


def polish_results_page(app, central, page_key):
    configure_results_styles(app, central)
    content = getattr(app, "content", None)
    if content is not None:
        polish_results_children(content, app)
    app._gph_results_page = page_key
    app._gph_results_polished = True
    central.GPH_UI_RESULTS_VERSION = RESULTS_VERSION
    return RESULTS_INFO
