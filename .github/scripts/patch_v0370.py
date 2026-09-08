from pathlib import Path

src = Path("source/gph_central.py")
text = src.read_text(encoding="utf-8")

if 'APP_VERSION = "0.37.0"' in text:
    raise SystemExit("v0.37.0 ja aplicada")
if 'APP_VERSION = "0.36.6"' not in text:
    raise SystemExit("Base esperada v0.36.6 nao encontrada")

text = text.replace("GP-H Central Histórica v0.36.6", "GP-H Central Histórica v0.37.0", 1)
text = text.replace('APP_VERSION = "0.36.6"', 'APP_VERSION = "0.37.0"', 1)

# ------------------------------------------------------------------
# Banco / inteligência: índice contextual comparando os três métodos.
# ------------------------------------------------------------------
marker = '''    def decision_concentration_from_generation(self, generation):\n'''
if marker not in text:
    raise SystemExit("Ponto de insercao contextual nao encontrado")

method = r'''    def decision_contextual_evidence(
        self, target=None, snapshot=None, window=120, recent_window=12,
        walk_forward=None,
    ):
        """
        Compara Reset, Puxada e Similaridade para a PRÓXIMA rodada usando
        somente evidência prospectiva já auditada + sinais atuais congelados.

        O índice é relativo (0–100) e NÃO representa probabilidade de acerto.
        Componentes indisponíveis são retirados e os pesos restantes são
        renormalizados. O método oficial nunca é trocado automaticamente.
        """
        methods = ("Reset Cobertura", "Puxada Combinada", "Similaridade")
        snapshot = snapshot or self.latest_decision_snapshot() or {}
        if target is None:
            if snapshot:
                target = {
                    "data": snapshot.get("target_data"),
                    "sorteio": snapshot.get("target_sorteio"),
                    "hora": snapshot.get("target_hora"),
                }
            else:
                target = self.next_operational_target() or {}
        target = dict(target or {})
        hour = str(target.get("hora") or "")
        weekday = self._decision_weekday_label(target.get("data"))

        try:
            window = max(1, int(window))
        except Exception:
            window = 120
        try:
            recent_window = max(1, int(recent_window))
        except Exception:
            recent_window = 12

        all_rows = self._decision_audited_rows(window="Todos")
        overall_rows = all_rows[:window]
        recent_rows = all_rows[:recent_window]
        hour_rows = [
            r for r in all_rows
            if str(r.get("target_hora") or "") == hour
        ][:window] if hour else []
        weekday_rows = [
            r for r in all_rows
            if self._decision_weekday_label(r.get("target_data")) == weekday
        ][:window] if weekday and weekday != "—" else []

        def perf_map(rows):
            return {
                r["method"]: r
                for r in self._decision_performance_from_rows(rows)
            }

        overall = perf_map(overall_rows)
        recent = perf_map(recent_rows)
        by_hour = perf_map(hour_rows)
        by_weekday = perf_map(weekday_rows)
        trend = {
            r["method"]: r
            for r in (self.decision_change_detection(
                recent_window=recent_window, baseline_window=30
            ).get("rows") or [])
        }

        def performance_score(metrics, reliable_at):
            if not metrics or int(metrics.get("rounds") or 0) <= 0:
                return None
            rounds = int(metrics.get("rounds") or 0)
            avg = float(metrics.get("avg_coverage") or 0.0)
            p2 = float(metrics.get("pct_2plus") or 0.0)
            coverage = self._decision_clip((avg - 0.50) / 2.50 * 100.0)
            raw = 0.65 * coverage + 0.35 * self._decision_clip(p2)
            reliability = min(1.0, rounds / max(1.0, float(reliable_at)))
            # Encolhe amostras pequenas em direção ao neutro (50).
            return round(self._decision_clip(50.0 + reliability * (raw - 50.0)), 2)

        stability_map = {
            "MELHORA": 85.0,
            "ESTÁVEL": 70.0,
            "AMOSTRA INSUFICIENTE": 50.0,
            "ATENÇÃO": 35.0,
            "QUEDA FORTE": 15.0,
        }

        # Convergência atual: quanto dos 5 bichos de cada método recebe apoio
        # de pelo menos uma das outras leituras atuais congeladas.
        signals = (snapshot or {}).get("signals") or {}
        current_sets = {}
        for method_name in methods:
            values = []
            for raw in (signals.get(method_name) or {}).get("groups") or []:
                try:
                    group = int(raw)
                except Exception:
                    continue
                if 1 <= group <= 25 and group not in values:
                    values.append(group)
            current_sets[method_name] = set(values[:5])

        convergence = {}
        for method_name in methods:
            own = current_sets.get(method_name) or set()
            if not own:
                convergence[method_name] = None
                continue
            others = [
                current_sets.get(other) or set()
                for other in methods if other != method_name
            ]
            reinforced = sum(
                1 for g in own if any(g in other_set for other_set in others)
            )
            convergence[method_name] = round(reinforced / len(own) * 100.0, 2)

        # Walk-Forward só entra se já foi executado nesta sessão. Abrir a tela
        # Decisão nunca dispara uma simulação pesada automaticamente.
        wf_rows = {}
        if isinstance(walk_forward, dict):
            source = walk_forward.get("paired_summary") or walk_forward.get("summary") or []
            wf_rows = {r.get("method"): r for r in source if r.get("method")}

        base_weights = {
            "hour": 0.35,
            "recent": 0.20,
            "stability": 0.15,
            "walk_forward": 0.10,
            "weekday": 0.08,
            "convergence": 0.07,
            "overall": 0.05,
        }

        rows = []
        for method_name in methods:
            h = by_hour.get(method_name)
            r = recent.get(method_name)
            o = overall.get(method_name)
            w = by_weekday.get(method_name)
            t = trend.get(method_name) or {}
            wf = wf_rows.get(method_name)

            factors = {
                "hour": performance_score(h, 20),
                "recent": performance_score(r, 12),
                "stability": stability_map.get(t.get("status"), 50.0) if t else None,
                "walk_forward": performance_score(wf, 30) if wf else None,
                "weekday": performance_score(w, 12),
                "convergence": convergence.get(method_name),
                "overall": performance_score(o, 20),
            }
            active = [key for key, value in factors.items() if value is not None]
            weight_total = sum(base_weights[key] for key in active)
            if weight_total <= 0:
                continue
            score = sum(
                float(factors[key]) * base_weights[key]
                for key in active
            ) / weight_total

            hour_rounds = int((h or {}).get("rounds") or 0)
            # Mesmo um placar excelente não vira confiança alta com poucas
            # observações do horário que está sendo previsto.
            if hour_rounds < 4:
                score = min(score, 58.0)
            elif hour_rounds < 8:
                score = min(score, 64.0)
            elif hour_rounds < 12:
                score = min(score, 72.0)
            elif hour_rounds < 20:
                score = min(score, 85.0)

            rows.append({
                "method": method_name,
                "index": round(self._decision_clip(score), 1),
                "hour_rounds": hour_rounds,
                "weekday_rounds": int((w or {}).get("rounds") or 0),
                "recent_rounds": int((r or {}).get("rounds") or 0),
                "overall_rounds": int((o or {}).get("rounds") or 0),
                "hour_avg": float((h or {}).get("avg_coverage") or 0.0),
                "overall_avg": float((o or {}).get("avg_coverage") or 0.0),
                "trend_status": t.get("status") or "—",
                "factors": factors,
                "active_weights": {
                    key: round(base_weights[key] / weight_total * 100.0, 1)
                    for key in active
                },
            })

        rows.sort(key=lambda item: (
            -item["index"], -item["hour_avg"], -item["overall_avg"], item["method"]
        ))
        best = rows[0] if rows else None
        second = rows[1] if len(rows) > 1 else None
        lead = (best["index"] - second["index"]) if best and second else 0.0

        if not best:
            status = "SEM DADOS"
            recommendation = "Ainda não há evidência prospectiva auditada suficiente para comparar os métodos."
        else:
            hour_rounds = int(best.get("hour_rounds") or 0)
            unstable = best.get("trend_status") in ("ATENÇÃO", "QUEDA FORTE")
            if hour_rounds < 8:
                status = "AMOSTRA INSUFICIENTE"
            elif hour_rounds >= 20 and lead >= 8.0 and not unstable:
                status = "FORTE"
            elif hour_rounds >= 12 and lead >= 4.0 and not unstable:
                status = "MODERADA"
            else:
                status = "BAIXA"

            if status == "AMOSTRA INSUFICIENTE":
                recommendation = (
                    f"O melhor sinal provisório é {best['method']}, mas há apenas "
                    f"{hour_rounds} leitura(s) auditada(s) neste horário. "
                    "Manter Reset + 3+1 oficial e acumular evidência."
                )
            elif best["method"] == "Reset Cobertura":
                recommendation = (
                    "Reset Cobertura segue com a melhor evidência contextual. "
                    "Reset + 3+1 permanece oficial."
                )
            else:
                recommendation = (
                    f"{best['method']} tem a melhor evidência contextual desta rodada, "
                    "mas Reset + 3+1 permanece oficial; o desafiante continua em observação/sombra."
                )

        return {
            "target": target,
            "hour": hour,
            "weekday": weekday,
            "window": window,
            "recent_window": recent_window,
            "official_method": "Reset Cobertura",
            "official_game": "Reset + 3+1",
            "rows": rows,
            "best": best,
            "lead": round(lead, 1),
            "status": status,
            "recommendation": recommendation,
            "walk_forward_used": bool(wf_rows),
            "base_weights": dict(base_weights),
            "note": "Índice de Evidência Contextual; não é probabilidade de acerto.",
        }

'''
text = text.replace(marker, method + marker, 1)

