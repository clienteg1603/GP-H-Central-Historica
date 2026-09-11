"""Recomendação operacional da próxima rodada — v0.48.2.

O último resultado disponível define apenas a base/estado atual e o próximo
alvo. A recomendação é escolhida em uma janela de até 90 dias anteriores,
comparando somente métodos que podem ser avaliados sem olhar o futuro.

Centena e Terno de Grupo são as únicas modalidades da disputa nesta fase.
O GP-H Meta histórico entra somente por Top 5 realmente congelado antes do
resultado. Esta camada não recalibra, retreina nem altera o cérebro Meta.
"""
from __future__ import annotations

import json
import threading
from datetime import date, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import gph_history_lab as lab

EVALUATION_DAYS = 90
MIN_CONTEXT_RECORDS = 8
STANDARD_CENTENAS = 20
STANDARD_TERNOS = 5

# Cada entrada abaixo precisa possuir um gerador operacional real na tela
# Jogar > Nova aposta. Não criamos uma modalidade apenas para fazê-la competir.
PLAY_MAPPING = {
    "Reset Cobertura": {
        "Centena": {
            "family": "Centena", "variant": "Normal", "kind": "Centena",
            "method": "Oficial • Reset + Lei GP-H", "quantity": STANDARD_CENTENAS,
        },
        "Terno de Grupo": {
            "family": "Grupo", "variant": "Terno", "kind": "Terno de Grupo",
            "method": "Oficial • Reset combinações", "quantity": STANDARD_TERNOS,
        },
    },
    "Puxada Combinada": {
        "Centena": {
            "family": "Centena", "variant": "Normal", "kind": "Centena",
            "method": "Experimental • Puxada Combinada", "quantity": STANDARD_CENTENAS,
        },
        "Terno de Grupo": {
            "family": "Grupo", "variant": "Terno", "kind": "Terno de Grupo",
            "method": "Experimental • Puxada Combinada", "quantity": STANDARD_TERNOS,
        },
    },
    "Similaridade": {
        "Centena": {
            "family": "Centena", "variant": "Normal", "kind": "Centena",
            "method": "Experimental • Similaridade do Dia", "quantity": STANDARD_CENTENAS,
        },
        "Terno de Grupo": {
            "family": "Grupo", "variant": "Terno", "kind": "Terno de Grupo",
            "method": "Experimental • Similaridade combinações", "quantity": STANDARD_TERNOS,
        },
    },
    "Histórico Concentrado": {
        "Terno de Grupo": {
            "family": "Grupo", "variant": "Fechamento", "kind": "Terno de Grupo",
            "method": "Histórico • Concentrado", "quantity": STANDARD_TERNOS,
            "apply_mode": "historical_concentrated_terno",
        },
    },
    "GP-H Meta v0.2": {
        "Centena": {
            "family": "Centena", "variant": "Normal", "kind": "Centena",
            "method": "★ META • GP-H Meta v0.2", "quantity": STANDARD_CENTENAS,
        },
        "Terno de Grupo": {
            "family": "Grupo", "variant": "Terno", "kind": "Terno de Grupo",
            "method": "★ META • GP-H Meta v0.2", "quantity": STANDARD_TERNOS,
        },
    },
}

LAB_SELECTORS = (
    "Reset Cobertura",
    "Puxada Combinada",
    "Similaridade",
    "Histórico Concentrado",
)


def _target_key(target):
    target = target or {}
    return (
        str(target.get("data") or ""),
        str(target.get("sorteio") or ""),
        str(target.get("hora") or ""),
    )


def _target_token(target):
    return "|".join(_target_key(target))


def _mean_hit(records, method):
    values = []
    for row in records:
        score = (row.get("scores") or {}).get(method)
        if score is None or score.get("hit") is None:
            continue
        values.append(float(score["hit"]))
    return (sum(values) / len(values), len(values)) if values else (None, 0)


