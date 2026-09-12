import unittest
import gph_meta_review as review


def row(cov, near=0):
    return {"coverage":cov,"actual":[1,2,3,4,5],"missed":[6,7,8,9],"near":[6][:near],"consensus":[],"low_support":[],"signals":{},"random_hits":1.0,"random_2plus":review._rand_2plus(5)}


class MetaReviewTests(unittest.TestCase):
    def test_eight_rounds_remain_structural_review(self):
        out=review.summarize([row(0) for _ in range(7)]+[row(2)])
        self.assertEqual(out["decision"],"REVISÃO ESTRUTURAL")
        self.assertAlmostEqual(out["rate2"],0.125)
        self.assertFalse(out["changes_meta"])
        self.assertTrue(out["target_is_diagnostic_only"])

    def test_twenty_rounds_above_fifty_keep_brain(self):
        out=review.summarize([row(2) for _ in range(11)]+[row(1) for _ in range(9)])
        self.assertEqual(out["decision"],"MANTER")


if __name__ == "__main__":
    unittest.main()
