from pathlib import Path
import ast, re

SOURCE = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')
text = SOURCE.read_text(encoding='utf-8')

if 'APP_VERSION = "0.39.0"' not in text:
    raise SystemExit('v0.40.0 deve partir exatamente da v0.39.0')

# ------------------------------------------------------------------
# Travas: os motores de previsão permanecem idênticos nesta fase.
# ------------------------------------------------------------------
LOCKED = {
    'decision_contextual_evidence', '_decision_confidence',
    'method_reset_coverage_v1', 'method_convergencia_g5', 'method_similarity_day',
    'generate_centenas_3plus1', 'centena_31_freeze_state', 'historical_pulls',
    'method_historico_concentrado_v01', 'generate_historical_concentrated_bundle',
}

def method_ast(src):
    tree = ast.parse(src)
    found = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in LOCKED:
            found[n.name] = ast.dump(n, include_attributes=False)
    missing = LOCKED - set(found)
    if missing:
        raise SystemExit(f'Funções críticas ausentes antes do patch: {sorted(missing)}')
    return found

locked_before = method_ast(text)

# ------------------------------------------------------------------
# 1) Versão.
# ------------------------------------------------------------------
text = text.replace('GP-H Central Histórica v0.39.0', 'GP-H Central Histórica v0.40.0', 1)
text = text.replace('APP_VERSION = "0.39.0"', 'APP_VERSION = "0.40.0"', 1)

# ------------------------------------------------------------------
# 2) decision_snapshots: extensão idempotente do MESMO histórico.
# ------------------------------------------------------------------
old_schema = '''                    signals_json TEXT NOT NULL DEFAULT '{}',
                    result_groups_json TEXT,
                    audited_at TEXT,
                    note TEXT,
'''
new_schema = '''                    signals_json TEXT NOT NULL DEFAULT '{}',
                    contextual_json TEXT,
                    contextual_frozen_at TEXT,
                    contextual_audit_json TEXT,
                    result_groups_json TEXT,
                    audited_at TEXT,
                    note TEXT,
'''
if old_schema not in text:
    raise SystemExit('Trecho do schema decision_snapshots não encontrado')
text = text.replace(old_schema, new_schema, 1)

migration_anchor = '''            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_decision_status "
                "ON decision_snapshots(status)"
            )

            # v0.30.0 — Laboratório Sombra.
'''
migration_new = '''            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_decision_status "
                "ON decision_snapshots(status)"
            )

            # v0.40.0 — a Decisão Contextual passa a ser congelada no próprio
            # snapshot prospectivo. Migração aditiva: bases antigas são preservadas
            # e NÃO recebem reconstrução contextual retroativa.
            decision_columns = {
                str(row[1]) for row in con.execute("PRAGMA table_info(decision_snapshots)").fetchall()
            }
            for column, sql_type in (
                ("contextual_json", "TEXT"),
                ("contextual_frozen_at", "TEXT"),
                ("contextual_audit_json", "TEXT"),
            ):
                if column not in decision_columns:
                    con.execute(f"ALTER TABLE decision_snapshots ADD COLUMN {column} {sql_type}")

            # v0.30.0 — Laboratório Sombra.
'''
if migration_anchor not in text:
    raise SystemExit('Âncora da migração decision_snapshots não encontrada')
text = text.replace(migration_anchor, migration_new, 1)

# ------------------------------------------------------------------
# 3) Parser do snapshot inclui os dois novos JSONs.
# ------------------------------------------------------------------
old_parser = '''        for field in ("components_json", "signals_json", "result_groups_json"):
            raw = d.get(field)
            key = field.replace("_json", "")
            try:
                d[key] = json.loads(raw) if raw else ({} if field != "result_groups_json" else [])
            except Exception:
                d[key] = {} if field != "result_groups_json" else []
'''
new_parser = '''        json_defaults = {
            "components_json": {},
            "signals_json": {},
            "contextual_json": {},
            "contextual_audit_json": {},
            "result_groups_json": [],
        }
        for field, default in json_defaults.items():
            raw = d.get(field)
            key = field.replace("_json", "")
            try:
                d[key] = json.loads(raw) if raw else copy.deepcopy(default)
            except Exception:
                d[key] = copy.deepcopy(default)
'''
if old_parser not in text:
    raise SystemExit('Parser decision snapshot não encontrado')
text = text.replace(old_parser, new_parser, 1)

