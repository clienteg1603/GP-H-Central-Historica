"""Pesquisa histórica isolada. Não grava resultados, jogos ou snapshots do usuário.

Protocolo 1: parâmetros fixos; treino expansivo, previsão antes da inserção do
alvo, comparação pareada. Resultados retrospectivos continuam exploratórios.
Somente biblioteca padrão, inclusive no executável Windows.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path
from urllib.parse import urlparse

PROTOCOL = "GP-H Pesquisa Histórica v1"
SELECTORS = {
    "Reset Cobertura": "method_reset_coverage_v1",
    "Puxada Combinada": "method_convergencia_g5",
    "Histórico Concentrado": "method_historico_concentrado_v01",
}
RANDOM_REPEATS = 200
MIN_TRAIN = 60
SEED = 478049
SCOPES = ("1º–5º", "1º")
LAW = "Lei GP-H atual"
HIER = "Hierárquica · mesmos 5 bichos"
FULL = "Hierárquica · seleção completa"
FREQ = "Frequência · mesmos 5 bichos"
GLOBAL_FREQ = "Frequência · seleção completa"
RANDOM = "Acaso · 20 entre 1.000"
CONDITIONAL_RANDOM = "Acaso · mesmos 5 bichos"
TERN_CURRENT = "5 Ternos · montagem atual"
TERN_OPT = "5 Ternos · cobertura conjunta"
TERN_RANDOM = "5 Ternos · montagem aleatória"


def group_of(number):
    return ((int(number) % 100 - 1) % 100) // 4 + 1


def key(draw):
    return draw["data"], draw["sorteio"], draw["hora"]


def stamp(draw):
    return draw["data"], draw["hora"]


def context(draw):
    return draw["source"], draw["sorteio"], draw["hora"]


def seeded(*parts):
    digest = hashlib.sha256(json.dumps([SEED, *parts], ensure_ascii=False).encode()).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def read_history(path):
    """Uma leitura consistente, somente leitura; rejeita a extração inteira se inválida."""
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute(
            "SELECT data,sorteio,hora,premio,milhar,centena,dezena,grupo,bicho,fonte "
            "FROM resultados ORDER BY data,hora,sorteio,premio"
        )]
    finally:
        con.close()
    batches = defaultdict(list)
    for row in rows:
        batches[key(row)].append(row)
    audit = {"input_rows": len(rows), "valid_draws": 0, "excluded": [], "sources": []}
    draws = []
    for draw_key, prizes in batches.items():
        reasons = []
        day, sorteio, hour = draw_key
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError()
        except (ValueError, TypeError):
            reasons.append("data inválida")
        if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", str(hour)):
            reasons.append("hora inválida")
        if sorted(p["premio"] for p in prizes) != [1, 2, 3, 4, 5]:
            reasons.append("prêmios ausentes ou duplicados")
        sources = set()
        for p in prizes:
            number = str(p["milhar"])
            if not re.fullmatch(r"[0-9]{4}", number):
                reasons.append("milhar sem quatro dígitos")
            elif (p["centena"] != number[-3:] or p["dezena"] != number[-2:]
                  or p["grupo"] != group_of(number)):
                reasons.append("derivados inconsistentes")
            source = str(p.get("fonte") or "não informada").strip()
            sources.add((urlparse(source).hostname or source).lower())
        if len(sources) != 1:
            reasons.append("fontes diferentes na mesma extração")
        if reasons:
            audit["excluded"].append({"key": list(draw_key), "reasons": sorted(set(reasons))})
            continue
        draws.append({"data": day, "sorteio": sorteio, "hora": hour,
                      "source": next(iter(sources)), "prizes": prizes})
    audit["valid_draws"] = len(draws)
    audit["sources"] = sorted({d["source"] for d in draws})
    return draws, audit


def gamma_q(a, x):
    """Cauda da gama regularizada para o teste qui-quadrado (sem SciPy)."""
    if x <= 0:
        return 1.0
    logscale = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1:
        term = total = 1.0 / a
        ap = a
        for _ in range(10000):
            ap += 1
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1e-13:
                break
        return max(0.0, min(1.0, 1 - total * math.exp(logscale)))
    b = x + 1 - a
    c = 1e300
    d = 1.0 / max(b, 1e-300)
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        if abs(d) < 1e-300:
            d = 1e-300
        c = b + an / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-13:
            break
    return max(0.0, min(1.0, h * math.exp(logscale)))


def chi_square(observed, expected, df):
    if df < 1 or not expected or min(expected) < 5:
        return None
    statistic = sum((o - e) ** 2 / e for o, e in zip(observed, expected))
    return gamma_q(df / 2, statistic / 2)


def bh_adjust(rows):
    valid = sorted((r for r in rows if r["p"] is not None), key=lambda r: r["p"])
    q = 1.0
    for i in range(len(valid) - 1, -1, -1):
        q = min(q, valid[i]["p"] * len(valid) / (i + 1))
        valid[i]["q"] = q


def structural_audit(draws, cancel=None):
    series = defaultdict(list)
    for draw in draws:
        for p in draw["prizes"]:
            series[(*context(draw), p["premio"])].append(p["milhar"])
    rows = []
    names = ("Milhar", "Centena", "Dezena", "Unidade")
    for ctx, numbers in sorted(series.items()):
        if cancel is not None and cancel.is_set():
            break
        n = len(numbers)
        def add(test, p, effect, halves):
            rows.append({"source": ctx[0], "sorteio": ctx[1], "hora": ctx[2],
                         "prize": ctx[3], "test": test, "n": n, "p": p,
                         "q": None, "effect": effect, "halves": halves})
        for pos, label in enumerate(names):
            values = [int(v[pos]) for v in numbers]
            counts = Counter(values)
            effect = max(abs(counts[d] / n - .1) for d in range(10))
            parts = (values[:n // 2], values[n // 2:])
            halves = [max(abs(Counter(part)[d] / len(part) - .1) for d in range(10))
                      if part else None for part in parts]
            add(label + " · uniformidade", chi_square([counts[i] for i in range(10)],
                [n / 10] * 10, 9), effect, halves)
            pairs = Counter(zip(values, values[1:]))
            left, right = Counter(values[:-1]), Counter(values[1:])
            ls, rs = sorted(left), sorted(right)
            expected = [left[a] * right[b] / (n - 1) for a in ls for b in rs] if n > 1 else []
            add(label + " · dependência entre extrações",
                chi_square([pairs[a, b] for a in ls for b in rs], expected, (len(ls) - 1) * (len(rs) - 1)),
                sum(a == b for a, b in zip(values, values[1:])) / max(1, n - 1), [])
        repeat = [int(len(set(v)) < 4) for v in numbers]
        hits = sum(repeat)
        # 1 - (10*9*8*7)/10^4 = 0,496 sob quatro dígitos iid uniformes.
        add("Dígitos repetidos na milhar", chi_square([hits, n - hits], [.496*n, .504*n], 1),
            hits / n, [sum(p)/len(p) if p else None for p in (repeat[:n//2], repeat[n//2:])])
    bh_adjust(rows)
    for row in rows:
        row["status"] = ("amostra insuficiente" if row["p"] is None else
                         "sinal exploratório" if row["q"] <= .05 else "sem desvio demonstrado")
    return rows


class NumberModel:
    """Cadeia grupo -> dezena do grupo -> algarismo da centena, por prêmio.

    Backoff sempre dentro da mesma fonte. A média das cinco distribuições é
    massa por prêmio, não uma probabilidade de acerto em qualquer dos prêmios.
    """
    def __init__(self):
        self.counts = defaultdict(Counter)
        self.last = defaultdict(dict)
        self.support = Counter()

    def add(self, draw):
        for p in draw["prizes"]:
            for ctx in ((draw["source"],), context(draw)):
                ident = (*ctx, p["premio"])
                self.counts[ident][p["centena"]] += 1
                self.last[ident][p["centena"]] = (*stamp(draw), draw["sorteio"], p["premio"])
        self.support[context(draw)] += 1

    @staticmethod
    def margins(counts):
        groups, ends = Counter(), Counter()
        for number, count in counts.items():
            groups[group_of(number)] += count
            ends[number[-2:]] += count
        return groups, ends

    def probabilities(self, target, scope):
        positions = [1] if scope == "1º" else range(1, 6)
        out = [0.0] * 1000
        for pos in positions:
            pool = self.counts[(target["source"], pos)]
            local = self.counts[(*context(target), pos)]
            pg, pd = self.margins(pool)
            lg, ld = self.margins(local)
            pn, ln = sum(pool.values()), sum(local.values())
            for num in range(1000):
                text = f"{num:03d}"
                g, d = group_of(text), text[-2:]
                gp = (pg[g] + 1) / (pn + 25)
                dp = (pd[d] + 1) / (pg[g] + 4)
                cp = (pool[text] + 1) / (pd[d] + 10)
                out[num] += ((lg[g] + 50*gp) / (ln+50)
                             * (ld[d] + 8*dp) / (lg[g]+8)
                             * (local[text] + 20*cp) / (ld[d]+20)) / len(positions)
        return out

    def frequency_ranking(self, target, scope):
        counts, lasts = Counter(), {}
        for pos in ([1] if scope == "1º" else range(1, 6)):
            ident = (target["source"], pos)
            counts.update(self.counts[ident])
            for num, at in self.last[ident].items():
                lasts[num] = max(lasts.get(num, ()), at)
        return sorted(range(1000), key=lambda n: (counts[f"{n:03d}"],
                      lasts.get(f"{n:03d}", ()), -n), reverse=True)


def pick_numbers(ranking, groups=None):
    if groups is None:
        return [f"{n:03d}" for n in ranking[:20]]
    result = []
    for g in groups:
        result.extend([f"{n:03d}" for n in ranking if group_of(n) == g][:4])
    return result


TRIPLES = list(combinations(range(5), 3))
TRIPLE_MASKS = [sum(1 << i for i in c) for c in TRIPLES]
PORTFOLIOS = list(combinations(range(10), 5))
PORTFOLIO_STATES = [tuple(m for m in range(32) if any(
    m & TRIPLE_MASKS[t] == TRIPLE_MASKS[t] for t in portfolio)) for portfolio in PORTFOLIOS]
UNIFORM_STATES = [sum((-1)**j * math.comb(m.bit_count(), j) *
    ((20 + m.bit_count() - j)/25)**5 for j in range(m.bit_count()+1)) for m in range(32)]


class TernoModel:
    def __init__(self):
        self.counts = defaultdict(Counter)

    def add(self, draw):
        mask = sum(1 << (g-1) for g in {p["grupo"] for p in draw["prizes"]})
        self.counts[(draw["source"],)][mask] += 1
        self.counts[context(draw)][mask] += 1

    def distribution(self, groups, target):
        def projected(counter):
            counts = Counter()
            for mask, n in counter.items():
                subset = sum(1 << i for i, g in enumerate(groups) if mask & (1 << (g-1)))
                counts[subset] += n
            return counts
        pool = projected(self.counts[(target["source"],)])
        local = projected(self.counts[context(target)])
        pn, ln = sum(pool.values()), sum(local.values())
        return [(local[m] + 30 * (pool[m]+20*UNIFORM_STATES[m])/(pn+20))/(ln+30)
                for m in range(32)]

    def optimize(self, groups, target, current):
        probs = self.distribution(groups, target)
        indices = tuple(sorted(TRIPLES.index(tuple(sorted(groups.index(g) for g in t))) for t in current))
        best = PORTFOLIOS.index(indices)
        score = sum(probs[m] for m in PORTFOLIO_STATES[best])
        for i, states in enumerate(PORTFOLIO_STATES):
            candidate = sum(probs[m] for m in states)
            if candidate > score + 1e-12:
                best, score = i, candidate
        return [[groups[j] for j in TRIPLES[t]] for t in PORTFOLIOS[best]], score


def wilson(hits, n):
    if not n:
        return [None, None]
    z = 1.959963984540054
    p = hits/n
    mid = (p+z*z/(2*n))/(1+z*z/n)
    radius = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return [max(0.0, mid-radius), min(1.0, mid+radius)]


def paired_evidence(records, candidate, comparator):
    deltas = [r["scores"][candidate]["hit"]-r["scores"][comparator]["hit"] for r in records]
    by_day = defaultdict(list)
    for row, delta in zip(records, deltas):
        by_day[row["target"]["data"]].append(delta)
    blocks = list(by_day.values())
    n = len(deltas)
    result = {"candidate": candidate, "comparator": comparator, "n": n,
              "days": len(blocks), "delta": sum(deltas)/n if n else None,
              "interval": [None, None], "p": None, "p_adjusted": None,
              "halves": [sum(p)/len(p) if p else None for p in (deltas[:n//2], deltas[n//2:])]}
    if len(blocks) < 10:
        return result
    rng = seeded("paired", candidate, comparator)
    totals = [(sum(b), len(b)) for b in blocks]
    sampled, more = [], 0
    observed = abs(sum(deltas))
    for _ in range(999):
        sample = [totals[rng.randrange(len(totals))] for _ in totals]
        sampled.append(sum(v for v, _ in sample)/sum(k for _, k in sample))
        permuted = sum(v * rng.choice((-1, 1)) for v, _ in totals)
        more += abs(permuted) >= observed - 1e-12
    sampled.sort()
    result.update(interval=[sampled[24], sampled[974]], p=(1+more)/1000)
    return result


def summarize(records):
    summary = []
    names = list(records[0]["scores"]) if records else []
    for name in names:
        scores = [r["scores"][name] for r in records]
        hits = sum(s["hit"] for s in scores)
        simulations = [sum(s["replicates"][i] for s in scores)/len(scores)
                       for i in range(RANDOM_REPEATS)] if "replicates" in scores[0] else []
        simulations.sort()
        summary.append({"method": name, "n": len(scores), "hits": hits,
                        "rate": hits/len(scores),
                        "interval": [simulations[4], simulations[194]] if simulations else wilson(hits, len(scores)),
                        "interval_kind": "faixa de simulação" if simulations else "Wilson descritivo",
                        "near2": sum(s.get("near2", 0) for s in scores),
                        "status": "controle"})
    pairs = [(HIER, LAW), (HIER, FREQ), (HIER, CONDITIONAL_RANDOM),
             (FULL, GLOBAL_FREQ), (FULL, RANDOM), (TERN_OPT, TERN_CURRENT), (TERN_OPT, TERN_RANDOM)]
    evidence = [paired_evidence(records, a, b) for a, b in pairs]
    valid = sorted((r for r in evidence if r["p"] is not None), key=lambda r: r["p"])
    last = 0.0
    for i, r in enumerate(valid):
        last = max(last, min(1.0, r["p"]*(len(valid)-i)))
        r["p_adjusted"] = last
    for row in summary:
        tests = [r for r in evidence if r["candidate"] == row["method"]]
        if tests:
            if not records:
                row["status"] = "inconclusivo"
            elif any(r["delta"] <= 0 for r in tests):
                row["status"] = "sem ganho demonstrado"
            elif all(r["days"] >= 20 and r["p_adjusted"] is not None and r["p_adjusted"] <= .05
                     and r["interval"][0] > 0 and all(v is not None and v > 0 for v in r["halves"])
                     for r in tests):
                row["status"] = "candidato a teste futuro"
            else:
                row["status"] = "inconclusivo"
    return summary, evidence


def run_history(db_class, db_path, options, progress=None, cancel=None):
    """Executa em cópia SQLite na memória; nenhum método lê o banco completo."""
    start, end = options["start"], options["end"]
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("A data inicial deve ser anterior ou igual à final.")
    scope = options.get("scope", SCOPES[0])
    selector = options.get("selector", next(iter(SELECTORS)))
    if scope not in SCOPES or selector not in SELECTORS:
        raise ValueError("Escopo ou seletor inválido.")
    draws, integrity = read_history(db_path)
    draws = [d for d in draws if d["data"] <= end]

    class PrefixDatabase(db_class):
        def __init__(self):
            self._memory = sqlite3.connect(":memory:")
            self._memory.row_factory = sqlite3.Row
            self.init_schema()

        def connect(self):
            return self._memory

    db = PrefixDatabase()
    number_model, terno_model = NumberModel(), TernoModel()
    index = {key(d): i for i, d in enumerate(draws)}
    pending = {}
    skipped = []
    for i, base in enumerate(draws):
        if not db._is_operational_draw(base):
            continue
        target = db._reset_expected_target(base)
        if not target or not start <= target["data"] <= end:
            continue
        if options.get("hour") and target["hora"] != options["hour"]:
            continue
        j = index.get(key(target))
        if j is None:
            skipped.append({"target": target, "reason": "alvo esperado ausente ou inválido"})
        elif stamp(draws[j]) <= stamp(base):
            skipped.append({"target": target, "reason": "ordem temporal ambígua"})
        elif i+1 < MIN_TRAIN:
            skipped.append({"target": target, "reason": f"treino menor que {MIN_TRAIN} extrações"})
        else:
            pending[i] = draws[j]
    records = []
    con = db._memory
    try:
        for i, base in enumerate(draws):
            if cancel is not None and cancel.is_set():
                break
            for p in base["prizes"]:
                con.execute("INSERT INTO resultados(data,sorteio,hora,premio,milhar,centena,dezena,grupo,bicho,fonte) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?)", tuple(p[c] for c in
                            ("data", "sorteio", "hora", "premio", "milhar", "centena", "dezena", "grupo", "bicho", "fonte")))
            con.commit()
            number_model.add(base)
            terno_model.add(base)
            if i not in pending:
                continue
            target = pending[i]
            if progress:
                progress(len(records), len(pending), f"{target['data']} · {target['sorteio']} {target['hora']}")
            try:
                selection = getattr(db, SELECTORS[selector])(*key(base), top_n=5)
                groups = [int(r["grupo"]) for r in selection.get("selected", [])]
                if len(groups) != 5 or len(set(groups)) != 5:
                    raise ValueError("seletor não produziu cinco grupos distintos")
                current = db.generate_gph_law_numbers(groups, total=20, scope=scope, previous_draw=base)
                law_numbers = [r["numero"] for r in current["rows"]]
                current_ternos = [[int(g) for g in r["numero"].split("-")] for r in
                                  db.generate_group_combinations(groups, "Terno de Grupo", total=5)["rows"]]
            except ValueError as exc:
                skipped.append({"target": {k: target[k] for k in ("data", "sorteio", "hora")}, "reason": str(exc)})
                continue
            probabilities = number_model.probabilities(target, scope)
            ranking = sorted(range(1000), key=lambda n: (-probabilities[n], n))
            freq_rank = number_model.frequency_ranking(target, scope)
            optimized, objective = terno_model.optimize(groups, target, current_ternos)
            predictions = {LAW: law_numbers, HIER: pick_numbers(ranking, groups),
                           FULL: pick_numbers(ranking), FREQ: pick_numbers(freq_rank, groups),
                           GLOBAL_FREQ: pick_numbers(freq_rank), TERN_CURRENT: current_ternos, TERN_OPT: optimized}
            # O alvo é consultado SOMENTE após a geração completa dos palpites.
            target_prizes = target["prizes"][:1] if scope == "1º" else target["prizes"]
            actual = {p["centena"] for p in target_prizes}
            actual_groups = {p["grupo"] for p in target["prizes"]}
            scores = {}
            for name, values in predictions.items():
                if name in (TERN_CURRENT, TERN_OPT):
                    best = max(len(set(t) & actual_groups) for t in values)
                    scores[name] = {"hit": int(best == 3), "near2": int(best == 2)}
                else:
                    if len(values) != 20 or len(set(values)) != 20:
                        raise AssertionError("Comparação exige 20 Centenas distintas.")
                    scores[name] = {"hit": int(bool(set(values) & actual)), "matched": sorted(set(values) & actual)}
            rng = seeded("controls", list(key(target)), scope, selector)
            all_ternos = [list(t) for t in combinations(groups, 3)]
            pools = {g: [f"{n:03d}" for n in range(1000) if group_of(n) == g] for g in groups}
            random_hits = {RANDOM: [], CONDITIONAL_RANDOM: [], TERN_RANDOM: []}
            for _ in range(RANDOM_REPEATS):
                random_hits[RANDOM].append(int(any(f"{n:03d}" in actual for n in rng.sample(range(1000), 20))))
                chosen = [n for g in groups for n in rng.sample(pools[g], 4)]
                random_hits[CONDITIONAL_RANDOM].append(int(bool(set(chosen) & actual)))
                chosen_ternos = rng.sample(all_ternos, 5)
                random_hits[TERN_RANDOM].append(int(any(set(t) <= actual_groups for t in chosen_ternos)))
            for name, hits in random_hits.items():
                scores[name] = {"hit": sum(hits)/RANDOM_REPEATS, "replicates": hits}
            records.append({"base": {k: base[k] for k in ("data", "sorteio", "hora")},
                "target": {k: target[k] for k in ("data", "sorteio", "hora", "source")},
                "train_draws": i+1, "context_train_draws": number_model.support[context(target)],
                "groups": groups, "predictions": predictions, "scores": scores,
                "result": [p["milhar"] for p in target["prizes"]], "terno_training_objective": objective})
    finally:
        con.close()
    if progress:
        progress(len(records), max(1, len(pending)), "Calculando auditoria e incerteza por dia…")
    subset = [d for d in draws if start <= d["data"] <= end and
              (not options.get("hour") or d["hora"] == options["hour"])]
    structural = structural_audit(subset, cancel)
    summary, evidence = summarize(records)
    if cancel is not None and cancel.is_set():
        for row in summary:
            if row["status"] != "controle":
                row["status"] = "inconclusivo · teste interrompido"
    hourly = []
    for ctx in sorted({context(r["target"]) for r in records}):
        part = [r for r in records if context(r["target"]) == ctx]
        for name in (LAW, HIER, FULL, TERN_CURRENT, TERN_OPT):
            hits = sum(r["scores"][name]["hit"] for r in part)
            hourly.append({"source": ctx[0], "sorteio": ctx[1], "hora": ctx[2], "method": name,
                           "n": len(part), "hits": hits, "rate": hits/len(part)})
    payload = json.dumps(draws, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {"protocol": PROTOCOL, "options": dict(options), "parameters": {
        "minimum_training_draws": MIN_TRAIN, "random_repetitions": RANDOM_REPEATS, "seed": SEED,
        "number_backoff": [25, 4, 10, 50, 8, 20], "terno_backoff": [20, 30],
        "resamples_per_comparison": 999, "multiple_comparisons": "Holm / auditoria BH"},
        "data_sha256": hashlib.sha256(payload).hexdigest(), "integrity": integrity,
        "cancelled": bool(cancel and cancel.is_set()), "records": records, "skipped": skipped,
        "summary": summary, "evidence": evidence, "hourly": hourly, "structural": structural,
        "limitations": [
            "Histórico já explorado: esta simulação não é confirmação independente nem prova de previsão.",
            "Usa a ordem das extrações da base atual; não reconstitui horários originais de publicação nem correções antigas.",
            "Nenhum resultado é aposta realizada; 2/3 não é vitória. Não se calcula lucro sem cotações.",
            "Centenas: 20 únicas. Ternos: cinco combinações dos mesmos cinco bichos, sempre do 1º ao 5º.",
            "Backoff numérico e Ternos separados por fonte; seletor e Lei GP-H usam sua lógica atual em cópia causal.",
            "Wilson é descritivo; comparações usam reamostragem/sinais por dia e pressupõem dias aproximadamente independentes.",
            "Uniformidade e dependência usam aproximação qui-quadrado; células esperadas menores que 5 não recebem p-valor.",
            "A auditoria é exploratória, corrige múltiplos testes com BH e não alimenta modelos automaticamente.",
            "Um candidato precisa de confirmação futura com parâmetros congelados; nenhum método é promovido automaticamente."]}


def history_worker(db_class, path, options, output, cancel):
    try:
        def progress(done, total, label):
            output.put(("progress", done, total, label))
        output.put(("done", run_history(db_class, path, options, progress, cancel)))
    except BaseException as exc:
        output.put(("error", f"{type(exc).__name__}: {exc}"))
