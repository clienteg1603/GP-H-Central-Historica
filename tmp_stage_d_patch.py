from pathlib import Path
import ast

SRC = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')
text = SRC.read_text(encoding='utf-8')
doc = DOC.read_text(encoding='utf-8')


def fn_dump(source, name):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(f'função não encontrada: {name}')


# A Etapa D é uma camada de tradução operacional. Ela NÃO pode alterar os
# motores, o Meta, a Etapa C, o 3+1 ou a lógica da Decisão Contextual.
critical = [
    'init_schema',
    '_meta_feature_names', '_meta_feature_vector', '_meta_fit_logit', '_meta_model_score',
    '_meta_training_records', '_meta_examples', '_meta_temporal_holdout', 'meta_shadow_prediction',
    'meta_walk_forward', 'method_reset_coverage_v1', 'method_convergencia_g5', 'method_similarity_day',
    'method_historico_concentrado_v01', 'generate_historical_concentrated_bundle',
    'generate_centenas_3plus1', 'centena_31_freeze_state', 'decision_contextual_evidence',
    'decision_contextual_audit_summary', 'decision_confidence_calibration', 'audit_decision_snapshots',
    'decision_walk_forward', '_decision_contextual_audit_payload', 'freeze_meta_snapshot',
    'meta_shadow_summary', 'historical_pulls', 'decision_adaptive_context',
    'decision_adaptive_audit_summary', '_decision_build_adaptive',
    '_decision_build_self_audit', '_decision_build_confidence_calibration',
]
before = {name: fn_dump(text, name) for name in critical}

assert 'APP_VERSION = "0.44.0"' in text
assert 'GP-H Central Histórica v0.44.0' in text
assert 'def decision_operational_recommendation(' not in text
assert 'def decision_operational_audit_summary(' not in text
assert 'def _decision_build_operational(' not in text

text = text.replace('GP-H Central Histórica v0.44.0', 'GP-H Central Histórica v0.45.0', 1)
text = text.replace('APP_VERSION = "0.44.0"', 'APP_VERSION = "0.45.0"', 1)
text = text.replace('text="v0.44 • cérebro v0.1 congelado"', 'text="v0.45 • cérebro v0.1 congelado"', 1)

freeze_old = '''        payload = copy.deepcopy(result or {})
        payload = self.decision_adaptive_context(payload, target=target, limit=120)
        frozen_at = datetime.now().isoformat(timespec="seconds")
'''
freeze_new = '''        payload = copy.deepcopy(result or {})
        payload = self.decision_adaptive_context(payload, target=target, limit=120)
        payload = self.decision_operational_recommendation(payload, target=target)
        frozen_at = datetime.now().isoformat(timespec="seconds")
'''
assert text.count(freeze_old) == 1, text.count(freeze_old)
text = text.replace(freeze_old, freeze_new, 1)

