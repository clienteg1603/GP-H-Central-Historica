import unittest

from gph_similarity_rank import distinct_similarity_groups


class SimilarityDistinctGroupsTests(unittest.TestCase):
    def test_fills_duplicate_slot_winners_until_five_distinct_groups(self):
        result = {
            "selected": [
                {"grupo": 7},
                {"grupo": 7},
                {"grupo": 12},
                {"grupo": 3},
                {"grupo": 12},
            ],
            "top_days": [
                {
                    "score": 80.0,
                    "target": {
                        "prizes": [
                            {"grupo": 7}, {"grupo": 12}, {"grupo": 3},
                            {"grupo": 18}, {"grupo": 21},
                        ]
                    },
                },
                {
                    "score": 60.0,
                    "target": {
                        "prizes": [
                            {"grupo": 7}, {"grupo": 18}, {"grupo": 21},
                            {"grupo": 5}, {"grupo": 12},
                        ]
                    },
                },
            ],
        }

        self.assertEqual(
            distinct_similarity_groups(result, 5),
            [7, 12, 3, 18, 21],
        )

    def test_preserves_unique_selected_order(self):
        result = {
            "selected": [
                {"grupo": 9}, {"grupo": 4}, {"grupo": 15},
                {"grupo": 2}, {"grupo": 20},
            ],
            "top_days": [],
        }
        self.assertEqual(distinct_similarity_groups(result, 5), [9, 4, 15, 2, 20])

    def test_never_invents_groups_when_history_is_insufficient(self):
        result = {
            "selected": [{"grupo": 6}, {"grupo": 6}],
            "top_days": [
                {"score": 50, "target": {"prizes": [{"grupo": 6}, {"grupo": 11}]}}
            ],
        }
        self.assertEqual(distinct_similarity_groups(result, 5), [6, 11])


if __name__ == "__main__":
    unittest.main()
