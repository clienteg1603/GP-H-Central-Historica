import sqlite3
import tempfile
import unittest
from pathlib import Path

from gph_ui_home import head_bicho_delay


class HeadBichoDelayTests(unittest.TestCase):
    def _database(self):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "home-delay.sqlite3"
        con = sqlite3.connect(path)
        con.execute(
            "CREATE TABLE resultados ("
            "data TEXT, sorteio TEXT, hora TEXT, premio INTEGER, milhar TEXT, "
            "centena TEXT, dezena TEXT, grupo INTEGER, bicho TEXT, fonte TEXT)"
        )
        return tmp, path, con

    def _add_complete_draw(self, con, day, p1_group):
        for prize in range(1, 6):
            # Grupo 3 reaparece deliberadamente fora da cabeça para provar que
            # 2º–5º prêmio não zeram o atraso específico do 1º prêmio.
            group = p1_group if prize == 1 else 3
            number = f"{day * 100 + prize:04d}"
            con.execute(
                "INSERT INTO resultados VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    f"2026-09-{day:02d}", "PT", f"{8 + day:02d}:00", prize,
                    number, number[-3:], number[-2:], group, f"Bicho {group}", "teste",
                ),
            )

    def test_only_first_prize_resets_head_delay(self):
        tmp, path, con = self._database()
        try:
            for day, group in enumerate((3, 1, 2, 1), start=1):
                self._add_complete_draw(con, day, group)
            con.commit()
            item = head_bicho_delay(path)
            self.assertIsNotNone(item)
            self.assertEqual(item["value"], 3)
            self.assertEqual(item["delay"], 3)
            self.assertEqual(item["last"]["premio"], 1)
            self.assertEqual(item["tie_count"], 1)
        finally:
            con.close()
            tmp.cleanup()

    def test_incomplete_latest_draw_does_not_reset_delay(self):
        tmp, path, con = self._database()
        try:
            for day, group in enumerate((3, 1, 2, 1), start=1):
                self._add_complete_draw(con, day, group)
            con.execute(
                "INSERT INTO resultados VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("2026-09-05", "PT", "13:00", 1, "9999", "999", "99", 3, "Bicho 3", "teste"),
            )
            con.commit()
            item = head_bicho_delay(path)
            self.assertEqual(item["value"], 3)
            self.assertEqual(item["delay"], 3)
        finally:
            con.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