operational_methods = r'''
    @staticmethod
    def decision_operational_recommendation(contextual, target=None):
        """
        Etapa D — Recomendação Operacional v0.1.

        Traduz a saída FINAL da Decisão Contextual (A+B+C) em uma conduta
        simples e auditável. Não cria novo índice, não recalcula pesos, não
        troca o líder e não altera qualquer jogo oficial.

        A Etapa D usa deliberadamente os níveis já produzidos pelas camadas
        anteriores:
        - FORTE: priorizar a leitura do líder;
        - MODERADA: priorizar com cautela;
        - BAIXA: sem vantagem clara;
        - AMOSTRA INSUFICIENTE / Etapa C em formação: evidência insuficiente.

        Assim, a D não introduz novos limiares numéricos no cérebro.
        """
        contextual = copy.deepcopy(contextual or {})
        target = dict(target or contextual.get("target") or {})
        best = copy.deepcopy(contextual.get("best") or {})
        adaptive = contextual.get("adaptive") or {}

        leader = best.get("method") or contextual.get("evidence_leader")
        status = str(contextual.get("status") or "SEM DADOS")
        try:
            lead = float(contextual.get("lead") or 0.0)
        except Exception:
            lead = 0.0
        try:
            leader_index = float(best.get("index") or 0.0)
        except Exception:
            leader_index = 0.0

        adaptive_schema = int(adaptive.get("schema") or 0)
        adaptive_active = bool(adaptive_schema == 1 and adaptive.get("active"))
        adaptive_state = adaptive.get("state") or ("ATIVA" if adaptive_active else "EM FORMAÇÃO")
        changed_by_c = bool(adaptive.get("changed_leader"))
        base_leader = adaptive.get("base_leader") or contextual.get("base_evidence_leader") or leader
        leader_source = "ADAPTATIVO" if adaptive_active else "BASE"

        action_code = "EVIDENCIA_INSUFICIENTE"
        headline = "EVIDÊNCIA INSUFICIENTE"
        action_label = "MANTER DECISÃO-BASE"
        actionable = False
        recommended_method = None

        if not leader or status in ("SEM DADOS", "AMOSTRA INSUFICIENTE"):
            reason = (
                "A Decisão ainda não possui evidência suficiente para transformar o líder em prioridade operacional. "
                "A leitura permanece apenas informativa."
            )
        elif adaptive_schema == 1 and not adaptive_active:
            reason = (
                "A Etapa C ainda está em formação. A Etapa D preserva a Decisão Contextual original e não usa "
                "a adaptação como justificativa operacional antes da amostra mínima."
            )
        elif status == "FORTE":
            action_code = "PRIORIZAR"
            headline = f"PRIORIZAR {leader.upper()}"
            action_label = "PRIORIZAR LEITURA"
            actionable = True
            recommended_method = leader
            reason = (
                f"A Decisão final classificou {leader} com confiança FORTE. A Etapa D apenas traduz essa conclusão "
                "em prioridade de leitura; não altera o método nem o jogo oficial."
            )
        elif status == "MODERADA":
            action_code = "PRIORIZAR_COM_CAUTELA"
            headline = f"PRIORIZAR COM CAUTELA {leader.upper()}"
            action_label = "PRIORIZAR COM CAUTELA"
            actionable = True
            recommended_method = leader
            reason = (
                f"A Decisão final favorece {leader}, mas a confiança é MODERADA. A leitura pode ser priorizada, "
                "sem tratá-la como vantagem forte."
            )
        else:
            action_code = "SEM_VANTAGEM_CLARA"
            headline = "SEM VANTAGEM CLARA"
            action_label = "NÃO PRIORIZAR MÉTODO"
            reason = (
                f"O líder atual é {leader}, porém a confiança é {status}. A Etapa D não transforma uma diferença "
                "fraca em recomendação operacional."
            )

        contextual["operational"] = {
            "schema": 1,
            "model": "OPERATIONAL_TRANSLATOR_V1",
            "state": "ATIVA" if adaptive_active else "EM FORMAÇÃO",
            "action_code": action_code,
            "headline": headline,
            "action_label": action_label,
            "actionable": bool(actionable),
            "recommended_method": recommended_method,
            "reference_leader": leader,
            "leader_source": leader_source,
            "base_leader": base_leader,
            "changed_by_c": changed_by_c,
            "confidence": status,
            "lead": round(lead, 1),
            "leader_index": round(leader_index, 1),
            "adaptive_state": adaptive_state,
            "adaptive_active": adaptive_active,
            "target": target,
            "reason": reason,
            "lookahead_safe": True,
            "changes_decision": False,
            "changes_official_game": False,
            "changes_meta": False,
            "note": (
                "Camada de tradução: não cria score, não muda líder, não altera Reset + 3+1 e não modifica o cérebro do Meta."
            ),
        }
        return contextual

    def decision_operational_audit_summary(self, limit=120):
        """Audita apenas recomendações da Etapa D realmente congeladas antes do resultado."""
        try:
            limit = max(1, min(1000, int(limit)))
        except Exception:
            limit = 120
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM decision_snapshots WHERE status='AUDITADO' "
                "AND contextual_json IS NOT NULL AND TRIM(contextual_json)<>'' "
                "AND contextual_audit_json IS NOT NULL AND TRIM(contextual_audit_json)<>'' "
                "ORDER BY target_data DESC,target_hora DESC,id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        evaluated = actionable = correct = sole_best = errors = 0
        no_clear = insufficient = 0
        selected_hits = []
        regrets = []
        recent = []
        action_counts = {}

        for raw in rows:
            row = self._decision_row_to_dict(raw)
            contextual = row.get("contextual") or {}
            operational = contextual.get("operational") or {}
            if int(operational.get("schema") or 0) != 1:
                continue
            audit = row.get("contextual_audit") or {}
            hits = audit.get("hits") or {}
            if not hits:
                continue

            evaluated += 1
            code = str(operational.get("action_code") or "SEM_DADOS")
            action_counts[code] = int(action_counts.get(code) or 0) + 1
            if code == "SEM_VANTAGEM_CLARA":
                no_clear += 1
            elif code == "EVIDENCIA_INSUFICIENTE":
                insufficient += 1

            is_actionable = bool(operational.get("actionable"))
            method = operational.get("recommended_method")
            result = None
            chosen_hits = None
            best_hits = None
            if is_actionable and method in hits:
                try:
                    chosen_hits = int(hits[method])
                    best_hits = max(int(v) for v in hits.values())
                except Exception:
                    chosen_hits = best_hits = None
                if chosen_hits is not None and best_hits is not None:
                    actionable += 1
                    selected_hits.append(chosen_hits)
                    regrets.append(best_hits - chosen_hits)
                    winners = [name for name, value in hits.items() if int(value) == best_hits]
                    if chosen_hits == best_hits:
                        correct += 1
                        if len(winners) == 1:
                            sole_best += 1
                        result = "MELHOR/EMPATE"
                    else:
                        errors += 1
                        result = "ABAIXO_DO_MELHOR"

            if len(recent) < 12:
                recent.append({
                    "data": row.get("target_data"),
                    "sorteio": row.get("target_sorteio"),
                    "hora": row.get("target_hora"),
                    "action_code": code,
                    "method": method,
                    "hits": chosen_hits,
                    "best_hits": best_hits,
                    "result": result,
                })

        return {
            "evaluated": evaluated,
            "actionable": actionable,
            "correct": correct,
            "sole_best": sole_best,
            "errors": errors,
            "no_clear": no_clear,
            "insufficient": insufficient,
            "best_or_tied_rate": (correct / actionable * 100.0) if actionable else None,
            "sole_best_rate": (sole_best / actionable * 100.0) if actionable else None,
            "avg_selected_coverage": (sum(selected_hits) / len(selected_hits)) if selected_hits else None,
            "avg_regret": (sum(regrets) / len(regrets)) if regrets else None,
            "action_counts": action_counts,
            "recent": recent,
            "lookahead_safe": True,
            "note": (
                "Somente recomendações D congeladas prospectivamente são avaliadas. Rodadas em que a D recomendou não priorizar não viram acerto/erro artificial."
            ),
        }
'''

