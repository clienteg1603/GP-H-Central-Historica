"""Hotfix v0.48.16 — normalização da Federal de domingo.

Corrige a equivalência entre o horário canônico FEDERAL 11:00 e registros
legados/importados como 11:20, sem alterar resultados, palpites ou cálculos.
"""
from __future__ import annotations

import copy
from datetime import datetime

HOTFIX_VERSION = "0.48.16"
CANONICAL_FEDERAL_HOUR = "11:00"
LEGACY_FEDERAL_HOURS = {"11:20", "11:20:00", "11h20", "11.20"}


def _hour_key(value):
    text = str(value or "").strip().lower().replace("h", ":").replace(".", ":")
    if len(text) == 4 and text[1] == ":":
        text = "0" + text
    if len(text) >= 5:
        text = text[:5]
    return text


def _is_sunday(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").weekday() == 6
    except Exception:
        return False


def is_sunday_federal(date_value, sorteio, hora):
    return (
        _is_sunday(date_value)
        and str(sorteio or "").strip().upper() == "FEDERAL"
        and _hour_key(hora) in {"11:00", "11:20"}
    )


def normalize_target(target):
    if not isinstance(target, dict):
        return target
    out = dict(target)
    date_value = out.get("data") or out.get("alvo_data")
    sorteio = out.get("sorteio") or out.get("alvo_sorteio")
    hora = out.get("hora") or out.get("alvo_hora")
    if is_sunday_federal(date_value, sorteio, hora):
        if "hora" in out:
            out["hora"] = CANONICAL_FEDERAL_HOUR
        if "alvo_hora" in out:
            out["alvo_hora"] = CANONICAL_FEDERAL_HOUR
    return out


def normalize_generation(generation):
    if not isinstance(generation, dict):
        return generation
    out = copy.deepcopy(generation)
    target = out.get("intended_target")
    if isinstance(target, dict):
        out["intended_target"] = normalize_target(target)
    return out


def normalize_legacy_rows(db):
    """Corrige somente alvos de jogos/bilhetes; não reescreve resultados."""
    changed_games = 0
    changed_tickets = 0
    with db.connect() as con:
        games = con.execute(
            "SELECT id, alvo_data, alvo_sorteio, alvo_hora FROM jogos_congelados "
            "WHERE UPPER(COALESCE(alvo_sorteio,''))='FEDERAL'"
        ).fetchall()
        for row in games:
            if is_sunday_federal(row["alvo_data"], row["alvo_sorteio"], row["alvo_hora"]) and _hour_key(row["alvo_hora"]) == "11:20":
                con.execute("UPDATE jogos_congelados SET alvo_hora=? WHERE id=?", (CANONICAL_FEDERAL_HOUR, int(row["id"])))
                changed_games += 1

        tickets = con.execute(
            "SELECT id, alvo_data, alvo_sorteio, alvo_hora FROM bilhetes "
            "WHERE UPPER(COALESCE(alvo_sorteio,''))='FEDERAL'"
        ).fetchall()
        for row in tickets:
            if is_sunday_federal(row["alvo_data"], row["alvo_sorteio"], row["alvo_hora"]) and _hour_key(row["alvo_hora"]) == "11:20":
                con.execute("UPDATE bilhetes SET alvo_hora=? WHERE id=?", (CANONICAL_FEDERAL_HOUR, int(row["id"])))
                changed_tickets += 1
    return {"games": changed_games, "tickets": changed_tickets}


def install_round_target_hotfix(central):
    db_class = central.Database
    if getattr(db_class, "_gph_v04816_target_hotfix", False):
        return

    original_init = db_class.__init__
    original_get_draw = db_class.get_draw
    original_next = db_class.next_operational_target
    original_future = db_class.future_operational_targets
    original_game_target = db_class.game_planned_target
    original_register_play = db_class.register_play
    original_register_ticket = db_class.register_ticket

    def init_fixed(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            self._gph_v04816_normalized = normalize_legacy_rows(self)
        except Exception as exc:
            self._gph_v04816_normalize_error = str(exc)

    def get_draw_fixed(self, draw_date, sorteio, hora):
        result = original_get_draw(self, draw_date, sorteio, hora)
        if result is None and _is_sunday(draw_date) and str(sorteio or "").strip().upper() == "FEDERAL":
            requested = _hour_key(hora)
            if requested in {"11:00", "11:20"}:
                for alias in ("11:00", "11:20"):
                    result = original_get_draw(self, draw_date, sorteio, alias)
                    if result is not None:
                        break
        if result is not None and is_sunday_federal(result.get("data"), result.get("sorteio"), result.get("hora")):
            result = dict(result)
            result["hora"] = CANONICAL_FEDERAL_HOUR
        return result

    def next_fixed(self):
        return normalize_target(original_next(self))

    def future_fixed(self, *args, **kwargs):
        return [normalize_target(x) for x in original_future(self, *args, **kwargs)]

    def game_target_fixed(self, game):
        return normalize_target(original_game_target(self, game))

    def register_play_fixed(self, generation, *args, **kwargs):
        return original_register_play(self, normalize_generation(generation), *args, **kwargs)

    def register_ticket_fixed(self, entries, *args, **kwargs):
        fixed_entries = []
        for entry in entries or []:
            new_entry = dict(entry)
            if isinstance(new_entry.get("generation"), dict):
                new_entry["generation"] = normalize_generation(new_entry["generation"])
            fixed_entries.append(new_entry)
        return original_register_ticket(self, fixed_entries, *args, **kwargs)

    db_class.__init__ = init_fixed
    db_class.get_draw = get_draw_fixed
    db_class.next_operational_target = next_fixed
    db_class.future_operational_targets = future_fixed
    db_class.game_planned_target = game_target_fixed
    db_class.register_play = register_play_fixed
    db_class.register_ticket = register_ticket_fixed
    db_class._gph_v04816_target_hotfix = True
