"""Etapa 5: acabamento visual comum das telas da área Análise.

Somente apresentação; consultas, métodos, cálculos, banco e Meta permanecem intactos.
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


def analysis_spec():
    return {"version": ANALYSIS_VERSION, "pages": tuple(TREE_BY_PAGE), "visual_only": True}


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


def _read(widget, key):
    try:
        return str(widget.cget(key) or "")
    except Exception:
        return ""


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