# ------------------------------------------------------------------
# 4) Motor de congelamento/auditoria da PRÓPRIA decisão.
# ------------------------------------------------------------------
insert_anchor = '''    def audit_decision_snapshots(self):
        """Audita somente snapshots cujo alvo já existe na base."""
'''
new_methods = r'''    def freeze_decision_contextual(self, snapshot=None, force=False):
        """
        Congela a primeira Decisão Contextual da rodada sem olhar o resultado.

        O congelamento automático usa a versão reproduzível sem Walk-Forward de
        sessão. Uma simulação executada depois pode continuar como diagnóstico,
        mas nunca reescreve o líder que será auditado.
        """
        snapshot = snapshot or self.latest_decision_snapshot()
        if not snapshot:
            raise ValueError("Não há snapshot prospectivo para congelar a Decisão Contextual.")

        target = {
            "data": snapshot.get("target_data"),
            "sorteio": snapshot.get("target_sorteio"),
            "hora": snapshot.get("target_hora"),
        }
        if not all(target.values()):
            raise ValueError("O snapshot não possui rodada-alvo completa.")

        # Regra anti-lookahead absoluta: nem force permite criar uma leitura
        # contextual depois que o resultado-alvo já existe na base.
        if self.get_draw(target["data"], target["sorteio"], target["hora"]):
            return snapshot, False

        existing = snapshot.get("contextual") or {}
        if existing and not force:
            return snapshot, False

        result = self.decision_contextual_evidence(
            target=target,
            snapshot=snapshot,
            window=120,
            recent_window=12,
            walk_forward=None,
        )
        frozen_at = datetime.now().isoformat(timespec="seconds")
        payload = copy.deepcopy(result or {})
        best = payload.get("best") or {}
        payload.update({
            "audit_schema": 1,
            "frozen_at": frozen_at,
            "frozen_app_version": APP_VERSION,
            "frozen_mode": "AUTO_SEM_WALK_FORWARD",
            "evidence_leader": best.get("method") if best else None,
        })

        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM decision_snapshots WHERE id=?",
                (int(snapshot["id"]),),
            ).fetchone()
            if row is None:
                raise ValueError("Snapshot de Decisão não encontrado.")
            current = self._decision_row_to_dict(row)
            if (current.get("contextual") or {}) and not force:
                return current, False
            # Revalida dentro da operação para não aceitar resultado que tenha
            # aparecido entre a leitura e a gravação.
            if self.get_draw(target["data"], target["sorteio"], target["hora"]):
                return current, False
            con.execute(
                "UPDATE decision_snapshots SET contextual_json=?, contextual_frozen_at=? WHERE id=?",
                (
                    json.dumps(payload, ensure_ascii=False),
                    frozen_at,
                    int(snapshot["id"]),
                ),
            )
            row = con.execute(
                "SELECT * FROM decision_snapshots WHERE id=?",
                (int(snapshot["id"]),),
            ).fetchone()
        return self._decision_row_to_dict(row), True

    @staticmethod
    def _decision_contextual_audit_payload(contextual, signals, result_groups):
        """Compara o líder congelado com a cobertura realmente obtida na rodada."""
        contextual = contextual or {}
        signals = signals or {}
        result_groups = [int(g) for g in (result_groups or [])]
        best = contextual.get("best") or {}
        leader = contextual.get("evidence_leader") or best.get("method")
        methods = ("Reset Cobertura", "Puxada Combinada", "Similaridade")

        hits = {}
        for name in methods:
            sig = signals.get(name) or {}
            if not sig.get("available"):
                continue
            value = sig.get("coverage_hits")
            if value is None:
                continue
            hits[name] = int(value)

        base = {
            "schema": 1,
            "leader": leader,
            "context_status": contextual.get("status") or "SEM DADOS",
            "leader_index": float(best.get("index") or 0.0) if best else None,
            "lead_index": float(contextual.get("lead") or 0.0),
            "hits": hits,
            "result_groups": result_groups,
        }
        if not leader or leader not in hits or not hits:
            base.update({
                "leader_hits": hits.get(leader) if leader else None,
                "best_hits": max(hits.values()) if hits else None,
                "best_methods": [],
                "classification": "SEM_DADOS",
                "is_best_or_tied": False,
                "is_sole_best": False,
            })
            return base

        best_hits = max(hits.values())
        winners = sorted(name for name, value in hits.items() if value == best_hits)
        leader_hits = int(hits[leader])
        if leader_hits == best_hits and len(winners) == 1:
            classification = "CORRETA_EXCLUSIVA"
        elif leader_hits == best_hits:
            classification = "CORRETA_EMPATE"
        else:
            classification = "INCORRETA"
        base.update({
            "leader_hits": leader_hits,
            "best_hits": int(best_hits),
            "best_methods": winners,
            "classification": classification,
            "is_best_or_tied": leader_hits == best_hits,
            "is_sole_best": classification == "CORRETA_EXCLUSIVA",
        })
        return base

    def decision_contextual_audit_summary(self, limit=120):
        """Resumo somente das decisões realmente congeladas a partir da v0.40.0."""
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM decision_snapshots "
                "WHERE status='AUDITADO' AND contextual_json IS NOT NULL "
                "AND TRIM(contextual_json)<>'' AND contextual_audit_json IS NOT NULL "
                "AND TRIM(contextual_audit_json)<>'' "
                "ORDER BY target_data DESC,target_hora DESC,id DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        parsed = [self._decision_row_to_dict(row) for row in rows]
        counts = {
            "audited_contextual": len(parsed),
            "evaluated": 0,
            "sole_correct": 0,
            "tied_best": 0,
            "incorrect": 0,
            "no_data": 0,
        }
        by_status = {}
        by_leader = {}
        recent = []

        for row in parsed:
            audit = row.get("contextual_audit") or {}
            contextual = row.get("contextual") or {}
            classification = audit.get("classification") or "SEM_DADOS"
            status = audit.get("context_status") or contextual.get("status") or "SEM DADOS"
            leader = audit.get("leader") or contextual.get("evidence_leader") or "—"

            if classification == "CORRETA_EXCLUSIVA":
                counts["sole_correct"] += 1
                counts["evaluated"] += 1
            elif classification == "CORRETA_EMPATE":
                counts["tied_best"] += 1
                counts["evaluated"] += 1
            elif classification == "INCORRETA":
                counts["incorrect"] += 1
                counts["evaluated"] += 1
            else:
                counts["no_data"] += 1

            for bucket_map, key in ((by_status, status), (by_leader, leader)):
                bucket = bucket_map.setdefault(key, {
                    "label": key, "total": 0, "evaluated": 0,
                    "sole_correct": 0, "tied_best": 0, "incorrect": 0,
                })
                bucket["total"] += 1
                if classification in ("CORRETA_EXCLUSIVA", "CORRETA_EMPATE", "INCORRETA"):
                    bucket["evaluated"] += 1
                    if classification == "CORRETA_EXCLUSIVA":
                        bucket["sole_correct"] += 1
                    elif classification == "CORRETA_EMPATE":
                        bucket["tied_best"] += 1
                    else:
                        bucket["incorrect"] += 1

            if len(recent) < 12:
                recent.append({
                    "target_data": row.get("target_data"),
                    "target_sorteio": row.get("target_sorteio"),
                    "target_hora": row.get("target_hora"),
                    "leader": leader,
                    "status": status,
                    "leader_index": audit.get("leader_index"),
                    "leader_hits": audit.get("leader_hits"),
                    "best_hits": audit.get("best_hits"),
                    "best_methods": audit.get("best_methods") or [],
                    "classification": classification,
                })

        evaluated = counts["evaluated"]
        counts["best_or_tied"] = counts["sole_correct"] + counts["tied_best"]
        counts["best_or_tied_rate"] = (
            counts["best_or_tied"] / evaluated * 100.0 if evaluated else None
        )
        counts["sole_correct_rate"] = (
            counts["sole_correct"] / evaluated * 100.0 if evaluated else None
        )

        def finish(values):
            out = []
            for bucket in values.values():
                n = bucket["evaluated"]
                bucket = dict(bucket)
                bucket["best_or_tied"] = bucket["sole_correct"] + bucket["tied_best"]
                bucket["best_or_tied_rate"] = (
                    bucket["best_or_tied"] / n * 100.0 if n else None
                )
                out.append(bucket)
            out.sort(key=lambda x: (-x["evaluated"], str(x["label"])))
            return out

        return {
            **counts,
            "by_status": finish(by_status),
            "by_leader": finish(by_leader),
            "recent": recent,
            "note": "Somente decisões contextuais congeladas antes do resultado; sem backfill retroativo.",
        }

'''
if insert_anchor not in text:
    raise SystemExit('Âncora de audit_decision_snapshots não encontrada')
