from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

# Estudo temporário: NÃO altera a Central e NÃO persiste nada no banco do usuário.
ROOT = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="gph_table1_study_"))
os.environ["GPH_DATA_DIR"] = str(TMP / "runtime")
os.environ["GPH_DISABLE_STARTUP_DIALOGS"] = "1"

spec = importlib.util.spec_from_file_location("gph_study_mod", ROOT / "source" / "gph_central.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

# Tabela 1 exata fornecida pelo usuário em 09/09/2026.
TABLE1 = {
    1: (25, 2, 13, 19, 20),
    2: (10, 1, 13, 19, 20),
    3: (11, 12, 21, 24, 10, 9),
    4: (6, 12, 14, 16, 5, 13),
    5: (13, 14, 8, 17, 18, 19),
    6: (7, 17, 12, 21, 22, 23),
    7: (6, 10, 25),
    8: (5, 12, 23),
    9: (15, 18, 3, 14),
    10: (7, 2, 3),
    11: (3, 6, 21),
    12: (6, 23, 22, 16, 3),
    13: (5, 1, 2, 19, 20),
    14: (5, 16, 22, 9),
    15: (9, 18, 4, 17),
    16: (12, 14, 22, 23),
    17: (5, 6, 20, 15),
    18: (9, 20, 15, 5),
    19: (1, 2, 13, 20),
    20: (1, 2, 13, 19, 24),
    21: (25, 3, 6),
    22: (14, 16, 6),
    23: (16, 12, 8, 6),
    24: (20, 3, 6),
    25: (21, 1, 7),
}


def table1_score(group, base_draw):
    """Pontuação tradicional: cada posição da extração-base indica 0/1 para o alvo.

    Repetições na base contam novamente porque cada prêmio é percorrido separadamente.
    O valor final é normalizado em 0..1 (máximo 5 fontes/posições).
    """
    g = int(group)
    score = 0
    for prize in (base_draw or {}).get("prizes") or []:
        try:
            src = int(prize.get("grupo"))
        except Exception:
            continue
        if g in TABLE1.get(src, ()):
            score += 1
    return min(1.0, max(0.0, score / 5.0))


class Table1MetaDatabase(mod.Database):
    @staticmethod
    def _meta_feature_names():
        return tuple(mod.Database._meta_feature_names()) + ("table1_score",)

    def _meta_feature_vector(self, group, signals, historical, base_draw):
        base = mod.Database._meta_feature_vector(self, group, signals, historical, base_draw)
        return list(base) + [table1_score(group, base_draw)]


def fetch_history(start=date(2026, 1, 2), end=date(2026, 8, 20)):
    rows = []
    missing = []
    day = start
    total = (end - start).days + 1
    i = 0
    while day <= end:
        i += 1
        ok = False
        last = None
        for attempt in range(3):
            try:
                _url, got = mod.fetch_day(day, timeout=25)
                rows.extend(got)
                ok = True
                break
            except Exception as exc:
                last = exc
                time.sleep(0.8 * (attempt + 1))
        if not ok:
            missing.append((day.isoformat(), str(last)))
        if i % 20 == 0 or day == end:
            print(f"FETCH {i}/{total} dias | {len(rows)} prêmios | falhas={len(missing)}", flush=True)
        day += timedelta(days=1)
    return rows, missing


def make_db(all_rows, cutoff, folder):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "study.db"
    if path.exists():
        path.unlink()
    db = mod.Database(path)
    selected = [r for r in all_rows if str(r.data) <= cutoff]
    db.upsert_rows(selected)
    return path, len(selected)


def meta_summary(result):
    for row in result.get("summary") or []:
        if row.get("method") == "GP-H Meta v0.1":
            return row
    return {}


def detail_map(result):
    out = {}
    for row in result.get("details") or []:
        target = row.get("target") or {}
        key = (target.get("data"), target.get("sorteio"), target.get("hora"))
        sig = (row.get("methods") or {}).get("GP-H Meta v0.1") or {}
        if sig.get("available"):
            out[key] = int(sig.get("coverage_hits") or 0)
    return out


def compare_pair(base, aug):
    a = detail_map(base)
    b = detail_map(aug)
    keys = sorted(set(a) & set(b))
    diffs = [b[k] - a[k] for k in keys]
    return {
        "paired_rounds": len(keys),
        "table1_wins": sum(d > 0 for d in diffs),
        "ties": sum(d == 0 for d in diffs),
        "table1_losses": sum(d < 0 for d in diffs),
        "avg_coverage_diff": (sum(diffs) / len(diffs)) if diffs else 0.0,
        "net_hits": sum(diffs),
    }


def run():
    all_rows, missing = fetch_history()
    print("HISTORY_FETCHED", len(all_rows), "prêmios", "missing_days", len(missing), flush=True)
    if missing:
        print("MISSING", json.dumps(missing[:20], ensure_ascii=False), flush=True)
    # A base tem 5 prêmios por extração. Exigimos cobertura praticamente completa.
    if len(all_rows) < 6200:
        raise RuntimeError(f"Histórico insuficiente para estudo rigoroso: apenas {len(all_rows)} prêmios.")

    cutoffs = ("2026-06-30", "2026-07-31", "2026-08-20")
    reports = []
    for cutoff in cutoffs:
        db_path, nrows = make_db(all_rows, cutoff, TMP / cutoff)
        print(f"\n=== CUTOFF {cutoff} | {nrows} prêmios ===", flush=True)

        db = mod.Database(db_path)
        baseline = db.meta_walk_forward(window=60)
        augdb = Table1MetaDatabase(db_path)
        augmented = augdb.meta_walk_forward(window=60)

        bs = meta_summary(baseline)
        ts = meta_summary(augmented)
        pair = compare_pair(baseline, augmented)
        report = {
            "cutoff": cutoff,
            "baseline": {
                "rounds": bs.get("rounds"),
                "avg_coverage": bs.get("avg_coverage"),
                "pct_2plus": bs.get("pct_2plus"),
                "pct_3plus": bs.get("pct_3plus"),
                "uplift_vs_random": bs.get("uplift_vs_random"),
            },
            "meta_plus_table1": {
                "rounds": ts.get("rounds"),
                "avg_coverage": ts.get("avg_coverage"),
                "pct_2plus": ts.get("pct_2plus"),
                "pct_3plus": ts.get("pct_3plus"),
                "uplift_vs_random": ts.get("uplift_vs_random"),
            },
            "paired": pair,
            "baseline_dates": [baseline.get("date_from"), baseline.get("date_to")],
            "augmented_dates": [augmented.get("date_from"), augmented.get("date_to")],
            "lookahead_safe": bool(baseline.get("lookahead_safe") and augmented.get("lookahead_safe")),
        }
        reports.append(report)
        print("REPORT", json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)

    total_rounds = sum(r["paired"]["paired_rounds"] for r in reports)
    total_net = sum(r["paired"]["net_hits"] for r in reports)
    wins = sum(r["paired"]["table1_wins"] for r in reports)
    ties = sum(r["paired"]["ties"] for r in reports)
    losses = sum(r["paired"]["table1_losses"] for r in reports)
    better_windows = 0
    for r in reports:
        b = r["baseline"]
        t = r["meta_plus_table1"]
        if (t.get("avg_coverage") or 0) > (b.get("avg_coverage") or 0):
            better_windows += 1

    # Regra de admissão conservadora, definida antes de ver os resultados:
    # 1) ganho líquido total > 0;
    # 2) melhora de cobertura em pelo menos 2 das 3 janelas;
    # 3) mais vitórias que derrotas no confronto rodada-a-rodada;
    admit = bool(total_net > 0 and better_windows >= 2 and wins > losses)
    final = {
        "feature": "table1_score",
        "current_meta_features": 20,
        "candidate_features": 21,
        "windows": len(reports),
        "paired_rounds": total_rounds,
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "net_hits": total_net,
        "better_windows": better_windows,
        "admit_table1_into_meta": admit,
        "reports": reports,
    }
    print("\nFINAL_RESULT", json.dumps(final, ensure_ascii=False, sort_keys=True), flush=True)
    (ROOT / "_study_meta_table1_result.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
