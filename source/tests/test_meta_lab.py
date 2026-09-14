import copy
import unittest

import gph_meta_lab as lab


def record(actual=None, signals=None):
    ranking = [
        {"rank": rank, "group": group, "score": 100 - rank}
        for rank, group in enumerate(range(1, 11), 1)
    ]
    return {
        "data": "2026-09-14",
        "sorteio": "PT",
        "hora": "14:00",
        "top5": [1, 2, 3, 4, 5],
        "ranking": ranking,
        "signals": signals or {},
        "support": lab._support_map(signals or {}),
        "actual": actual or [1, 2, 8, 9, 10],
    }


class MetaLabTests(unittest.TestCase):
    def test_lab_contract_never_changes_official_brain(self):
        self.assertTrue(lab.META_LAB_INFO["experimental_only"])
        self.assertFalse(lab.META_LAB_INFO["changes_meta"])
        self.assertFalse(lab.META_LAB_INFO["changes_weights"])
        self.assertFalse(lab.META_LAB_INFO["changes_scores"])
        self.assertFalse(lab.META_LAB_INFO["changes_generators"])
        self.assertFalse(lab.META_LAB_INFO["changes_betting"])
        self.assertTrue(lab.META_LAB_INFO["uses_only_frozen_inputs"])

    def test_consensus_guard_swaps_only_one_low_support_boundary_group(self):
        row = record(signals={"Reset": [6], "Puxada": [6], "Historico": [4]})
        self.assertEqual(lab.select_consensus_guard(row), [1, 2, 3, 4, 6])
        self.assertEqual(row["top5"], [1, 2, 3, 4, 5])

    def test_border_variant_keeps_top3_and_reorders_only_four_to_eight(self):
        row = record(
            signals={
                "Reset": [6, 4],
                "Puxada": [6, 7],
                "Similaridade": [7],
            }
        )
        chosen = lab.select_border_4_8(row)
        self.assertEqual(chosen[:3], [1, 2, 3])
        self.assertEqual(set(chosen[3:]), {6, 7})

    def test_candidate_selection_does_not_look_at_result(self):
        base = record(signals={"Reset": [6, 7], "Puxada": [6], "Historico": [8]})
        other = copy.deepcopy(base)
        other["actual"] = [20, 21, 22, 23, 24]
        for selector in (
            lab.select_official,
            lab.select_consensus_guard,
            lab.select_border_4_8,
            lab.select_consensus_3_10,
        ):
            self.assertEqual(selector(base), selector(other))

    def test_first_21_are_baseline_and_22nd_starts_prospective_lab(self):
        rows = [record(actual=[1, 11, 12, 13, 14]) for _ in range(23)]
        report = lab.evaluate_lab(rows)
        self.assertEqual(report["baseline_n"], 21)
        self.assertEqual(report["prospective_n"], 2)
        self.assertEqual(report["total_n"], 23)
        self.assertFalse(report["changes_meta"])
        self.assertFalse(report["automatic_promotion"])
        self.assertFalse(report["betting_enabled"])

    def test_consensus_loss_records_methods_and_rank(self):
        row = record(actual=[1, 2, 6], signals={"Reset": [6], "Puxada": [6]})
        losses = lab.consensus_losses([row])
        self.assertEqual(len(losses), 1)
        self.assertEqual(losses[0]["group"], 6)
        self.assertEqual(losses[0]["rank"], 6)
        self.assertEqual(set(losses[0]["methods"]), {"Reset", "Puxada"})


if __name__ == "__main__":
    unittest.main()
