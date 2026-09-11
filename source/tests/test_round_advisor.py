"""Regressões da recomendação da rodada v0.48.2."""
import json
import sqlite3
import unittest

import gph_history_lab as lab
import gph_round_advisor as advisor


def make_records(n, sorteio="PT", hora="14:00", *, law=0.0, law_control=0.0,
                 tern=0.0, tern_control=0.0):
    rows = []
    for i in range(n):
        rows.append({
            "target": {"data": f"2026-08-{(i % 28) + 1:02d}", "sorteio": sorteio, "hora": hora},
            "scores": {
                lab.LAW: {"hit": float(law)},
                lab.CONDITIONAL_RANDOM: {"hit": float(law_control)},
                lab.TERN_CURRENT: {"hit": float(tern)},
                lab.TERN_RANDOM: {"hit": float(tern_control)},
            },
        })
    return rows


class RoundAdvisorTests(unittest.TestCase):
    def setUp(self):
        self.target = {"data": "2026-09-10", "sorteio": "PT", "hora": "14:00"}

    def test_choose_best_across_methods_and_modalities(self):
        reports = {
            "Reset Cobertura": {"records": make_records(20, law=.48, law_control=.25, tern=.20, tern_control=.15)},
            "Puxada Combinada": {"records": make_records(20, law=.40, law_control=.30, tern=.42, tern_control=.30)},
            "Similaridade": {"records": make_records(20, law=.44, law_control=.25, tern=.36, tern_control=.20)},
            "Histórico Concentrado": {"records": make_records(20, law=.90, law_control=.10, tern=.46, tern_control=.20)},
            "GP-H Meta v0.2": {"records": make_records(20, law=.39, law_control=.25, tern=.52, tern_control=.20)},
        }
        rec = advisor.choose_recommendation(reports, self.target)
        self.assertEqual(rec["selector"], "GP-H Meta v0.2")
        self.assertEqual(rec["kind"], "Terno de Grupo")
        self.assertEqual(rec["method"], "★ META • GP-H Meta v0.2")
        self.assertEqual(rec["quantity"], 5)
        self.assertAlmostEqual(rec["gain"], .32)
        self.assertFalse(any(
            row["selector"] == "Histórico Concentrado" and row["kind"] == "Centena"
            for row in [rec] + rec["alternatives"]
        ))

    def test_fifty_percent_is_not_selection_input(self):
        reports = {
            "Reset Cobertura": {"records": make_records(20, law=.40, law_control=.10, tern=.10, tern_control=.08)},
            "Puxada Combinada": {"records": make_records(20, law=.51, law_control=.49, tern=.45, tern_control=.40)},
        }
        rec = advisor.choose_recommendation(reports, self.target)
        self.assertEqual(rec["selector"], "Reset Cobertura")
        self.assertEqual(rec["kind"], "Centena")
        self.assertLess(rec["rate"], .50)
        self.assertAlmostEqual(rec["gain"], .30)

    def test_prefers_exact_context_with_enough_support(self):
        exact = make_records(8, sorteio="PT", hora="14:00", law=.75, law_control=.20, tern=.10, tern_control=.10)
        other = make_records(20, sorteio="OUTRO", hora="14:00", law=.05, law_control=.20, tern=.05, tern_control=.10)
        candidates = advisor.candidates_from_report("Similaridade", {"records": exact + other}, self.target)
        centena = next(row for row in candidates if row["kind"] == "Centena")
        self.assertEqual(centena["context"], "mesma extração e horário")
        self.assertEqual(centena["n"], 8)
        self.assertAlmostEqual(centena["rate"], .75)

    def test_falls_back_to_same_hour_when_exact_sample_is_short(self):
        exact = make_records(7, sorteio="PT", hora="14:00", law=.70, law_control=.20, tern=.20, tern_control=.10)
        other = make_records(13, sorteio="OUTRO", hora="14:00", law=.20, law_control=.20, tern=.20, tern_control=.10)
        candidates = advisor.candidates_from_report("Reset Cobertura", {"records": exact + other}, self.target)
        centena = next(row for row in candidates if row["kind"] == "Centena")
        self.assertEqual(centena["context"], "mesmo horário")
        self.assertEqual(centena["n"], 20)
        self.assertAlmostEqual(centena["rate"], (7*.70 + 13*.20) / 20)

    def test_empty_reports_are_rejected_instead_of_guessing(self):
        with self.assertRaises(ValueError):
            advisor.choose_recommendation({name: {"records": []} for name in advisor.PLAY_MAPPING}, self.target)

    def test_play_mapping_contains_every_comparable_method(self):
        self.assertEqual(set(advisor.PLAY_MAPPING), {
            "Reset Cobertura", "Puxada Combinada", "Similaridade",
            "Histórico Concentrado", "GP-H Meta v0.2",
        })
        self.assertEqual(set(advisor.PLAY_MAPPING["Histórico Concentrado"]), {"Terno de Grupo"})
        for name in ("Reset Cobertura", "Puxada Combinada", "Similaridade", "GP-H Meta v0.2"):
            self.assertEqual(set(advisor.PLAY_MAPPING[name]), {"Centena", "Terno de Grupo"})

    def test_historical_concentrated_preview_is_editable_as_terno(self):
        rows = [{"numero": "01-02-03"}, {"numero": "01-02-04"}]
        kind, selected = advisor._generation_rows_for_edit({
            "historical_concentrated": True,
            "kind": "Fechamento de Grupo",
            "rows": rows,
        })
        self.assertEqual(kind, "Terno de Grupo")
        self.assertEqual(selected, rows)

    def test_frozen_meta_reader_requires_real_freeze_and_five_distinct_groups(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE decision_snapshots(target_data TEXT,target_sorteio TEXT,target_hora TEXT,meta_json TEXT,meta_frozen_at TEXT,id INTEGER)")
        con.execute("INSERT INTO decision_snapshots VALUES(?,?,?,?,?,?)", (
            "2026-08-10", "PT", "14:00", json.dumps({"available": True, "groups": [1,2,3,4,5]}), "2026-08-10T13:59:00", 1))
        con.execute("INSERT INTO decision_snapshots VALUES(?,?,?,?,?,?)", (
            "2026-08-11", "PT", "14:00", json.dumps({"available": True, "groups": [6,7,8,9,10]}), None, 2))
        con.execute("INSERT INTO decision_snapshots VALUES(?,?,?,?,?,?)", (
            "2026-08-12", "PT", "14:00", json.dumps({"available": True, "groups": [1,1,2,3,4]}), "2026-08-12T13:59:00", 3))
        con.commit()

        class FakeDB:
            def connect(self):
                return con

        mapping, diag = advisor._load_frozen_meta_groups(FakeDB(), "2026-08-01", "2026-08-31", "14:00")
        self.assertEqual(mapping, {"2026-08-10|PT|14:00": [1,2,3,4,5]})
        self.assertEqual(diag["eligible_rows"], 1)
        self.assertEqual(diag["rejected_rows"], 1)

    def test_frozen_selector_constant_is_separate_from_reconstructed_selectors(self):
        self.assertNotIn(lab.FROZEN_SELECTOR, lab.SELECTORS)
        self.assertIn("Similaridade", lab.SELECTORS)


if __name__ == "__main__":
    unittest.main()
