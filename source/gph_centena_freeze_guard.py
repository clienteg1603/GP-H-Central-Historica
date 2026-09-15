"""Congelamento rotativo de dezena por bicho — Lei GP-H.

Regra operacional a partir da v0.48.28:
- cada bicho mantém UMA dezena congelada: a dezena da aparição mais recente
  desse bicho até a extração-base;
- quando o mesmo bicho reaparece em outra dezena, a anterior é liberada e a
  nova dezena passa a ser a congelada;
- a dezena congelada é retirada do ranking ativo antes da geração numérica;
- por isso, com quatro Centenas, a Lei continua 3+1, mas usa as duas dezenas
  historicamente mais fortes ENTRE AS QUE ESTÃO LIVRES;
- o cutoff recebido em ``previous_draw`` é respeitado, portanto laboratórios e
  walk-forward continuam sem olhar o futuro.

A Lei GP-H é o ponto comum de Meta, Reset, Puxada Combinada, Similaridade,
Seca do Dia e demais seletores. A proteção é instalada nessa camada comum e
na rotina 3+1 direta, para nenhum método escapar da mesma regra.
"""
from __future__ import annotations

from contextvars import ContextVar


_ACTIVE_FREEZE = ContextVar("gph_active_centena_freeze", default=None)


def _norm_dezena(value):
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    try:
        return f"{int(text) % 100:02d}"
    except Exception:
        return text.zfill(2)[-2:]


def _draw_key(draw):
    draw = draw or {}
    return (
        str(draw.get("data") or ""),
        str(draw.get("sorteio") or ""),
        str(draw.get("hora") or ""),
    )


def _group_prizes(draw, group):
    try:
        group = int(group)
    except Exception:
        return []
    out = []
    for prize in (draw or {}).get("prizes") or []:
        try:
            if int(prize.get("grupo") or 0) == group:
                out.append(prize)
        except Exception:
            continue
    return out


def _cutoff_draws(db, previous_draw=None):
    base = previous_draw
    if base is None:
        base = db.latest_operational_draw()
    if base is None:
        return None, []

    try:
        draws = list(db._draws_in_order())
    except Exception:
        draws = []

    base_key = _draw_key(base)
    cutoff_idx = next(
        (i for i, draw in enumerate(draws) if _draw_key(draw) == base_key),
        None,
    )
    if cutoff_idx is None:
        # Compatibilidade com testes/entradas manuais ainda não persistidas:
        # nunca usa um sorteio posterior ao cutoff fornecido.
        return base, [base]
    return base, draws[:cutoff_idx + 1]


def frozen_dezena_for_group(db, group, previous_draw=None):
    """Retorna a dezena atualmente congelada do bicho no cutoff informado.

    A aparição mais recente do bicho substitui o estado anterior. Se houver
    repetição do mesmo bicho em mais de um prêmio da mesma extração, usa-se a
    primeira ocorrência da lista de prêmios (maior colocação), mantendo um
    único estado de congelamento por bicho.
    """
    _base, draws = _cutoff_draws(db, previous_draw=previous_draw)
    for draw in reversed(draws):
        prizes = _group_prizes(draw, group)
        if not prizes:
            continue
        for prize in prizes:
            dezena = _norm_dezena(prize.get("dezena"))
            if dezena:
                return dezena
    return None


def _freeze_event_for_group(db, group, previous_draw=None):
    base, draws = _cutoff_draws(db, previous_draw=previous_draw)
    locked = frozen_dezena_for_group(db, group, previous_draw=base)
    if not locked:
        return None
    for draw in reversed(draws):
        prizes = _group_prizes(draw, group)
        if not prizes:
            continue
        first = next(
            (p for p in prizes if _norm_dezena(p.get("dezena")) == locked),
            prizes[0],
        )
        return {
            "data": draw.get("data"),
            "sorteio": draw.get("sorteio"),
            "hora": draw.get("hora"),
            "dezena": locked,
            "premio": first.get("premio"),
            "motivo": "ultima_dezena_aparecida_do_bicho",
        }
    return None


def _freeze_map(db, groups, previous_draw=None):
    out = {}
    seen = set()
    for raw in groups or []:
        try:
            group = int(raw)
        except Exception:
            continue
        if group in seen:
            continue
        seen.add(group)
        locked = frozen_dezena_for_group(db, group, previous_draw=previous_draw)
        if locked:
            out[group] = locked
    return out


def _context_for(db):
    ctx = _ACTIVE_FREEZE.get()
    if not ctx or ctx.get("db_id") != id(db):
        return None
    return ctx


def _annotate_result(result, freeze_map):
    if not isinstance(result, dict):
        return result
    result["freeze_rule"] = "ultima_dezena_do_bicho_rotativa"
    result["frozen_dezenas_by_group"] = {
        str(group): dezena for group, dezena in sorted(freeze_map.items())
    }

    for animal in result.get("animals") or []:
        try:
            group = int(animal.get("grupo"))
        except Exception:
            continue
        locked = freeze_map.get(group)
        animal["frozen"] = bool(locked)
        animal["frozen_dezena"] = locked
        animal["freeze_rule"] = "ultima_dezena_do_bicho_rotativa"

    for row in result.get("rows") or []:
        try:
            group = int(row.get("grupo"))
        except Exception:
            continue
        locked = freeze_map.get(group)
        if locked:
            row["frozen"] = True
            row["frozen_dezena"] = locked
            row["freeze_rule"] = "ultima_dezena_do_bicho_rotativa"
    return result


