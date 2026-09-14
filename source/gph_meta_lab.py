"""Meta Lab prospectivo do GP-H — v0.48.23.

Esta camada existe para investigar a fronteira do Top 5 sem tocar no cérebro
oficial do Meta. Ela lê exclusivamente snapshots já congelados antes do
resultado e calcula variantes determinísticas usando apenas o ranking Meta e os
sinais que já existiam naquele instante.

As primeiras 21 rodadas válidas formam o baseline diagnóstico que motivou a
abertura do laboratório. A partir da 22ª rodada, as mesmas variantes ficam
congeladas e passam a ser avaliadas prospectivamente. Nenhuma variante é usada
para apostar, gerar jogos, alterar pesos, score, confiança ou o Top 5 oficial.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk

LAB_BASELINE_ROUNDS = 21
LAB_MAX_ROUNDS = 90
LAB_VERSION = "1.0"

META_LAB_INFO = {
    "version": LAB_VERSION,
    "experimental_only": True,
    "changes_meta": False,
    "changes_weights": False,
    "changes_scores": False,
    "changes_generators": False,
    "changes_betting": False,
    "changes_database": False,
    "uses_only_frozen_inputs": True,
    "baseline_rounds": LAB_BASELINE_ROUNDS,
}


def _load(value, default):
    if isinstance(value, type(default)):
        return value
    try:
        out = json.loads(value or "")
        return out if isinstance(out, type(default)) else default
    except Exception:
        return default


def _groups(values, limit=None, unique=True):
    out = []
    for raw in values or []:
        if isinstance(raw, dict):
            raw = raw.get("grupo")
        try:
            group = int(raw)
        except Exception:
            continue
        if not 1 <= group <= 25:
            continue
        if not unique or group not in out:
            out.append(group)
        if limit and len(out) >= limit:
            break
    return out


def _result_groups(db, row):
    audit = _load(row.get("meta_audit_json"), {})
    values = _groups(audit.get("result_groups"), unique=False)
    if values:
        return values
    values = _groups(_load(row.get("result_groups_json"), []), unique=False)
    if values:
        return values
    try:
        draw = db.get_draw(row.get("target_data"), row.get("target_sorteio"), row.get("target_hora"))
    except Exception:
        draw = None
    return _groups(
        [p.get("grupo") for p in ((draw or {}).get("prizes") or [])[:5] if isinstance(p, dict)],
        unique=False,
    )


def _ranking(meta):
    out = []
    for index, item in enumerate(list((meta or {}).get("ranking") or []), 1):
        if not isinstance(item, dict):
            continue
        try:
            group = int(item.get("grupo"))
            rank = int(item.get("rank") or index)
        except Exception:
            continue
        if not 1 <= group <= 25:
            continue
        score = item.get("score")
        try:
            score = float(score) if score is not None else None
        except Exception:
            score = None
        out.append({"rank": rank, "group": group, "score": score})
    out.sort(key=lambda item: (item["rank"], item["group"]))
    if not out:
        out = [
            {"rank": index, "group": group, "score": None}
            for index, group in enumerate(_groups((meta or {}).get("groups"), 5), 1)
        ]
    return out


def _signals(row):
    payload = _load(row.get("signals_json"), {})
    answer = {}
    for name, item in payload.items():
        if isinstance(item, dict) and item.get("available") is not False:
            groups = _groups(item.get("groups"))
            if groups:
                answer[str(name)] = groups
    return answer


def _support_map(signals):
    support = {group: [] for group in range(1, 26)}
    for name, groups in (signals or {}).items():
        for group in _groups(groups):
            support[group].append(str(name))
    return support


def collect_frozen_records(db, limit=LAB_MAX_ROUNDS):
    """Lê snapshots Meta congelados e monta a matéria-prima do laboratório."""
    con = db.connect()
    try:
        rows = con.execute(
            """SELECT id,target_data,target_sorteio,target_hora,meta_json,meta_frozen_at,
                meta_audit_json,result_groups_json,signals_json
                FROM decision_snapshots
                WHERE meta_json IS NOT NULL AND TRIM(meta_json)<>''
                  AND meta_frozen_at IS NOT NULL AND TRIM(meta_frozen_at)<>''
                ORDER BY target_data DESC,target_hora DESC,id DESC LIMIT ?""",
            (max(1, int(limit) * 3),),
        ).fetchall()
    finally:
        try:
            con.close()
        except Exception:
            pass

    out = []
    for raw in rows:
        row = dict(raw)
        meta = _load(row.get("meta_json"), {})
        if meta.get("available") is False:
            continue
        top5 = _groups(meta.get("groups"), 5)
        if len(top5) != 5:
            continue
        actual = _result_groups(db, row)
        if not actual:
            continue
        ranking = _ranking(meta)
        signals = _signals(row)
        support = _support_map(signals)
        out.append(
            {
                "data": row.get("target_data"),
                "sorteio": row.get("target_sorteio"),
                "hora": row.get("target_hora"),
                "top5": list(top5),
                "ranking": ranking,
                "signals": signals,
                "support": support,
                "actual": sorted(set(_groups(actual, unique=False))),
            }
        )
        if len(out) >= int(limit):
            break
    out.reverse()
    return out


def _rank_map(record):
    return {
        int(item["group"]): int(item["rank"])
        for item in (record.get("ranking") or [])
        if isinstance(item, dict) and item.get("group") is not None and item.get("rank") is not None
    }


def _ranked_groups(record, max_rank=25):
    seen = set()
    answer = []
    for item in sorted(
        [item for item in (record.get("ranking") or []) if isinstance(item, dict)],
        key=lambda item: (int(item.get("rank") or 999), int(item.get("group") or 999)),
    ):
        try:
            group = int(item.get("group"))
            rank = int(item.get("rank"))
        except Exception:
            continue
        if rank > max_rank or not 1 <= group <= 25 or group in seen:
            continue
        seen.add(group)
        answer.append(group)
    return answer


def _support_count(record, group):
    support = record.get("support") or _support_map(record.get("signals") or {})
    return len(support.get(int(group), []) or [])


def _ordered_selection(record, groups, limit=5):
    """Normaliza a seleção e preserva a ordem original do ranking quando possível."""
    wanted = []
    for group in groups or []:
        try:
            group = int(group)
        except Exception:
            continue
        if 1 <= group <= 25 and group not in wanted:
            wanted.append(group)
    ranks = _rank_map(record)
    wanted.sort(key=lambda group: (ranks.get(group, 999), group))
    if len(wanted) < limit:
        for group in _ranked_groups(record, 25):
            if group not in wanted:
                wanted.append(group)
            if len(wanted) >= limit:
                break
    if len(wanted) < limit:
        for group in _groups(record.get("top5")):
            if group not in wanted:
                wanted.append(group)
            if len(wanted) >= limit:
                break
    return wanted[:limit]


def select_official(record):
    return list(_groups(record.get("top5"), 5))


def select_consensus_guard(record):
    """Variante A: permite no máximo uma troca de fronteira por consenso 2+."""
    official = select_official(record)
    if len(official) != 5:
        return official
    ranks = _rank_map(record)
    outsiders = [
        group
        for group in _ranked_groups(record, 10)
        if group not in official and _support_count(record, group) >= 2
    ]
    outsiders.sort(key=lambda group: (-_support_count(record, group), ranks.get(group, 999), group))
    victims = [
        group
        for group in official
        if ranks.get(group, official.index(group) + 1) >= 4 and _support_count(record, group) <= 1
    ]
    victims.sort(key=lambda group: (_support_count(record, group), -ranks.get(group, 0), group))
    if outsiders and victims:
        challenger = outsiders[0]
        victim = victims[0]
        if _support_count(record, challenger) > _support_count(record, victim):
            official = [group for group in official if group != victim] + [challenger]
    return _ordered_selection(record, official, 5)


def select_border_4_8(record):
    """Variante B: preserva 1–3 e reordena somente a fronteira original 4–8."""
    official = select_official(record)
    ranks = _rank_map(record)
    fixed = official[:3]
    pool = [group for group in _ranked_groups(record, 8) if 4 <= ranks.get(group, 999) <= 8]
    pool.sort(key=lambda group: (-_support_count(record, group), ranks.get(group, 999), group))
    chosen = list(fixed)
    for group in pool:
        if group not in chosen:
            chosen.append(group)
        if len(chosen) >= 5:
            break
    return _ordered_selection(record, chosen, 5)


def select_consensus_3_10(record):
    """Variante C: preserva 1–2 e escolhe 3 vagas entre ranks 3–10 por convergência."""
    official = select_official(record)
    ranks = _rank_map(record)
    chosen = official[:2]
    pool = [group for group in _ranked_groups(record, 10) if 3 <= ranks.get(group, 999) <= 10]
    pool.sort(key=lambda group: (-_support_count(record, group), ranks.get(group, 999), group))
    for group in pool:
        if group not in chosen:
            chosen.append(group)
        if len(chosen) >= 5:
            break
    return _ordered_selection(record, chosen, 5)


@dataclass(frozen=True)
class LabVariant:
    key: str
    label: str
    selector: object
    description: str


VARIANTS = (
    LabVariant("official", "Meta oficial congelado", select_official, "Referência; nunca é alterado pelo laboratório."),
    LabVariant("guard", "A · Consenso protegido", select_consensus_guard, "No máximo 1 troca: consenso 2+ pode substituir fronteira com <=1 sinal."),
    LabVariant("border", "B · Fronteira 4–8", select_border_4_8, "Mantém ranks 1–3 e reordena somente 4–8 por convergência."),
    LabVariant("consensus", "C · Consenso 3–10", select_consensus_3_10, "Mantém ranks 1–2 e disputa 3 vagas entre 3–10 por convergência."),
)


def evaluate_variant(records, selector):
    rows = list(records or [])
    if not rows:
        return {"n": 0, "coverage_avg": 0.0, "rate2": 0.0, "rate3": 0.0, "hits": 0, "better": 0, "equal": 0, "worse": 0}
    hits = 0
    two_plus = 0
    three_plus = 0
    better = equal = worse = 0
    for row in rows:
        chosen = set(_groups(selector(row), 5))
        actual = set(_groups(row.get("actual"), unique=True))
        cov = len(chosen & actual)
        official_cov = len(set(select_official(row)) & actual)
        hits += cov
        two_plus += int(cov >= 2)
        three_plus += int(cov >= 3)
        if cov > official_cov:
            better += 1
        elif cov < official_cov:
            worse += 1
        else:
            equal += 1
    n = len(rows)
    return {
        "n": n,
        "coverage_avg": hits / n,
        "rate2": two_plus / n,
        "rate3": three_plus / n,
        "hits": hits,
        "better": better,
        "equal": equal,
        "worse": worse,
    }


def consensus_losses(records):
    losses = []
    for row in records or []:
        actual = set(_groups(row.get("actual")))
        official = set(select_official(row))
        ranks = _rank_map(row)
        support = row.get("support") or _support_map(row.get("signals") or {})
        for group in sorted(actual - official):
            methods = list(support.get(group, []) or [])
            if len(methods) < 2:
                continue
            losses.append(
                {
                    "data": row.get("data"),
                    "sorteio": row.get("sorteio"),
                    "hora": row.get("hora"),
                    "group": group,
                    "rank": ranks.get(group),
                    "methods": methods,
                }
            )
    return losses


def evaluate_lab(records):
    rows = list(records or [])
    baseline = rows[:LAB_BASELINE_ROUNDS]
    prospective = rows[LAB_BASELINE_ROUNDS:]
    variants = []
    for variant in VARIANTS:
        variants.append(
            {
                "key": variant.key,
                "label": variant.label,
                "description": variant.description,
                "baseline": evaluate_variant(baseline, variant.selector),
                "prospective": evaluate_variant(prospective, variant.selector),
            }
        )
    if len(rows) < LAB_BASELINE_ROUNDS:
        status = "AGUARDANDO BASELINE"
    elif not prospective:
        status = "LAB ABERTO — AGUARDANDO 1ª RODADA PROSPECTIVA"
    elif len(prospective) < 9:
        status = "COLETANDO PROSPECTIVO"
    else:
        status = "CHECKPOINT 30+ DISPONÍVEL PARA REVISÃO HUMANA"
    return {
        "available": bool(rows),
        "status": status,
        "total_n": len(rows),
        "baseline_n": len(baseline),
        "prospective_n": len(prospective),
        "variants": variants,
        "consensus_losses": consensus_losses(rows),
        "changes_meta": False,
        "uses_only_frozen_inputs": True,
        "automatic_promotion": False,
        "betting_enabled": False,
    }


def meta_lab_report(db, limit=LAB_MAX_ROUNDS):
    return evaluate_lab(collect_frozen_records(db, limit))


def _pct(value):
    return f"{100 * float(value):.1f}%".replace(".", ",")


def _num(value):
    return f"{float(value):.2f}".replace(".", ",")


def _metric_text(metric):
    if not metric or not metric.get("n"):
        return "—"
    return f"{_num(metric['coverage_avg'])}/5 • 2+ {_pct(metric['rate2'])}"


def _delta_text(metric, official):
    if not metric or not metric.get("n") or not official or not official.get("n"):
        return "—"
    delta = float(metric["coverage_avg"]) - float(official["coverage_avg"])
    sign = "+" if delta > 0 else ""
    return f"{sign}{_num(delta)} • {metric['better']}↑ {metric['worse']}↓"


def _build(app, body):
    try:
        report = meta_lab_report(app.db)
    except Exception as exc:
        card = ttk.Frame(body, style="Card.TFrame", padding=10)
        card.pack(fill="x", pady=(8, 0))
        ttk.Label(card, text="META LAB — RECALIBRAÇÃO EXPERIMENTAL", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(card, text=str(exc), style="CardMuted.TLabel").pack(anchor="w")
        return

    card = ttk.Frame(body, style="Card.TFrame", padding=12)
    card.pack(fill="x", pady=(8, 0))
    head = ttk.Frame(card, style="Card.TFrame")
    head.pack(fill="x")
    ttk.Label(head, text="META LAB — RECALIBRAÇÃO EXPERIMENTAL", style="CardTitle.TLabel").pack(side="left")
    ttk.Label(head, text="oficial congelado • não aposta • sem promoção automática", style="CardMuted.TLabel").pack(side="right")

    ttk.Label(
        card,
        text=(
            f"STATUS: {report['status']} — primeiras {LAB_BASELINE_ROUNDS} rodadas = baseline diagnóstico; "
            "da 22ª em diante = validação prospectiva das variantes já congeladas."
        ),
        style="Card.TLabel",
        wraplength=1500,
        justify="left",
    ).pack(fill="x", anchor="w", pady=(7, 5))
    ttk.Label(
        card,
        text=(
            "O Meta oficial continua sendo a referência e não recebe pesos, scores ou regras novas. "
            "O laboratório apenas pergunta se a fronteira 4–10 e o consenso entre métodos poderiam selecionar melhor o Top 5."
        ),
        style="CardMuted.TLabel",
        wraplength=1500,
        justify="left",
    ).pack(fill="x", anchor="w", pady=(0, 7))

    table = ttk.Treeview(
        card,
        columns=("variant", "baseline", "prospective", "delta", "rule"),
        show="headings",
        height=4,
    )
    headings = (
        ("variant", "Variante", 190),
        ("baseline", f"Baseline ({report['baseline_n']}/{LAB_BASELINE_ROUNDS})", 180),
        ("prospective", f"Prospectivo ({report['prospective_n']})", 180),
        ("delta", "Δ prospectivo vs oficial", 150),
        ("rule", "Regra congelada", 390),
    )
    for key, title, width in headings:
        table.heading(key, text=title)
        table.column(key, width=width, anchor="w", stretch=True)

    official = next((item for item in report["variants"] if item["key"] == "official"), None)
    official_prospective = (official or {}).get("prospective") or {}
    for item in report["variants"]:
        table.insert(
            "",
            "end",
            values=(
                item["label"],
                _metric_text(item["baseline"]),
                _metric_text(item["prospective"]),
                "referência" if item["key"] == "official" else _delta_text(item["prospective"], official_prospective),
                item["description"],
            ),
        )
    table.pack(fill="x", pady=(0, 7))

    losses = report.get("consensus_losses") or []
    if losses:
        ttk.Label(
            card,
            text="AUDITORIA DE CONSENSO PERDIDO — mostra por que um bicho real deixado fora tinha 2+ métodos apontando para ele.",
            style="CardMuted.TLabel",
            wraplength=1500,
            justify="left",
        ).pack(fill="x", anchor="w", pady=(0, 4))
        loss_table = ttk.Treeview(
            card,
            columns=("target", "group", "rank", "methods"),
            show="headings",
            height=min(6, max(2, len(losses))),
        )
        for key, title, width in (
            ("target", "Alvo", 210),
            ("group", "Bicho/Grupo", 100),
            ("rank", "Rank Meta", 85),
            ("methods", "Métodos que concordavam", 520),
        ):
            loss_table.heading(key, text=title)
            loss_table.column(key, width=width, anchor="w", stretch=True)
        for item in losses[-8:]:
            loss_table.insert(
                "",
                "end",
                values=(
                    f"{item.get('data')} • {item.get('sorteio')} • {item.get('hora')}",
                    f"G{int(item['group']):02d}",
                    item.get("rank") if item.get("rank") is not None else "—",
                    " • ".join(item.get("methods") or []),
                ),
            )
        loss_table.pack(fill="x", pady=(0, 7))

    status = tk.StringVar(
        value="Nenhuma variante pode substituir o Meta oficial automaticamente. O primeiro checkpoint forte continua em 30 rodadas totais."
    )
    footer = ttk.Frame(card, style="Card.TFrame")
    footer.pack(fill="x")
    ttk.Label(footer, textvariable=status, style="CardMuted.TLabel", wraplength=1200).pack(side="left")

    def copy_summary():
        lines = [
            "GP-H Meta Lab — recalibração experimental",
            f"Status: {report['status']}",
            f"Rodadas totais: {report['total_n']}",
            f"Baseline: {report['baseline_n']}/{LAB_BASELINE_ROUNDS}",
            f"Prospectivas do Lab: {report['prospective_n']}",
            "",
        ]
        for item in report["variants"]:
            lines.append(
                f"{item['label']}: baseline {_metric_text(item['baseline'])}; "
                f"prospectivo {_metric_text(item['prospective'])}"
            )
        lines.extend(("", "Meta oficial não alterado. Lab não aposta e não promove variante automaticamente."))
        try:
            app.clipboard_clear()
            app.clipboard_append("\n".join(lines))
            app.update_idletasks()
            status.set("Resumo do Meta Lab copiado.")
        except Exception as exc:
            status.set(str(exc))

    ttk.Button(footer, text="COPIAR META LAB", command=copy_summary).pack(side="right")


def install_meta_lab(central_module):
    cls = central_module.App
    if getattr(cls, "_meta_lab_v04823_installed", False):
        return
    original = getattr(cls, "_decision_build_coverage_evolution", None)
    if original is None:
        return

    def wrapped(self, body, *args, **kwargs):
        result = original(self, body, *args, **kwargs)
        try:
            _build(self, body)
        except Exception:
            pass
        return result

    cls._decision_build_coverage_evolution = wrapped
    cls._meta_lab_v04823_installed = True
