import unittest

import gph_centena_freeze_guard as guard


class FakeDB:
    def __init__(self, latest=None, original_state=None):
        self.latest = latest
        self.original_state = dict(original_state or {
            "frozen": False,
            "trigger": None,
            "released_by": {"motivo": "liberada_pela_maquina_antiga"},
        })

    def latest_operational_draw(self):
        return self.latest

    def centena_31_freeze_state(self, group, principal_dezena, previous_draw=None):
        return dict(self.original_state)


class FakeCentral:
    Database = FakeDB


class CentenaFreezeGuardTests(unittest.TestCase):
    def setUp(self):
        # Cada teste usa uma classe nova porque a instalação faz monkeypatch.
        class DB(FakeDB):
            pass
        self.DB = DB
        self.Central = type("Central", (), {"Database": DB})
        guard.install_centena_freeze_guard(self.Central)

    def test_268_macaco_blocks_68_on_next_generation(self):
        previous = {
            "data": "2026-09-15",
            "sorteio": "PT",
            "hora": "14:00",
            "prizes": [
                {"premio": 1, "numero": "1268", "centena": "268", "dezena": "68", "grupo": 17},
                {"premio": 2, "numero": "7772", "centena": "772", "dezena": "72", "grupo": 18},
            ],
        }
        db = self.DB(latest=previous)
        state = db.centena_31_freeze_state(17, "68", previous_draw=previous)
        self.assertTrue(state["frozen"])
        self.assertTrue(state["previous_round_lock"])
        self.assertEqual(state["freeze_reason"], "principal_na_rodada_imediatamente_anterior")
        self.assertEqual(state["trigger"]["dezenas"], ["68"])
        self.assertIsNone(state["released_by"])

    def test_previous_round_lock_overrides_old_release_state(self):
        previous = {
            "data": "2026-09-15",
            "sorteio": "PT",
            "hora": "14:00",
            "prizes": [{"dezena": 68, "grupo": 17}],
        }
        db = self.DB(
            latest=previous,
            original_state={
                "frozen": False,
                "trigger": None,
                "released_by": {"data": "2026-09-15", "hora": "14:00"},
            },
        )
        state = db.centena_31_freeze_state(17, "68", previous_draw=previous)
        self.assertTrue(state["frozen"])
        self.assertIsNone(state["released_by"])

    def test_nonprincipal_dezena_does_not_create_new_lock(self):
        previous = {
            "data": "2026-09-15",
            "sorteio": "PT",
            "hora": "14:00",
            "prizes": [{"dezena": "67", "grupo": 17}],
        }
        db = self.DB(latest=previous)
        state = db.centena_31_freeze_state(17, "68", previous_draw=previous)
        self.assertFalse(state["frozen"])
        self.assertFalse(state["previous_round_lock"])
        self.assertEqual(state["freeze_reason"], "maquina_persistente")

    def test_same_dezena_other_group_does_not_lock(self):
        previous = {
            "data": "2026-09-15",
            "sorteio": "PT",
            "hora": "14:00",
            "prizes": [{"dezena": "68", "grupo": 18}],
        }
        db = self.DB(latest=previous)
        state = db.centena_31_freeze_state(17, "68", previous_draw=previous)
        self.assertFalse(state["frozen"])
        self.assertFalse(state["previous_round_lock"])

    def test_historical_previous_draw_is_respected_instead_of_latest(self):
        latest = {
            "data": "2026-09-16",
            "sorteio": "PT",
            "hora": "14:00",
            "prizes": [{"dezena": "68", "grupo": 17}],
        }
        historical = {
            "data": "2026-08-20",
            "sorteio": "PTM",
            "hora": "11:00",
            "prizes": [{"dezena": "67", "grupo": 17}],
        }
        db = self.DB(latest=latest)
        state = db.centena_31_freeze_state(17, "68", previous_draw=historical)
        self.assertFalse(state["previous_round_lock"])
        self.assertFalse(state["frozen"])

    def test_none_previous_draw_uses_latest_operational_draw(self):
        latest = {
            "data": "2026-09-15",
            "sorteio": "PT",
            "hora": "14:00",
            "prizes": [{"dezena": "68", "grupo": 17}],
        }
        db = self.DB(latest=latest)
        state = db.centena_31_freeze_state(17, "68")
        self.assertTrue(state["frozen"])
        self.assertTrue(state["previous_round_lock"])


if __name__ == "__main__":
    unittest.main()
