"""Assistente de rodada da v0.48.1.

A camada é deliberadamente fina: reutiliza o laboratório histórico v0.48.0
para medir alternativas já jogáveis na Central e apenas configura a tela
Jogar > Nova aposta. A avaliação não grava no banco, não recalibra o Meta e
não consulta o resultado da rodada futura.
"""
from __future__ import annotations

import threading
from datetime import date, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import gph_history_lab as lab

EVALUATION_DAYS = 90
MIN_CONTEXT_RECORDS = 8

# Somente combinações que já possuem gerador real na tela Nova aposta.
PLAY_MAPPING = {
    "Reset Cobertura": {
        "Centena": {
            "family": "Centena",
            "variant": "Normal",
            "kind": "Centena",
            "method": "Oficial • Reset + Lei GP-H",
            "quantity": 20,
        },
        "Terno de Grupo": {
            "family": "Grupo",
            "variant": "Terno",
            "kind": "Terno de Grupo",
            "method": "Oficial • Reset combinações",
            "quantity": 5,
        },
    },
    "Puxada Combinada": {
        "Centena": {
            "family": "Centena",
            "variant": "Normal",
            "kind": "Centena",
            "method": "Experimental • Puxada Combinada",
            "quantity": 20,
        },
        "Terno de Grupo": {
            "family": "Grupo",
            "variant": "Terno",
            "kind": "Terno de Grupo",
            "method": "Experimental • Puxada Combinada",
            "quantity": 5,
        },
    },
}


def _target_key(target):
    target = target or {}
    return (str(target.get("data") or ""), str(target.get("sorteio") or ""), str(target.get("hora") or ""))


def _mean_hit(records, method):
    values = []
    for row in records:
        score = (row.get("scores") or {}).get(method)
        if score is None or score.get("hit") is None:
            continue
        values.append(float(score["hit"]))
    return (sum(values) / len(values), len(values)) if values else (None, 0)