def _context_records(report, target):
    """Prefere mesma extração+hora; com pouca amostra usa a mesma hora."""
    records = list((report or {}).get("records") or [])
    exact = [
        row for row in records
        if str((row.get("target") or {}).get("sorteio") or "") == str(target.get("sorteio") or "")
        and str((row.get("target") or {}).get("hora") or "") == str(target.get("hora") or "")
    ]
    if len(exact) >= MIN_CONTEXT_RECORDS:
        return exact, "mesma extração e horário"
    return records, "mesmo horário"


def candidates_from_report(selector, report, target):
    """Converte relatório causal em candidatos realmente jogáveis."""
    playable = PLAY_MAPPING.get(selector) or {}
    if not playable:
        return []
    records, context_label = _context_records(report, target)
    if not records:
        return []

    candidates = []
    specs = (
        ("Centena", lab.LAW, lab.CONDITIONAL_RANDOM),
        ("Terno de Grupo", lab.TERN_CURRENT, lab.TERN_RANDOM),
    )
    for kind, method_name, control_name in specs:
        if kind not in playable:
            continue
        rate, n = _mean_hit(records, method_name)
        control_rate, control_n = _mean_hit(records, control_name)
        if rate is None or control_rate is None or not n or not control_n:
            continue
        play = dict(playable[kind])
        candidates.append({
            "selector": selector,
            "kind": kind,
            "lab_method": method_name,
            "control": control_name,
            "rate": rate,
            "control_rate": control_rate,
            "gain": rate - control_rate,
            "n": min(n, control_n),
            "context": context_label,
            **play,
        })
    return candidates


def choose_recommendation(reports, target):
    """Escolhe o melhor par método × modalidade pelo ganho sobre seu controle.

    A régua de 50% do projeto NÃO participa desta função: não existe corte,
    peso, bônus ou alvo de calibração ligado a 50%.
    """
    candidates = []
    for selector, report in (reports or {}).items():
        candidates.extend(candidates_from_report(selector, report, target))
    if not candidates:
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
    if best["n"] < 12:
        best["confidence"] = "AMOSTRA CURTA"
    elif best["gain"] <= 0:
        best["confidence"] = "SEM GANHO SOBRE O CONTROLE"
    elif best["n"] >= 20 and best["gain"] >= 0.05:
        best["confidence"] = "SINAL HISTÓRICO MAIS FORTE"
    else:
        best["confidence"] = "SINAL HISTÓRICO POSITIVO"
    return best


def _load_frozen_meta_groups(db, start_day, end_day, target_hour):
    """Lê somente Top 5 Meta que já estava congelado antes do resultado.

    Não chama meta_shadow_prediction, meta_walk_forward ou qualquer rotina de
    treino. Linhas antigas sem meta_frozen_at ficam deliberadamente de fora.
    """
    con = db.connect()
    try:
        rows = con.execute(
            """
            SELECT target_data,target_sorteio,target_hora,meta_json,meta_frozen_at
            FROM decision_snapshots
            WHERE target_data BETWEEN ? AND ?
              AND target_hora=?
              AND meta_json IS NOT NULL AND TRIM(meta_json)<>''
              AND meta_frozen_at IS NOT NULL AND TRIM(meta_frozen_at)<>''
            ORDER BY target_data,target_hora,id
            """,
            (start_day, end_day, target_hour),
        ).fetchall()
    finally:
        con.close()

    mapping = {}
    rejected = 0
    for row in rows:
        try:
            meta = json.loads(row["meta_json"] or "{}")
        except Exception:
            rejected += 1
            continue
        if meta.get("available") is False:
            rejected += 1
            continue
        groups = []
        for raw in list(meta.get("groups") or [])[:5]:
            try:
                group = int(raw)
            except Exception:
                continue
            if 1 <= group <= 25 and group not in groups:
                groups.append(group)
        if len(groups) != 5:
            rejected += 1
            continue
        token = "|".join((str(row["target_data"]), str(row["target_sorteio"]), str(row["target_hora"])))
        mapping[token] = groups
    return mapping, {"frozen_rows": len(rows), "eligible_rows": len(mapping), "rejected_rows": rejected}