# ------------------------------------------------------------------
# UI: bloco contextual imediatamente abaixo da hero da próxima rodada.
# ------------------------------------------------------------------
ui_marker = '''    def _decision_build_stage2(self, body, snapshot):\n'''
if ui_marker not in text:
    raise SystemExit("Ponto de insercao UI contextual nao encontrado")

ui_method = r'''    def _decision_build_contextual(self, body, snapshot):
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

        card = ttk.Frame(body, style="Card.TFrame", padding=11)
        card.pack(fill="x", pady=(0, 8))
        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(
            head, text="DECISÃO CONTEXTUAL DA PRÓXIMA RODADA",
            style="CardTitle.TLabel",
        ).pack(side="left")
        ttk.Label(
            head,
            text=f"{result.get('hour') or '—'} • {result.get('weekday') or '—'}",
            style="CardMuted.TLabel",
        ).pack(side="right")

        best = result.get("best") or {}
        if best:
            main = (
                f"Melhor evidência atual: {best.get('method')} • "
                f"{result.get('status')} • índice {float(best.get('index') or 0):.0f}/100"
            )
        else:
            main = "Ainda não há evidência contextual suficiente para ranquear os métodos."
        ttk.Label(
            card, text=main, style="Card.TLabel",
            font=("Segoe UI Semibold", 13), wraplength=1080,
        ).pack(anchor="w", pady=(6, 2))
        ttk.Label(
            card,
            text=(
                f"Oficial: Reset + 3+1 • nenhuma troca automática. "
                f"{result.get('recommendation') or ''}"
            ),
            style="CardMuted.TLabel", wraplength=1080, justify="left",
        ).pack(anchor="w", pady=(0, 7))

        cols = ("method", "index", "hour", "recent", "stability", "weekday", "wf", "conv", "n")
        tree = ttk.Treeview(card, columns=cols, show="headings", height=3)
        heads = {
            "method": "Método", "index": "Índice", "hour": "Horário",
            "recent": "Recente", "stability": "Estabilidade", "weekday": "Dia",
            "wf": "Walk-Fwd", "conv": "Converg.", "n": "N hora",
        }
        widths = {
            "method": 195, "index": 65, "hour": 82, "recent": 82,
            "stability": 92, "weekday": 72, "wf": 78, "conv": 78, "n": 58,
        }
        for col in cols:
            tree.heading(col, text=heads[col])
            tree.column(col, width=widths[col], anchor="w" if col == "method" else "center")

        def fmt(value):
            return "—" if value is None else f"{float(value):.0f}"

        for row in result.get("rows") or []:
            factors = row.get("factors") or {}
            tree.insert("", "end", values=(
                row.get("method"),
                f"{float(row.get('index') or 0):.0f}",
                fmt(factors.get("hour")),
                fmt(factors.get("recent")),
                fmt(factors.get("stability")),
                fmt(factors.get("weekday")),
                fmt(factors.get("walk_forward")),
                fmt(factors.get("convergence")),
                int(row.get("hour_rounds") or 0),
            ))
        tree.pack(fill="x", pady=(0, 5))

        wf_note = (
            "Walk-Forward usado: última simulação concluída nesta sessão."
            if result.get("walk_forward_used")
            else "Walk-Forward ainda não executado nesta sessão; esse componente foi retirado e os demais pesos foram renormalizados."
        )
        ttk.Label(
            card,
            text=(
                "Pesos-base: horário 35% • recente 20% • estabilidade 15% • "
                "Walk-Forward 10% • dia da semana 8% • convergência atual 7% • geral 5%. "
                + wf_note
            ),
            style="CardMuted.TLabel", wraplength=1080, justify="left",
        ).pack(anchor="w", pady=(2, 1))
        ttk.Label(
            card,
            text=(
                "O índice serve para comparar evidência relativa entre métodos. "
                "Não é porcentagem de chance de prêmio e não altera o método oficial."
            ),
            style="CardMuted.TLabel", wraplength=1080,
        ).pack(anchor="w")

'''
text = text.replace(ui_marker, ui_method + ui_marker, 1)

