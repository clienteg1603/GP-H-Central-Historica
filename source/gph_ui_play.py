"""Etapa 4 da cura visual: Jogar / Nova aposta.

Apresentação somente. Não altera métodos, Meta, banco, critérios de decisão
ou geradores. Substitui apenas o cartão visual do assistente da próxima rodada.
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox

PLAY_POLISH_INFO = {
    "stage": 4,
    "visual_only": True,
    "changes_meta": False,
    "changes_database": False,
    "changes_generators": False,
    "changes_methods": False,
}


def _short_kind(value):
    return "Terno" if str(value or "") == "Terno de Grupo" else str(value or "Centena")


def _clear(frame):
    for child in frame.winfo_children():
        child.destroy()


def _polished_advisor_card(app, advisor, app_version):
    body = getattr(app, "play_body", None)
    if body is None:
        return

    app._round_advisor_recommendation = None
    card = ttk.Frame(body, style="Card.TFrame", padding=(14, 12))
    children = list(body.winfo_children())
    pack_args = {"fill": "x", "pady": (0, 10)}
    if children:
        pack_args["before"] = children[0]
    card.pack(**pack_args)
    app._round_advisor_card = card

    # Cabeçalho compacto: o usuário entende o propósito sem um parágrafo longo.
    header = ttk.Frame(card, style="Card.TFrame")
    header.pack(fill="x")
    ttk.Label(header, text="ASSISTENTE DA PRÓXIMA RODADA", style="Section.TLabel").pack(side="left")
    ttk.Label(
        header,
        text=f"v{app_version} • histórico causal • sem look-ahead",
        style="CardMuted.TLabel",
    ).pack(side="right")

    target = None
    try:
        target = app.db.next_operational_target()
    except Exception:
        pass
    target_text = advisor._format_target(app, target) if target else "Próxima rodada ainda não identificada"

    flow = ttk.Frame(card, style="Card.TFrame")
    flow.pack(fill="x", pady=(10, 8))
    for col in range(3):
        flow.columnconfigure(col, weight=1, uniform="playflow")

    def flow_box(col, eyebrow, value):
        box = ttk.Frame(flow, style="Card2.TFrame", padding=(10, 8))
        box.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 4, 0 if col == 2 else 4))
        ttk.Label(box, text=eyebrow, style="CardMuted.TLabel").pack(anchor="w")
        label = ttk.Label(box, text=value, style="Card.TLabel", wraplength=330, justify="left")
        label.pack(anchor="w", pady=(3, 0))
        return label

    round_value = flow_box(0, "1 • RODADA", target_text)
    recommendation_value = flow_box(1, "2 • RECOMENDAÇÃO", "Aguardando avaliação")
    games_value = flow_box(2, "3 • JOGOS", "Gerados depois da avaliação")

    summary = ttk.Frame(card, style="Card.TFrame")
    summary.pack(fill="x", pady=(2, 5))
    status = ttk.Label(
        summary,
        text="Compare os métodos válidos e deixe a Central indicar método e modalidade.",
        style="Card.TLabel", wraplength=1100, justify="left",
    )
    status.pack(fill="x", anchor="w")
    evidence = ttk.Label(
        summary,
        text="A quantidade e o valor permanecem editáveis nos controles da aposta abaixo.",
        style="CardMuted.TLabel", wraplength=1100, justify="left",
    )
    evidence.pack(fill="x", anchor="w", pady=(3, 0))

    metrics = ttk.Frame(card, style="Card.TFrame")
    metrics.pack(fill="x", pady=(5, 3))
    metric_labels = []
    for col, (name, initial) in enumerate((("ACERTO", "—"), ("CONTROLE", "—"), ("DIFERENÇA", "—"), ("AMOSTRA", "—"))):
        metrics.columnconfigure(col, weight=1, uniform="playmetrics")
        box = ttk.Frame(metrics, style="Card2.TFrame", padding=(9, 6))
        box.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 3, 0 if col == 3 else 3))
        ttk.Label(box, text=name, style="CardMuted.TLabel").pack(anchor="w")
        value = ttk.Label(box, text=initial, style="Card.TLabel")
        value.pack(anchor="w", pady=(2, 0))
        metric_labels.append(value)

    actions = ttk.Frame(card, style="Card.TFrame")
    actions.pack(fill="x", pady=(7, 0))
    eval_btn = ttk.Button(actions, text="AVALIAR PRÓXIMA RODADA", style="Primary.TButton")
    recalc_btn = ttk.Button(actions, text="RECALCULAR JOGOS", style="Secondary.TButton", state="disabled")
    edit_btn = ttk.Button(actions, text="EDITAR PALPITES", style="Secondary.TButton", state="disabled")
    details_btn = ttk.Button(actions, text="VER COMPARAÇÃO", style="Quiet.TButton", state="disabled")
    eval_btn.pack(side="left")
    recalc_btn.pack(side="left", padx=(7, 0))
    edit_btn.pack(side="left", padx=(7, 0))
    details_btn.pack(side="right")

    technical = ttk.Frame(card, style="Card2.TFrame", padding=(10, 8))
    technical_visible = {"value": False}
    ranking_label = ttk.Label(
        technical, text="", style="CardMuted.TLabel", wraplength=1100, justify="left"
    )
    ranking_label.pack(fill="x", anchor="w")

    def set_details_visible(show=None):
        if show is None:
            show = not technical_visible["value"]
        technical_visible["value"] = bool(show)
        if show:
            technical.pack(fill="x", pady=(8, 0))
            details_btn.configure(text="OCULTAR COMPARAÇÃO")
        else:
            technical.pack_forget()
            details_btn.configure(text="VER COMPARAÇÃO")

    details_btn.configure(command=set_details_visible)

    def set_busy(busy):
        try:
            if busy:
                eval_btn.state(["disabled"])
                recalc_btn.state(["disabled"])
                edit_btn.state(["disabled"])
                details_btn.state(["disabled"])
            else:
                eval_btn.state(["!disabled"])
                if app._round_advisor_recommendation:
                    recalc_btn.state(["!disabled"])
                    details_btn.state(["!disabled"])
                    if getattr(app, "play_generation", None):
                        edit_btn.state(["!disabled"])
        except tk.TclError:
            pass

    def render_recommendation(rec, prefix="Recomendado e gerado"):
        quantity = advisor._current_quantity(app, rec)
        target_now = advisor._format_target(app, rec.get("target"))
        round_value.configure(text=target_now)
        recommendation_value.configure(text=f"{rec['selector']} • {_short_kind(rec['kind'])}")
        games_value.configure(text=f"{quantity} palpites • prontos para revisar")
        status.configure(text=f"{prefix}: {rec['selector']} → {rec['kind']} • {rec['confidence']}")
        evidence.configure(text=(
            f"Contexto: {rec['context']} • o desempenho abaixo é do padrão histórico comparável "
            "(20 Centenas ou 5 Ternos)."
        ))
        metric_labels[0].configure(text=advisor._pct(rec["rate"]))
        metric_labels[1].configure(text=advisor._pct(rec["control_rate"]))
        metric_labels[2].configure(text=advisor._pp(rec["gain"]))
        metric_labels[3].configure(text=f"n={int(rec['n'])}")

        ordered = [rec] + list(rec.get("alternatives") or [])[:7]
        lines = ["COMPARAÇÃO DOS MÉTODOS"]
        lines += [advisor._candidate_line(i, item) for i, item in enumerate(ordered, 1)]
        excluded = list(rec.get("excluded_methods") or [])
        if excluded:
            lines += ["", "FORA DA COMPARAÇÃO"]
            lines += [f"• {row['method']}: {row['reason']}" for row in excluded[:8]]
        ranking_label.configure(text="\n".join(lines))

    def finish_ok(rec):
        try:
            if not card.winfo_exists():
                return
            app._round_advisor_recommendation = rec
            advisor._apply_recommendation(app, rec, keep_quantity=False)
            render_recommendation(rec)
            recalc_btn.state(["!disabled"])
            edit_btn.state(["!disabled"])
            details_btn.state(["!disabled"])
        except Exception as exc:
            status.configure(text="A avaliação terminou, mas os jogos não puderam ser aplicados automaticamente.")
            evidence.configure(text=str(exc))
        finally:
            set_busy(False)

    def finish_error(exc):
        try:
            if not card.winfo_exists():
                return
            recommendation_value.configure(text="Avaliação indisponível")
            games_value.configure(text="Nenhum jogo alterado")
            status.configure(text="Não foi possível concluir a avaliação desta rodada.")
            evidence.configure(text=str(exc))
            ranking_label.configure(text="")
            set_details_visible(False)
        finally:
            set_busy(False)

    def worker():
        try:
            rec = advisor.evaluate_next_round(app)
        except Exception as exc:
            try:
                app.after(0, lambda exc=exc: finish_error(exc))
            except Exception:
                pass
            return
        try:
            app.after(0, lambda rec=rec: finish_ok(rec))
        except Exception:
            pass

    def evaluate():
        recommendation_value.configure(text="Avaliando…")
        games_value.configure(text="Aguardando recomendação")
        status.configure(text="Comparando os métodos com histórico causal válido para o próximo horário…")
        evidence.configure(text="Janela de até 90 dias; nenhuma rodada futura entra na análise.")
        for value in metric_labels:
            value.configure(text="—")
        ranking_label.configure(text="")
        set_details_visible(False)
        set_busy(True)
        threading.Thread(target=worker, name="gph-round-advisor-ui-stage4", daemon=True).start()

    def recalculate():
        rec = app._round_advisor_recommendation
        if not rec:
            return
        try:
            advisor._apply_recommendation(app, rec, keep_quantity=True)
            render_recommendation(rec, prefix="Jogos recalculados")
            edit_btn.state(["!disabled"])
        except Exception as exc:
            messagebox.showerror("Recalcular jogos", str(exc), parent=app)

    def edit():
        try:
            if advisor._edit_current_generation(app):
                games_value.configure(text="Palpites editados manualmente")
                status.configure(text="Edição manual aplicada. Revise quantidade e valor antes de adicionar ao bilhete.")
                evidence.configure(text="RECALCULAR JOGOS restaura a geração do método recomendado usando a quantidade atual.")
        except Exception as exc:
            messagebox.showerror("Editar palpites", str(exc), parent=app)

    eval_btn.configure(command=evaluate)
    recalc_btn.configure(command=recalculate)
    edit_btn.configure(command=edit)


def install_play_polish(advisor, app_version):
    """Troca somente a apresentação do cartão do assistente já existente."""
    if getattr(advisor, "_gph_ui_play_stage4_installed", False):
        return PLAY_POLISH_INFO

    def build(app):
        return _polished_advisor_card(app, advisor, app_version)

    advisor._build_advisor_card = build
    advisor._gph_ui_play_stage4_installed = True
    return PLAY_POLISH_INFO