anchor = '\n    def decision_adaptive_audit_summary(self, limit=120):\n'
assert text.count(anchor) == 1, text.count(anchor)
text = text.replace(anchor, '\n' + operational_methods + anchor, 1)

page_old = '''        self._decision_build_confidence_calibration(body)
        self._decision_build_adaptive(body, snapshot)
        self._decision_build_meta(body, snapshot)
'''
page_new = '''        self._decision_build_confidence_calibration(body)
        self._decision_build_adaptive(body, snapshot)
        self._decision_build_operational(body, snapshot)
        self._decision_build_meta(body, snapshot)
'''
assert text.count(page_old) == 1, text.count(page_old)
text = text.replace(page_old, page_new, 1)

operational_ui = r'''
    def _decision_build_operational(self, body, snapshot):
        """Etapa D: traduz A+B+C em uma conduta de leitura sem criar novo cérebro."""
        contextual = (snapshot or {}).get("contextual") or {}
        operational = contextual.get("operational") or {}
        card = ttk.Frame(body, style="Card.TFrame", padding=10)
        card.pack(fill="x", pady=(0, 8))
        head = ttk.Frame(card, style="Card.TFrame"); head.pack(fill="x")
        ttk.Label(head, text="RECOMENDAÇÃO OPERACIONAL — ETAPA D", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(head, text="tradução da decisão • sem novo score", style="CardMuted.TLabel").pack(side="right")

        if int(operational.get("schema") or 0) != 1:
            ttk.Label(
                card,
                text=(
                    "Esta rodada foi congelada antes da Etapa D e não será reconstruída. "
                    "A recomendação operacional começa na próxima rodada congelada pela v0.45.0."
                ),
                style="CardMuted.TLabel", wraplength=1050,
            ).pack(anchor="w", pady=(6, 0))
            return

        headline = operational.get("headline") or "EVIDÊNCIA INSUFICIENTE"
        reference = operational.get("reference_leader") or "—"
        confidence = operational.get("confidence") or "—"
        lead = float(operational.get("lead") or 0.0)
        defs = (
            ("CONDUTA", headline),
            ("MÉTODO DE REFERÊNCIA", reference),
            ("CONFIANÇA", confidence),
            ("VANTAGEM", f"{lead:+.1f} pts"),
        )
        kpis = ttk.Frame(card, style="Card.TFrame"); kpis.pack(fill="x", pady=(7, 7))
        for idx, (title, value) in enumerate(defs):
            box = ttk.Frame(kpis, style="Card2.TFrame", padding=8)
            box.pack(side="left", fill="x", expand=True, padx=(0, 6 if idx < 3 else 0))
            ttk.Label(box, text=title, style="CardMuted.TLabel").pack(anchor="w")
            ttk.Label(
                box, text=str(value), style="Card.TLabel",
                font=(UI_FONT_SEMIBOLD, UI_FONT_SIZES["kpi"]), wraplength=245,
            ).pack(anchor="w")

        source = "líder adaptativo" if operational.get("leader_source") == "ADAPTATIVO" else "líder-base"
        ttk.Label(
            card,
            text=str(operational.get("reason") or ""),
            style="Card.TLabel", wraplength=1050,
        ).pack(anchor="w", pady=(0, 3))
        ttk.Label(
            card,
            text=(
                f"Fonte operacional: {source} • Etapa C: {operational.get('adaptive_state') or '—'} • "
                f"índice do líder {float(operational.get('leader_index') or 0):.1f}."
            ),
            style="CardMuted.TLabel", wraplength=1050,
        ).pack(anchor="w")
        ttk.Label(
            card,
            text=(
                "Proteções: a Etapa D não cria pontuação, não troca o líder, não altera Reset/Puxada/Similaridade, "
                "não modifica o GP-H Meta e não troca o Reset + 3+1 oficial."
            ),
            style="CardMuted.TLabel", wraplength=1050,
        ).pack(anchor="w", pady=(2, 0))

        audit = self.db.decision_operational_audit_summary(limit=120)
        evaluated = int(audit.get("evaluated") or 0)
        actionable = int(audit.get("actionable") or 0)
        if actionable:
            rate = float(audit.get("best_or_tied_rate") or 0.0)
            regret = float(audit.get("avg_regret") or 0.0)
            coverage = float(audit.get("avg_selected_coverage") or 0.0)
            ttk.Label(
                card,
                text=(
                    f"Auditoria D: {evaluated} rodada(s) registrada(s) • {actionable} recomendação(ões) acionável(is) • "
                    f"{rate:.1f}% terminaram melhor/empatadas • cobertura média {coverage:.2f} • arrependimento médio {regret:.2f}. "
                    f"Sem vantagem clara: {int(audit.get('no_clear') or 0)} • evidência insuficiente: {int(audit.get('insufficient') or 0)}."
                ),
                style="CardMuted.TLabel", wraplength=1050,
            ).pack(anchor="w", pady=(3, 0))
        elif evaluated:
            ttk.Label(
                card,
                text=(
                    f"Auditoria D: {evaluated} rodada(s) já registrada(s), ainda sem recomendação acionável. "
                    f"Sem vantagem clara: {int(audit.get('no_clear') or 0)} • evidência insuficiente: {int(audit.get('insufficient') or 0)}."
                ),
                style="CardMuted.TLabel", wraplength=1050,
            ).pack(anchor="w", pady=(3, 0))
        else:
            ttk.Label(
                card,
                text="Auditoria D: coleta prospectiva iniciada; nenhuma recomendação da Etapa D foi encerrada ainda.",
                style="CardMuted.TLabel", wraplength=1050,
            ).pack(anchor="w", pady=(3, 0))
'''

