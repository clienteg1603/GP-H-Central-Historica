import unittest

import gph_meta_freeze_guard as guard


class FakeDB:
    def __init__(self, target):
        self.target = dict(target)
        self.draw_exists = False
        self.meta_payload = None
        self.snapshot = None
        self.freeze_decision_calls = 0
        self.freeze_meta_calls = 0
        self.audit_calls = 0

    def next_operational_target(self):
        return dict(self.target) if self.target else None

    def get_draw(self, data, sorteio, hora):
        return {"data": data, "sorteio": sorteio, "hora": hora} if self.draw_exists else None

    def freeze_decision_snapshot(self, force=False):
        self.freeze_decision_calls += 1
        if self.snapshot is None:
            self.snapshot = {
                "target_data": self.target["data"],
                "target_sorteio": self.target["sorteio"],
                "target_hora": self.target["hora"],
                "meta": self.meta_payload,
            }
            return self.snapshot, True
        return self.snapshot, False

    def freeze_meta_snapshot(self, snapshot=None, force=False):
        self.freeze_meta_calls += 1
        if force:
            raise AssertionError("A guarda nunca pode usar force=True")
        if self.draw_exists:
            raise AssertionError("Tentativa de congelar Meta depois do resultado")
        if snapshot.get("meta"):
            return snapshot, False
        snapshot["meta"] = {
            "available": True,
            "status": "OK",
            "groups": [1, 2, 3, 4, 5],
        }
        self.meta_payload = snapshot["meta"]
        return snapshot, True

    def audit_decision_snapshots(self):
        self.audit_calls += 1
        return 7


class FakeApp:
    def __init__(self):
        self.db = FakeDB({"data": "2026-09-15", "sorteio": "PT", "hora": "14:00"})
        self.scheduled = []
        self._startup_cancelled = False

    def after(self, delay, callback):
        self.scheduled.append((delay, callback))
        return "after-id"


class FakeCentral:
    Database = FakeDB
    App = FakeApp


class MetaFreezeGuardTests(unittest.TestCase):
    def test_pending_target_gets_meta_frozen(self):
        db = FakeDB({"data": "2026-09-15", "sorteio": "PTM", "hora": "11:00"})
        result = guard.ensure_next_meta_frozen(db)
        self.assertEqual(result["status"], "CONGELADO")
        self.assertTrue(result["created"])
        self.assertEqual(db.freeze_decision_calls, 1)
        self.assertEqual(db.freeze_meta_calls, 1)
        self.assertTrue(db.snapshot["meta"]["available"])

    def test_existing_result_blocks_retroactive_freeze(self):
        db = FakeDB({"data": "2026-09-15", "sorteio": "PT", "hora": "14:00"})
        db.draw_exists = True
        result = guard.ensure_next_meta_frozen(db)
        self.assertEqual(result["status"], "RESULTADO_JA_EXISTE")
        self.assertEqual(db.freeze_decision_calls, 0)
        self.assertEqual(db.freeze_meta_calls, 0)

    def test_existing_meta_is_never_overwritten(self):
        db = FakeDB({"data": "2026-09-15", "sorteio": "PTV", "hora": "16:00"})
        original = {"available": True, "groups": [5, 4, 3, 2, 1], "marker": "primeiro"}
        db.meta_payload = original
        db.snapshot = {
            "target_data": db.target["data"],
            "target_sorteio": db.target["sorteio"],
            "target_hora": db.target["hora"],
            "meta": original,
        }
        result = guard.ensure_next_meta_frozen(db)
        self.assertEqual(result["status"], "JA_CONGELADO")
        self.assertEqual(db.freeze_meta_calls, 0)
        self.assertEqual(db.snapshot["meta"]["marker"], "primeiro")

    def test_all_operational_slot_shapes_are_accepted(self):
        slots = [
            ("PPT", "09:00"),
            ("PTM", "11:00"),
            ("FEDERAL", "11:00"),
            ("PT", "14:00"),
            ("PTV", "16:00"),
            ("PTN", "18:00"),
            ("FEDERAL", "20:00"),
            ("CORUJA", "21:00"),
        ]
        for sorteio, hora in slots:
            with self.subTest(sorteio=sorteio, hora=hora):
                db = FakeDB({"data": "2026-09-16", "sorteio": sorteio, "hora": hora})
                result = guard.ensure_next_meta_frozen(db)
                self.assertEqual(result["status"], "CONGELADO")
                self.assertEqual(result["target"][1:], (sorteio, hora))

    def test_audit_wrapper_freezes_next_meta_and_watchdog_is_scheduled(self):
        # Classes novas para não interferir nos demais testes por monkeypatch global.
        class DB(FakeDB):
            pass

        class App:
            def __init__(self):
                self.db = DB({"data": "2026-09-15", "sorteio": "PTN", "hora": "18:00"})
                self.scheduled = []
                self._startup_cancelled = False

            def after(self, delay, callback):
                self.scheduled.append((delay, callback))
                return "id"

        class Central:
            Database = DB
            App = App

        guard.install_meta_freeze_guard(Central)
        db = DB({"data": "2026-09-15", "sorteio": "CORUJA", "hora": "21:00"})
        self.assertEqual(db.audit_decision_snapshots(), 7)
        self.assertEqual(db.freeze_meta_calls, 1)
        self.assertEqual(db._gph_meta_freeze_guard_last["status"], "CONGELADO")

        app = App()
        self.assertTrue(app.scheduled)
        first_delay, callback = app.scheduled[0]
        self.assertEqual(first_delay, 2300)
        callback()
        self.assertEqual(app.db.freeze_meta_calls, 1)
        self.assertGreaterEqual(len(app.scheduled), 2)


if __name__ == "__main__":
    unittest.main()
