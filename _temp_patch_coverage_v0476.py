from pathlib import Path

SRC = Path("source/gph_central.py")
DOC = Path("source/DOCUMENTACAO_GP-H.txt")
s = SRC.read_text(encoding="utf-8")

assert 'APP_VERSION = "0.47.5"' in s, "versão-base 0.47.5 não encontrada"
s = s.replace('APP_VERSION = "0.47.5"', 'APP_VERSION = "0.47.6"', 1)

# ---------------------------------------------------------------------------
# Banco/diagnóstico: Evolução de Cobertura, sem tocar no cérebro do Meta.
# ---------------------------------------------------------------------------
core_anchor = '    def decision_performance_by_hour(self, window=120):\n'
assert core_anchor in s, "âncora decision_performance_by_hour não encontrada"
core_code = r'''    @staticmethod
    def _coverage_terno_matches_snapshot(snapshot, game):
        """Aceita só Terno Meta gerado para a MESMA base prospectiva do snapshot."""
        snapshot = snapshot or {}
        game = game or {}
        selector = str(game.get("seletor") or "").strip().casefold()
        if not selector.startswith("gp-h meta v0."):
            return False
        if str(game.get("tipo") or "").strip() != "Terno de Grupo":
            return False
        for snap_key, game_key in (
            ("base_data", "base_data"),
            ("base_sorteio", "base_sorteio"),
            ("base_hora", "base_hora"),
        ):
            a = str(snapshot.get(snap_key) or "").strip()
            b = str(game.get(game_key) or "").strip()
            if not a or not b or a != b:
                return False
        return True

    @staticmethod
    def _coverage_evolution_summary(records, window, target_pct=50.0):
        """Resume uma janela diagnóstica; não alimenta ranking, pesos ou Meta."""
        try:
            window = max(1, int(window))
        except Exception:
            window = 20
        rows = list(records or [])[:window]
        n = len(rows)
        if not n:
            return {
                "window": window, "rounds": 0, "avg_coverage": None,
                "pct_2plus": None, "goal_met": False,
                "terno_rounds": 0, "terno_3of3": 0, "terno_3of3_rate": None,
                "conversion_opportunities": 0, "conversion_3of3": 0,
                "conversion_rate": None, "opportunities_without_core_terno": 0,
                "latest_best_terno": None,
            }

        coverages = [int(r.get("coverage_hits") or 0) for r in rows]
        terno_rows = [r for r in rows if r.get("best_terno") is not None]
        opportunities = [
            r for r in rows
            if int(r.get("coverage_hits") or 0) >= 3
            and r.get("best_core_terno") is not None
        ]
        uncovered_opportunities = [
            r for r in rows
            if int(r.get("coverage_hits") or 0) >= 3
            and r.get("best_core_terno") is None
        ]
        conversions = sum(int(r.get("best_core_terno") or 0) >= 3 for r in opportunities)
        terno_wins = sum(int(r.get("best_terno") or 0) >= 3 for r in terno_rows)
        latest_best = next(
            (int(r["best_terno"]) for r in rows if r.get("best_terno") is not None),
            None,
        )
        pct_2plus = sum(v >= 2 for v in coverages) / n * 100.0
        return {
            "window": window,
            "rounds": n,
            "avg_coverage": sum(coverages) / n,
            "pct_2plus": pct_2plus,
            "goal_met": pct_2plus > float(target_pct),
            "terno_rounds": len(terno_rows),
            "terno_3of3": terno_wins,
            "terno_3of3_rate": (terno_wins / len(terno_rows) * 100.0) if terno_rows else None,
            "conversion_opportunities": len(opportunities),
            "conversion_3of3": conversions,
            "conversion_rate": (conversions / len(opportunities) * 100.0) if opportunities else None,
            "opportunities_without_core_terno": len(uncovered_opportunities),
            "latest_best_terno": latest_best,
        }

    def decision_coverage_evolution(self, windows=(20, 30, 60), recent_limit=10):
        """
        Auditoria prospectiva do objetivo GP-H: cobertura do Top 5 Meta e conversão em Terno.

        Usa somente snapshots Meta congelados antes do resultado. Para a montagem,
        considera somente Ternos de Grupo registrados com seletor GP-H Meta v0.x e
        cuja extração-base coincide com a base do snapshot. A meta de Taxa 2+ > 50%
        é exclusivamente uma régua de avaliação: esta rotina não altera o Meta.
        """
        target_pct = 50.0
        try:
            windows = tuple(sorted({max(1, int(v)) for v in windows}))
        except Exception:
            windows = (20, 30, 60)
        if not windows:
            windows = (20, 30, 60)
        try:
            recent_limit = max(1, min(30, int(recent_limit)))
        except Exception:
            recent_limit = 10
        needed = max(max(windows), recent_limit)

        raw_rows = self._decision_audited_rows(window="Todos")
        records = []
        with self.connect() as con:
            for raw in raw_rows:
                row = self._decision_row_to_dict(raw)
                meta = row.get("meta") or {}
                audit = row.get("meta_audit") or {}
                if not audit.get("available"):
                    continue
                core_groups = []
                for raw_group in (meta.get("groups") or [])[:5]:
                    try:
                        group = int(raw_group)
                    except Exception:
                        continue
                    if 1 <= group <= 25 and group not in core_groups:
                        core_groups.append(group)
                if not core_groups:
                    continue

                result_groups = []
                for raw_group in (audit.get("result_groups") or []):
                    try:
                        group = int(raw_group)
                    except Exception:
                        continue
                    if 1 <= group <= 25:
                        result_groups.append(group)
                if not result_groups:
                    try:
                        decoded = json.loads(row.get("result_groups_json") or "[]")
                    except Exception:
                        decoded = []
                    result_groups = [int(g) for g in decoded if str(g).isdigit() and 1 <= int(g) <= 25]
                if not result_groups:
                    continue

                result_set = set(result_groups)
                coverage = int(audit.get("coverage_hits") or len(set(core_groups) & result_set))
                games = con.execute(
                    "SELECT * FROM jogos_congelados WHERE alvo_data=? "
                    "AND COALESCE(alvo_sorteio,'')=COALESCE(?, '') "
                    "AND COALESCE(alvo_hora,'')=COALESCE(?, '') "
                    "AND tipo='Terno de Grupo' ORDER BY id",
                    (row.get("target_data"), row.get("target_sorteio"), row.get("target_hora")),
                ).fetchall()

                best_terno = None
                best_core_terno = None
                terno_count = 0
                core_terno_count = 0
                for game_raw in games:
                    game = dict(game_raw)
                    if not self._coverage_terno_matches_snapshot(row, game):
                        continue
                    items = con.execute(
                        "SELECT * FROM jogos_itens WHERE jogo_id=? ORDER BY ordem",
                        (int(game["id"]),),
                    ).fetchall()
                    for item_raw in items:
                        item = dict(item_raw)
                        groups = []
                        for g in self._decision_groups_from_item(game, item):
                            try:
                                group = int(g)
                            except Exception:
                                continue
                            if 1 <= group <= 25 and group not in groups:
                                groups.append(group)
                        if len(groups) != 3:
                            continue
                        hits = len(set(groups) & result_set)
                        terno_count += 1
                        best_terno = hits if best_terno is None else max(best_terno, hits)
                        if set(groups).issubset(set(core_groups)):
                            core_terno_count += 1
                            best_core_terno = hits if best_core_terno is None else max(best_core_terno, hits)

                if coverage < 3:
                    diagnostic = "TERNO 3/3 FORA DO TOP 5" if best_terno == 3 else "NÚCLEO < 3"
                elif best_core_terno is None:
                    diagnostic = "TERNOS FORA DO TOP 5" if best_terno is not None else "SEM TERNO META"
                elif best_core_terno >= 3:
                    diagnostic = "CONVERTEU 3→3"
                else:
                    diagnostic = "MONTAGEM NÃO CONVERTEU"

                records.append({
                    "target_data": row.get("target_data"),
                    "target_sorteio": row.get("target_sorteio"),
                    "target_hora": row.get("target_hora"),
                    "core_groups": core_groups,
                    "result_groups": result_groups,
                    "coverage_hits": coverage,
                    "best_terno": best_terno,
                    "best_core_terno": best_core_terno,
                    "terno_count": terno_count,
                    "core_terno_count": core_terno_count,
                    "diagnostic": diagnostic,
                })
                if len(records) >= needed:
                    break

        summaries = [
            self._coverage_evolution_summary(records, window, target_pct=target_pct)
            for window in windows
        ]
        return {
            "objective": "Atingir pelo menos 2 bichos corretos no Top 5 em mais de 50% das rodadas e converter cobertura suficiente em Ternos 3/3.",
            "target_2plus_pct": target_pct,
            "target_is_diagnostic_only": True,
            "lookahead_safe": True,
            "changes_meta": False,
            "windows": summaries,
            "recent": records[:recent_limit],
            "eligible_rounds": len(records),
            "note": (
                "Cobertura usa o Top 5 Meta congelado. Conversão 3→3 só usa Ternos Meta registrados, "
                "da mesma base prospectiva e formados integralmente pelo Top 5; ausência de Terno não vira falha de conversão."
            ),
        }

'''
if '    def decision_coverage_evolution(self, windows=(20, 30, 60), recent_limit=10):\n' not in s:
    s = s.replace(core_anchor, core_code + core_anchor, 1)

