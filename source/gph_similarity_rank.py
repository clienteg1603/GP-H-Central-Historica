"""Helpers de ranking para a Similaridade do Dia.

A previsão posicional da Similaridade pode repetir o mesmo grupo em mais de
um dos cinco prêmios. Para geração de jogos, porém, quando o usuário pede N
bichos precisamos entregar até N grupos distintos sem perder a prioridade dos
vencedores posicionais e sem inventar grupos fora da evidência histórica.
"""
from __future__ import annotations


def distinct_similarity_groups(result, top_n=5):
    """Retorna grupos distintos em ordem determinística de prioridade.

    1. Mantém, na ordem original, os vencedores dos cinco slots de ``selected``.
    2. Se houve repetição e ainda faltam grupos, completa com os demais grupos
       mais fortes dos dias históricos usados, somando os votos ponderados de
       todos os cinco prêmios.

    O helper nunca inventa um grupo: se a amostra não contiver grupos distintos
    suficientes, devolve somente os que realmente existem.
    """
    try:
        limit = max(1, min(25, int(top_n)))
    except Exception:
        limit = 5

    chosen = []
    seen = set()

    def add(raw_group):
        try:
            group = int(raw_group)
        except (TypeError, ValueError):
            return
        if not 1 <= group <= 25 or group in seen:
            return
        seen.add(group)
        chosen.append(group)

    for row in (result or {}).get("selected") or []:
        add((row or {}).get("grupo"))
        if len(chosen) >= limit:
            return chosen[:limit]

    aggregate = {}
    first_seen = {}
    serial = 0
    for candidate in (result or {}).get("top_days") or []:
        try:
            weight = max(float((candidate or {}).get("score") or 0.0), 0.0001)
        except (TypeError, ValueError):
            weight = 0.0001
        target = (candidate or {}).get("target") or {}
        for prize in target.get("prizes") or []:
            try:
                group = int((prize or {}).get("grupo"))
            except (TypeError, ValueError):
                continue
            if not 1 <= group <= 25:
                continue
            aggregate[group] = aggregate.get(group, 0.0) + weight
            first_seen.setdefault(group, serial)
            serial += 1

    ordered = sorted(
        aggregate,
        key=lambda group: (-aggregate[group], first_seen.get(group, 10**9), group),
    )
    for group in ordered:
        add(group)
        if len(chosen) >= limit:
            break

    return chosen[:limit]