call_anchor = '''        if not snapshot:\n            return\n\n        # Componentes transparentes do índice.\n'''
call_new = '''        if not snapshot:\n            return\n\n        # v0.37.0 — comparação contextual dos métodos para a próxima rodada.\n        self._decision_build_contextual(body, snapshot)\n\n        # Componentes transparentes do índice.\n'''
if call_anchor not in text:
    raise SystemExit("Chamada contextual na Decisao nao encontrada")
text = text.replace(call_anchor, call_new, 1)

# Atualiza o texto Sobre sem remover o histórico anterior.
about_anchor = '            "Atualizações recentes:\\n"\n'
about_new = (
    '            "Atualizações recentes:\\n"\n'
    '            "• v0.37.0 — Decisão Contextual cruza horário, recente, estabilidade, Walk-Forward opcional, dia, convergência e geral sem trocar o método oficial.\\n"\n'
)
if about_anchor in text:
    text = text.replace(about_anchor, about_new, 1)

src.write_text(text, encoding="utf-8")

# Documentação consolidada.
doc = Path("source/DOCUMENTACAO_GP-H.txt")
if doc.exists():
    d = doc.read_text(encoding="utf-8")
    revision = '''REVISÃO v0.37.0 — DECISÃO CONTEXTUAL\n- Nova camada “Decisão Contextual da Próxima Rodada” compara Reset Cobertura, Puxada Combinada e Similaridade especificamente para o horário/dia que está por vir.\n- O novo Índice de Evidência Contextual NÃO é probabilidade de acerto; é apenas uma escala relativa de 0–100 para ordenar força de evidência entre métodos.\n- Pesos-base: mesmo horário 35%, desempenho recente 20%, estabilidade 15%, Walk-Forward 10%, dia da semana 8%, convergência atual 7% e desempenho geral 5%.\n- Quando um componente não está disponível — especialmente Walk-Forward ainda não executado na sessão — ele é retirado e os demais pesos são renormalizados, sem inventar dado neutro.\n- Amostras pequenas do mesmo horário são encolhidas e limitam o índice; abaixo de 8 leituras auditadas a recomendação aparece explicitamente como AMOSTRA INSUFICIENTE.\n- A convergência atual funciona apenas como confirmação de baixa ponderação e não escolhe sozinha o vencedor histórico.\n- O Reset + 3+1 continua oficial em qualquer cenário; a Decisão Contextual pode apontar um desafiante com melhor evidência sem promovê-lo automaticamente.\n- Toda a comparação usa snapshots prospectivos já congelados/auditados; nenhum resultado futuro é usado para reconstruir recomendação passada.\n- A tela Decisão continua com rolamento inteligente e mantém intactos Índice de Consistência, Campeão × Desafiante, tendência, contexto por horário/dia, Walk-Forward e Laboratório Sombra.\n\n'''
    if not d.startswith("REVISÃO v0.37.0"):
        d = revision + d
    d = d.replace("VERSÃO ATUAL: v0.36.6", "VERSÃO ATUAL: v0.37.0", 1)
    doc.write_text(d, encoding="utf-8")

upd = Path("source/ATUALIZACOES_PROGRAMA_v0.35.txt")
if upd.exists():
    u = upd.read_text(encoding="utf-8")
    u = u.replace("GP-H CENTRAL HISTÓRICA v0.36.6", "GP-H CENTRAL HISTÓRICA v0.37.0", 1)
    note = '''\nNovidades v0.37.0:\n- Decisão Contextual para a próxima rodada, comparando os três seletores com foco maior no mesmo horário.\n- Índice de Evidência Contextual 0–100, explicitamente separado de probabilidade de acerto.\n- Cruza horário, recente, estabilidade, Walk-Forward quando disponível, dia da semana, convergência atual e desempenho geral.\n- Amostra pequena reduz a força da conclusão e pode resultar em AMOSTRA INSUFICIENTE.\n- Reset + 3+1 continua oficial e nenhuma promoção é automática.\n'''
    if "Novidades v0.37.0:" not in u:
        u += note
    upd.write_text(u, encoding="utf-8")

print("Patch v0.37.0 aplicado")