text = text.replace(insert_anchor, new_methods + insert_anchor, 1)

# ------------------------------------------------------------------
# 5) Auditoria existente passa a anexar o veredito contextual.
# ------------------------------------------------------------------
old_audit = '''    def audit_decision_snapshots(self):
        """Audita somente snapshots cujo alvo já existe na base."""
        changed = 0
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM decision_snapshots WHERE status='PENDENTE' ORDER BY id"
            ).fetchall()
            for row in rows:
                target = self.get_draw(row["target_data"], row["target_sorteio"], row["target_hora"])
                if not target or len(target.get("prizes") or []) < 5:
                    continue
                result_groups = [int(p["grupo"]) for p in target["prizes"]]
                result_set = set(result_groups)
                try:
                    signals = json.loads(row["signals_json"] or "{}")
                except Exception:
                    signals = {}
                for sig in signals.values():
                    groups = [int(g) for g in (sig.get("groups") or [])]
                    sig["coverage_hits"] = len(set(groups) & result_set)
                    if sig.get("positional") and len(groups) >= 5:
                        sig["position_hits"] = sum(
                            1 for i in range(5) if int(groups[i]) == int(result_groups[i])
                        )
                    else:
                        sig["position_hits"] = None
                con.execute(
                    "UPDATE decision_snapshots SET status='AUDITADO',signals_json=?,result_groups_json=?,audited_at=? WHERE id=?",
                    (
                        json.dumps(signals, ensure_ascii=False),
                        json.dumps(result_groups),
                        datetime.now().isoformat(timespec="seconds"),
                        int(row["id"]),
                    ),
                )
                changed += 1
        return changed
'''
new_audit = '''    def audit_decision_snapshots(self):
        """Audita snapshots e, quando existente, a própria decisão contextual congelada."""
        changed = 0
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM decision_snapshots WHERE status='PENDENTE' ORDER BY id"
            ).fetchall()
            for row in rows:
                target = self.get_draw(row["target_data"], row["target_sorteio"], row["target_hora"])
                if not target or len(target.get("prizes") or []) < 5:
                    continue
                result_groups = [int(p["grupo"]) for p in target["prizes"]]
                result_set = set(result_groups)
                try:
                    signals = json.loads(row["signals_json"] or "{}")
                except Exception:
                    signals = {}
                for sig in signals.values():
                    groups = [int(g) for g in (sig.get("groups") or [])]
                    sig["coverage_hits"] = len(set(groups) & result_set)
                    if sig.get("positional") and len(groups) >= 5:
                        sig["position_hits"] = sum(
                            1 for i in range(5) if int(groups[i]) == int(result_groups[i])
                        )
                    else:
                        sig["position_hits"] = None

                # Linhas antigas seguem válidas para desempenho dos métodos, mas
                # não recebem uma decisão contextual inventada depois do resultado.
                try:
                    contextual = json.loads(row["contextual_json"] or "{}")
                except Exception:
                    contextual = {}
                contextual_audit = (
                    self._decision_contextual_audit_payload(contextual, signals, result_groups)
                    if contextual else None
                )
                con.execute(
                    "UPDATE decision_snapshots SET status='AUDITADO',signals_json=?,"
                    "contextual_audit_json=?,result_groups_json=?,audited_at=? WHERE id=?",
                    (
                        json.dumps(signals, ensure_ascii=False),
                        json.dumps(contextual_audit, ensure_ascii=False) if contextual_audit else None,
                        json.dumps(result_groups),
                        datetime.now().isoformat(timespec="seconds"),
                        int(row["id"]),
                    ),
                )
                changed += 1
        return changed
'''
if old_audit not in text:
    raise SystemExit('Corpo antigo de audit_decision_snapshots não encontrado')
