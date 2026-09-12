"""Regressões da proteção de amostra mínima da recomendação v0.48.4."""
import unittest

import gph_history_lab as lab
import gph_round_advisor as advisor
from gph_round_advisor_guard import install_round_advisor_guard, MIN_RANKING_SAMPLE


def make_records(n, *, law, law_control, tern=0.0, tern_control=0.0,
                 sorteio="PT", hora="14:00"):
    rows = []
    for i in range(n):
        rows.append({
            "target": {"data": f"2026-09-{(i % 28) + 1:02d}", "sorteio": sorteio, "hora": hora},
            "scores": {
                lab.LAW: {"hit": float(law)},
                lab.CONDITIONAL_RANDOM: {"hit": float(law_control)},
                lab.TERN_CURRENT: {"hit": float(tern)},
                lab.TERN_RANDOM: {"hit": float(tern_control)},
            },
        })
    return rows


class RoundAdvisorGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_round_advisor_guard(advisor, "0.48.4")

    def setUp(self):
        self.target = {"data": "2026-09-12", "sorteio": "PT", "hora": "14:00"}

    def test_one_of_one_cannot_beat_supported_method(self):
        reports = {
            "GP-H Meta v0.2": {"records": make_records(1, law=1.0, law_control=.28, tern=1.0, tern_control=.10)},
            "Similaridade": {"records": make_records(43, law=.163, law_control=.085, tern=.02, tern_control=.02)},
            "Puxada Combinada": {"records": make_records(76, law=.132, law_control=.083, tern=.013, tern_control=.013)},
        }
        rec = advisor.choose_recommendation(reports, self.target)
        self.assertEqual(rec["selector"], "Similaridade")
        self.assertEqual(rec["kind"], "Centena")
        self.assertGreaterEqual(rec["n"], MIN_RANKING_SAMPLE)
        short = rec.get("sample_exclusions") or []
        self.assertTrue(any(row["selector"] == "GP-H Meta v0.2" and row["n"] == 1 for row in short))

    def test_exactly_eight_is_eligible(self):
        reports = {
            "Reset Cobertura": {"records": make_records(8, law=.40, law_control=.10)},
            "Similaridade": {"records": make_records(7, law=.90, law_control=.10)},
        }
        rec = advisor.choose_recommendation(reports, self.target)
        self.assertEqual(rec["selector"], "Reset Cobertura")
        self.assertEqual(rec["n"], 8)
        self.assertEqual(rec["confidence"], "AMOSTRA CURTA")

    def test_all_short_samples_fail_instead_of_guessing(self):
        reports = {
            "Reset Cobertura": {"records": make_records(7, law=.50, law_control=.10)},
            "GP-H Meta v0.2": {"records": make_records(1, law=1.0, law_control=.10)},
        }
        with self.assertRaisesRegex(ValueError, "mínimo de 8 rodadas"):
            advisor.choose_recommendation(reports, self.target)

    def test_fifty_percent_still_not_used_as_cutoff(self):
        reports = {
            "Reset Cobertura": {"records": make_records(20, law=.40, law_control=.10)},
            "Puxada Combinada": {"records": make_records(20, law=.55, law_control=.50)},
        }
        rec = advisor.choose_recommendation(reports, self.target)
        self.assertEqual(rec["selector"], "Reset Cobertura")
        self.assertLess(rec["rate"], .50)
        self.assertAlmostEqual(rec["gain"], .30)


if __name__ == "__main__":
    unittest.main()
