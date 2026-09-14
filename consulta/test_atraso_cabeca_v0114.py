from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "gph_consulta.py"

spec = importlib.util.spec_from_file_location("gph_consulta_v0114", SOURCE)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def prize_rows(draw_no: int, head_group: int, second_group: int):
    hour = f"{8 + draw_no * 2:02d}:00"
    groups = (head_group, second_group, 5, 6, 7)
    rows = []
    for prize, group in enumerate(groups, start=1):
        rows.append({
            "data": "2026-09-14",
            "sorteio": f"T{draw_no}",
            "hora": hour,
            "premio": prize,
            "milhar": f"{draw_no}{prize}{group:02d}"[-4:],
            "centena": f"{prize}{group:02d}"[-3:],
            "dezena": f"{group:02d}",
            "grupo": group,
            "bicho": module.BICHOS.get(group, str(group)),
        })
    return rows


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _sql):
        return FakeCursor(self.rows)


class FakeReader:
    def __init__(self, rows):
        self.rows = rows

    def available(self):
        return True

    def connect(self):
        return FakeConnection(self.rows)


def calculate(rows):
    return module.HistoryReader.delay_leaders(FakeReader(rows))


# Grupo 1 saiu na cabeça na primeira extração e reapareceu depois somente no 2º prêmio.
# O atraso geral deve considerar essas reaparições, mas o atraso da cabeça não.
rows = []
rows += prize_rows(1, head_group=1, second_group=4)
rows += prize_rows(2, head_group=2, second_group=1)
rows += prize_rows(3, head_group=3, second_group=1)
result = calculate(rows)
assert result["bicho_cabeca"]["value"] == 1, result
assert result["bicho_cabeca"]["delay"] == 2, result
assert int(result["bicho_cabeca"]["last"]["premio"]) == 1, result
assert result["bicho"]["value"] != 1, "A reaparição fora da cabeça deve zerar o atraso geral do grupo 1"

# Quando o grupo 1 volta ao 1º prêmio, ele deixa imediatamente de liderar o atraso da cabeça.
rows += prize_rows(4, head_group=1, second_group=8)
result = calculate(rows)
assert result["bicho_cabeca"]["value"] == 2, result
assert result["bicho_cabeca"]["delay"] == 2, result
assert int(result["bicho_cabeca"]["last"]["premio"]) == 1, result

print("OK: atraso de cabeça da Consulta v0.1.14 validado")
