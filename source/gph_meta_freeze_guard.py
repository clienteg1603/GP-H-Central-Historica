"""Guarda prospectiva de congelamento do GP-H Meta — v0.48.24.

Garante que a próxima rodada operacional receba o primeiro snapshot Meta antes
do resultado, sem depender de abrir a tela Decisão nem de gerar uma aposta Meta.

Regras de segurança:
- nunca cria/recria Meta se o resultado-alvo já existe;
- nunca sobrescreve um Meta já congelado;
- usa exclusivamente freeze_decision_snapshot/freeze_meta_snapshot existentes;
- não faz backfill de rodadas antigas;
- não altera pesos, treino, ranking, geradores ou auditoria do cérebro Meta.
"""
from __future__ import annotations

GUARD_VERSION = "0.48.24"
WATCHDOG_MS = 15_000


def _target_key(target):
    target = target or {}
    return (
        str(target.get("data") or ""),
        str(target.get("sorteio") or ""),
        str(target.get("hora") or ""),
    )


def _snapshot_target(snapshot):
    snapshot = snapshot or {}
    return (
        str(snapshot.get("target_data") or ""),
        str(snapshot.get("target_sorteio") or ""),
        str(snapshot.get("target_hora") or ""),
    )


def ensure_next_meta_frozen(db):
    """Garante Meta congelado somente para a próxima rodada ainda sem resultado."""
    target = db.next_operational_target()
    if not target or not all(_target_key(target)):
        return {"status": "SEM_ALVO", "created": False, "target": _target_key(target)}

    key = _target_key(target)
    if db.get_draw(*key):
        # Proteção anti-lookahead: jamais cria Meta depois que o alvo já saiu.
        return {"status": "RESULTADO_JA_EXISTE", "created": False, "target": key}

    snapshot, _snapshot_created = db.freeze_decision_snapshot(force=False)
    if not snapshot:
        return {"status": "SEM_SNAPSHOT", "created": False, "target": key}

    snapshot_key = _snapshot_target(snapshot)
    if snapshot_key != key:
        raise RuntimeError(
            "Snapshot prospectivo não corresponde à próxima rodada operacional: "
            f"esperado={key!r}, snapshot={snapshot_key!r}."
        )

    if snapshot.get("meta"):
        return {"status": "JA_CONGELADO", "created": False, "target": key}

    frozen, created = db.freeze_meta_snapshot(snapshot=snapshot, force=False)
    meta = (frozen or {}).get("meta") or {}
    if not meta:
        return {"status": "NAO_CONGELADO", "created": False, "target": key}

    return {
        "status": "CONGELADO" if created else "JA_CONGELADO",
        "created": bool(created),
        "target": key,
        "available": bool(meta.get("available")),
        "meta_status": str(meta.get("status") or ""),
    }


def install_meta_freeze_guard(central_module):
    """Instala garantia pós-auditoria + watchdog enquanto a Central estiver aberta."""
    db_class = central_module.Database
    app_class = central_module.App
    if getattr(db_class, "_gph_meta_freeze_guard_v04824", False):
        return

    original_audit = db_class.audit_decision_snapshots
    original_app_init = app_class.__init__

    def audit_with_meta_freeze(self, *args, **kwargs):
        result = original_audit(self, *args, **kwargs)
        try:
            self._gph_meta_freeze_guard_last = ensure_next_meta_frozen(self)
            self._gph_meta_freeze_guard_error = ""
        except Exception as exc:
            # A auditoria anterior continua válida; a falha fica registrada e o
            # watchdog tentará novamente enquanto o alvo ainda estiver pendente.
            self._gph_meta_freeze_guard_error = str(exc)
        return result

    def app_init_with_watchdog(self, *args, **kwargs):
        original_app_init(self, *args, **kwargs)

        def tick():
            if getattr(self, "_startup_cancelled", False):
                return
            try:
                self._gph_meta_freeze_watchdog_last = ensure_next_meta_frozen(self.db)
                self._gph_meta_freeze_watchdog_error = ""
            except Exception as exc:
                self._gph_meta_freeze_watchdog_error = str(exc)
            try:
                self.after(WATCHDOG_MS, tick)
            except Exception:
                pass

        try:
            self.after(2_300, tick)
        except Exception:
            pass

    db_class.audit_decision_snapshots = audit_with_meta_freeze
    app_class.__init__ = app_init_with_watchdog
    db_class._gph_meta_freeze_guard_v04824 = True
    app_class._gph_meta_freeze_guard_v04824 = True
