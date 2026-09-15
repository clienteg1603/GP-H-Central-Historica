import unittest
from unittest import mock

import gph_ui_decision_guides as guides


class _FakeApp:
    def __init__(self):
        self.decision_view = "summary"
        self.calls = []
        self.content = None

    def _decision_build_contextual(self, body, snapshot):
        self.calls.append(("contextual", body, snapshot))
        return "contextual-ok"

    def _decision_build_coverage_evolution(self, body, *args, **kwargs):
        self.calls.append(("coverage", body, args, kwargs))
        return "coverage-ok"

    def _build_shadow_lab_section(self, body, *args, **kwargs):
        self.calls.append(("lab", body, args, kwargs))
        return "lab-ok"

    def show_decision_page(self, *args, **kwargs):
        self.calls.append(("show", args, kwargs))
        return "show-ok"


class _FakeCentral:
    App = _FakeApp


class DecisionGuidesTests(unittest.TestCase):
    def setUp(self):
        # cada teste recebe classe nova para evitar wrappers acumulados
        class App(_FakeApp):
            pass
        self.central = type("Central", (), {"App": App})

    def test_flags_keep_business_logic_untouched(self):
        info = guides.DECISION_GUIDES_INFO
        self.assertTrue(info["visual_only"])
        for key in (
            "changes_meta", "changes_weights", "changes_scores", "changes_database",
            "changes_generators", "changes_methods", "changes_audit", "changes_lab",
            "changes_freeze",
        ):
            self.assertFalse(info[key], key)

    def test_visible_technical_titles_are_simplified(self):
        self.assertEqual(
            guides.TITLE_REPLACEMENTS["DECISÃO ADAPTATIVA — ETAPA C"],
            "AJUSTE ADAPTATIVO · TÉCNICO",
        )
        self.assertEqual(
            guides.TITLE_REPLACEMENTS["RECOMENDAÇÃO OPERACIONAL — ETAPA D"],
            "RECOMENDAÇÃO OPERACIONAL",
        )

    def test_guides_only_enter_their_respective_views(self):
        with mock.patch.object(guides, "_build_understand_guide") as understand, \
             mock.patch.object(guides, "_build_tracking_guide") as tracking, \
             mock.patch.object(guides, "_build_test_guide") as testing, \
             mock.patch.object(guides, "_simplify_visible_titles"):
            guides.install_decision_guides(self.central)
            app = self.central.App()

            app.decision_view = "analysis"
            self.assertEqual(app._decision_build_contextual("body", {"x": 1}), "contextual-ok")
            understand.assert_called_once()

            app.decision_view = "audit"
            self.assertEqual(app._decision_build_coverage_evolution("body2"), "coverage-ok")
            tracking.assert_called_once()

            app.decision_view = "lab"
            self.assertEqual(app._build_shadow_lab_section("body3"), "lab-ok")
            testing.assert_called_once()

            self.assertEqual([call[0] for call in app.calls], ["contextual", "coverage", "lab"])

    def test_summary_does_not_gain_extra_stage_guides(self):
        with mock.patch.object(guides, "_build_understand_guide") as understand, \
             mock.patch.object(guides, "_build_tracking_guide") as tracking, \
             mock.patch.object(guides, "_build_test_guide") as testing, \
             mock.patch.object(guides, "_simplify_visible_titles"):
            guides.install_decision_guides(self.central)
            app = self.central.App()
            app.decision_view = "summary"
            app._decision_build_contextual("a", {})
            app._decision_build_coverage_evolution("b")
            app._build_shadow_lab_section("c")
            understand.assert_not_called()
            tracking.assert_not_called()
            testing.assert_not_called()

    def test_installer_is_idempotent(self):
        first = guides.install_decision_guides(self.central)
        contextual_after_first = self.central.App._decision_build_contextual
        second = guides.install_decision_guides(self.central)
        self.assertIs(contextual_after_first, self.central.App._decision_build_contextual)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
