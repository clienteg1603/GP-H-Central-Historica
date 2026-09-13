"""Apoio enxuto da Home do GP-H.

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