# ---------------------------------------------------------------------------
# Interface: painel dentro de Decisão > Auditoria.
# ---------------------------------------------------------------------------
ui_anchor = '    def _decision_build_adaptive(self, body, snapshot):\n'
assert ui_anchor in s, "âncora _decision_build_adaptive não encontrada"
ui_code = r'''    def _decision_build_coverage_evolution(self, body):
        """Painel diagnóstico do objetivo de cobertura e conversão em Ternos."""
        try:
            report = self.db.decision_coverage_evolution(windows=(20, 30, 60), recent_limit=10)
        except Exception as exc:
            card = ttk.Frame(body, style="Card.TFrame", padding=10)
            card.pack(fill="x", pady=(0, 8))
            ttk.Label(card, text="EVOLUÇÃO DE COBERTURA", style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(
                card, text=f"Não foi possível montar o painel: {exc}",
                style="CardMuted.TLabel", wraplength=1050,
            ).pack(anchor="w", pady=(5, 0))
            return

        card = ttk.Frame(body, style="Card.TFrame", padding=10)
        card.pack(fill="x", pady=(0, 8))
        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="EVOLUÇÃO DE COBERTURA", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(head, text="diagnóstico • janelas 20 / 30 / 60", style="CardMuted.TLabel").pack(side="right")
        ttk.Label(
            card,
            text=(
                "Objetivo oficial de evolução: primeiro elevar a cobertura dos grupos; depois transformar essa cobertura em mais Ternos 3/3. "
                "A régua Taxa 2+ > 50% serve apenas para avaliação e NÃO entra no cérebro do Meta, nos pesos ou no ranking."
            ),
            style="CardMuted.TLabel", wraplength=1050, justify="left",
        ).pack(anchor="w", pady=(5, 7))

        summaries = report.get("windows") or []
        short = next((r for r in summaries if int(r.get("window") or 0) == 20), summaries[0] if summaries else {})
        rounds = int(short.get("rounds") or 0)
        avg = short.get("avg_coverage")
        p2 = short.get("pct_2plus")
        conv = short.get("conversion_rate")
        best = short.get("latest_best_terno")
        status = "META ATINGIDA" if short.get("goal_met") else ("EM FORMAÇÃO" if rounds < 20 else "ABAIXO DE 50%")

        kpis = ttk.Frame(card, style="Card.TFrame")
        kpis.pack(fill="x", pady=(0, 8))
        defs = (
            ("COBERTURA DO NÚCLEO", "—" if avg is None else f"{float(avg):.2f}/5", f"média • {rounds} rodada(s)"),
            ("TAXA 2+", "—" if p2 is None else f"{float(p2):.1f}%", f"> 50% • {status}"),
            ("MELHOR TERNO", "—" if best is None else f"{int(best)}/3", "rodada mais recente com Terno Meta"),
            ("CONVERSÃO 3→3", "—" if conv is None else f"{float(conv):.1f}%", f"{int(short.get('conversion_3of3') or 0)}/{int(short.get('conversion_opportunities') or 0)} oportunidade(s)"),
        )
        for idx, (title, value, sub) in enumerate(defs):
            box = ttk.Frame(kpis, style="Card2.TFrame", padding=8)
            box.pack(side="left", fill="x", expand=True, padx=(0, 6 if idx < 3 else 0))
            ttk.Label(box, text=title, style="CardMuted.TLabel").pack(anchor="w")
            ttk.Label(box, text=value, style="Card.TLabel", font=(UI_FONT_SEMIBOLD, UI_FONT_SIZES["kpi"])).pack(anchor="w", pady=(2, 0))
            ttk.Label(box, text=sub, style="CardMuted.TLabel", wraplength=230).pack(anchor="w", pady=(1, 0))

        if not summaries or not int(report.get("eligible_rounds") or 0):
            ttk.Label(
                card,
                text="A coleta ainda não possui snapshots Meta auditados suficientes para formar este painel.",
                style="CardMuted.TLabel", wraplength=1050,
            ).pack(anchor="w")
            return

        ttk.Label(card, text="Janelas móveis", style="Section.TLabel").pack(anchor="w", pady=(2, 4))
        cols = ("window", "rounds", "coverage", "p2", "ternos", "terno3", "conversion")
        tree = ttk.Treeview(card, columns=cols, show="headings", height=3)
        heads = {
            "window": "Janela", "rounds": "Rodadas", "coverage": "Cobertura média",
            "p2": "Taxa 2+", "ternos": "Rodadas c/ Terno", "terno3": "Terno 3/3", "conversion": "Conversão 3→3",
        }
        widths = {"window": 80, "rounds": 80, "coverage": 130, "p2": 110, "ternos": 130, "terno3": 120, "conversion": 135}
        for col in cols:
            tree.heading(col, text=heads[col])
            tree.column(col, width=widths[col], anchor="center")
        for row in summaries:
            p2v = row.get("pct_2plus")
            tr = row.get("terno_3of3_rate")
            cv = row.get("conversion_rate")
            tree.insert("", "end", values=(
                f"{int(row.get('window') or 0)}",
                int(row.get("rounds") or 0),
                "—" if row.get("avg_coverage") is None else f"{float(row['avg_coverage']):.2f}/5",
                "—" if p2v is None else f"{float(p2v):.1f}%" + (" ✓" if row.get("goal_met") else ""),
                int(row.get("terno_rounds") or 0),
                "—" if tr is None else f"{int(row.get('terno_3of3') or 0)} • {float(tr):.1f}%",
                "—" if cv is None else f"{int(row.get('conversion_3of3') or 0)}/{int(row.get('conversion_opportunities') or 0)} • {float(cv):.1f}%",
            ))
        tree.pack(fill="x", pady=(0, 8))

        recent = report.get("recent") or []
        if recent:
            ttk.Label(card, text="Rodadas recentes — onde está a falha?", style="Section.TLabel").pack(anchor="w", pady=(2, 4))
            rcols = ("round", "coverage", "terno", "conversion", "diagnostic")
            rtree = ttk.Treeview(card, columns=rcols, show="headings", height=min(8, len(recent)))
            rheads = {
                "round": "Rodada", "coverage": "Núcleo", "terno": "Melhor Terno",
                "conversion": "Terno do Top 5", "diagnostic": "Diagnóstico",
            }
            rwidths = {"round": 260, "coverage": 80, "terno": 105, "conversion": 115, "diagnostic": 260}
            for col in rcols:
                rtree.heading(col, text=rheads[col])
                rtree.column(col, width=rwidths[col], anchor="w" if col in ("round", "diagnostic") else "center")
            for row in recent:
                try:
                    day = datetime.strptime(str(row.get("target_data") or ""), "%Y-%m-%d").strftime("%d/%m/%Y")
                except Exception:
                    day = str(row.get("target_data") or "—")
                best_all = row.get("best_terno")
                best_core = row.get("best_core_terno")
                rtree.insert("", "end", values=(
                    f"{day} • {row.get('target_sorteio') or '—'} {row.get('target_hora') or '—'}",
                    f"{int(row.get('coverage_hits') or 0)}/5",
                    "—" if best_all is None else f"{int(best_all)}/3",
                    "—" if best_core is None else f"{int(best_core)}/3",
                    row.get("diagnostic") or "—",
                ))
            rtree.pack(fill="x", pady=(0, 6))

        ttk.Label(
            card,
            text=(
                "Leitura: NÚCLEO < 3 indica que o Top 5 não ofereceu três bichos corretos; MONTAGEM NÃO CONVERTEU indica que havia cobertura suficiente, "
                "mas nenhum Terno Meta do próprio Top 5 fechou 3/3. Rodadas sem Terno Meta rastreável não são contadas como falha de conversão."
            ),
            style="CardMuted.TLabel", wraplength=1050, justify="left",
        ).pack(anchor="w")

'''
if '    def _decision_build_coverage_evolution(self, body):\n' not in s:
    s = s.replace(ui_anchor, ui_code + ui_anchor, 1)

