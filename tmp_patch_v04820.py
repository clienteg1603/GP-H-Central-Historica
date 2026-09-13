from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
CENTRAL = ROOT / "source" / "gph_central.py"
HOME_HELPER = ROOT / "source" / "gph_ui_home.py"
VERSION = ROOT / "source" / "gph_version.py"
DOC = ROOT / "source" / "DOCUMENTACAO_GP-H.txt"
TEST = ROOT / "source" / "tests" / "test_home_head_delay_v04820.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperado 1 trecho, encontrados {count}")
    return text.replace(old, new, 1)


src = CENTRAL.read_text(encoding="utf-8")
start = src.find("    def show_home(self):")
if start < 0:
    raise SystemExit("show_home não encontrado")
end = src.find("\n    def ", start + 10)
if end < 0:
    raise SystemExit("fim de show_home não encontrado")
home = src[start:end]

home = replace_once(
    home,
    "        delays = self.db.delay_leaders()\n",
    "        delays = self.db.delay_leaders()\n"
    "        # v0.48.20: atraso específico da cabeça (somente 1º prêmio).\n"
    "        # É uma métrica paralela; o atraso de Bicho 1º–5º permanece intacto.\n"
    "        try:\n"
    "            from gph_ui_home import head_bicho_delay\n"
    "            head_delay = head_bicho_delay(DB_PATH)\n"
    "            if head_delay:\n"
    "                delays[\"bicho_p1\"] = head_delay\n"
    "        except Exception:\n"
    "            # A Home continua utilizável mesmo se a métrica adicional falhar.\n"
    "            pass\n",
    "injeção do atraso da cabeça",
)

home = replace_once(
    home,
    "        main.grid_rowconfigure(0, weight=1)\n",
    "        main.grid_rowconfigure(0, weight=1)\n"
    "        main.grid_rowconfigure(1, weight=0)\n",
    "segunda linha compacta da Home",
)

home = replace_once(
    home,
    "        # DIREITA — próxima rodada, último resultado vertical e atrasos atuais.\n",
    "        # DIREITA — próxima rodada e último resultado vertical.\n",
    "comentário da coluna direita",
)

home = replace_once(
    home,
    "        latest_card.pack(fill=\"both\", expand=True, pady=(0, 6))\n",
    "        latest_card.pack(fill=\"both\", expand=True)\n",
    "expansão do último resultado",
)

home = replace_once(
    home,
    "        # Atrasos atuais — mais legíveis, abaixo do último resultado.\n"
    "        delay_card = ttk.Frame(side, style=\"Card.TFrame\", padding=(10, 7))\n"
    "        delay_card.pack(fill=\"x\")\n",
    "        # v0.48.20 — faixa horizontal inferior. Ela ocupa as duas colunas e\n"
    "        # aproveita a área livre da Home sem alongar a coluna da direita.\n"
    "        delay_card = ttk.Frame(main, style=\"Card.TFrame\", padding=(10, 7))\n"
    "        delay_card.grid(\n"
    "            row=1, column=0, columnspan=2, sticky=\"ew\", pady=(7, 0)\n"
    "        )\n",
    "reposicionamento do cartão de atrasos",
)

# Dentro do bloco de atrasos há exatamente dois tratamentos especiais de bicho:
# valor principal e valores empatados.
count_bicho_conditions = home.count('            if field == "bicho":')
if count_bicho_conditions != 2:
    raise SystemExit(
        f"condições de bicho no atraso: esperado 2, encontrados {count_bicho_conditions}"
    )
home = home.replace(
    '            if field == "bicho":',
    '            if field in ("bicho", "bicho_p1"):',
)

old_loop = (
    '        for idx, (field, caption) in enumerate((("bicho", "Bicho"), '
    '("centena", "Centena"), ("dezena", "Dezena"))):\n'
)
new_loop = (
    "        delay_fields = (\n"
    '            ("bicho", "Bicho · 1º–5º"),\n'
    '            ("bicho_p1", "Cabeça · 1º prêmio"),\n'
    '            ("centena", "Centena"),\n'
    '            ("dezena", "Dezena"),\n'
    "        )\n"
    "        for idx, (field, caption) in enumerate(delay_fields):\n"
)
home = replace_once(home, old_loop, new_loop, "quatro indicadores de atraso")

