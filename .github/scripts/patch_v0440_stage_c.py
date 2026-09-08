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


# A Etapa C é deliberadamente aditiva. O único método existente que precisa ser
# tocado é freeze_decision_contextual, para aplicar a camada adaptativa ANTES do
# congelamento prospectivo. Todo o restante abaixo deve permanecer idêntico.
critical = [
    '_meta_feature_names', '_meta_feature_vector', '_meta_fit_logit', '_meta_model_score',
    '_meta_training_records', '_meta_examples', '_meta_temporal_holdout', 'meta_shadow_prediction',
    'meta_walk_forward', 'method_reset_coverage_v1', 'method_convergencia_g5', 'method_similarity_day',
    'method_historico_concentrado_v01', 'generate_historical_concentrated_bundle',
    'generate_centenas_3plus1', 'centena_31_freeze_state', 'decision_contextual_evidence',
    'decision_contextual_audit_summary', 'decision_confidence_calibration', 'audit_decision_snapshots',
    'decision_walk_forward', '_decision_contextual_audit_payload', 'freeze_meta_snapshot',
    'meta_shadow_summary', 'historical_pulls', '_decision_build_self_audit',
    '_decision_build_confidence_calibration',
]
before = {name: fn_dump(text, name) for name in critical}

assert 'APP_VERSION = "0.43.0"' in text
assert 'def decision_adaptive_context(' not in text
assert 'def decision_adaptive_audit_summary(' not in text

text = text.replace('GP-H Central Histórica v0.43.0', 'GP-H Central Histórica v0.44.0', 1)
text = text.replace('APP_VERSION = "0.43.0"', 'APP_VERSION = "0.44.0"', 1)
text = text.replace('text="v0.43 • cérebro v0.1 congelado"', 'text="v0.44 • cérebro v0.1 congelado"', 1)

