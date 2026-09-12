"""Proteção de amostra mínima para a Recomendação da Próxima Rodada — v0.48.4.

Esta camada não altera nenhum seletor, cérebro Meta, peso, score ou gerador.
Ela atua somente na comparação operacional: candidatos com menos de oito
rodadas válidas ficam visíveis como amostra insuficiente, mas não podem vencer
o ranking. A régua de 50% continua exclusivamente diagnóstica.
"""
from __future__ import annotations

MIN_RANKING_SAMPLE = 8


def install_round_advisor_guard(advisor, app_version):
    if getattr(advisor, "_round_advisor_guard_v0484_installed", False):
        return

    original_candidates = advisor.candidates_from_report
    original_evaluate = advisor.evaluate_next_round
    original_build_card = advisor._build_advisor_card

    def choose_recommendation(reports, target):
        candidates = []
        short = []
        for selector, report in (reports or {}).items():
            for item in original_candidates(selector, report, target):
                row = dict(item)
                if int(row.get("n") or 0) < MIN_RANKING_SAMPLE:
                    short.append(row)
                else:
                    candidates.append(row)

        if not candidates:
            if short:
                raise ValueError(
                    "Os métodos possuem histórico causal, mas nenhum atingiu o mínimo de "
                    f"{MIN_RANKING_SAMPLE} rodadas válidas para participar da recomendação."
                )
            raise ValueError("Nenhum método produziu amostra causal comparável para esta rodada.")

        candidates.sort(
            key=lambda item: (
                float(item["gain"]),
                float(item["rate"]),
                int(item["n"]),
                1 if item["kind"] == "Centena" else 0,
                str(item["selector"]),
            ),
            reverse=True,
        )
        best = dict(candidates[0])
        best["alternatives"] = [dict(item) for item in candidates[1:]]
        best["sample_exclusions"] = [dict(item) for item in short]
        best["minimum_ranking_sample"] = MIN_RANKING_SAMPLE

        if best["n"] < 12:
            best["confidence"] = "AMOSTRA CURTA"
        elif best["gain"] <= 0:
            best["confidence"] = "SEM GANHO SOBRE O CONTROLE"
        elif best["n"] >= 20 and best["gain"] >= 0.05:
            best["confidence"] = "SINAL HISTÓRICO MAIS FORTE"
        else:
            best["confidence"] = "SINAL HISTÓRICO POSITIVO"
        return best

    def evaluate_next_round(app):
        rec = original_evaluate(app)
        excluded = list(rec.get("excluded_methods") or [])
        for row in rec.pop("sample_exclusions", []) or []:
            label = "Centena" if row.get("kind") == "Centena" else "Terno"
            n = int(row.get("n") or 0)
            excluded.append({
                "method": f"{row.get('selector', 'Método')} → {label}",
                "reason": (
                    f"amostra insuficiente — {n} rodada{'s' if n != 1 else ''} válida"
                    f"{'s' if n != 1 else ''}; mínimo {MIN_RANKING_SAMPLE} para disputar"
                ),
            })
        rec["excluded_methods"] = excluded
        rec["minimum_ranking_sample"] = MIN_RANKING_SAMPLE
        rec["changes_meta"] = False
        rec["fifty_percent_is_diagnostic_only"] = True
        return rec

    def build_advisor_card(app):
        # A etiqueta antiga era literal "v0.48.2". Interceptamos apenas essa
        # criação de Label para exibir a versão efetiva sem reescrever o módulo
        # histórico inteiro.
        original_label = advisor.ttk.Label

        def label_proxy(*args, **kwargs):
            if str(kwargs.get("text") or "").startswith("v0.48.2 •"):
                kwargs["text"] = f"v{app_version} • até 90 dias • mínimo {MIN_RANKING_SAMPLE} • sem look-ahead"
            return original_label(*args, **kwargs)

        advisor.ttk.Label = label_proxy
        try:
            return original_build_card(app)
        finally:
            advisor.ttk.Label = original_label

    advisor.choose_recommendation = choose_recommendation
    advisor.evaluate_next_round = evaluate_next_round
    advisor._build_advisor_card = build_advisor_card
    advisor.MIN_RANKING_SAMPLE = MIN_RANKING_SAMPLE
    advisor._round_advisor_guard_v0484_installed = True