text = text.replace(old_audit, new_audit, 1)

# ------------------------------------------------------------------
# 6) Sync: transporta a primeira decisão contextual e sua auditoria.
# ------------------------------------------------------------------
old_sync = '''    def _merge_sync_decision_snapshots(self, rows):
        added = updated = 0
        if not rows:
            return added, updated
        cols_allowed = {
            "created_at","base_data","base_sorteio","base_hora","target_data","target_sorteio","target_hora",
            "status","confidence_score","confidence_label","recommendation","components_json","signals_json",
            "result_groups_json","audited_at","note",
        }
        with self.connect() as con:
            for remote in rows:
                key = (
                    remote.get("base_data"), remote.get("base_sorteio"), remote.get("base_hora"),
                    remote.get("target_data"), remote.get("target_sorteio"), remote.get("target_hora"),
                )
                if not all(key):
                    continue
                local = con.execute(
                    "SELECT * FROM decision_snapshots WHERE base_data=? AND base_sorteio=? AND base_hora=? "
                    "AND target_data=? AND target_sorteio=? AND target_hora=?", key
                ).fetchone()
                if local is None:
                    data = {k: remote.get(k) for k in cols_allowed if k in remote}
                    keys = list(data)
                    con.execute(
                        f"INSERT INTO decision_snapshots ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                        [data[k] for k in keys],
                    )
                    added += 1
                    continue
                # A previsão mais antiga é a canônica; auditoria pode vir de qualquer PC.
                local_created = str(local["created_at"] or "9999")
                remote_created = str(remote.get("created_at") or "9999")
                changes = {}
                if remote_created < local_created:
                    for k in ("created_at","confidence_score","confidence_label","recommendation","components_json","signals_json","note"):
                        if k in remote:
                            changes[k] = remote.get(k)
                if str(remote.get("status") or "") == "AUDITADO" and str(local["status"] or "") != "AUDITADO":
                    for k in ("status","signals_json","result_groups_json","audited_at"):
                        changes[k] = remote.get(k)
                if changes:
                    sets = ",".join(f"{k}=?" for k in changes)
                    con.execute(f"UPDATE decision_snapshots SET {sets} WHERE id=?", list(changes.values()) + [int(local["id"])])
                    updated += 1
        return added, updated
'''
new_sync = '''    def _merge_sync_decision_snapshots(self, rows):
        added = updated = 0
        if not rows:
            return added, updated
        cols_allowed = {
            "created_at","base_data","base_sorteio","base_hora","target_data","target_sorteio","target_hora",
            "status","confidence_score","confidence_label","recommendation","components_json","signals_json",
            "contextual_json","contextual_frozen_at","contextual_audit_json",
            "result_groups_json","audited_at","note",
        }
        with self.connect() as con:
            for remote in rows:
                key = (
                    remote.get("base_data"), remote.get("base_sorteio"), remote.get("base_hora"),
                    remote.get("target_data"), remote.get("target_sorteio"), remote.get("target_hora"),
                )
                if not all(key):
                    continue
                local = con.execute(
                    "SELECT * FROM decision_snapshots WHERE base_data=? AND base_sorteio=? AND base_hora=? "
                    "AND target_data=? AND target_sorteio=? AND target_hora=?", key
                ).fetchone()
                if local is None:
                    data = {k: remote.get(k) for k in cols_allowed if k in remote}
                    keys = list(data)
                    con.execute(
                        f"INSERT INTO decision_snapshots ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                        [data[k] for k in keys],
                    )
                    added += 1
                    continue

                # A previsão-base mais antiga continua canônica.
                local_created = str(local["created_at"] or "9999")
                remote_created = str(remote.get("created_at") or "9999")
                changes = {}
                if remote_created < local_created:
                    for k in ("created_at","confidence_score","confidence_label","recommendation","components_json","signals_json","note"):
                        if k in remote:
                            changes[k] = remote.get(k)

                # Para a Decisão Contextual vale o mesmo princípio: a primeira
                # leitura congelada entre os PCs é a canônica.
                local_ctx = str(local["contextual_json"] or "").strip()
                remote_ctx = str(remote.get("contextual_json") or "").strip()
                local_ctx_at = str(local["contextual_frozen_at"] or "9999")
                remote_ctx_at = str(remote.get("contextual_frozen_at") or "9999")
                if remote_ctx and (not local_ctx or remote_ctx_at < local_ctx_at):
                    changes["contextual_json"] = remote.get("contextual_json")
                    changes["contextual_frozen_at"] = remote.get("contextual_frozen_at")

                if str(remote.get("status") or "") == "AUDITADO" and str(local["status"] or "") != "AUDITADO":
                    for k in ("status","signals_json","contextual_audit_json","result_groups_json","audited_at"):
                        changes[k] = remote.get(k)
                elif (
                    str(local["status"] or "") == "AUDITADO"
                    and not str(local["contextual_audit_json"] or "").strip()
                    and str(remote.get("contextual_audit_json") or "").strip()
                ):
                    changes["contextual_audit_json"] = remote.get("contextual_audit_json")

                if changes:
                    sets = ",".join(f"{k}=?" for k in changes)
                    con.execute(
                        f"UPDATE decision_snapshots SET {sets} WHERE id=?",
                        list(changes.values()) + [int(local["id"])],
                    )
                    updated += 1
        return added, updated
'''
if old_sync not in text:
    raise SystemExit('Bloco sync decision_snapshots não encontrado')