def evaluate_next_round(app):
    """Avalia a próxima rodada usando somente informação anterior ao alvo."""
    target = app.db.next_operational_target()
    latest = app.db.latest_operational_draw()
    if not target or not latest:
        raise ValueError("Não foi possível identificar a próxima rodada ou a última base disponível.")

    end_day = date.fromisoformat(str(latest["data"]))
    start_day = max(date(2026, 1, 2), end_day - timedelta(days=EVALUATION_DAYS - 1))
    reports = {}
    excluded = []

    for selector in LAB_SELECTORS:
        options = {
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "scope": "1º–5º",
            "selector": selector,
            "hour": str(target.get("hora") or ""),
        }
        try:
            report = lab.run_history(type(app.db), app.db.path, options)
        except Exception as exc:
            excluded.append({"method": selector, "reason": f"erro na avaliação causal: {exc}"})
            continue
        reports[selector] = report
        if not report.get("records"):
            reason = "sem rodadas comparáveis na janela de 90 dias"
            if selector == "Similaridade":
                reason += " com cinco grupos distintos"
            excluded.append({"method": selector, "reason": reason})

    frozen_meta, meta_diag = _load_frozen_meta_groups(
        app.db, start_day.isoformat(), end_day.isoformat(), str(target.get("hora") or "")
    )
    if frozen_meta:
        try:
            meta_report = lab.run_history(
                type(app.db), app.db.path,
                {
                    "start": start_day.isoformat(),
                    "end": end_day.isoformat(),
                    "scope": "1º–5º",
                    "selector": lab.FROZEN_SELECTOR,
                    "frozen_groups": frozen_meta,
                    "hour": str(target.get("hora") or ""),
                },
            )
            reports["GP-H Meta v0.2"] = meta_report
            if not meta_report.get("records"):
                excluded.append({"method": "GP-H Meta v0.2", "reason": "Top 5 congelados encontrados, mas sem rodada comparável válida"})
        except Exception as exc:
            excluded.append({"method": "GP-H Meta v0.2", "reason": f"histórico congelado não pôde ser auditado: {exc}"})
    else:
        excluded.append({
            "method": "GP-H Meta v0.2",
            "reason": "sem Top 5 Meta prospectivo congelado utilizável para este horário na janela",
        })

    # Seca do Dia é uma leitura exclusivamente de 1º prêmio; misturá-la com o
    # protocolo 1º–5º de Centena/Terno criaria uma comparação metodologicamente
    # desigual. Ela fica visível como excluída, não esquecida.
    excluded.append({
        "method": "Seca do Dia 1º",
        "reason": "fora da disputa: objetivo exclusivo de 1º prêmio, não comparável ao protocolo 1º–5º",
    })

    usable = {name: report for name, report in reports.items() if report.get("records")}
    recommendation = choose_recommendation(usable, target)
    recommendation.update({
        "target": dict(target),
        "base": {k: latest.get(k) for k in ("data", "sorteio", "hora")},
        "base_end": end_day.isoformat(),
        "window_start": start_day.isoformat(),
        "evaluation_days": EVALUATION_DAYS,
        "reports_used": sorted(usable),
        "excluded_methods": excluded,
        "meta_frozen_diagnostic": meta_diag,
        "lookahead_safe": True,
        "changes_meta": False,
        "fifty_percent_is_diagnostic_only": True,
    })
    return recommendation


def _pct(value):
    return f"{100.0 * float(value):.1f}%".replace(".", ",")


def _pp(value):
    return f"{100.0 * float(value):+.1f} p.p.".replace(".", ",")


