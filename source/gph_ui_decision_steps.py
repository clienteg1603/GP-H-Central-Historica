"""Decisão em 4 etapas — v0.48.25.

Camada exclusivamente visual. Simplifica o Resumo para uso diário e renomeia
as quatro visões existentes sem alterar qualquer cálculo, snapshot, Meta,
método, auditoria, laboratório ou gerador.
"""
from __future__ import annotations

from copy import deepcopy

from gph_meta_lab import meta_lab_report
from gph_meta_review import meta_structural_review

DECISION_STEPS_VERSION = "1.0"
STEP_LABELS = {
    "summary": "1 · Agora",
    "analysis": "2 · Entender",
    "audit": "3 · Acompanhar",
    "lab": "4 · Testar",
}

DECISION_STEPS_INFO = {
    "version": DECISION_STEPS_VERSION,
    "visual_only": True,
    "changes_meta": False,
    "changes_weights": False,
    "changes_scores": False,
    "changes_database": False,
    "changes_generators": False,
    "changes_methods": False,
    "changes_audit": False,
    "changes_lab": False,
}


def _pct(value):
    try:
        return f"{100.0 * float(value):.1f}%".replace(".", ",")
    except Exception:
        return "—"


def _num(value):
    try:
        return f"{float(value):.2f}".replace(".", ",")
    except Exception:
        return "—"


def _groups(values, limit=5):
    out = []
    for raw in values or []:
        if isinstance(raw, dict):
            raw = raw.get("grupo")
        try:
            group = int(raw)
        except Exception:
            continue
        if 1 <= group <= 25 and group not in out:
            out.append(group)
        if len(out) >= limit:
            break
    return out


def build_quick_summary_data(snapshot, review=None, lab=None):
    """Transforma dados já calculados em uma leitura curta, sem recalcular decisão."""
    snap = deepcopy(snapshot or {})
    contextual = snap.get("contextual") or {}
    operational = contextual.get("operational") or {}
    meta = snap.get("meta") or {}
    review = deepcopy(review or {})
    lab = deepcopy(lab or {})

    rows = []
    for item in contextual.get("rows") or []:
        if not isinstance(item, dict):
            continue
        method = item.get("method") or item.get("name")
        if not method:
            continue
        try:
            index = float(item.get("index"))
        except Exception:
            index = None
        rows.append({"method": str(method), "index": index})
    rows.sort(key=lambda item: (-(item["index"] if item["index"] is not None else -9999), item["method"]))

    return {
        "headline": operational.get("headline") or "EVIDÊNCIA INSUFICIENTE",
        "reference": operational.get("reference_leader") or contextual.get("evidence_leader") or "—",
        "confidence": operational.get("confidence") or contextual.get("status") or "—",
        "lead": float(operational.get("lead") or contextual.get("lead") or 0.0),
        "reason": operational.get("reason") or contextual.get("recommendation") or "",
        "top5": _groups(meta.get("groups"), 5),
        "meta_status": meta.get("status") or ("CONGELADO" if meta else "AGUARDANDO"),
        "context_rows": rows[:3],
        "review_n": int(review.get("n") or 0),
        "coverage": review.get("coverage_avg"),
        "rate2": review.get("rate2"),
        "random_avg": review.get("random_avg"),
        "random_rate2": review.get("random_rate2"),
        "review_decision": review.get("decision") or "—",
        "lab_status": lab.get("status") or "—",
        "lab_baseline": int(lab.get("baseline_n") or 0),
        "lab_prospective": int(lab.get("prospective_n") or 0),
    }


def _animal_text(central, groups):
    names = getattr(central, "BICHOS", {}) or {}
    out = []
    for group in groups or []:
        name = names.get(group) if hasattr(names, "get") else None
        out.append(f"{name} ({group:02d})" if name else f"Grupo {group:02d}")
    return "  •  ".join(out) if out else "Aguardando congelamento do Meta"


def _rename_step_buttons(app):
    root = getattr(app, "content", None)
    if root is None:
        return
    old_to_new = {
        "Resumo": STEP_LABELS["summary"],
        "Análise": STEP_LABELS["analysis"],
        "Auditoria": STEP_LABELS["audit"],
        "Laboratório": STEP_LABELS["lab"],
    }

    def walk(widget):
        try:
            children = list(widget.winfo_children())
        except Exception:
            return
        for child in children:
            try:
                if str(child.winfo_class() or "") == "TButton":
                    text = str(child.cget("text") or "")
                    if text in old_to_new:
                        child.configure(text=old_to_new[text])
            except Exception:
                pass
            walk(child)

    walk(root)


