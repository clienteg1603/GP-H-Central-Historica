"""Etapa 3 da cura visual do GP-H: Home como painel de comando.

Esta camada só reorganiza/apresenta informações já existentes. Não altera
Meta, métodos, banco, auditoria, geração ou critérios de decisão.
"""
from __future__ import annotations

HOME_POLISH_VERSION = "3.0"
HOME_POLISH_INFO = {
    "stage": 3,
    "visual_only": True,
    "changes_meta": False,
    "changes_database": False,
    "changes_generators": False,
    "changes_methods": False,
}


def _safe_call(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _target_text(app, target):
    if not target:
        return "Nenhuma rodada identificada"
    try:
        return app._format_target(target)
    except Exception:
        parts = [str(target.get(k) or "").strip() for k in ("data", "sorteio", "hora")]
        return " • ".join(p for p in parts if p) or "Rodada não identificada"


def _latest_text(latest):
    if not latest:
        return "Nenhum resultado disponível"
    parts = [str(latest.get(k) or "").strip() for k in ("data", "sorteio", "hora")]
    return " • ".join(p for p in parts if p) or "Último resultado disponível"


def _find_scroll_body(root):
    """Localiza o body rolável criado pela Home legada, sem depender de path Tk."""
    stack = list(root.winfo_children()) if root is not None else []
    while stack:
        widget = stack.pop(0)
        if getattr(widget, "_gph_scroll_canvas", None) is not None:
            return widget
        try:
            stack.extend(widget.winfo_children())
        except Exception:
            pass
    return None


def _metric_card(central, parent, title, value, subtitle="", *, command=None):
    card = central.ttk.Frame(parent, style="Card.TFrame", padding=(12, 10))
    central.ttk.Label(card, text=title, style="CardMuted.TLabel").pack(anchor="w")
    central.ttk.Label(
        card,
        text=value,
        style="Card.TLabel",
        font=(central.UI_FONT_SEMIBOLD, central.UI_FONT_SIZES["section"]),
        wraplength=245,
        justify="left",
    ).pack(anchor="w", pady=(4, 2))
    if subtitle:
        central.ttk.Label(
            card,
            text=subtitle,
            style="CardMuted.TLabel",
            wraplength=245,
            justify="left",
        ).pack(anchor="w")
    if command is not None:
        central.ttk.Button(
            card, text="ABRIR", command=command, style="Quiet.TButton"
        ).pack(anchor="w", pady=(8, 0))
    return card


def _meta_snapshot(app):
    """Resumo diagnóstico leve. Nunca recalcula nem retreina o Meta."""
    result = {
        "label": "EM OBSERVAÇÃO",
        "value": "Sem amostra suficiente",
        "subtitle": "Abra Decisão → Auditoria para os detalhes prospectivos.",
    }
    evolution = _safe_call(lambda: app.db.decision_coverage_evolution(windows=(20,), recent_limit=10), None)
    if not evolution:
        return result

    # A API já existe no banco; toleramos tanto lista quanto dicionário para
    # manter compatibilidade com versões anteriores da auditoria.
    row = None
    if isinstance(evolution, dict):
        windows = evolution.get("windows")
        if isinstance(windows, dict):
            row = windows.get(20) or windows.get("20")
        elif isinstance(windows, list) and windows:
            row = windows[0]
        row = row or evolution.get("20") or evolution.get(20)
    elif isinstance(evolution, (list, tuple)) and evolution:
        row = evolution[0]
    if not isinstance(row, dict):
        return result

    rounds = int(row.get("rounds") or 0)
    pct = row.get("pct_2plus")
    avg = row.get("avg_coverage")
    if pct is not None:
        result["value"] = f"Taxa 2+ {float(pct):.1f}%".replace(".", ",")
    elif avg is not None:
        result["value"] = f"Cobertura {float(avg):.2f}/5".replace(".", ",")
    if rounds:
        avg_text = ""
        if avg is not None:
            avg_text = f" • média {float(avg):.2f}/5".replace(".", ",")
        result["subtitle"] = f"{rounds} rodada(s) elegível(is){avg_text}. Meta segue diagnóstico, não prioridade automática."
    return result


def _recommendation_snapshot(app, target):
    rec = getattr(app, "_round_advisor_recommendation", None)
    if not isinstance(rec, dict):
        return {
            "value": "Ainda não avaliada",
            "subtitle": "A recomendação causal é calculada em Jogar → Nova aposta.",
        }

    rec_target = rec.get("target") or {}
    wanted = tuple(str((target or {}).get(k) or "") for k in ("data", "sorteio", "hora"))
    got = tuple(str(rec_target.get(k) or "") for k in ("data", "sorteio", "hora"))
    if target and got != wanted:
        return {
            "value": "Avaliação ficou antiga",
            "subtitle": "Entrou uma nova rodada. Reavalie antes de usar a recomendação.",
        }

    method = str(rec.get("selector") or "Método")
    kind = str(rec.get("kind") or "")
    confidence = str(rec.get("confidence") or "")
    n = int(rec.get("n") or 0)
    return {
        "value": f"{method} • {kind}" if kind else method,
        "subtitle": " • ".join(p for p in (confidence, f"n={n}" if n else "") if p),
    }


def _pending_snapshot(app, target):
    if not target:
        return 0
    rows = _safe_call(lambda: app.db.pending_operational_games_for_target(target), []) or []
    return len(rows)


def _inject_command_center(app, central):
    body = _find_scroll_body(getattr(app, "content", None))
    if body is None:
        return False

    children = list(body.winfo_children())
    command_center = central.ttk.Frame(body, style="Surface.TFrame")
    pack_args = {"fill": "x", "pady": (0, 14)}
    if children:
        pack_args["before"] = children[0]
    command_center.pack(**pack_args)

    head = central.ttk.Frame(command_center, style="Surface.TFrame")
    head.pack(fill="x", pady=(0, 10))
    central.ttk.Label(head, text="PAINEL DE COMANDO", style="PageTitle.TLabel").pack(side="left")
    central.ttk.Label(
        head,
        text="o que precisa da sua atenção agora",
        style="PageSubtitle.TLabel",
    ).pack(side="left", padx=(12, 0), pady=(5, 0))

    target = _safe_call(app.db.next_operational_target, None)
    latest = _safe_call(app.db.latest_operational_draw, None)
    pending = _pending_snapshot(app, target)
    recommendation = _recommendation_snapshot(app, target)
    meta = _meta_snapshot(app)

    grid = central.ttk.Frame(command_center, style="Surface.TFrame")
    grid.pack(fill="x")
    for col in range(4):
        grid.columnconfigure(col, weight=1, uniform="homecmd")

    cards = (
        _metric_card(
            central, grid, "PRÓXIMA RODADA", _target_text(app, target),
            "Base operacional identificada automaticamente.", command=app.show_play_page,
        ),
        _metric_card(
            central, grid, "RECOMENDAÇÃO", recommendation["value"], recommendation["subtitle"],
            command=app.show_play_page,
        ),
        _metric_card(
            central, grid, "META", meta["value"], meta["subtitle"],
            command=lambda: app.show_decision_page(view="audit"),
        ),
        _metric_card(
            central, grid, "ÚLTIMO RESULTADO", _latest_text(latest),
            f"{pending} jogo(s) pendente(s) para o próximo alvo." if pending else "Sem pendência operacional para o próximo alvo.",
            command=app.show_results,
        ),
    )
    for col, card in enumerate(cards):
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 5, 0 if col == 3 else 5))

    actions = central.ttk.Frame(command_center, style="Surface.TFrame")
    actions.pack(fill="x", pady=(10, 0))
    central.ttk.Button(actions, text="JOGAR AGORA", command=app.show_play_page, style="Primary.TButton").pack(side="left")
    central.ttk.Button(actions, text="ABRIR DECISÃO", command=app.show_decision_page, style="Secondary.TButton").pack(side="left", padx=(8, 0))
    central.ttk.Button(actions, text="VER RESULTADOS", command=app.show_results, style="Secondary.TButton").pack(side="left", padx=(8, 0))
    central.ttk.Button(actions, text="ATUALIZAR PAINEL", command=app.show_home, style="Quiet.TButton").pack(side="right")

    if children:
        separator = central.ttk.Frame(body, style="Surface.TFrame")
        central.ttk.Label(separator, text="DETALHES DA CENTRAL", style="Eyebrow.TLabel").pack(anchor="w")
        separator.pack(fill="x", pady=(0, 8), before=children[0])

    app._gph_home_command_center = command_center
    return True


def install_home_polish(central):
    """Instala a Home de comando preservando a Home legada logo abaixo."""
    app_cls = central.App
    if getattr(app_cls, "_gph_ui_home_installed", False):
        return HOME_POLISH_INFO

    original_show_home = app_cls.show_home

    def show_home(self, *args, **kwargs):
        result = original_show_home(self, *args, **kwargs)
        try:
            _inject_command_center(self, central)
        except Exception as exc:
            # A cura visual nunca pode impedir o uso da Home original.
            self._gph_home_polish_error = str(exc)
        return result

    app_cls.show_home = show_home
    app_cls._gph_ui_home_installed = True
    central.GPH_UI_HOME_VERSION = HOME_POLISH_VERSION
    return HOME_POLISH_INFO