home = replace_once(
    home,
    "                box.pack(side=\"left\", fill=\"x\", expand=True, padx=(0, 4 if idx < 2 else 0))\n",
    "                box.pack(\n"
    "                    side=\"left\", fill=\"x\", expand=True,\n"
    "                    padx=(0, 4 if idx < len(delay_fields) - 1 else 0),\n"
    "                )\n",
    "espaçamento dos quatro indicadores",
)

src = src[:start] + home + src[end:]
CENTRAL.write_text(src, encoding="utf-8")

HOME_HELPER.write_text(
    '''"""Apoio enxuto da Home do GP-H.

A antiga camada visual experimental continua desativada. Desde a v0.48.20 este
módulo abriga apenas cálculos auxiliares da Visão Geral, sem substituir a Home.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def head_bicho_delay(db_path: str | Path) -> dict[str, Any] | None:
    """Retorna o bicho há mais extrações completas sem sair no 1º prêmio.

    Aparições no 2º–5º prêmio não zeram esta contagem. A estrutura retornada é
    compatível com ``Database.delay_leaders()`` para a Home poder renderizar as
    duas métricas lado a lado sem alterar a regra do atraso geral.
    """
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT data,sorteio,hora,premio,milhar,centena,dezena,grupo,bicho "
            "FROM resultados WHERE premio BETWEEN 1 AND 5 "
            "ORDER BY data,hora,sorteio,premio"
        ).fetchall()
    except (sqlite3.Error, OSError):
        return None
    finally:
        try:
            con.close()
        except Exception:
            pass

    draws: dict[tuple[str, str, str], dict[int, dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        key = (str(item["data"]), str(item["hora"]), str(item["sorteio"]))
        try:
            prize = int(item["premio"])
        except (TypeError, ValueError):
            continue
        draws.setdefault(key, {})[prize] = item

    # A mesma régua conceitual do atraso atual: só extrações completas contam.
    complete = [by_prize for by_prize in draws.values() if all(p in by_prize for p in range(1, 6))]
    if not complete:
        return None

    last_index: dict[int, int] = {}
    last_row: dict[int, dict[str, Any]] = {}
    for idx, by_prize in enumerate(complete):
        first = by_prize[1]
        try:
            group = int(first["grupo"])
        except (TypeError, ValueError, KeyError):
            continue
        last_index[group] = idx
        last_row[group] = first

    if not last_index:
        return None

    total = len(complete)
    by_group = {group: total - 1 - pos for group, pos in last_index.items()}
    max_delay = max(by_group.values())
    ties = sorted(group for group, delay in by_group.items() if delay == max_delay)
    leader = ties[0]
    return {
        "value": leader,
        "delay": max_delay,
        "tie_count": len(ties),
        "ties": ties,
        "last": last_row[leader],
    }
''',
    encoding="utf-8",
)

TEST.write_text(
    '''import sqlite3
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
''',
    encoding="utf-8",
)

version_text = VERSION.read_text(encoding="utf-8")
version_text = replace_once(
    version_text,
    'APP_VERSION = "0.48.19"',
    'APP_VERSION = "0.48.20"',
    "versão 0.48.20",
)
VERSION.write_text(version_text, encoding="utf-8")

doc_text = DOC.read_text(encoding="utf-8")
entry = """REVISÃO v0.48.20 — HOME: ATRASOS EM FAIXA + CABEÇA\n- Move “Atrasos atuais” da coluna direita para uma faixa horizontal inferior ocupando as duas colunas da Visão Geral.\n- O “Último resultado” passa a ocupar sozinho o espaço restante da coluna direita e ganha mais altura.\n- Mantém o atraso de Bicho 1º–5º sem mudança e acrescenta “Cabeça · 1º prêmio”, zerado apenas quando o bicho sai no 1º prêmio.\n- A nova métrica conta somente extrações completas e ignora aparições do mesmo bicho no 2º–5º prêmio.\n- A faixa inferior usa quatro cartões compactos: Bicho 1º–5º, Cabeça 1º prêmio, Centena e Dezena, preservando tooltip e leitura de última ocorrência.\n- Mudança restrita à Home/estatística de atraso; Meta, métodos, geradores, financeiro e auditorias permanecem inalterados.\n\n"""
if not doc_text.startswith("REVISÃO v0.48.20"):
    DOC.write_text(entry + doc_text, encoding="utf-8")

print("Patch v0.48.20 aplicado com sucesso.")
