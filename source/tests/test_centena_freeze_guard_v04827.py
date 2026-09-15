import unittest

import gph_centena_freeze_guard as guard


def draw(day, hour, group=None, dezena=None, sorteio="PT"):
    prizes = []
    if group is not None:
        prizes.append({
            "premio": 1,
            "numero": f"12{int(dezena):02d}",
            "centena": f"2{int(dezena):02d}",
            "dezena": f"{int(dezena):02d}",
            "grupo": int(group),
        })
    return {
        "data": day,
        "sorteio": sorteio,
        "hora": hour,
        "prizes": prizes,
    }


class FakeDB:
    def __init__(self, draws):
        self.draws = list(draws)

    def _draws_in_order(self):
        return list(self.draws)

    def latest_operational_draw(self):
        return self.draws[-1] if self.draws else None

    def number_rankings_for_group(self, group, kind="Centena", scope="1º–5º", date_to=None):
        if str(kind).casefold() == "dezena":
            # Ranking histórico fixo do Macaco usado nos exemplos do usuário.
            return [
                {"numero": "68", "ocorrencias": 40},
                {"numero": "67", "ocorrencias": 30},
                {"numero": "66", "ocorrencias": 20},
                {"numero": "65", "ocorrencias": 10},
            ]
        return []

    def centena_31_freeze_state(self, group, principal_dezena, previous_draw=None):
        # Simula a máquina antiga: a extensão v0.48.28 precisa neutralizar esse
        # deslocamento dentro da geração, pois a dezena bloqueada já saiu do ranking.
        return {"frozen": True, "trigger": {"legacy": True}, "released_by": None}

    @staticmethod
    def _rows(group, main, extra):
        return [
            {"grupo": group, "numero": f"1{main}"},
            {"grupo": group, "numero": f"2{main}"},
            {"grupo": group, "numero": f"3{main}"},
            {"grupo": group, "numero": f"1{extra}"},
        ]

    def generate_gph_law_numbers(
        self,
        groups,
        kind="Centena",
        total=20,
        previous_draw=None,
        scope="1º–5º",
        date_to=None,
    ):
        group = int(groups[0])
        ranking = self.number_rankings_for_group(
            group, kind="Dezena", scope=scope, date_to=date_to
        )
        principal, segunda, terceira = ranking[:3]
        state = self.centena_31_freeze_state(
            group, principal["numero"], previous_draw=previous_draw
        )
        if state.get("frozen"):
            main, extra = segunda["numero"], terceira["numero"]
        else:
            main, extra = principal["numero"], segunda["numero"]
        return {
            "rows": self._rows(group, main, extra),
            "animals": [{"grupo": group, "main_dezena": main, "extra_dezena": extra}],
        }

    def generate_centenas_3plus1(self, groups, previous_draw=None):
        group = int(groups[0])
        ranking = self.number_rankings_for_group(group, kind="Dezena")
        principal, segunda, terceira = ranking[:3]
        state = self.centena_31_freeze_state(
            group, principal["numero"], previous_draw=previous_draw
        )
        if state.get("frozen"):
            main, extra = segunda["numero"], terceira["numero"]
        else:
            main, extra = principal["numero"], segunda["numero"]
        return {
            "rows": self._rows(group, main, extra),
            "animals": [{"grupo": group, "main_dezena": main, "extra_dezena": extra}],
        }


class CentenaFreezeGuardTests(unittest.TestCase):
    def setUp(self):
        class DB(FakeDB):
            pass
        self.DB = DB
        self.Central = type("Central", (), {"Database": DB})
        guard.install_centena_freeze_guard(self.Central)

    def endings(self, result):
        return [row["numero"][-2:] for row in result["rows"]]

    def test_268_macaco_freezes_68_and_uses_67_plus_66(self):
        base = draw("2026-09-15", "14:00", 17, 68)
        db = self.DB([base])
        result = db.generate_gph_law_numbers([17], total=4, previous_draw=base)
        self.assertEqual(self.endings(result), ["67", "67", "67", "66"])
        self.assertNotIn("68", self.endings(result))
        self.assertEqual(result["frozen_dezenas_by_group"]["17"], "68")

    def test_macaco_67_releases_68_and_freezes_67(self):
        first = draw("2026-09-15", "14:00", 17, 68)
        second = draw("2026-09-15", "16:00", 17, 67, sorteio="PTV")
        db = self.DB([first, second])
        result = db.generate_gph_law_numbers([17], total=4, previous_draw=second)
        endings = self.endings(result)
        self.assertEqual(endings, ["68", "68", "68", "66"])
        self.assertIn("68", endings)      # 68 foi liberada.
        self.assertNotIn("67", endings)   # 67 assumiu o congelamento.
        self.assertEqual(result["frozen_dezenas_by_group"]["17"], "67")

    def test_freeze_persists_until_same_bicho_appears_again(self):
        macaco = draw("2026-09-15", "14:00", 17, 68)
        other = draw("2026-09-15", "16:00", 18, 72, sorteio="PTV")
        db = self.DB([macaco, other])
        self.assertEqual(guard.frozen_dezena_for_group(db, 17, other), "68")
        result = db.generate_gph_law_numbers([17], total=4, previous_draw=other)
        self.assertNotIn("68", self.endings(result))

    def test_historical_cutoff_never_reads_future_reappearance(self):
        old = draw("2026-08-20", "14:00", 17, 68)
        future = draw("2026-08-20", "16:00", 17, 67, sorteio="PTV")
        db = self.DB([old, future])
        self.assertEqual(guard.frozen_dezena_for_group(db, 17, old), "68")
        old_result = db.generate_gph_law_numbers([17], total=4, previous_draw=old)
        self.assertNotIn("68", self.endings(old_result))
        self.assertIn("67", self.endings(old_result))

    def test_direct_3plus1_uses_same_rotating_rule(self):
        first = draw("2026-09-15", "14:00", 17, 68)
        second = draw("2026-09-15", "16:00", 17, 67, sorteio="PTV")
        db = self.DB([first, second])
        result = db.generate_centenas_3plus1([17], previous_draw=second)
        self.assertEqual(self.endings(result), ["68", "68", "68", "66"])
        self.assertNotIn("67", self.endings(result))

    def test_state_reports_the_actual_frozen_dezena_outside_generation(self):
        first = draw("2026-09-15", "14:00", 17, 68)
        second = draw("2026-09-15", "16:00", 17, 67, sorteio="PTV")
        db = self.DB([first, second])
        state = db.centena_31_freeze_state(17, "68", previous_draw=second)
        self.assertTrue(state["frozen"])
        self.assertEqual(state["frozen_dezena"], "67")
        self.assertEqual(state["freeze_rule"], "rotativa_por_bicho")

    def test_latest_operational_draw_is_used_when_cutoff_omitted(self):
        first = draw("2026-09-15", "14:00", 17, 68)
        second = draw("2026-09-15", "16:00", 17, 67, sorteio="PTV")
        db = self.DB([first, second])
        self.assertEqual(guard.frozen_dezena_for_group(db, 17), "67")


if __name__ == "__main__":
    unittest.main()
