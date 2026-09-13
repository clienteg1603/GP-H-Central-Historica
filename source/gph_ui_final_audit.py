"""Etapa 10 da cura visual: auditoria final e endurecimento de regressões.

Esta camada fecha a cura visual sem redesenhar páginas novamente. Ela consolida
os contratos visuais das etapas anteriores, aplica somente pequenos ajustes de
consistência e registra um diagnóstico em tempo de execução. Não altera banco,
Meta, métodos, geradores, auditoria de apostas ou lógica financeira.
"""
from __future__ import annotations

from gph_ui_foundation import COMBOBOX_POPUP_NATIVE, DIALOG_INFO

FINAL_AUDIT_VERSION = "10.0"
FINAL_AUDIT_INFO = {
    "stage": 10,
    "visual_only": True,
    "changes_meta": False,
    "changes_database": False,
    "changes_generators": False,
    "changes_methods": False,
    "changes_financial": False,
    "changes_round_audit": False,
}

FINAL_CONTENT_PADDING = (20, 14, 20, 12)


def _safe_style_map(style, name, **kwargs):
    try:
        style.map(name, **kwargs)
    except Exception:
        pass


def runtime_audit(app, central):
    """Retorna um retrato pequeno dos contratos visuais críticos da cura."""
    checks = {
        "stage10_visual_only": bool(FINAL_AUDIT_INFO["visual_only"]),
        "combobox_popup_native": bool(COMBOBOX_POPUP_NATIVE),
        "dialog_runtime_hook_disabled": not bool(DIALOG_INFO.get("runtime_polish_enabled", True)),
        "no_dialog_map_binding": not bool(getattr(app, "_gph_dialog_binding_installed", False)),
        "navigation_installed": bool(getattr(central.App, "_gph_ui_navigation_installed", False)),
        "results_polish_installed": bool(getattr(central.App, "_gph_ui_results_installed", False)),
        "content_exists": getattr(app, "content", None) is not None,
    }
    checks["passed"] = all(checks.values())
    return checks


def apply_final_audit(app, central):
    """Aplica apenas ajustes finais seguros e grava o diagnóstico da Etapa 10."""
    content = getattr(app, "content", None)
    if content is not None:
        try:
            content.configure(padding=FINAL_CONTENT_PADDING)
        except Exception:
            pass

    # Estados de foco/desabilitado ficam coerentes sem tocar no popup interno
    # dos Combobox. O menu suspenso continua integralmente nativo do Windows/Tk.
    try:
        style = central.ttk.Style(app)
        c = app.colors
        _safe_style_map(style, "TButton", foreground=[("disabled", c["muted"])])
        _safe_style_map(style, "Primary.TButton", foreground=[("disabled", c["muted"])])
        _safe_style_map(style, "Secondary.TButton", foreground=[("disabled", c["muted"])])
        _safe_style_map(
            style,
            "TCombobox",
            fieldbackground=[("readonly", c["entry"])],
            foreground=[("readonly", c["text"])],
        )
    except Exception:
        pass

    audit = runtime_audit(app, central)
    app._gph_final_visual_audit = audit
    central.GPH_UI_FINAL_AUDIT_VERSION = FINAL_AUDIT_VERSION
    return FINAL_AUDIT_INFO