def _format_target(app, target):
    try:
        return app._format_target(target)
    except Exception:
        return " • ".join(v for v in _target_key(target) if v)


def _find_target_label(app, target):
    wanted = _target_key(target)
    for label, item in (getattr(app, "play_target_map", {}) or {}).items():
        if _target_key(item) == wanted:
            return label
    return None


def _current_quantity(app, recommendation):
    if recommendation.get("apply_mode") == "historical_concentrated_terno":
        try:
            return max(1, int(str(app.play_hc_ternos.get()).strip()))
        except Exception:
            return int(recommendation["quantity"])
    try:
        return max(1, int(str(app.play_total.get()).strip()))
    except Exception:
        return int(recommendation["quantity"])


def _apply_recommendation(app, recommendation, keep_quantity=False):
    current_next = app.db.next_operational_target()
    if _target_key(current_next) != _target_key(recommendation.get("target")):
        raise ValueError("Entrou um resultado novo enquanto a avaliação estava aberta. Avalie a próxima rodada novamente.")

    label = _find_target_label(app, recommendation["target"])
    if label is None:
        raise ValueError("A próxima rodada não está mais disponível na lista da tela.")
    quantity = _current_quantity(app, recommendation) if keep_quantity else int(recommendation["quantity"])

    # O valor e o modo de valor digitados pelo usuário são preservados.
    app.play_target_var.set(label)
    app.play_scope.set("1º–5º")

    if recommendation.get("apply_mode") == "historical_concentrated_terno":
        app.play_family.set("Grupo")
        app.play_variant.set("Fechamento")
        app.play_kind.set("Fechamento de Grupo")
        app.play_method.set("Histórico • Concentrado")
        app.play_hc_base_animals.set("5")
        app.play_hc_duplas.set("0")
        app.play_hc_ternos.set(str(quantity))
        app.play_hc_quadras.set("0")
        app.play_hc_quinas.set("0")
    else:
        app.play_family.set(recommendation["family"])
        app.play_variant.set(recommendation["variant"])
        app.play_kind.set(recommendation["kind"])
        app.play_method.set(recommendation["method"])
        app.play_total.set(str(quantity))

    app.play_controls_changed()
    try:
        app.play_target_changed()
    except Exception:
        pass
    app.play_generate()


def _generation_rows_for_edit(generation):
    if not generation:
        return None, []
    if generation.get("historical_concentrated"):
        # A recomendação v0.48.2 configura o Fechamento Concentrado somente
        # com Ternos; portanto as linhas visíveis desse bundle são editadas
        # como Terno de Grupo, sem depender de estrutura interna do bundle.
        return "Terno de Grupo", list(generation.get("rows") or [])
    return str(generation.get("kind") or ""), list(generation.get("rows") or [])


def _edit_current_generation(app):
    generation = getattr(app, "play_generation", None)
    manual_kind, rows = _generation_rows_for_edit(generation)
    if not rows or not manual_kind:
        messagebox.showinfo("Editar palpites", "Gere os palpites da recomendação primeiro.", parent=app)
        return False
    numbers = [str(row.get("numero") or "").strip() for row in rows]
    numbers = [number for number in numbers if number]
    text = simpledialog.askstring(
        "Editar palpites antes de usar",
        "Altere, remova ou acrescente palpites separados por vírgula.\nNada é registrado até você adicionar ao bilhete.",
        initialvalue=", ".join(numbers),
        parent=app,
    )
    if text is None:
        return False

    scope = "1º–5º"
    edited = app.db.manual_generation(manual_kind, text, scope=scope)
    target = (generation or {}).get("intended_target") or app.play_get_selected_target()
    edited["intended_target"] = dict(target or {})
    edited["target_mode"] = "ALVO_ESPECIFICO"
    edited["strategy"] = "Manual"
    edited["selector"] = "Manual"
    edited["origem_jogada"] = "Manual • ajuste da recomendação"

    if manual_kind == "Terno de Grupo":
        app.play_family.set("Grupo")
        app.play_variant.set("Terno")
        app.play_kind.set("Terno de Grupo")
    else:
        app.play_family.set("Centena")
        app.play_variant.set("Normal")
        app.play_kind.set("Centena")
    app.play_method.set("Manual")
    app.play_total.set(str(len(edited.get("rows") or [])))
    app.play_controls_changed()
    app.play_generation = edited
    app.play_generation_groups = list(edited.get("groups") or [])
    app.play_render_generation()
    app.play_financial_refresh()
    return True