text = text.replace(old_sync, new_sync, 1)

# ------------------------------------------------------------------
# 7) Após cada resultado, já prepara a próxima Decisão, igual à Sombra.
# ------------------------------------------------------------------
old_result_cycle = '''        try:
            _shadow_row, shadow_created = self.ensure_shadow_snapshot(
                trigger="POS_RESULTADO"
            )
        except Exception:
            shadow_created = False

        return {
'''
new_result_cycle = '''        try:
            _shadow_row, shadow_created = self.ensure_shadow_snapshot(
                trigger="POS_RESULTADO"
            )
        except Exception:
            shadow_created = False

        # v0.40.0 — a inteligência da Decisão também passa a ser coletada
        # automaticamente após cada resultado, sem depender de abrir a tela.
        try:
            _decision_row, decision_created = self.freeze_decision_snapshot(force=False)
            _decision_row, contextual_created = self.freeze_decision_contextual(_decision_row, force=False)
        except Exception:
            decision_created = False
            contextual_created = False

        return {
'''
if old_result_cycle not in text:
    raise SystemExit('Ciclo pós-resultado não encontrado')
text = text.replace(old_result_cycle, new_result_cycle, 1)

old_return_tail = '''            "shadow_created_count": 1 if shadow_created else 0,
            "decision_audited_count": decision_changed,
        }
'''
new_return_tail = '''            "shadow_created_count": 1 if shadow_created else 0,
            "decision_audited_count": decision_changed,
            "decision_created_count": 1 if decision_created else 0,
            "contextual_created_count": 1 if contextual_created else 0,
        }
'''
if old_return_tail not in text:
    raise SystemExit('Retorno de auditoria pós-resultado não encontrado')
