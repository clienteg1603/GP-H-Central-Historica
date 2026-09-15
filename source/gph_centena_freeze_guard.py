"""Guarda universal de congelamento da dezena principal.

A Lei GP-H já centraliza a geração numérica de Meta, Reset, Puxada,
Similaridade, Seca e seletores futuros. Esta extensão acrescenta uma trava de
precedência simples e prospectiva: se a dezena principal do bicho apareceu na
extração-base imediatamente anterior, ela NÃO pode voltar a ser usada na
rodada seguinte.

A máquina persistente histórica continua existindo. A trava da rodada anterior
apenas tem precedência sobre uma eventual liberação ocorrida no mesmo evento.
Exemplo: Macaco principal 68 + resultado-base 268/G17 => próxima geração usa
segunda+terceira dezenas, nunca 68.
"""
from __future__ import annotations


def _norm_dezena(value):
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    try:
        return f"{int(text) % 100:02d}"
    except Exception:
        return text.zfill(2)[-2:]


def _previous_group_prizes(previous_draw, group):
    try:
        group = int(group)
    except Exception:
        return []
    prizes = (previous_draw or {}).get("prizes") or []
    out = []
    for prize in prizes:
        try:
            if int(prize.get("grupo") or 0) == group:
                out.append(prize)
        except Exception:
            continue
    return out


def previous_draw_has_principal(previous_draw, group, principal_dezena):
    """True quando a principal saiu no mesmo bicho da extração-base."""
    principal = _norm_dezena(principal_dezena)
    if not principal:
        return False
    return any(
        _norm_dezena(prize.get("dezena")) == principal
        for prize in _previous_group_prizes(previous_draw, group)
    )


def _previous_event(previous_draw, group):
    prizes = _previous_group_prizes(previous_draw, group)
    return {
        "data": (previous_draw or {}).get("data"),
        "sorteio": (previous_draw or {}).get("sorteio"),
        "hora": (previous_draw or {}).get("hora"),
        "dezenas": [_norm_dezena(prize.get("dezena")) for prize in prizes],
        "motivo": "trava_rodada_anterior",
    }


def install_centena_freeze_guard(central_module):
    """Instala a trava no ponto comum usado por todos os geradores numéricos."""
    db_cls = central_module.Database
    if getattr(db_cls, "_gph_centena_freeze_guard_v04827_installed", False):
        return

    original = db_cls.centena_31_freeze_state

    def centena_31_freeze_state(self, group, principal_dezena, previous_draw=None):
        base = previous_draw
        if base is None:
            base = self.latest_operational_draw()

        state = original(
            self,
            group,
            principal_dezena,
            previous_draw=base,
        )
        state = dict(state or {})

        locked = previous_draw_has_principal(base, group, principal_dezena)
        state["previous_round_lock"] = bool(locked)
        state["previous_round_dezenas"] = [
            _norm_dezena(prize.get("dezena"))
            for prize in _previous_group_prizes(base, group)
        ]

        if locked:
            # A rodada imediatamente anterior tem precedência. Isso corrige o
            # caso em que a máquina persistente liberava a principal porque o
            # mesmo bicho reapareceu justamente com a própria principal.
            state["frozen"] = True
            state["trigger"] = _previous_event(base, group)
            state["released_by"] = None
            state["freeze_reason"] = "principal_na_rodada_imediatamente_anterior"
        else:
            state.setdefault("freeze_reason", "maquina_persistente")

        return state

    db_cls.centena_31_freeze_state = centena_31_freeze_state
    db_cls._gph_centena_freeze_guard_v04827_installed = True