def _candidate_line(index, item):
    label = "Centena" if item["kind"] == "Centena" else "Terno"
    return (
        f"{index}) {item['selector']} → {label} • acerto {_pct(item['rate'])} • "
        f"controle {_pct(item['control_rate'])} • Δ {_pp(item['gain'])} • n={item['n']}"
    )


def _build_advisor_card(app):
    body = getattr(app, "play_body", None)
    if body is None:
        return

    app._round_advisor_recommendation = None
    card = ttk.Frame(body, style="Card.TFrame", padding=(12, 10))
    children = list(body.winfo_children())
    pack_args = {"fill": "x", "pady": (0, 6)}
    if children:
        pack_args["before"] = children[0]
    card.pack(**pack_args)
    app._round_advisor_card = card

    head = ttk.Frame(card, style="Card.TFrame")
    head.pack(fill="x")
    ttk.Label(head, text="RECOMENDAÇÃO DA PRÓXIMA RODADA", style="Section.TLabel").pack(side="left")
    ttk.Label(head, text="v0.48.2 • até 90 dias • sem look-ahead", style="CardMuted.TLabel").pack(side="right")

    intro = ttk.Label(
        card,
        text=(
            "O último resultado define o estado atual e o próximo horário. A Central então compara os métodos "
            "com histórico causal válido e decide entre Centena e Terno de Grupo."
        ),
        style="CardMuted.TLabel", wraplength=1050, justify="left",
    )
    intro.pack(fill="x", anchor="w", pady=(4, 7))

    status = ttk.Label(card, text="Pronto para avaliar a próxima rodada.", style="Card.TLabel", wraplength=1050, justify="left")
    status.pack(fill="x", anchor="w", pady=(0, 3))
    details = ttk.Label(
        card,
        text="Quantidade e Valor continuam editáveis. A régua de 50% não participa da escolha.",
        style="CardMuted.TLabel", wraplength=1050, justify="left",
    )
    details.pack(fill="x", anchor="w", pady=(0, 4))
    ranking_label = ttk.Label(card, text="", style="CardMuted.TLabel", wraplength=1050, justify="left")
    ranking_label.pack(fill="x", anchor="w", pady=(0, 7))

    actions = ttk.Frame(card, style="Card.TFrame")
    actions.pack(fill="x")
    recalc_btn = ttk.Button(actions, text="RECALCULAR JOGOS", state="disabled")
    edit_btn = ttk.Button(actions, text="EDITAR PALPITES", state="disabled")

    def set_busy(busy):
        try:
            if busy:
                eval_btn.state(["disabled"]); recalc_btn.state(["disabled"]); edit_btn.state(["disabled"])
            else:
                eval_btn.state(["!disabled"])
                if app._round_advisor_recommendation:
                    recalc_btn.state(["!disabled"])
                    if getattr(app, "play_generation", None):
                        edit_btn.state(["!disabled"])
        except tk.TclError:
            pass

    def render_recommendation(rec, prefix="Recomendado e gerado"):
        target_text = _format_target(app, rec.get("target"))
        quantity = _current_quantity(app, rec)
        status.configure(text=(
            f"{prefix}: {rec['selector']} → {rec['kind']} • {quantity} palpites\n"
            f"Alvo: {target_text} • {rec['confidence']}"
        ))
        details.configure(text=(
            f"Histórico usado: {rec['n']} rodadas ({rec['context']}) • acerto {_pct(rec['rate'])} • "
            f"controle equivalente {_pct(rec['control_rate'])} • diferença {_pp(rec['gain'])}. "
            "O desempenho mostrado refere-se ao padrão testado de 20 Centenas ou 5 Ternos."
        ))
        ordered = [rec] + list(rec.get("alternatives") or [])[:4]
        lines = ["RANKING DA DISPUTA"] + [_candidate_line(i, item) for i, item in enumerate(ordered, 1)]
        excluded = list(rec.get("excluded_methods") or [])
        if excluded:
            brief = " • ".join(f"{x['method']}: {x['reason']}" for x in excluded[:5])
            lines += ["", "FORA DA COMPARAÇÃO: " + brief]
        ranking_label.configure(text="\n".join(lines))

    def finish_ok(rec):
        try:
            if not card.winfo_exists():
                return
            app._round_advisor_recommendation = rec
            _apply_recommendation(app, rec, keep_quantity=False)
            render_recommendation(rec)
            recalc_btn.state(["!disabled"]); edit_btn.state(["!disabled"])
        except Exception as exc:
            status.configure(text="A avaliação terminou, mas os jogos não puderam ser aplicados automaticamente.")
            details.configure(text=str(exc))
        finally:
            set_busy(False)

    def finish_error(exc):
        try:
            if not card.winfo_exists():
                return
            status.configure(text="Não foi possível concluir a avaliação desta rodada.")
            details.configure(text=str(exc))
            ranking_label.configure(text="")
        finally:
            set_busy(False)

    def worker():
        try:
            rec = evaluate_next_round(app)
        except Exception as exc:
            try: app.after(0, lambda exc=exc: finish_error(exc))
            except Exception: pass
            return
        try: app.after(0, lambda rec=rec: finish_ok(rec))
        except Exception: pass

    def evaluate():
        status.configure(text="Avaliando o próximo horário em todos os métodos com histórico válido…")
        details.configure(text="Janela de até 90 dias; cada previsão histórica usa somente resultados anteriores ao próprio alvo.")
        ranking_label.configure(text="")
        set_busy(True)
        threading.Thread(target=worker, name="gph-round-advisor-v0482", daemon=True).start()

    def recalculate():
        rec = app._round_advisor_recommendation
        if not rec:
            return
        try:
            _apply_recommendation(app, rec, keep_quantity=True)
            render_recommendation(rec, prefix="Jogos recalculados")
            edit_btn.state(["!disabled"])
        except Exception as exc:
            messagebox.showerror("Recalcular jogos", str(exc), parent=app)

    def edit():
        try:
            if _edit_current_generation(app):
                status.configure(text="Palpites editados manualmente. Revise quantidade/valor antes de adicionar ao bilhete.")
                details.configure(text="RECALCULAR JOGOS restaura a geração do método recomendado para a quantidade atual.")
        except Exception as exc:
            messagebox.showerror("Editar palpites", str(exc), parent=app)

    eval_btn = ttk.Button(actions, text="AVALIAR PRÓXIMA RODADA", style="Accent.TButton", command=evaluate)
    eval_btn.pack(side="left", padx=(0, 6))
    recalc_btn.configure(command=recalculate); recalc_btn.pack(side="left", padx=(0, 6))
    edit_btn.configure(command=edit); edit_btn.pack(side="left")


def install_round_advisor(central_module):
    """Instala a extensão sem substituir Database, geradores ou cérebro Meta."""
    app_class = central_module.App
    if getattr(app_class, "_round_advisor_v0482_installed", False):
        return
    original = app_class.play_show_new

    def play_show_new_with_advisor(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        try:
            _build_advisor_card(self)
        except Exception:
            pass
        return result

    app_class.play_show_new = play_show_new_with_advisor
    app_class._round_advisor_v0482_installed = True
