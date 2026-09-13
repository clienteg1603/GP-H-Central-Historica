from types import SimpleNamespace
import unittest

import gph_bugfix_round_targets as hotfix


class RoundTargetHotfixTests(unittest.TestCase):
    def test_sunday_federal_1120_becomes_1100(self):
        target = {"data": "2026-09-13", "sorteio": "FEDERAL", "hora": "11:20"}
        fixed = hotfix.normalize_target(target)
        self.assertEqual(fixed["hora"], "11:00")
        self.assertEqual(target["hora"], "11:20")

    def test_other_days_and_draws_are_untouched(self):
        wed = {"data": "2026-09-16", "sorteio": "FEDERAL", "hora": "20:00"}
        pt = {"data": "2026-09-13", "sorteio": "PT", "hora": "14:00"}
        self.assertEqual(hotfix.normalize_target(wed), wed)
        self.assertEqual(hotfix.normalize_target(pt), pt)

    def test_generation_normalization_is_copy_safe(self):
        generation = {
            "kind": "Centena",
            "intended_target": {"data": "2026-09-13", "sorteio": "FEDERAL", "hora": "11:20"},
            "rows": [{"numero": "123"}],
        }
        fixed = hotfix.normalize_generation(generation)
        self.assertEqual(fixed["intended_target"]["hora"], "11:00")
        self.assertEqual(generation["intended_target"]["hora"], "11:20")

    def test_get_draw_accepts_legacy_result_hour(self):
        class FakeDatabase:
            def __init__(self, *args, **kwargs):
                pass

            def get_draw(self, draw_date, sorteio, hora):
                if (draw_date, sorteio, hora) == ("2026-09-13", "FEDERAL", "11:20"):
                    return {"data": draw_date, "sorteio": sorteio, "hora": hora, "prizes": []}
                return None

            def next_operational_target(self):
                return {"data": "2026-09-13", "sorteio": "FEDERAL", "hora": "11:20"}

            def future_operational_targets(self, count=12):
                return [self.next_operational_target()]

            def game_planned_target(self, game):
                return {"data": game["alvo_data"], "sorteio": game["alvo_sorteio"], "hora": game["alvo_hora"]}

            def register_play(self, generation, *args, **kwargs):
                return generation["intended_target"]["hora"]

            def register_ticket(self, entries, *args, **kwargs):
                return entries[0]["generation"]["intended_target"]["hora"]

        central = SimpleNamespace(Database=FakeDatabase)
        hotfix.install_round_target_hotfix(central)
        db = FakeDatabase()
        draw = db.get_draw("2026-09-13", "FEDERAL", "11:00")
        self.assertIsNotNone(draw)
        self.assertEqual(draw["hora"], "11:00")
        self.assertEqual(db.next_operational_target()["hora"], "11:00")


if __name__ == "__main__":
    unittest.main()
