"""Regressões do laboratório: causalidade, isolamento e comparações equivalentes."""
import hashlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import random
import sys
import tempfile
import threading
import unittest
from datetime import date, timedelta
from itertools import combinations

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gph_central as central
import gph_history_lab as lab


def fixture(path, days=18, seed=771):
    db = central.Database(path)
    rng = random.Random(seed)
    day = date(2026, 1, 2)
    with db.connect() as con:
        for offset in range(days):
            current = day+timedelta(days=offset)
            for name, hour in db._operational_schedule_for_date(current.isoformat()):
                for prize in range(1, 6):
                    number = f"{rng.randrange(10000):04d}"
                    group = lab.group_of(number)
                    con.execute("INSERT INTO resultados(data,sorteio,hora,premio,milhar,centena,dezena,grupo,bicho,fonte) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (current.isoformat(), name, hour, prize, number, number[-3:], number[-2:], group, central.BICHOS[group], "https://example.test/result"))
    return db


class HistoricalLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/"test.db"
        self.db = fixture(self.path)
        self.options = {"start": "2026-01-17", "end": "2026-01-18", "scope": "1º–5º", "selector": "Reset Cobertura"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_hierarchy_is_normalized_and_preserves_group_support(self):
        draws, _ = lab.read_history(self.path)
        model = lab.NumberModel()
        target = draws[-1]
        for scope in lab.SCOPES:
            probabilities = model.probabilities(target, scope)
            self.assertAlmostEqual(sum(probabilities), 1)
            self.assertTrue(all(abs(p-.001) < 1e-12 for p in probabilities))
        for d in draws[:-1]:
            model.add(d)
        for scope in lab.SCOPES:
            probabilities = model.probabilities(target, scope)
            self.assertAlmostEqual(sum(probabilities), 1)
            self.assertTrue(all(p > 0 for p in probabilities))
            groups = [1, 5, 12, 20, 25]
            nums = lab.pick_numbers(sorted(range(1000), key=lambda n: -probabilities[n]), groups)
            self.assertEqual(len(set(nums)), 20)
            self.assertEqual({g: sum(lab.group_of(n) == g for n in nums) for g in groups}, {g: 4 for g in groups})
        self.assertEqual(lab.group_of("000"), 25)
        self.assertEqual(lab.group_of("004"), 1)

    def test_terno_optimum_equals_independent_exhaustive_search(self):
        model = lab.TernoModel()
        draws, _ = lab.read_history(self.path)
        for d in draws[:-1]:
            model.add(d)
        groups = [3, 10, 17, 1, 25]
        current = [[3, 10, 17], [3, 10, 1], [3, 17, 1], [10, 17, 1], [3, 10, 25]]
        optimized, score = model.optimize(groups, draws[-1], current)
        probs = model.distribution(groups, draws[-1])
        self.assertAlmostEqual(sum(probs), 1)
        self.assertAlmostEqual(sum(lab.UNIFORM_STATES), 1)
        outcomes = [(set(g for j, g in enumerate(groups) if m & (1 << j)), p) for m, p in enumerate(probs)]
        all_trios = list(combinations(groups, 3))
        brute = max(sum(p for outcome, p in outcomes if any(set(t) <= outcome for t in games))
                    for games in combinations(all_trios, 5))
        self.assertAlmostEqual(score, brute)
        self.assertEqual(len({tuple(sorted(t)) for t in optimized}), 5)
        self.assertTrue(all(len(t) == len(set(t)) == 3 for t in optimized))

    def test_real_generator_integration_readonly_and_no_lookahead(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        first = lab.run_history(central.Database, self.path, self.options)
        self.assertGreater(len(first["records"]), 0)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        target = first["records"][0]["target"]
        # Muda o alvo e todo o futuro: a previsão para esse alvo é idêntica.
        with self.db.connect() as con:
            con.execute("UPDATE resultados SET milhar='0000',centena='000',dezena='00',grupo=25,bicho='Vaca' "
                        "WHERE data > ? OR (data=? AND hora>=?)", (target["data"], target["data"], target["hora"]))
        second = lab.run_history(central.Database, self.path, self.options)
        self.assertEqual(first["records"][0]["predictions"], second["records"][0]["predictions"])
        self.assertEqual(first["records"][0]["groups"], second["records"][0]["groups"])
        for row in first["records"]:
            self.assertLess(lab.stamp(row["base"]), lab.stamp(row["target"]))
            for name in (lab.LAW, lab.HIER, lab.FULL, lab.FREQ, lab.GLOBAL_FREQ):
                self.assertEqual(len(set(row["predictions"][name])), 20)
            for name in (lab.RANDOM, lab.CONDITIONAL_RANDOM, lab.TERN_RANDOM):
                self.assertEqual(len(row["scores"][name]["replicates"]), 200)

    def test_extended_future_does_not_change_prior_predictions(self):
        one = lab.run_history(central.Database, self.path, self.options)
        altered = dict(self.options, end="2026-01-19")
        two = lab.run_history(central.Database, self.path, altered)
        self.assertEqual([r["predictions"] for r in one["records"]],
                         [r["predictions"] for r in two["records"][:len(one["records"])]] )

    def test_gaps_and_invalid_draws_are_not_bridged(self):
        draws, _ = lab.read_history(self.path)
        removed = next(d for d in draws if d["data"] == "2026-01-17" and d["sorteio"] == "PT")
        invalid = next(d for d in draws if d["data"] == "2026-01-18" and d["sorteio"] == "PTV")
        with self.db.connect() as con:
            con.execute("DELETE FROM resultados WHERE data=? AND sorteio=? AND hora=?", lab.key(removed))
            con.execute("UPDATE resultados SET centena='x' WHERE data=? AND sorteio=? AND hora=? AND premio=1", lab.key(invalid))
        result = lab.run_history(central.Database, self.path, self.options)
        self.assertEqual(len(result["integrity"]["excluded"]), 1)
        missing = {lab.key(s["target"]) for s in result["skipped"]}
        self.assertIn(lab.key(removed), missing)
        self.assertIn(lab.key(invalid), missing)
        for r in result["records"]:
            self.assertEqual(lab.key(self.db._reset_expected_target(r["base"])), lab.key(r["target"]))

    def test_other_selectors_and_first_prize(self):
        options = dict(self.options, start="2026-01-17", end="2026-01-17", scope="1º", hour="14:00")
        for selector in lab.SELECTORS:
            result = lab.run_history(central.Database, self.path, dict(options, selector=selector))
            self.assertGreater(len(result["records"]), 0)
            for row in result["records"]:
                actual = row["result"][0][-3:]
                self.assertEqual(row["scores"][lab.HIER]["hit"], int(actual in row["predictions"][lab.HIER]))
                self.assertEqual(row["target"]["hora"], "14:00")

    def test_cancellation_and_insufficient_data(self):
        event = threading.Event()
        event.set()
        result = lab.run_history(central.Database, self.path, self.options, cancel=event)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["records"], [])
        result = lab.run_history(central.Database, self.path, dict(self.options, start="2026-01-02", end="2026-01-03"))
        self.assertEqual(result["records"], [])
        self.assertTrue(result["skipped"])

    def test_statistics_reference_values_and_sparse_audit(self):
        self.assertAlmostEqual(lab.gamma_q(1, 2), math.exp(-2))
        self.assertAlmostEqual(lab.gamma_q(.5, 1), math.erfc(1), places=10)
        self.assertAlmostEqual(lab.gamma_q(4.5, 16.919/2), .05, places=5)
        self.assertIsNone(lab.chi_square([1, 0], [.5, .5], 1))
        rows = [{"p": p} for p in [.01, .04, .03, None]]
        lab.bh_adjust(rows)
        self.assertAlmostEqual(rows[0]["q"], .03)
        draws, _ = lab.read_history(self.path)
        audit = lab.structural_audit(draws[:4])
        self.assertTrue(all(r["q"] is None for r in audit))
        self.assertTrue(all(r["status"] == "amostra insuficiente" for r in audit))

    def test_source_specific_backoff(self):
        draws, _ = lab.read_history(self.path)
        model = lab.NumberModel()
        for d in draws:
            model.add(d)
        unknown_source = dict(draws[-1], source="outra-fonte")
        self.assertTrue(all(abs(p-.001)<1e-12 for p in model.probabilities(unknown_source, "1º–5º")))

    def test_background_worker_spawn_returns_serializable_report(self):
        ctx = mp.get_context("spawn")
        output, cancel = ctx.Queue(), ctx.Event()
        options = dict(self.options, start="2026-01-17", end="2026-01-17", hour="14:00")
        process = ctx.Process(target=lab.history_worker, args=(central.Database, str(self.path), options, output, cancel))
        process.start()
        try:
            while True:
                item = output.get(timeout=30)
                if item[0] != "progress":
                    break
            self.assertEqual(item[0], "done", str(item)[:500])
            self.assertTrue(item[1]["records"])
            json.dumps(item[1], allow_nan=False)
            process.join(timeout=5)
            self.assertEqual(process.exitcode, 0)
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            output.close()

    def test_no_spurious_confirmation_for_empty_or_tied_results(self):
        records = []
        for i in range(30):
            records.append({"target": {"data": (date(2026, 1, 1)+timedelta(days=i)).isoformat()},
                "scores": {n: {"hit": 0} for n in (lab.LAW, lab.HIER, lab.FULL, lab.FREQ,
                    lab.GLOBAL_FREQ, lab.RANDOM, lab.CONDITIONAL_RANDOM, lab.TERN_CURRENT, lab.TERN_OPT, lab.TERN_RANDOM)}})
        summary, evidence = lab.summarize(records)
        self.assertFalse(any(s["status"] == "candidato a teste futuro" for s in summary))
        self.assertTrue(all(e["p_adjusted"] == 1 for e in evidence))


@unittest.skipUnless(sys.platform == "win32" or os.environ.get("DISPLAY"), "interface requer display")
class UIIntegrationTests(unittest.TestCase):
    def test_widget_build_and_reopen(self):
        import tkinter as tk
        from tkinter import ttk
        from gph_history_ui import HistoryLabUI
        with tempfile.TemporaryDirectory() as tmp:
            root = tk.Tk()
            root.withdraw()
            try:
                root.db = fixture(Path(tmp)/"ui.db", days=1)
                root.colors = {"card": "#182029", "text": "#eeeeee"}
                lab_ui = HistoryLabUI(root, central.CalendarField)
                container = ttk.Frame(root)
                container.pack()
                lab_ui.build(container)
                root.update_idletasks()
                self.assertTrue(lab_ui.alive())
                self.assertIn("disabled", lab_ui.cancel_btn.state())
                container.destroy()
                self.assertFalse(lab_ui.alive())
                container = ttk.Frame(root)
                lab_ui.build(container)
                self.assertTrue(lab_ui.alive())
            finally:
                root.destroy()


if __name__ == "__main__":
    unittest.main()
