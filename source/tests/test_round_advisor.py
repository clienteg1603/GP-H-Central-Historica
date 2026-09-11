"""Regressões da recomendação de rodada v0.48.1.

Os testes são deliberadamente puros: a camada escolhe entre resultados já
calculados pelo laboratório v0.48.0 e não precisa abrir a interface para provar
que não usa a meta diagnóstica de 50% como entrada.
"""
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

    def test_choose_best_gain_and_maps_to_playable_method(self):
        reports = {
            "Reset Cobertura": {"records": make_records(
                20, law=.48, law_control=.25, tern=.20, tern_control=.15)},
            "Puxada Combinada": {"records": make_records(
                20, law=.40, law_control=.30, tern=.42, tern_control=.30)},
        }
        rec = advisor.choose_recommendation(reports, self.target)
        self.assertEqual(rec["selector"], "Reset Cobertura")
        self.assertEqual(rec["kind"], "Centena")
        self.assertEqual(rec["method"], "Oficial • Reset + Lei GP-H")
        self.assertEqual(rec["quantity"], 20)
        self.assertAlmostEqual(rec["gain"], .23)

    def test_fifty_percent_is_not_a_selection_input(self):
        # O vencedor está abaixo de 50%, mas tem o maior ganho contra o seu
        # controle equivalente. Se 50% virasse corte/peso, este teste falharia.
        reports = {
            "Reset Cobertura": {"records": make_records(
                20, law=.40, law_control=.10, tern=.10, tern_control=.08)},
            "Puxada Combinada": {"records": make_records(
                20, law=.51, law_control=.49, tern=.45, tern_control=.40)},
        }
        rec = advisor.choose_recommendation(reports, self.target)
        self.assertEqual(rec["selector"], "Reset Cobertura")
        self.assertEqual(rec["kind"], "Centena")
        self.assertLess(rec["rate"], .50)
        self.assertAlmostEqual(rec["gain"], .30)

    def test_prefers_exact_draw_context_with_enough_support(self):
        exact = make_records(8, sorteio="PT", hora="14:00", law=.75, law_control=.20,
                             tern=.10, tern_control=.10)
        other = make_records(20, sorteio="OUTRO", hora="14:00", law=.05, law_control=.20,
                             tern=.05, tern_control=.10)
        candidates = advisor.candidates_from_report(
            "Reset Cobertura", {"records": exact + other}, self.target)
        centena = next(row for row in candidates if row["kind"] == "Centena")
        self.assertEqual(centena["context"], "mesma extração e horário")
        self.assertEqual(centena["n"], 8)
        self.assertAlmostEqual(centena["rate"], .75)

    def test_falls_back_to_same_hour_when_exact_sample_is_short(self):
        exact = make_records(7, sorteio="PT", hora="14:00", law=.70, law_control=.20,
                             tern=.20, tern_control=.10)
        other = make_records(13, sorteio="OUTRO", hora="14:00", law=.20, law_control=.20,
                             tern=.20, tern_control=.10)
        candidates = advisor.candidates_from_report(
            "Reset Cobertura", {"records": exact + other}, self.target)
        centena = next(row for row in candidates if row["kind"] == "Centena")
        self.assertEqual(centena["context"], "mesmo horário")
        self.assertEqual(centena["n"], 20)
        self.assertAlmostEqual(centena["rate"], (7*.70 + 13*.20) / 20)

    def test_empty_report_is_rejected_instead_of_guessing(self):
        with self.assertRaises(ValueError):
            advisor.choose_recommendation({
                "Reset Cobertura": {"records": []},
                "Puxada Combinada": {"records": []},
            }, self.target)

    def test_only_playable_tested_pairs_are_exposed(self):
        self.assertEqual(set(advisor.PLAY_MAPPING), {"Reset Cobertura", "Puxada Combinada"})
        for selector in advisor.PLAY_MAPPING.values():
            self.assertEqual(set(selector), {"Centena", "Terno de Grupo"})
        self.assertEqual(advisor.PLAY_MAPPING["Reset Cobertura"]["Terno de Grupo"]["quantity"], 5)


if __name__ == "__main__":
    unittest.main()