adaptive_methods = r'''
    def decision_adaptive_context(
        self, contextual, target=None, limit=120, min_total=30,
        min_method_rounds=20, max_adjustment=3.0,
    ):
        """
        Etapa C — Decisão Adaptativa v0.1.

        Usa SOMENTE auditorias contextuais já encerradas antes da rodada-alvo
        para aplicar uma correção pequena e regularizada aos índices dos três
        métodos. A camada não toca nas fórmulas de Reset/Puxada/Similaridade,
        não altera o GP-H Meta e não muda o Reset + 3+1 oficial.

        Princípios:
        - sem look-ahead: nenhuma rodada igual/posterior ao alvo entra;
        - ativação somente com amostra mínima pareada;
        - ajuste máximo por método limitado a +/- max_adjustment pontos;
        - histórico geral domina; mesmo horário entra apenas como refinamento;
        - calibração de nível pode apenas REBAIXAR confiança incoerente, nunca
          promover confiança artificialmente;
        - decisão-base permanece gravada dentro do payload para auditoria A/B.
        """
        contextual = copy.deepcopy(contextual or {})
        target = dict(target or contextual.get("target") or {})
        methods = ("Reset Cobertura", "Puxada Combinada", "Similaridade")
        rows = [copy.deepcopy(r) for r in (contextual.get("rows") or []) if r.get("method") in methods]
        base_best = copy.deepcopy(contextual.get("best") or (rows[0] if rows else {}))
        base_leader = base_best.get("method")
        base_status = contextual.get("status") or "SEM DADOS"
        base_lead = float(contextual.get("lead") or 0.0)
        base_recommendation = contextual.get("recommendation") or ""

        try:
            limit = max(20, min(500, int(limit)))
        except Exception:
            limit = 120
        try:
            min_total = max(20, min(200, int(min_total)))
        except Exception:
            min_total = 30
        try:
            min_method_rounds = max(8, min(100, int(min_method_rounds)))
        except Exception:
            min_method_rounds = 20
        try:
            max_adjustment = max(0.5, min(5.0, float(max_adjustment)))
        except Exception:
            max_adjustment = 3.0

        def before_target(row):
            td = str(target.get("data") or "")
            th = str(target.get("hora") or "")
            rd = str(row.get("target_data") or "")
            rh = str(row.get("target_hora") or "")
            if not td:
                return True
            if rd < td:
                return True
            if rd > td:
                return False
            if th and rh:
                return rh < th
            return False

        with self.connect() as con:
            raw_rows = con.execute(
                "SELECT * FROM decision_snapshots WHERE status='AUDITADO' "
                "AND contextual_json IS NOT NULL AND TRIM(contextual_json)<>'' "
                "AND contextual_audit_json IS NOT NULL AND TRIM(contextual_audit_json)<>'' "
                "ORDER BY target_data DESC,target_hora DESC,id DESC LIMIT 500"
            ).fetchall()

        prior = []
        for raw in raw_rows:
            row = self._decision_row_to_dict(raw)
            if not before_target(row):
                continue
            audit = row.get("contextual_audit") or {}
            hits = audit.get("hits") or {}
            usable = {}
            for name in methods:
                if name not in hits or hits.get(name) is None:
                    continue
                try:
                    usable[name] = int(hits.get(name))
                except Exception:
                    pass
            if len(usable) < 2:
                continue
            prior.append((row, usable))
            if len(prior) >= limit:
                break

        # Cada rodada compara os métodos contra o MESMO resultado. Assim a
        # confiabilidade é pareada e não depende de qual método foi escolhido.
        stats = {
            name: {"rounds": 0, "best_or_tied": 0, "sole_best": 0,
                   "same_hour_rounds": 0, "same_hour_best_or_tied": 0}
            for name in methods
        }
        status_stats = {}
        valid_rounds = 0
        target_hour = str(target.get("hora") or "")

        for row, hits in prior:
            best_hits = max(hits.values())
            winners = [name for name, value in hits.items() if value == best_hits]
            valid_rounds += 1
            for name, value in hits.items():
                s = stats[name]
                s["rounds"] += 1
                s["best_or_tied"] += int(value == best_hits)
                s["sole_best"] += int(value == best_hits and len(winners) == 1)
                if target_hour and str(row.get("target_hora") or "") == target_hour:
                    s["same_hour_rounds"] += 1
                    s["same_hour_best_or_tied"] += int(value == best_hits)

            # Para calibrar o NÍVEL, usa a decisão-base que existiria sem Etapa C.
            # Isso evita que a adaptação aprenda a justificar a si mesma.
            old_ctx = row.get("contextual") or {}
            old_audit = row.get("contextual_audit") or {}
            old_base_leader = old_ctx.get("base_evidence_leader") or old_audit.get("leader")
            old_status = old_ctx.get("base_status") or old_audit.get("context_status") or old_ctx.get("status")
            if old_base_leader in hits and old_status:
                bucket = status_stats.setdefault(str(old_status), {"rounds": 0, "success": 0})
                bucket["rounds"] += 1
                bucket["success"] += int(hits[old_base_leader] == best_hits)

        total_obs = sum(s["rounds"] for s in stats.values())
        total_success = sum(s["best_or_tied"] for s in stats.values())
        global_rate = (total_success / total_obs) if total_obs else 0.0
        enough_methods = sum(1 for s in stats.values() if s["rounds"] >= min_method_rounds)
        active = valid_rounds >= min_total and enough_methods >= 3 and bool(rows)

        prior_strength = 12.0
        same_hour_strength = 8.0
        method_rows = []
        by_name = {r.get("method"): r for r in rows}
        for name in methods:
            base_row = copy.deepcopy(by_name.get(name) or {"method": name, "index": 0.0})
            s = stats[name]
            n = int(s["rounds"])
            wins = int(s["best_or_tied"])
            if n:
                overall_rate = (wins + prior_strength * global_rate) / (n + prior_strength)
            else:
                overall_rate = global_rate

            hn = int(s["same_hour_rounds"])
            hw = int(s["same_hour_best_or_tied"])
            if hn >= 6:
                same_rate = (hw + same_hour_strength * overall_rate) / (hn + same_hour_strength)
                blended = 0.75 * overall_rate + 0.25 * same_rate
            else:
                same_rate = None
                blended = overall_rate

            raw_adjustment = max(-max_adjustment, min(max_adjustment, (blended - global_rate) * 12.0))
            applied = raw_adjustment if active else 0.0
            base_index = float(base_row.get("index") or 0.0)
            adaptive_index = self._decision_clip(base_index + applied)
            base_row["base_index"] = round(base_index, 1)
            base_row["adaptive_adjustment"] = round(applied, 2)
            base_row["adaptive_index"] = round(adaptive_index, 1)
            base_row["index"] = round(adaptive_index, 1) if active else round(base_index, 1)
            method_rows.append({
                "method": name,
                "base_index": round(base_index, 1),
                "raw_adjustment": round(raw_adjustment, 2),
                "applied_adjustment": round(applied, 2),
                "adaptive_index": round(adaptive_index, 1),
                "rounds": n,
                "best_or_tied_rate": round((wins / n * 100.0), 2) if n else None,
                "sole_best_rate": round((s["sole_best"] / n * 100.0), 2) if n else None,
                "same_hour_rounds": hn,
                "same_hour_rate": round((hw / hn * 100.0), 2) if hn else None,
                "blended_rate": round(blended * 100.0, 2) if n else None,
            })

        if active:
            rows.sort(key=lambda r: (-float(r.get("index") or 0.0), -float(r.get("hour_avg") or 0.0), -float(r.get("overall_avg") or 0.0), str(r.get("method") or "")))
            # Substitui índices da cópia pelas correções calculadas.
            adj_map = {r["method"]: r for r in method_rows}
            for row in rows:
                a = adj_map.get(row.get("method")) or {}
                row["base_index"] = a.get("base_index")
                row["adaptive_adjustment"] = a.get("applied_adjustment")
                row["adaptive_index"] = a.get("adaptive_index")
                row["index"] = a.get("adaptive_index", row.get("index"))
            rows.sort(key=lambda r: (-float(r.get("index") or 0.0), -float(r.get("hour_avg") or 0.0), -float(r.get("overall_avg") or 0.0), str(r.get("method") or "")))

        final_best = copy.deepcopy(rows[0] if rows else base_best)
        final_second = rows[1] if len(rows) > 1 else None
        final_lead = (
            float(final_best.get("index") or 0.0) - float(final_second.get("index") or 0.0)
            if final_best and final_second else base_lead
        )

        # Mantém a mesma regra estrutural de confiança; a Etapa C só recalcula
        # o lead depois da correção pequena. Depois, a calibração B pode REBAIXAR
        # um nível empiricamente incoerente — nunca promover.
        if active and final_best:
            hour_rounds = int(final_best.get("hour_rounds") or 0)
            unstable = final_best.get("trend_status") in ("ATENÇÃO", "QUEDA FORTE")
            if hour_rounds < 8:
                structural_status = "AMOSTRA INSUFICIENTE"
            elif hour_rounds >= 20 and final_lead >= 8.0 and not unstable:
                structural_status = "FORTE"
            elif hour_rounds >= 12 and final_lead >= 4.0 and not unstable:
                structural_status = "MODERADA"
            else:
                structural_status = "BAIXA"
        else:
            structural_status = base_status

        final_status = structural_status
        downgrade_reasons = []
        if active:
            chain = (("FORTE", "MODERADA"), ("MODERADA", "BAIXA"))
            for upper, lower in chain:
                if final_status != upper:
                    continue
                up = status_stats.get(upper) or {}
                lo = status_stats.get(lower) or {}
                un = int(up.get("rounds") or 0)
                ln = int(lo.get("rounds") or 0)
                if un < 8 or ln < 8:
                    continue
                ur = float(up.get("success") or 0) / un
                lr = float(lo.get("success") or 0) / ln
                # Só reage a inversão visível (>5 pp), evitando microajustes.
                if ur + 0.05 < lr:
                    downgrade_reasons.append(
                        f"{upper} {ur*100:.0f}% < {lower} {lr*100:.0f}% na auditoria-base"
                    )
                    final_status = lower

        final_leader = final_best.get("method") if final_best else base_leader
        changed_leader = bool(active and final_leader and base_leader and final_leader != base_leader)
        changed_status = bool(active and final_status != base_status)

        if not active:
            state = "EM FORMAÇÃO"
            recommendation = (
                f"Etapa C ainda observando: {valid_rounds}/{min_total} rodada(s) pareada(s). "
                "A Decisão Contextual original foi preservada. Reset + 3+1 continua oficial."
            )
        else:
            state = "ATIVA"
            if changed_leader:
                recommendation = (
                    f"A adaptação conservadora mudou o líder de {base_leader} para {final_leader} após auditoria pareada. "
                    "Reset + 3+1 continua oficial; a mudança da própria Decisão será auditada prospectivamente."
                )
            else:
                recommendation = (
                    f"A adaptação conservadora confirmou {final_leader} como líder. "
                    "Reset + 3+1 continua oficial e a Etapa C segue sendo auditada prospectivamente."
                )
            if downgrade_reasons:
                recommendation += " Confiança rebaixada pela calibração: " + "; ".join(downgrade_reasons) + "."

        contextual["base_rows"] = copy.deepcopy(contextual.get("rows") or [])
        contextual["base_best"] = base_best
        contextual["base_lead"] = round(base_lead, 1)
        contextual["base_status"] = base_status
        contextual["base_recommendation"] = base_recommendation
        contextual["base_evidence_leader"] = base_leader
        contextual["adaptive"] = {
            "schema": 1,
            "model": "DECISION_ADAPTIVE_SHRINK_V1",
            "state": state,
            "active": bool(active),
            "training_rounds": valid_rounds,
            "minimum_rounds": min_total,
            "minimum_method_rounds": min_method_rounds,
            "enough_methods": enough_methods,
            "global_best_or_tied_rate": round(global_rate * 100.0, 2) if total_obs else None,
            "max_adjustment": max_adjustment,
            "methods": method_rows,
            "base_leader": base_leader,
            "final_leader": final_leader,
            "changed_leader": changed_leader,
            "base_status": base_status,
            "structural_status": structural_status,
            "final_status": final_status,
            "changed_status": changed_status,
            "status_stats": copy.deepcopy(status_stats),
            "downgrade_reasons": downgrade_reasons,
            "lookahead_safe": True,
            "changes_official_game": False,
            "note": "Ajuste regularizado e limitado a +/-3 pontos; aprende apenas com auditorias anteriores ao alvo.",
        }

        if active:
            contextual["rows"] = rows
            contextual["best"] = final_best
            contextual["lead"] = round(final_lead, 1)
            contextual["status"] = final_status
            contextual["recommendation"] = recommendation
            contextual["evidence_leader"] = final_leader
        else:
            contextual["evidence_leader"] = base_leader
            contextual["recommendation"] = base_recommendation

        return contextual

    def decision_adaptive_audit_summary(self, limit=120):
        """Audita apenas decisões da Etapa C realmente congeladas antes do resultado."""
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

        evaluated = active_rounds = changed = improved = harmed = neutral = 0
        base_success = adaptive_success = 0
        delta_hits = []
        recent = []
        for raw in rows:
            row = self._decision_row_to_dict(raw)
            contextual = row.get("contextual") or {}
            adaptive = contextual.get("adaptive") or {}
            if int(adaptive.get("schema") or 0) != 1:
                continue
            audit = row.get("contextual_audit") or {}
            hits = audit.get("hits") or {}
            base_leader = adaptive.get("base_leader") or contextual.get("base_evidence_leader")
            final_leader = adaptive.get("final_leader") or audit.get("leader")
            if base_leader not in hits or final_leader not in hits or not hits:
                continue
            try:
                bh = int(hits[base_leader]); ah = int(hits[final_leader])
                best_hits = max(int(v) for v in hits.values())
            except Exception:
                continue
            evaluated += 1
            active_rounds += int(bool(adaptive.get("active")))
            base_success += int(bh == best_hits)
            adaptive_success += int(ah == best_hits)
            delta_hits.append(ah - bh)
            was_changed = base_leader != final_leader
            if was_changed:
                changed += 1
                if ah > bh:
                    improved += 1
                elif ah < bh:
                    harmed += 1
                else:
                    neutral += 1
            else:
                neutral += 1
            if len(recent) < 12:
                recent.append({
                    "data": row.get("target_data"),
                    "sorteio": row.get("target_sorteio"),
                    "hora": row.get("target_hora"),
                    "active": bool(adaptive.get("active")),
                    "base_leader": base_leader,
                    "final_leader": final_leader,
                    "base_hits": bh,
                    "final_hits": ah,
                    "delta": ah - bh,
                })

        return {
            "evaluated": evaluated,
            "active_rounds": active_rounds,
            "changed": changed,
            "improved": improved,
            "harmed": harmed,
            "neutral": neutral,
            "base_best_or_tied_rate": (base_success / evaluated * 100.0) if evaluated else None,
            "adaptive_best_or_tied_rate": (adaptive_success / evaluated * 100.0) if evaluated else None,
            "avg_hit_delta": (sum(delta_hits) / len(delta_hits)) if delta_hits else None,
            "recent": recent,
            "lookahead_safe": True,
            "note": "Somente snapshots congelados já com Etapa C; nenhuma rodada antiga é reconstruída.",
        }

'''