def _context_records(report, target):
    """Prefere mesma extração+hora; com pouca amostra usa a mesma hora.

    run_history já recebeu o filtro de hora. O fallback é explícito para não
    fingir precisão quando, por exemplo, uma Federal dominical ainda tem poucos
    casos dentro da janela recente.
    """
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
    """Converte um relatório do laboratório em candidatos diretamente jogáveis."""
    records, context_label = _context_records(report, target)
    if not records:
        return []

    candidates = []
    specs = (
        ("Centena", lab.LAW, lab.CONDITIONAL_RANDOM),
        ("Terno de Grupo", lab.TERN_CURRENT, lab.TERN_RANDOM),
    )
    for kind, method_name, control_name in specs:
        rate, n = _mean_hit(records, method_name)
        control_rate, control_n = _mean_hit(records, control_name)
        if rate is None or control_rate is None or not n or not control_n:
            continue
        play = dict(PLAY_MAPPING[selector][kind])
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
    """Escolhe pelo ganho de acerto sobre o controle equivalente.

    Não compara retorno financeiro nem usa a meta de 50% como peso. O 50% do
    projeto continua sendo apenas régua de avaliação fora deste seletor.
    """
    candidates = []
    for selector, report in (reports or {}).items():
        if selector in PLAY_MAPPING:
            candidates.extend(candidates_from_report(selector, report, target))
    if not candidates:
        raise ValueError("A base ainda não produziu amostra suficiente para avaliar esta rodada.")

    candidates.sort(
        key=lambda item: (
            float(item["gain"]),
            float(item["rate"]),
            int(item["n"]),
            1 if item["kind"] == "Centena" else 0,
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


def evaluate_next_round(app):
    """Roda o protocolo da v0.48.0 até a última extração já conhecida."""
    target = app.db.next_operational_target()
    latest = app.db.latest_operational_draw()
    if not target or not latest:
        raise ValueError("Não foi possível identificar a próxima rodada ou a última base disponível.")

    end_day = date.fromisoformat(str(latest["data"]))
    start_day = max(date(2026, 1, 2), end_day - timedelta(days=EVALUATION_DAYS - 1))
    reports = {}
    for selector in PLAY_MAPPING:
        options = {
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "scope": "1º–5º",
            "selector": selector,
            "hour": str(target.get("hora") or ""),
        }
        # run_history trabalha sobre cópia SQLite temporal e treino anterior ao alvo.
        reports[selector] = lab.run_history(type(app.db), app.db.path, options)

    recommendation = choose_recommendation(reports, target)
    recommendation.update({
        "target": dict(target),
        "base_end": end_day.isoformat(),
        "window_start": start_day.isoformat(),
        "lookahead_safe": True,
        "changes_meta": False,
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


def _apply_recommendation(app, recommendation, keep_quantity=False):
    current_next = app.db.next_operational_target()
    if _target_key(current_next) != _target_key(recommendation.get("target")):
        raise ValueError("Entrou um resultado novo enquanto a avaliação estava aberta. Clique em AVALIAR PRÓXIMA RODADA novamente.")

    label = _find_target_label(app, recommendation["target"])
    if label is None:
        raise ValueError("A próxima rodada não está mais disponível na lista da tela.")

    quantity = str(recommendation["quantity"])
    if keep_quantity:
        try:
            quantity = str(max(1, int(str(app.play_total.get()).strip())))
        except Exception:
            quantity = str(recommendation["quantity"])

    # O valor digitado pelo usuário é intencionalmente preservado.
    app.play_target_var.set(label)
    app.play_family.set(recommendation["family"])
    app.play_variant.set(recommendation["variant"])
    app.play_kind.set(recommendation["kind"])
    app.play_scope.set("1º–5º")
    app.play_method.set(recommendation["method"])
    app.play_total.set(quantity)
    app.play_controls_changed()
    try:
        app.play_target_changed()
    except Exception:
        pass
    app.play_generate()


def _edit_current_generation(app):
    generation = getattr(app, "play_generation", None)
    rows = list((generation or {}).get("rows") or [])
    if not rows:
        messagebox.showinfo("Editar palpites", "Gere os palpites da recomendação primeiro.", parent=app)
        return False
    numbers = [str(row.get("numero") or "").strip() for row in rows]
    numbers = [number for number in numbers if number]
    initial = ", ".join(numbers)
    text = simpledialog.askstring(
        "Editar palpites antes de usar",
        "Altere, remova ou acrescente palpites separados por vírgula.\nNada é registrado até você adicionar o jogo ao bilhete.",
        initialvalue=initial,
        parent=app,
    )
    if text is None:
        return False

    kind = str(app.play_kind.get())
    scope = str(app.play_scope.get())
    submode = app.play_submode.get() if kind == "Milhar" and hasattr(app, "play_submode") else None
    edited = app.db.manual_generation(kind, text, scope=scope, submodalidade=submode)
    target = (generation or {}).get("intended_target") or app.play_get_selected_target()
    edited["intended_target"] = dict(target or {})
    edited["target_mode"] = "ALVO_ESPECIFICO"
    edited["strategy"] = "Manual"
    edited["selector"] = "Manual"
    edited["origem_jogada"] = "Manual • ajuste da recomendação"

    app.play_method.set("Manual")
    app.play_controls_changed()
    app.play_generation = edited
    app.play_generation_groups = list(edited.get("groups") or [])
    app.play_total.set(str(len(edited.get("rows") or [])))
    app.play_render_generation()
    app.play_financial_refresh()
    return True


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
    badge = ttk.Label(head, text="v0.48.1 • histórico, sem mexer no Meta", style="CardMuted.TLabel")
    badge.pack(side="right")

    intro = ttk.Label(
        card,
        text=(
            "Compara, na mesma faixa de horário, Centenas e Ternos que a Central já consegue gerar. "
            "A escolha usa o ganho de acerto sobre um controle aleatório equivalente; não usa a meta de 50% como peso."
        ),
        style="CardMuted.TLabel",
        wraplength=1050,
        justify="left",
    )
    intro.pack(fill="x", anchor="w", pady=(4, 7))

    status = ttk.Label(card, text="Pronto para avaliar a próxima rodada.", style="Card.TLabel", wraplength=1050, justify="left")
    status.pack(fill="x", anchor="w", pady=(0, 3))
    details = ttk.Label(
        card,
        text="A avaliação é somente leitura. Quantidade e Valor continuam editáveis nos campos normais logo abaixo.",
        style="CardMuted.TLabel",
        wraplength=1050,
        justify="left",
    )
    details.pack(fill="x", anchor="w", pady=(0, 7))

    actions = ttk.Frame(card, style="Card.TFrame")
    actions.pack(fill="x")

    recalc_btn = ttk.Button(actions, text="RECALCULAR JOGOS", state="disabled")
    edit_btn = ttk.Button(actions, text="EDITAR PALPITES", state="disabled")

    def set_busy(busy):
        try:
            if busy:
                eval_btn.state(["disabled"])
                recalc_btn.state(["disabled"])
                edit_btn.state(["disabled"])
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
        status.configure(
            text=(
                f"{prefix}: {rec['kind']} • {rec['method']} • {rec['quantity']} palpites padrão\n"
                f"Alvo: {target_text} • {rec['confidence']}"
            )
        )
        details.configure(
            text=(
                f"Histórico: {rec['n']} rodadas ({rec['context']}) • acerto {_pct(rec['rate'])} • "
                f"controle {_pct(rec['control_rate'])} • diferença {_pp(rec['gain'])}. "
                "Você pode mudar Quantidade e Valor abaixo. Ao mudar a quantidade, clique RECALCULAR JOGOS; "
                "a taxa histórica exibida continua referente ao padrão testado de 20 Centenas ou 5 Ternos."
            )
        )

    def finish_ok(rec):
        try:
            if not card.winfo_exists():
                return
            app._round_advisor_recommendation = rec
            _apply_recommendation(app, rec, keep_quantity=False)
            render_recommendation(rec)
            recalc_btn.state(["!disabled"])
            edit_btn.state(["!disabled"])
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
        finally:
            set_busy(False)

    def worker():
        try:
            rec = evaluate_next_round(app)
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
        status.configure(text="Avaliando a próxima rodada com o histórico já disponível…")
        details.configure(text="Usando janela recente de até 90 dias; cada alvo histórico é previsto somente com dados anteriores a ele.")
        set_busy(True)
        threading.Thread(target=worker, name="gph-round-advisor", daemon=True).start()

    def recalculate():
        rec = app._round_advisor_recommendation
        if not rec:
            return
        try:
            _apply_recommendation(app, rec, keep_quantity=True)
            quantity = str(app.play_total.get())
            render_recommendation({**rec, "quantity": quantity}, prefix="Jogos recalculados")
            edit_btn.state(["!disabled"])
        except Exception as exc:
            messagebox.showerror("Recalcular jogos", str(exc), parent=app)

    def edit():
        try:
            if _edit_current_generation(app):
                status.configure(text="Palpites editados manualmente. Revise o valor e adicione ao bilhete somente quando quiser.")
                details.configure(text="RECALCULAR JOGOS volta para o método recomendado usando a quantidade atualmente informada.")
        except Exception as exc:
            messagebox.showerror("Editar palpites", str(exc), parent=app)

    eval_btn = ttk.Button(actions, text="AVALIAR PRÓXIMA RODADA", style="Accent.TButton", command=evaluate)
    eval_btn.pack(side="left", padx=(0, 6))
    recalc_btn.configure(command=recalculate)
    recalc_btn.pack(side="left", padx=(0, 6))
    edit_btn.configure(command=edit)
    edit_btn.pack(side="left")


def install_round_advisor(central_module):
    """Instala a extensão sem alterar Database, Meta ou os geradores existentes."""
    app_class = central_module.App
    if getattr(app_class, "_round_advisor_v0481_installed", False):
        return
    original = app_class.play_show_new

    def play_show_new_with_advisor(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        try:
            _build_advisor_card(self)
        except Exception:
            # A tela antiga continua funcional mesmo se a camada opcional falhar.
            pass
        return result

    app_class.play_show_new = play_show_new_with_advisor
    app_class._round_advisor_v0481_installed = True