ui_anchor = '\n    def _decision_build_self_audit(self, body):\n'
assert text.count(ui_anchor) == 1, text.count(ui_anchor)
text = text.replace(ui_anchor, '\n' + operational_ui + ui_anchor, 1)

revision = '''REVISÃO v0.45.0 — ETAPA D / RECOMENDAÇÃO OPERACIONAL v0.1
- Fecha a sequência A/B/C/D da Decisão Contextual com uma camada de tradução operacional. A Etapa D NÃO cria novo score, não recalcula pesos e não escolhe um novo líder.
- A D usa exatamente o líder e o nível final já produzidos por A+B+C: FORTE = priorizar a leitura; MODERADA = priorizar com cautela; BAIXA = sem vantagem clara; AMOSTRA INSUFICIENTE = evidência insuficiente.
- Enquanto a Etapa C estiver EM FORMAÇÃO, a D preserva a decisão-base e não usa adaptação incompleta como justificativa operacional.
- Cada recomendação fica armazenada dentro do contextual_json antes do resultado, com líder de referência, fonte BASE/ADAPTATIVO, confiança, vantagem, índice e proteções anti-lookahead.
- A Auditoria D mede somente recomendações acionáveis: taxa em que o método recomendado terminou melhor/empatado, cobertura média e arrependimento médio contra o melhor método da rodada. Rodadas de “sem vantagem clara” ou “evidência insuficiente” não são transformadas artificialmente em acerto/erro.
- Novo painel “RECOMENDAÇÃO OPERACIONAL — ETAPA D” mostra conduta, método de referência, confiança, vantagem, origem do líder e auditoria prospectiva acumulada.
- Proteções permanentes: a Etapa D não altera Reset Cobertura, Puxada Combinada, Similaridade, Histórico Concentrado, 3+1, GP-H Meta v0.1 nem o Reset + 3+1 oficial.
- REGRA DE CONGELAMENTO: concluída a Etapa D, o Meta/Decisão entra em observação prospectiva por 2–3 dias sem novas mudanças estruturais por desempenho. Corrigir imediatamente apenas erros técnicos; depois fazer checkpoint Meta × Reset × Puxada × Similaridade × Histórico × acaso e preferir 20–30 rodadas antes de nova recalibração relevante.

'''
assert not doc.startswith('REVISÃO v0.45.0')
doc = revision + doc

# Validação sintática e proteção AST dos motores existentes.
ast.parse(text)
after = {name: fn_dump(text, name) for name in critical}
changed = [name for name in critical if before[name] != after[name]]
assert not changed, f'Funções protegidas alteradas: {changed}'

assert text.count('def decision_operational_recommendation(') == 1
assert text.count('def decision_operational_audit_summary(') == 1
assert text.count('def _decision_build_operational(') == 1
assert text.count('self._decision_build_operational(body, snapshot)') == 1
assert 'payload = self.decision_operational_recommendation(payload, target=target)' in text

SRC.write_text(text, encoding='utf-8')
DOC.write_text(doc, encoding='utf-8')
print('Etapa D aplicada com sucesso; motores protegidos permaneceram idênticos por AST.')