anchor = '    def audit_decision_snapshots(self):\n'
assert anchor in text
text = text.replace(anchor, adaptive_methods + anchor, 1)

# Aplicação no congelamento prospectivo. A Decisão Contextual base é calculada
# exatamente como antes; só depois recebe a camada C, ainda antes do resultado.
old_freeze = '''        result = self.decision_contextual_evidence(\n            target=target,\n            snapshot=snapshot,\n            window=120,\n            recent_window=12,\n            walk_forward=None,\n        )\n        frozen_at = datetime.now().isoformat(timespec="seconds")\n        payload = copy.deepcopy(result or {})\n        best = payload.get("best") or {}\n'''
new_freeze = '''        result = self.decision_contextual_evidence(\n            target=target,\n            snapshot=snapshot,\n            window=120,\n            recent_window=12,\n            walk_forward=None,\n        )\n        payload = copy.deepcopy(result or {})\n        payload = self.decision_adaptive_context(payload, target=target, limit=120)\n        frozen_at = datetime.now().isoformat(timespec="seconds")\n        best = payload.get("best") or {}\n'''
assert old_freeze in text
text = text.replace(old_freeze, new_freeze, 1)

ui_method = r'''
    def _decision_build_adaptive(self, body, snapshot):
        """Etapa C: mostra a camada adaptativa e sua auditoria A/B prospectiva."""
        contextual = (snapshot or {}).get("contextual") or {}
        adaptive = contextual.get("adaptive") or {}
        card = ttk.Frame(body, style="Card.TFrame", padding=10)
        card.pack(fill="x", pady=(0, 8))
        head = ttk.Frame(card, style="Card.TFrame"); head.pack(fill="x")
        ttk.Label(head, text="DECISÃO ADAPTATIVA — ETAPA C", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(head, text="correção conservadora • auditável A/B", style="CardMuted.TLabel").pack(side="right")

        if int(adaptive.get("schema") or 0) != 1:
            ttk.Label(
                card,
                text=(
                    "Esta rodada foi congelada antes da Etapa C. Ela não será reconstruída. "
                    "A camada adaptativa começa a ser registrada na próxima rodada congelada pela v0.44.0."
                ),
                style="CardMuted.TLabel", wraplength=1050,
            ).pack(anchor="w", pady=(6, 0))
            return

        state = adaptive.get("state") or "EM FORMAÇÃO"
        base_leader = adaptive.get("base_leader") or "—"
        final_leader = adaptive.get("final_leader") or base_leader
        changed = "SIM" if adaptive.get("changed_leader") else "NÃO"
        defs = (
            ("ESTADO", state),
            ("LÍDER BASE", base_leader),
            ("LÍDER ADAPTATIVO", final_leader),
            ("MUDOU A ESCOLHA?", changed),
        )
        kpis = ttk.Frame(card, style="Card.TFrame"); kpis.pack(fill="x", pady=(7, 7))
        for idx, (title, value) in enumerate(defs):
            box = ttk.Frame(kpis, style="Card2.TFrame", padding=8)
            box.pack(side="left", fill="x", expand=True, padx=(0, 6 if idx < 3 else 0))
            ttk.Label(box, text=title, style="CardMuted.TLabel").pack(anchor="w")
            ttk.Label(box, text=str(value), style="Card.TLabel", font=(UI_FONT_SEMIBOLD, UI_FONT_SIZES["kpi"]), wraplength=245).pack(anchor="w")

        methods = adaptive.get("methods") or []
        if methods:
            cols = ("method", "base", "adjust", "final", "n", "rate", "hour")
            tree = ttk.Treeview(card, columns=cols, show="headings", height=max(3, min(4, len(methods))))
            heads = {
                "method": "Método", "base": "Índice base", "adjust": "Ajuste C",
                "final": "Índice final", "n": "N", "rate": "Melhor/empate", "hour": "Mesmo horário",
            }
            widths = {"method": 190, "base": 90, "adjust": 85, "final": 90, "n": 55, "rate": 120, "hour": 145}
            for col in cols:
                tree.heading(col, text=heads[col])
                tree.column(col, width=widths[col], anchor="w" if col == "method" else "center")
            for row in methods:
                rate = row.get("best_or_tied_rate")
                hn = int(row.get("same_hour_rounds") or 0)
                hr = row.get("same_hour_rate")
                hour_text = "—" if not hn else f"{float(hr or 0):.0f}% ({hn})"
                tree.insert("", "end", values=(
                    row.get("method"),
                    f"{float(row.get('base_index') or 0):.1f}",
                    f"{float(row.get('applied_adjustment') or 0):+.2f}",
                    f"{float(row.get('adaptive_index') or 0):.1f}",
                    int(row.get("rounds") or 0),
                    "—" if rate is None else f"{float(rate):.1f}%",
                    hour_text,
                ))
            tree.pack(fill="x", pady=(0, 5))

        training = int(adaptive.get("training_rounds") or 0)
        minimum = int(adaptive.get("minimum_rounds") or 30)
        ttk.Label(
            card,
            text=(
                f"Base adaptativa: {training}/{minimum} rodada(s) pareada(s) • ajuste máximo ±{float(adaptive.get('max_adjustment') or 3):.0f} pontos. "
                "O histórico geral é regularizado e o mesmo horário entra apenas como refinamento."
            ),
            style="CardMuted.TLabel", wraplength=1050,
        ).pack(anchor="w")
        if adaptive.get("downgrade_reasons"):
            ttk.Label(
                card,
                text="Rebaixamento de confiança: " + "; ".join(adaptive.get("downgrade_reasons") or []),
                style="CardMuted.TLabel", wraplength=1050,
            ).pack(anchor="w", pady=(2, 0))

        audit = self.db.decision_adaptive_audit_summary(limit=120)
        evaluated = int(audit.get("evaluated") or 0)
        if evaluated:
            base_rate = audit.get("base_best_or_tied_rate")
            adapt_rate = audit.get("adaptive_best_or_tied_rate")
            delta = audit.get("avg_hit_delta")
            ttk.Label(
                card,
                text=(
                    f"Auditoria C: {evaluated} rodada(s) • base {float(base_rate or 0):.1f}% melhor/empate • "
                    f"adaptativa {float(adapt_rate or 0):.1f}% • mudanças {int(audit.get('changed') or 0)} • "
                    f"melhorou {int(audit.get('improved') or 0)} / piorou {int(audit.get('harmed') or 0)} • "
                    f"Δ médio de cobertura {float(delta or 0):+.2f}."
                ),
                style="CardMuted.TLabel", wraplength=1050,
            ).pack(anchor="w", pady=(3, 0))
        else:
            ttk.Label(
                card,
                text="Auditoria C: coleta prospectiva iniciada; nenhuma rodada da Etapa C foi encerrada ainda.",
                style="CardMuted.TLabel", wraplength=1050,
            ).pack(anchor="w", pady=(3, 0))

        ttk.Label(
            card,
            text=(
                "A Etapa C pode alterar qual método a Decisão considera líder, mas não troca o jogo oficial. "
                "Toda mudança fica congelada antes do resultado e é comparada depois com a decisão-base que teria sido usada sem a adaptação."
            ),
            style="CardMuted.TLabel", wraplength=1050,
        ).pack(anchor="w", pady=(2, 0))

'''

