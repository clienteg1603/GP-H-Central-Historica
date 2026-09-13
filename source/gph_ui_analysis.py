"""Etapa 5 da cura visual das telas de análise."""
from __future__ import annotations

ANALYSIS_VERSION = "5.0"
ANALYSIS_INFO = {"stage": 5, "visual_only": True, "changes_meta": False, "changes_database": False, "changes_generators": False, "changes_methods": False}

PAGE_SPECS = {
    "search": ("show_search", "tree"),
    "statistics": ("show_statistics_page", "stat_tree"),
    "pulls": ("show_pulls_page", "pull_tree"),
    "methods": ("show_methods_page", "method_tree"),
}


def analysis_spec():
    return {"version": ANALYSIS_VERSION, "pages": tuple(PAGE_SPECS), "visual_only": True}