text = text.replace(old_return_tail, new_return_tail, 1)

# ------------------------------------------------------------------
# 8) Ciclo automático e abertura da tela garantem o congelamento contextual.
# ------------------------------------------------------------------
old_auto = '''            if target and not self.db.get_draw(target["data"], target["sorteio"], target["hora"]):
                self.db.freeze_decision_snapshot(force=False)
'''
new_auto = '''            if target and not self.db.get_draw(target["data"], target["sorteio"], target["hora"]):
                snapshot, _created = self.db.freeze_decision_snapshot(force=False)
                self.db.freeze_decision_contextual(snapshot, force=False)
'''
if old_auto not in text:
    raise SystemExit('Ciclo automático da Decisão não encontrado')
text = text.replace(old_auto, new_auto, 1)

old_show_freeze = '''        try:
            self.db.audit_decision_snapshots()
            snapshot, _created = self.db.freeze_decision_snapshot(force=False)
        except Exception as exc:
'''
new_show_freeze = '''        try:
            self.db.audit_decision_snapshots()
            snapshot, _created = self.db.freeze_decision_snapshot(force=False)
            snapshot, _context_created = self.db.freeze_decision_contextual(snapshot, force=False)
        except Exception as exc:
'''
if old_show_freeze not in text:
    raise SystemExit('Congelamento ao abrir Decisão não encontrado')
text = text.replace(old_show_freeze, new_show_freeze, 1)

# ------------------------------------------------------------------
# 9) O painel principal mostra a leitura CONGELADA, não recalcula ao abrir.
# ------------------------------------------------------------------
old_context_start = '''    def _decision_build_contextual(self, body, snapshot):
        """Painel v0.37.0: melhor evidência para o contexto da próxima rodada."""
        target = {
            "data": snapshot.get("target_data"),
            "sorteio": snapshot.get("target_sorteio"),
            "hora": snapshot.get("target_hora"),
        }
        wf = getattr(self, "walk_forward_last_result", None)
        result = self.db.decision_contextual_evidence(
            target=target, snapshot=snapshot, window=120,
            recent_window=12, walk_forward=wf,
        )
'''
new_context_start = '''    def _decision_build_contextual(self, body, snapshot):
        """Painel auditável: exibe a primeira leitura contextual congelada da rodada."""
        result = snapshot.get("contextual") or {}
'''
if old_context_start not in text:
    raise SystemExit('Início do painel contextual não encontrado')
text = text.replace(old_context_start, new_context_start, 1)

old_wf_note = '''        wf_note = (
            "Walk-Forward usado: última simulação concluída nesta sessão."
            if result.get("walk_forward_used")
            else "Walk-Forward ainda não executado nesta sessão; esse componente foi retirado e os demais pesos foram renormalizados."
        )
'''
new_wf_note = '''        frozen_at = str(snapshot.get("contextual_frozen_at") or result.get("frozen_at") or "—").replace("T", " ")
        wf_note = (
            f"Leitura auditável congelada em {frozen_at}. "
            "O congelamento automático não usa Walk-Forward de sessão; simulações posteriores "
            "continuam como diagnóstico e não reescrevem esta escolha."
        )
'''
if old_wf_note not in text:
    raise SystemExit('Nota Walk-Forward contextual não encontrada')
text = text.replace(old_wf_note, new_wf_note, 1)

# Insere a auditoria da própria decisão logo após o painel contextual.
call_anchor = '''        # v0.37.0 — comparação contextual dos métodos para a próxima rodada.
        self._decision_build_contextual(body, snapshot)

        # Componentes transparentes do índice.
'''
call_new = '''        # v0.37.0/v0.40.0 — leitura contextual agora é congelada e auditável.
        self._decision_build_contextual(body, snapshot)
        self._decision_build_self_audit(body)

        # Componentes transparentes do índice.
'''
if call_anchor not in text:
    raise SystemExit('Chamada do painel contextual não encontrada')
text = text.replace(call_anchor, call_new, 1)