def install_centena_freeze_guard(central_module):
    """Instala a regra rotativa no ponto comum de todos os geradores."""
    db_cls = central_module.Database
    if getattr(db_cls, "_gph_centena_freeze_guard_v04828_installed", False):
        return

    original_rankings = db_cls.number_rankings_for_group
    original_state = db_cls.centena_31_freeze_state
    original_law = db_cls.generate_gph_law_numbers
    original_31 = db_cls.generate_centenas_3plus1

    def number_rankings_for_group(self, group, kind="Centena", *args, **kwargs):
        rows = list(original_rankings(self, group, kind, *args, **kwargs) or [])
        ctx = _context_for(self)
        if not ctx or str(kind or "").strip().casefold() != "dezena":
            return rows
        try:
            group_int = int(group)
        except Exception:
            return rows
        locked = ctx.get("frozen", {}).get(group_int)
        if not locked:
            return rows

        # O gerador antigo continua fazendo toda a distribuição 3+1/2:1.
        # Apenas retiramos a dezena congelada do conjunto ativo, empurrando-a
        # para o fim do ranking. As três dezenas livres preservam sua ordem
        # histórica original.
        active = [r for r in rows if _norm_dezena(r.get("numero")) != locked]
        blocked = [r for r in rows if _norm_dezena(r.get("numero")) == locked]
        return active + blocked

    def centena_31_freeze_state(self, group, principal_dezena, previous_draw=None):
        ctx = _context_for(self)
        locked = None
        if ctx:
            try:
                locked = ctx.get("frozen", {}).get(int(group))
            except Exception:
                locked = None
        if locked is None:
            locked = frozen_dezena_for_group(
                self, group, previous_draw=previous_draw
            )

        if not locked:
            # Sem aparição anterior desse bicho, mantém compatibilidade com a
            # estrutura antiga, embora isso seja raro numa base já madura.
            return original_state(
                self, group, principal_dezena, previous_draw=previous_draw
            )

        event = _freeze_event_for_group(
            self, group, previous_draw=previous_draw
        )
        state = {
            "grupo": int(group),
            "principal": _norm_dezena(principal_dezena),
            "frozen_dezena": locked,
            "frozen_dezenas": [locked],
            "trigger": event,
            "released_by": None,
            "freeze_reason": "ultima_dezena_aparecida_do_bicho",
            "freeze_rule": "rotativa_por_bicho",
        }

        if ctx:
            # Dentro da geração, a dezena congelada já foi removida do ranking
            # ativo. Retornar frozen=True faria a máquina antiga deslocar uma
            # segunda vez (e poderia descartar uma dezena livre), por isso o
            # deslocamento legado é neutralizado somente neste contexto.
            state["frozen"] = False
            state["rotating_freeze_active"] = True
            state["engine_shift_suppressed"] = True
        else:
            # Para telas/diagnósticos, há um congelamento real ativo.
            state["frozen"] = True
            state["rotating_freeze_active"] = True
            state["engine_shift_suppressed"] = False
        return state

    def _run_with_context(self, groups, previous_draw, callback):
        base = previous_draw
        if base is None:
            base = self.latest_operational_draw()
        freeze_map = _freeze_map(self, groups, previous_draw=base)
        token = _ACTIVE_FREEZE.set({
            "db_id": id(self),
            "frozen": freeze_map,
            "previous_draw": base,
        })
        try:
            result = callback(base)
        finally:
            _ACTIVE_FREEZE.reset(token)
        return _annotate_result(result, freeze_map)

    def generate_gph_law_numbers(
        self,
        groups,
        kind="Centena",
        total=20,
        previous_draw=None,
        scope="1º–5º",
        date_to=None,
    ):
        if str(kind or "").strip().casefold() not in ("centena", "milhar"):
            return original_law(
                self,
                groups,
                kind=kind,
                total=total,
                previous_draw=previous_draw,
                scope=scope,
                date_to=date_to,
            )

        return _run_with_context(
            self,
            groups,
            previous_draw,
            lambda base: original_law(
                self,
                groups,
                kind=kind,
                total=total,
                previous_draw=base,
                scope=scope,
                date_to=date_to,
            ),
        )

    def generate_centenas_3plus1(self, groups, previous_draw=None):
        return _run_with_context(
            self,
            groups,
            previous_draw,
            lambda base: original_31(
                self,
                groups,
                previous_draw=base,
            ),
        )

    db_cls.number_rankings_for_group = number_rankings_for_group
    db_cls.centena_31_freeze_state = centena_31_freeze_state
    db_cls.generate_gph_law_numbers = generate_gph_law_numbers
    db_cls.generate_centenas_3plus1 = generate_centenas_3plus1
    db_cls._gph_centena_freeze_guard_v04828_installed = True