def _build_summary_operational(app, body, snapshot, central):
    try:
        review = meta_structural_review(app.db)
    except Exception:
        review = {}
    try:
        lab = meta_lab_report(app.db)
    except Exception:
        lab = {}
    data = build_quick_summary_data(snapshot, review, lab)

    card = central.ttk.Frame(body, style="Card.TFrame", padding=12)
    card.pack(fill="x", pady=(0, 8))
    top = central.ttk.Frame(card, style="Card.TFrame")
    top.pack(fill="x")
    central.ttk.Label(top, text="ETAPA 1 · O QUE IMPORTA AGORA", style="CardTitle.TLabel").pack(side="left")
    central.ttk.Label(top, text="leitura rápida • sem esconder os detalhes", style="CardMuted.TLabel").pack(side="right")

    try:
        target = app._decision_target_text(snapshot)
    except Exception:
        target = "Próxima rodada"
    central.ttk.Label(card, text=target, style="CardMuted.TLabel").pack(anchor="w", pady=(7, 1))
    central.ttk.Label(card, text=str(data["headline"]), style="Kpi.TLabel").pack(anchor="w", pady=(0, 8))

    kpis = central.ttk.Frame(card, style="Card.TFrame")
    kpis.pack(fill="x", pady=(0, 8))
    defs = (
        ("MÉTODO", data["reference"]),
        ("CONFIANÇA", data["confidence"]),
        ("VANTAGEM", f"{data['lead']:+.1f} pts"),
        ("META LAB", f"{data['lab_prospective']} prospectiva(s)"),
    )
    for idx, (title, value) in enumerate(defs):
        box = central.ttk.Frame(kpis, style="Card2.TFrame", padding=8)
        box.pack(side="left", fill="x", expand=True, padx=(0, 6 if idx < len(defs)-1 else 0))
        central.ttk.Label(box, text=title, style="KpiCaption.TLabel").pack(anchor="w")
        central.ttk.Label(box, text=str(value), style="Card.TLabel").pack(anchor="w", pady=(2, 0))

    central.ttk.Label(card, text="TOP 5 META OFICIAL CONGELADO", style="KpiCaption.TLabel").pack(anchor="w")
    central.ttk.Label(card, text=_animal_text(central, data["top5"]), style="Card.TLabel", wraplength=1200).pack(anchor="w", pady=(2, 8))

    health = central.ttk.Frame(card, style="Card2.TFrame", padding=9)
    health.pack(fill="x", pady=(0, 7))
    health_text = (
        f"Saúde do Meta • {data['review_n']} rodada(s) • cobertura {_num(data['coverage'])}/5 "
        f"(acaso {_num(data['random_avg'])}/5) • Taxa 2+ {_pct(data['rate2'])} "
        f"(acaso ~{_pct(data['random_rate2'])}) • diagnóstico: {data['review_decision']}."
    )
    central.ttk.Label(health, text=health_text, style="CardMuted.TLabel", wraplength=1250, justify="left").pack(anchor="w")
    central.ttk.Label(
        health,
        text=f"Meta Lab: {data['lab_status']} • baseline {data['lab_baseline']} • prospectivo {data['lab_prospective']}.",
        style="CardMuted.TLabel", wraplength=1250, justify="left",
    ).pack(anchor="w", pady=(3, 0))

    if data["reason"]:
        central.ttk.Label(card, text=str(data["reason"]), style="CardMuted.TLabel", wraplength=1250, justify="left").pack(anchor="w")
    central.ttk.Label(
        card,
        text="Para entender os números, use 2 · Entender. Para acompanhar desempenho real, use 3 · Acompanhar. Experimentos ficam em 4 · Testar.",
        style="CardMuted.TLabel", wraplength=1250,
    ).pack(anchor="w", pady=(6, 0))


def _build_summary_context(app, body, snapshot, central):
    data = build_quick_summary_data(snapshot)
    card = central.ttk.Frame(body, style="Card.TFrame", padding=10)
    card.pack(fill="x", pady=(0, 8))
    central.ttk.Label(card, text="POR QUE ESSA LEITURA?", style="CardTitle.TLabel").pack(anchor="w")
    rows = data.get("context_rows") or []
    if not rows:
        text = "Ainda não há comparação contextual suficiente para resumir."
    else:
        parts = []
        for row in rows:
            index = "—" if row["index"] is None else f"{row['index']:.1f}"
            parts.append(f"{row['method']} {index}")
        text = "  •  ".join(parts)
    central.ttk.Label(card, text=text, style="Card.TLabel", wraplength=1200).pack(anchor="w", pady=(5, 2))
    central.ttk.Label(
        card,
        text="Esses índices só ordenam a força relativa da evidência. Eles NÃO são porcentagem de chance de prêmio.",
        style="CardMuted.TLabel", wraplength=1200,
    ).pack(anchor="w")


def install_decision_steps(central):
    """Instala a organização em etapas sobre a tela existente."""
    app_cls = central.App
    if getattr(app_cls, "_gph_decision_steps_v04825_installed", False):
        return DECISION_STEPS_INFO

    original_operational = app_cls._decision_build_operational
    original_contextual = app_cls._decision_build_contextual
    original_show = app_cls.show_decision_page

    def operational(self, body, snapshot):
        if getattr(self, "decision_view", None) == "summary":
            return _build_summary_operational(self, body, snapshot, central)
        return original_operational(self, body, snapshot)

    def contextual(self, body, snapshot):
        if getattr(self, "decision_view", None) == "summary":
            return _build_summary_context(self, body, snapshot, central)
        return original_contextual(self, body, snapshot)

    def show(self, *args, **kwargs):
        result = original_show(self, *args, **kwargs)
        try:
            _rename_step_buttons(self)
        except Exception as exc:
            self._gph_decision_steps_error = str(exc)
        return result

    app_cls._decision_build_operational = operational
    app_cls._decision_build_contextual = contextual
    app_cls.show_decision_page = show
    app_cls._gph_decision_steps_v04825_installed = True
    central.GPH_UI_DECISION_STEPS_VERSION = DECISION_STEPS_VERSION
    return DECISION_STEPS_INFO