ui_anchor = '    def _decision_build_self_audit(self, body):\n'
assert ui_anchor in text
text = text.replace(ui_anchor, ui_method + ui_anchor, 1)

call_old = '''        self._decision_build_contextual(body, snapshot)\n        self._decision_build_self_audit(body)\n        self._decision_build_confidence_calibration(body)\n        self._decision_build_meta(body, snapshot)\n'''
call_new = '''        self._decision_build_contextual(body, snapshot)\n        self._decision_build_self_audit(body)\n        self._decision_build_confidence_calibration(body)\n        self._decision_build_adaptive(body, snapshot)\n        self._decision_build_meta(body, snapshot)\n'''
assert call_old in text
text = text.replace(call_old, call_new, 1)

revision = '''REVISÃO v0.44.0 — ETAPA C / DECISÃO ADAPTATIVA v0.1
- A Etapa C passa a usar as auditorias prospectivas das Etapas A/B para fazer uma correção pequena e regularizada na escolha contextual entre Reset Cobertura, Puxada Combinada e Similaridade.
- A Decisão Contextual BASE continua sendo calculada exatamente como antes. Depois dela, e ainda ANTES do resultado, a camada DECISION_ADAPTIVE_SHRINK_V1 pode ajustar cada índice em no máximo ±3 pontos.
- A adaptação fica EM FORMAÇÃO até acumular pelo menos 30 rodadas pareadas anteriores e pelo menos 20 observações válidas para cada um dos três métodos. Até lá, ajuste aplicado = zero e a decisão-base é preservada.
- O desempenho de cada método é medido de forma pareada nas mesmas rodadas: quantas vezes ele terminou melhor ou empatado. As taxas recebem shrinkage para a média geral; o mesmo horário só refina a leitura quando possui suporte mínimo.
- Sem look-ahead: a Etapa C ignora qualquer snapshot igual ou posterior à rodada-alvo. Nenhuma decisão antiga é reconstruída.
- A calibração da Etapa B pode somente REBAIXAR um nível de confiança quando houver inversão clara (>5 pp) entre níveis com pelo menos 8 casos. A Etapa C nunca promove confiança automaticamente por esse mecanismo.
- Cada snapshot v0.44+ preserva base_best/base_status/base_evidence_leader e também o resultado adaptativo. Após o sorteio, a Auditoria C compara decisão-base × decisão adaptativa e registra mudança, melhora, piora, neutralidade e delta médio de cobertura.
- IMPORTANTE: a Etapa C NÃO altera as fórmulas de Reset, Puxada, Similaridade, Histórico Concentrado, 3+1 nem o GP-H Meta v0.1. Reset + 3+1 continua sendo o jogo oficial protegido.
- O novo painel “DECISÃO ADAPTATIVA — ETAPA C” mostra estado, líder-base, líder adaptativo, ajustes, amostra, mesmo horário e auditoria A/B prospectiva.

'''
doc = revision + doc

SRC.write_text(text, encoding='utf-8')
DOC.write_text(doc, encoding='utf-8')

# Sintaxe + invariantes: nada crítico fora do congelamento contextual pode mudar.
ast.parse(text)
for name, old_dump in before.items():
    new_dump = fn_dump(text, name)
    assert new_dump == old_dump, f'função crítica alterada indevidamente: {name}'

assert 'APP_VERSION = "0.44.0"' in text
assert 'def decision_adaptive_context(' in text
assert 'def decision_adaptive_audit_summary(' in text
assert 'DECISÃO ADAPTATIVA — ETAPA C' in text
assert 'self._decision_build_adaptive(body, snapshot)' in text
assert 'payload = self.decision_adaptive_context(payload, target=target, limit=120)' in text
assert doc.startswith('REVISÃO v0.44.0')
print('PATCH v0.44.0 ETAPA C OK')
