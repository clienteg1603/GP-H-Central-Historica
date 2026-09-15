"""Guias de leitura da Decisão — v0.48.26.

Camada exclusivamente visual. Acrescenta explicações curtas às etapas 2, 3 e 4
e simplifica alguns títulos técnicos exibidos, sem alterar cálculo, Meta, banco,
métodos, auditorias, laboratórios, snapshots, congelamentos ou geradores.
"""
from __future__ import annotations

from gph_meta_lab import meta_lab_report
from gph_meta_review import meta_structural_review

DECISION_GUIDES_VERSION = "1.0"

DECISION_GUIDES_INFO = {
    "version": DECISION_GUIDES_VERSION,
    "visual_only": True,
    "changes_meta": False,
    "changes_weights": False,
    "changes_scores": False,
    "changes_database": False,
    "changes_generators": False,
    "changes_methods": False,
    "changes_audit": False,
    "changes_lab": False,
    "changes_freeze": False,
}

TITLE_REPLACEMENTS = {
    "DECISÃO ADAPTATIVA — ETAPA C": "AJUSTE ADAPTATIVO · TÉCNICO",
    "RECOMENDAÇÃO OPERACIONAL — ETAPA D": "RECOMENDAÇÃO OPERACIONAL",
    "CALIBRAÇÃO DA CONFIANÇA — ETAPA B": "CALIBRAÇÃO DA CONFIANÇA · TÉCNICO",
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


def _guide_card(central, body, title, subtitle, lines):
    card = central.ttk.Frame(body, style="Card.TFrame", padding=11)
    card.pack(fill="x", pady=(0, 8))
    head = central.ttk.Frame(card, style="Card.TFrame")
    head.pack(fill="x")
    central.ttk.Label(head, text=title, style="CardTitle.TLabel").pack(side="left")
    central.ttk.Label(head, text=subtitle, style="CardMuted.TLabel").pack(side="right")
    for idx, text in enumerate(lines):
        central.ttk.Label(
            card,
            text=text,
            style="Card.TLabel" if idx == 0 else "CardMuted.TLabel",
            wraplength=1250,
            justify="left",
        ).pack(anchor="w", pady=((7 if idx == 0 else 3), 0))
    return card


def _build_understand_guide(central, body):
    return _guide_card(
        central,
        body,
        "ETAPA 2 · ENTENDER A DECISÃO",
        "explicação • não muda o palpite",
        (
            "Leia esta etapa na ordem: método favorecido → confiança → motivo da vantagem → histórico que sustenta a leitura.",
            "Índice = força relativa da evidência entre métodos. Vantagem = distância em pontos entre os primeiros colocados. Nenhum dos dois é porcentagem de chance de prêmio.",
            "Ajuste adaptativo é uma correção pequena e conservadora baseada apenas em auditorias anteriores; quando ainda está em formação, a decisão-base é preservada.",
        ),
    )


def _tracking_snapshot(app):
    try:
        review = meta_structural_review(app.db) or {}
    except Exception:
        review = {}
    try:
        lab = meta_lab_report(app.db) or {}
    except Exception:
        lab = {}
    return review, lab


def _build_tracking_guide(app, central, body):
    review, lab = _tracking_snapshot(app)
    n = int(review.get("n") or 0)
    coverage = review.get("coverage_avg")
    rate2 = review.get("rate2")
    rnd = review.get("random_avg")
    rnd2 = review.get("random_rate2")
    diagnosis = review.get("decision") or "AGUARDANDO AMOSTRA"
    prospective = int(lab.get("prospective_n") or 0)
    lab_status = lab.get("status") or "AGUARDANDO"

    quick = (
        f"Leitura rápida: {n} rodada(s) Meta • cobertura {_num(coverage)}/5 vs acaso {_num(rnd)}/5 • "
        f"Taxa 2+ {_pct(rate2)} vs acaso ~{_pct(rnd2)} • diagnóstico {diagnosis}."
    )
    lab_line = f"Meta Lab: {lab_status} • {prospective} rodada(s) prospectiva(s) após o baseline."
    return _guide_card(
        central,
        body,
        "ETAPA 3 · ACOMPANHAR O QUE FUNCIONA",
        "resultado real • prospectivo",
        (
            quick,
            "Os quatro números mais importantes aqui são: Cobertura do Meta, Taxa 2+, comparação com o acaso e desempenho prospectivo do Meta Lab.",
            lab_line,
            "Rank 6–10 e Consenso perdido são diagnósticos de fronteira: ajudam a descobrir se o Meta identifica bons candidatos, mas corta os bichos errados na hora de formar o Top 5.",
        ),
    )


def _build_test_guide(central, body):
    return _guide_card(
        central,
        body,
        "ETAPA 4 · TESTAR SEM MEXER NO OFICIAL",
        "laboratório • isolado",
        (
            "Tudo nesta etapa é experimental: serve para comparar ideias antes de qualquer mudança no método oficial.",
            "Laboratório Sombra congela leituras antes do resultado. Pesquisa Histórica testa regras no passado com proteção contra olhar o futuro.",
            "Nenhum experimento desta área vira aposta, troca o Meta ou é promovido automaticamente. Uma mudança só deve sair daqui depois de validação fora da amostra e decisão explícita.",
        ),
    )


def _simplify_visible_titles(app):
    root = getattr(app, "content", None)
    if root is None:
        return

    def walk(widget):
        try:
            children = list(widget.winfo_children())
        except Exception:
            return
        for child in children:
            try:
                text = str(child.cget("text") or "")
                replacement = TITLE_REPLACEMENTS.get(text)
                if replacement:
                    child.configure(text=replacement)
            except Exception:
                pass
            walk(child)

    walk(root)


def install_decision_guides(central):
    app_cls = central.App
    if getattr(app_cls, "_gph_decision_guides_v04826_installed", False):
        return DECISION_GUIDES_INFO

    original_contextual = app_cls._decision_build_contextual
    original_coverage = app_cls._decision_build_coverage_evolution
    original_lab = app_cls._build_shadow_lab_section
    original_show = app_cls.show_decision_page

    def contextual(self, body, snapshot):
        if getattr(self, "decision_view", None) == "analysis":
            _build_understand_guide(central, body)
        return original_contextual(self, body, snapshot)

    def coverage(self, body, *args, **kwargs):
        if getattr(self, "decision_view", None) == "audit":
            _build_tracking_guide(self, central, body)
        return original_coverage(self, body, *args, **kwargs)

    def lab(self, body, *args, **kwargs):
        if getattr(self, "decision_view", None) == "lab":
            _build_test_guide(central, body)
        return original_lab(self, body, *args, **kwargs)

    def show(self, *args, **kwargs):
        result = original_show(self, *args, **kwargs)
        try:
            _simplify_visible_titles(self)
        except Exception as exc:
            self._gph_decision_guides_error = str(exc)
        return result

    app_cls._decision_build_contextual = contextual
    app_cls._decision_build_coverage_evolution = coverage
    app_cls._build_shadow_lab_section = lab
    app_cls.show_decision_page = show
    app_cls._gph_decision_guides_v04826_installed = True
    central.GPH_UI_DECISION_GUIDES_VERSION = DECISION_GUIDES_VERSION
    return DECISION_GUIDES_INFO