# UI da auditoria, antes da Etapa 2.
stage2_anchor = '''    def _decision_build_stage2(self, body, snapshot):
'''
self_audit_ui = r'''    def _decision_build_self_audit(self, body):
        summary = self.db.decision_contextual_audit_summary(limit=120)
        card = ttk.Frame(body, style="Card.TFrame", padding=10)
        card.pack(fill="x", pady=(0, 8))
        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="AUDITORIA DA PRÓPRIA DECISÃO", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(
            head, text="coleta prospectiva desde v0.40.0 • sem backfill",
            style="CardMuted.TLabel",
        ).pack(side="right")

        evaluated = int(summary.get("evaluated") or 0)
        if not evaluated:
            ttk.Label(
                card,
                text=(
                    "Coleta iniciada. Ainda não existe uma Decisão Contextual v0.40.0 "
                    "com resultado auditado. Rodadas antigas não são reconstruídas."
                ),
                style="CardMuted.TLabel", wraplength=1050,
            ).pack(anchor="w", pady=(6, 0))
            return

        rate = summary.get("best_or_tied_rate")
        rate_text = "—" if rate is None else f"{float(rate):.1f}%"
        kpis = ttk.Frame(card, style="Card.TFrame")
        kpis.pack(fill="x", pady=(7, 7))
        defs = (
            ("DECISÕES AUDITADAS", evaluated),
            ("MELHOR OU EMPATADA", rate_text),
            ("MELHOR EXCLUSIVA", int(summary.get("sole_correct") or 0)),
            ("INCORRETAS", int(summary.get("incorrect") or 0)),
        )
        for idx, (title, value) in enumerate(defs):
            box = ttk.Frame(kpis, style="Card2.TFrame", padding=8)
            box.pack(side="left", fill="x", expand=True, padx=(0, 6 if idx < 3 else 0))
            ttk.Label(box, text=title, style="CardMuted.TLabel").pack(anchor="w")
            ttk.Label(
                box, text=str(value), style="Card.TLabel",
                font=(UI_FONT_SEMIBOLD, UI_FONT_SIZES["kpi"]),
            ).pack(anchor="w")

        cols = ("target", "leader", "status", "index", "hits", "best", "verdict")
        tree = ttk.Treeview(card, columns=cols, show="headings", height=min(6, max(3, len(summary.get("recent") or []))))
        heads = {
            "target": "Rodada", "leader": "Líder congelado", "status": "Nível",
            "index": "Índice", "hits": "Acerto", "best": "Melhor", "verdict": "Veredito",
        }
        widths = {
            "target": 150, "leader": 180, "status": 150,
            "index": 62, "hits": 70, "best": 115, "verdict": 145,
        }
        for col in cols:
            tree.heading(col, text=heads[col])
            tree.column(col, width=widths[col], anchor="w" if col in ("target", "leader", "status", "best", "verdict") else "center")

        verdict_labels = {
            "CORRETA_EXCLUSIVA": "Correta exclusiva",
            "CORRETA_EMPATE": "Correta em empate",
            "INCORRETA": "Incorreta",
            "SEM_DADOS": "Sem dados",
        }
        for row in summary.get("recent") or []:
            try:
                d = datetime.strptime(str(row.get("target_data")), "%Y-%m-%d").strftime("%d/%m")
            except Exception:
                d = str(row.get("target_data") or "—")
            target = f"{d} {row.get('target_sorteio') or '—'} {row.get('target_hora') or ''}".strip()
            leader_hits = row.get("leader_hits")
            best_hits = row.get("best_hits")
            hit_text = "—" if leader_hits is None else f"{int(leader_hits)}/5"
            best_names = row.get("best_methods") or []
            best_text = ", ".join(
                {"Reset Cobertura":"Reset", "Puxada Combinada":"Puxada", "Similaridade":"Similar."}.get(name, name)
                for name in best_names
            ) or "—"
            idx = row.get("leader_index")
            tree.insert("", "end", values=(
                target,
                row.get("leader") or "—",
                row.get("status") or "—",
                "—" if idx is None else f"{float(idx):.0f}",
                hit_text,
                (f"{best_text} ({int(best_hits)}/5)" if best_hits is not None else best_text),
                verdict_labels.get(row.get("classification"), row.get("classification") or "—"),
            ))
        tree.pack(fill="x", pady=(0, 4))

        statuses = [r for r in summary.get("by_status") or [] if int(r.get("evaluated") or 0) > 0]
        if statuses:
            status_text = "   •   ".join(
                f"{r['label']}: {r['best_or_tied']}/{r['evaluated']} ({r['best_or_tied_rate']:.0f}%)"
                for r in statuses[:5]
                if r.get("best_or_tied_rate") is not None
            )
            if status_text:
                ttk.Label(
                    card,
                    text="Por nível congelado: " + status_text,
                    style="CardMuted.TLabel", wraplength=1050,
                ).pack(anchor="w")
        ttk.Label(
            card,
            text=(
                "Empate é registrado separadamente e não conta como vitória exclusiva. "
                "Este painel mede a qualidade da escolha entre métodos; não altera o Reset + 3+1 oficial."
            ),
            style="CardMuted.TLabel", wraplength=1050,
        ).pack(anchor="w", pady=(2, 0))

'''
if stage2_anchor not in text:
    raise SystemExit('Âncora Stage2 não encontrada')