old_audit = '''        if view == "audit":\n            self._decision_build_self_audit(body)\n            self._decision_build_confidence_calibration(body)\n            self._decision_build_meta(body, snapshot)\n            return\n'''
new_audit = '''        if view == "audit":\n            self._decision_build_coverage_evolution(body)\n            self._decision_build_self_audit(body)\n            self._decision_build_confidence_calibration(body)\n            self._decision_build_meta(body, snapshot)\n            return\n'''
assert old_audit in s, "bloco Auditoria da Decisão não encontrado"
s = s.replace(old_audit, new_audit, 1)

SRC.write_text(s, encoding="utf-8", newline="\n")

doc = DOC.read_text(encoding="utf-8")
entry = '''REVISÃO v0.47.6 — EVOLUÇÃO DE COBERTURA / META DIAGNÓSTICA\n\n- Decisão > Auditoria recebe o painel Evolução de Cobertura, com janelas móveis de 20, 30 e 60 rodadas.\n- O objetivo oficial desta fase fica explícito: primeiro elevar a capacidade de colocar pelo menos 2 bichos corretos no Top 5 em mais de 50% das rodadas; depois converter cobertura suficiente em mais Ternos 3/3; Quadras e Quinas ficam para etapa posterior.\n- Cobertura do núcleo mede quantos grupos do resultado estavam no Top 5 do GP-H Meta congelado antes do sorteio. Taxa 2+ mede a frequência de rodadas com pelo menos dois acertos de grupo.\n- Melhor Terno mede 0/3, 1/3, 2/3 ou 3/3 usando apenas Ternos de Grupo GP-H Meta realmente registrados antes do resultado.\n- Conversão 3→3 considera somente oportunidades em que o Top 5 tinha pelo menos 3 bichos corretos e existe Terno Meta rastreável, gerado da mesma extração-base e integralmente contido no Top 5. Ausência de Terno não é transformada em falha.\n- O diagnóstico recente separa falha de núcleo (cérebro não ofereceu 3 grupos) de falha de montagem (núcleo tinha 3+, mas os Ternos do Top 5 não fecharam 3/3).\n- Ternos de Reset, Manual, Puxada, Similaridade ou bilhetes Meta reaproveitados para outra base não contaminam a Conversão 3→3.\n- A meta de 50% é SOMENTE uma régua de avaliação. Ela não entra nas características, pesos, regressão, score, ranking, calibração ou decisão do GP-H Meta; nenhum cérebro foi recalibrado nesta versão.\n\n'''
if not doc.startswith("REVISÃO v0.47.6"):
    DOC.write_text(entry + doc, encoding="utf-8", newline="\n")
