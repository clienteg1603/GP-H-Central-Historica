import copy
import unittest
from types import SimpleNamespace

import gph_ui_decision_steps as steps


class DecisionStepsV04825Tests(unittest.TestCase):
    def test_contract_is_visual_only(self):
        info = steps.DECISION_STEPS_INFO
        self.assertTrue(info["visual_only"])
        for key in (
            "changes_meta", "changes_weights", "changes_scores", "changes_database",
            "changes_generators", "changes_methods", "changes_audit", "changes_lab",
        ):
            self.assertFalse(info[key], key)

    def test_step_labels_are_simple_and_ordered(self):
        self.assertEqual(
            steps.STEP_LABELS,
            {
                "summary": "1 · Agora",
                "analysis": "2 · Entender",
                "audit": "3 · Acompanhar",
                "lab": "4 · Testar",
            },
        )

    def test_quick_summary_only_translates_existing_data(self):
        snapshot = {
            "contextual": {
                "status": "MODERADA",
                "lead": 4.2,
                "evidence_leader": "Puxada Combinada",
                "recommendation": "texto",
                "operational": {
                    "headline": "PRIORIZAR COM CAUTELA PUXADA COMBINADA",
                    "reference_leader": "Puxada Combinada",
                    "confidence": "MODERADA",
                    "lead": 4.2,
                    "reason": "motivo",
                },
                "rows": [
                    {"method": "Reset Cobertura", "index": 61.0},
                    {"method": "Puxada Combinada", "index": 68.5},
                    {"method": "Similaridade", "index": 57.2},
                ],
            },
            "meta": {"status": "EXPERIMENTAL", "groups": [3, 9, 14, 18, 25]},
        }
        review = {
            "n": 21, "coverage_avg": 0.95, "rate2": 0.143,
            "random_avg": 0.90, "random_rate2": 0.207,
            "decision": "RECALIBRAR EM LABORATÓRIO",
        }
        lab = {"status": "COLETANDO PROSPECTIVO", "baseline_n": 21, "prospective_n": 2}
        original = copy.deepcopy(snapshot)

        out = steps.build_quick_summary_data(snapshot, review, lab)

        self.assertEqual(snapshot, original)
        self.assertEqual(out["reference"], "Puxada Combinada")
        self.assertEqual(out["confidence"], "MODERADA")
        self.assertEqual(out["top5"], [3, 9, 14, 18, 25])
        self.assertEqual(out["review_n"], 21)
        self.assertEqual(out["lab_prospective"], 2)
        self.assertEqual(out["context_rows"][0]["method"], "Puxada Combinada")

    def test_installer_wraps_without_replacing_technical_views(self):
        class DummyApp:
            def _decision_build_operational(self, body, snapshot):
                return "operational-original"

            def _decision_build_contextual(self, body, snapshot):
                return "contextual-original"

            def show_decision_page(self, *args, **kwargs):
                return "show-original"

        central = SimpleNamespace(App=DummyApp)
        info = steps.install_decision_steps(central)
        self.assertIs(info, steps.DECISION_STEPS_INFO)
        self.assertTrue(DummyApp._gph_decision_steps_v04825_installed)
        app = DummyApp()
        app.decision_view = "analysis"
        self.assertEqual(app._decision_build_operational(None, {}), "operational-original")
        self.assertEqual(app._decision_build_contextual(None, {}), "contextual-original")
        # Idempotente: uma segunda instalação não empilha wrappers.
        self.assertIs(steps.install_decision_steps(central), steps.DECISION_STEPS_INFO)


if __name__ == "__main__":
    unittest.main()