text = text.replace(stage2_anchor, self_audit_ui + stage2_anchor, 1)

# ------------------------------------------------------------------
# 10) Histórico Sobre + documentação.
# ------------------------------------------------------------------
needle = '            "• v0.39.0 —'
pos = text.find(needle)
if pos < 0:
    raise SystemExit('Linha v0.39.0 do Sobre não encontrada')
text = text[:pos] + (
    '            "• v0.40.0 — auditoria prospectiva da própria Decisão: líder contextual congelado antes da rodada e conferido depois, sem backfill.\\n"\n'
) + text[pos:]

# ------------------------------------------------------------------
# 11) Validações estruturais.
# ------------------------------------------------------------------
ast.parse(text)
locked_after = method_ast(text)
for name in LOCKED:
    if locked_before[name] != locked_after[name]:
        raise SystemExit(f'MOTOR CRÍTICO ALTERADO INDEVIDAMENTE: {name}')

required = [
    'APP_VERSION = "0.40.0"',
    'contextual_json TEXT',
    'contextual_frozen_at TEXT',
    'contextual_audit_json TEXT',
    'def freeze_decision_contextual(',
    'def _decision_contextual_audit_payload(',
    'def decision_contextual_audit_summary(',
    'def _decision_build_self_audit(',
    'CORRETA_EXCLUSIVA', 'CORRETA_EMPATE', 'INCORRETA',
    'AUTO_SEM_WALK_FORWARD',
]
for marker in required:
    if marker not in text:
        raise SystemExit(f'Marcador ausente após patch: {marker}')

SOURCE.write_text(text, encoding='utf-8')

doc = DOC.read_text(encoding='utf-8')
revision = '''REVISÃO v0.40.0 — AUDITORIA PROSPECTIVA DA PRÓPRIA DECISÃO
- A Decisão Contextual deixa de existir apenas como cálculo exibido na tela e passa a ser congelada dentro do mesmo decision_snapshot antes da rodada-alvo.
- O congelamento salva líder de evidência, índices dos três métodos, diferença entre 1º e 2º, nível FORTE/MODERADA/BAIXA/AMOSTRA INSUFICIENTE, fatores ativos e horário/data do congelamento.
- O congelamento auditável usa modo reproduzível sem Walk-Forward de sessão. Executar Walk-Forward depois continua sendo diagnóstico e nunca reescreve a decisão já congelada.
- Regra anti-lookahead: se o resultado-alvo já existe na base, a Central não cria contextual_json nem mesmo por force; rodadas antigas sem leitura contextual permanecem sem backfill.
- Após o resultado, a Central compara a cobertura 1º–5º do líder congelado contra Reset Cobertura, Puxada Combinada e Similaridade na mesma rodada.
- Vereditos separados: CORRETA_EXCLUSIVA quando o líder foi sozinho o melhor; CORRETA_EMPATE quando terminou empatado entre os melhores; INCORRETA quando outro método teve cobertura maior; SEM_DADOS quando não havia líder avaliável.
- Novo painel “AUDITORIA DA PRÓPRIA DECISÃO” mostra quantidade de decisões avaliadas, taxa em que o líder foi melhor ou empatado, vitórias exclusivas, erros, histórico recente e recorte por nível de confiança contextual.
- A coleta é automática após cada novo resultado e também na abertura da Central/tela Decisão; não depende de o usuário abrir a página antes da rodada.
- Sincronização multi-PC passa a transportar contextual_json/contextual_frozen_at/contextual_audit_json; entre duas leituras do mesmo alvo, o congelamento contextual mais antigo é o canônico.
- Nenhum peso do Índice de Evidência Contextual foi alterado. Reset + 3+1 continua oficial e nenhum método é promovido automaticamente.
- Reset Cobertura, Puxada Combinada, Similaridade, Histórico Concentrado, 3+1 e demais motores foram preservados por comparação AST antes/depois.

'''
if not doc.startswith('REVISÃO v0.40.0'):
    doc = revision + doc
DOC.write_text(doc, encoding='utf-8')

print('PATCH v0.40.0 OK')
print('Linhas:', len(text.splitlines()))
print('Motores preservados:', ', '.join(sorted(LOCKED)))
