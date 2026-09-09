from pathlib import Path
import re

p = Path('source/gph_central.py')
s = p.read_text(encoding='utf-8')


def one(old, new, label):
    global s
    n = s.count(old)
    if n != 1:
        raise SystemExit(f'{label}: esperado 1 trecho, encontrado {n}')
    s = s.replace(old, new, 1)


one('GP-H Central Histórica v0.46.7', 'GP-H Central Histórica v0.46.8', 'doc version')
one('APP_VERSION = "0.46.7"', 'APP_VERSION = "0.46.8"', 'app version')

# ---------------------------------------------------------------------------
# Novo gerador Meta 2:1. Não altera o 3+1 oficial existente.
# ---------------------------------------------------------------------------
marker = '\n\n\n    def method_similarity_day(\n'
if s.count(marker) != 1:
    raise SystemExit('marcador para inserir Meta 2:1 não encontrado de forma única')
meta_generator = r'''

    def generate_centenas_meta_21(
        self,
        groups: list[int],
        total=20,
        previous_draw=None,
    ):
        """Centenas flexíveis do GP-H Meta usando proporção aproximada 2:1.

        A seleção de bichos vem do ranking Meta. A quantidade total é dividida
        de forma equilibrada entre os bichos; sobras ficam primeiro com os
        líderes do ranking. Dentro de cada bicho, aproximadamente 2/3 das
        Centenas usam a dezena principal ativa e 1/3 a segunda ativa.

        A máquina de congelamento do 3+1 é REUTILIZADA, sem alteração:
        principal livre -> principal + segunda; principal congelada -> segunda
        + terceira. Assim, 4 Centenas continuam sendo 3+1, 5 viram 3+2,
        6 viram 4+2, 8 viram 5+3 e 9 viram 6+3.
        """
        unique_groups = []
        for value in groups:
            g = int(value)
            if 1 <= g <= 25 and g not in unique_groups:
                unique_groups.append(g)
        if not unique_groups:
            raise ValueError("O GP-H Meta não forneceu bichos para gerar Centenas.")

        total = max(1, int(total))
        if total < len(unique_groups):
            raise ValueError(
                f"Com {len(unique_groups)} bichos, informe pelo menos {len(unique_groups)} Centenas "
                "para que cada bicho receba ao menos uma."
            )

        counts = self.distribute_game_counts(total, unique_groups, kind="Centena")
        if sum(counts.values()) != total:
            raise ValueError("Não foi possível distribuir a quantidade pedida entre os bichos do Meta.")

        # Cada dezena possui 10 Centenas possíveis. Para preservar a proporção
        # 2:1 usando exatamente duas dezenas ativas, o limite íntegro é 15 por
        # bicho (10 + 5). Acima disso seria necessário quebrar a regra acordada.
        overloaded = [(g, qty) for g, qty in counts.items() if int(qty) > 15]
        if overloaded:
            worst = max(qty for _g, qty in overloaded)
            raise ValueError(
                f"A distribuição 2:1 suporta até 15 Centenas por bicho; a configuração atual "
                f"chegaria a {worst}. Aumente a quantidade de bichos do Meta ou reduza as Centenas."
            )

        if previous_draw is None:
            previous_draw = self.latest_operational_draw()
        if previous_draw is None:
            raise ValueError("Não há extração-base para aplicar o estado das dezenas.")

        rows = []
        animals = []

        for rank_group, g in enumerate(unique_groups, start=1):
            qty = int(counts[g])
            dez_rank = self.number_rankings_for_group(g, kind="Dezena", scope="1º–5º")
            if len(dez_rank) < 3:
                raise ValueError(f"Ranking de dezenas insuficiente para o grupo {g:02d}.")

            principal, segunda, terceira = dez_rank[:3]
            freeze_state = self.centena_31_freeze_state(
                g, principal["numero"], previous_draw=previous_draw
            )
            frozen = bool(freeze_state.get("frozen"))

            if frozen:
                main_dez = segunda["numero"]
                extra_dez = terceira["numero"]
                main_name = "2/3 na 2ª dezena (principal congelada)"
                extra_name = "1/3 na 3ª dezena"
            else:
                main_dez = principal["numero"]
                extra_dez = segunda["numero"]
                main_name = "2/3 na principal"
                extra_name = "1/3 na 2ª dezena"

            # Arredondamento ao inteiro mais próximo de 2/3, sem banker's round.
            main_count = (2 * qty + 1) // 3
            extra_count = qty - main_count

            main_rank = self.centena_rankings_for_dezena(g, main_dez, scope="1º–5º")
            extra_rank = self.centena_rankings_for_dezena(g, extra_dez, scope="1º–5º")
            if len(main_rank) < main_count or len(extra_rank) < extra_count:
                raise ValueError(f"Centenas insuficientes nas dezenas ativas do grupo {g:02d}.")

            animals.append({
                "grupo": g,
                "bicho": BICHOS[g],
                "rank_bicho": rank_group,
                "principal": principal["numero"],
                "segunda": segunda["numero"],
                "terceira": terceira["numero"],
                "principal_tied": principal["ocorrencias"] == segunda["ocorrencias"],
                "frozen": frozen,
                "freeze_trigger": freeze_state.get("trigger"),
                "freeze_released_by": freeze_state.get("released_by"),
                "freeze_rule": "persistente_ate_reaparicao_do_bicho",
                "main_dezena": main_dez,
                "extra_dezena": extra_dez,
                "main_count": main_count,
                "extra_count": extra_count,
                "total_count": qty,
            })

            for pos, c in enumerate(main_rank[:main_count], start=1):
                rows.append({
                    "grupo": g, "bicho": BICHOS[g], "numero": c["numero"],
                    "dezena_base": main_dez, "regra": main_name,
                    "ocorrencias": c["ocorrencias"], "ultima": c["ultima"],
                    "rank_no_bicho": pos, "rank_bicho": rank_group,
                    "frozen": frozen, "principal": principal["numero"],
                    "segunda": segunda["numero"], "terceira": terceira["numero"],
                })
            for pos, c in enumerate(extra_rank[:extra_count], start=1):
                rows.append({
                    "grupo": g, "bicho": BICHOS[g], "numero": c["numero"],
                    "dezena_base": extra_dez, "regra": extra_name,
                    "ocorrencias": c["ocorrencias"], "ultima": c["ultima"],
                    "rank_no_bicho": main_count + pos, "rank_bicho": rank_group,
                    "frozen": frozen, "principal": principal["numero"],
                    "segunda": segunda["numero"], "terceira": terceira["numero"],
                })

        return {
            "kind": "Centena",
            "strategy": "Meta 2:1",
            "scope": "1º–5º",
            "groups": unique_groups,
            "counts": counts,
            "requested_total": total,
            "generated_total": len(rows),
            "rows": rows,
            "animals": animals,
            "previous_draw": previous_draw,
            "freeze_rule": "mesma_maquina_do_3plus1",
            "distribution_rule": "aprox_2_tercos_mais_1_terco",
        }
'''
s = s.replace(marker, meta_generator + marker, 1)

# Variável de quantidade de bichos Meta.
one(
'''        self.play_method = tk.StringVar(value="Oficial • Reset + 3+1")
        self.play_total = tk.StringVar(value="20")
        self.play_hc_base_animals = tk.StringVar(value="5")''',
'''        self.play_method = tk.StringVar(value="Oficial • Reset + 3+1")
        self.play_total = tk.StringVar(value="20")
        self.play_meta_animals = tk.StringVar(value="5")
        self.play_hc_base_animals = tk.StringVar(value="5")''',
'play meta var')

# Cartão visual dedicado ao Meta.
one(
'''        self.play_method_badge.grid(row=2, column=5, sticky="w", pady=(2, 0))

        # FECHAMENTO HISTÓRICO CONCENTRADO (visível apenas na variação Fechamento)''',
'''        self.play_method_badge.grid(row=2, column=5, sticky="w", pady=(2, 0))

        # GP-H META v0.1 — seletor jogável, visualmente separado dos demais.
        self.play_meta_card = tk.Frame(
            self.play_body,
            bg=self.colors["card2"],
            highlightbackground="#19A7B8",
            highlightthickness=2,
            bd=0,
            padx=12,
            pady=9,
        )
        meta_head = tk.Frame(self.play_meta_card, bg=self.colors["card2"])
        meta_head.pack(fill="x")
        tk.Label(
            meta_head, text="GP-H META v0.1", bg=self.colors["card2"],
            fg=self.colors["text"], font=("Segoe UI Semibold", 12),
        ).pack(side="left")
        tk.Label(
            meta_head, text="META • ADAPTATIVO", bg="#0B6273", fg="#E7FDFF",
            font=("Segoe UI Semibold", 8), padx=8, pady=3,
        ).pack(side="left", padx=(10, 0))
        tk.Label(
            self.play_meta_card,
            text="Ranking aprendido continuamente com rodadas auditadas. O cérebro permanece congelado em estrutura; somente os dados de treino avançam.",
            bg=self.colors["card2"], fg=self.colors["muted"],
            font=("Segoe UI", 8), anchor="w", justify="left",
        ).pack(fill="x", pady=(5, 7))
        meta_controls = tk.Frame(self.play_meta_card, bg=self.colors["card2"])
        meta_controls.pack(fill="x")
        self.play_meta_animals_label = tk.Label(
            meta_controls, text="Bichos do ranking Meta", bg=self.colors["card2"],
            fg=self.colors["text"], font=("Segoe UI", 9),
        )
        self.play_meta_animals_label.grid(row=0, column=0, sticky="w")
        self.play_meta_animals_spin = ttk.Spinbox(
            meta_controls, from_=1, to=25, textvariable=self.play_meta_animals, width=7,
        )
        self.play_meta_animals_spin.grid(row=1, column=0, sticky="w", pady=(2, 0), padx=(0, 14))
        self.play_meta_status = tk.Label(
            meta_controls, text="Escolha quantos bichos do topo do Meta entrarão no jogo.",
            bg=self.colors["card2"], fg=self.colors["muted"],
            font=("Segoe UI", 8), anchor="w", justify="left",
        )
        self.play_meta_status.grid(row=0, column=1, rowspan=2, sticky="w")
        meta_controls.grid_columnconfigure(1, weight=1)
        self.play_meta_card.pack_forget()

        # FECHAMENTO HISTÓRICO CONCENTRADO (visível apenas na variação Fechamento)''',
'meta card')

one(
'''        ttk.Label(
            self.play_hc_card, text="HISTÓRICO CONCENTRADO", style="CardMuted.TLabel"
        ).grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 5))''',
'''        ttk.Label(
            self.play_hc_card, text="FECHAMENTO CONFIGURÁVEL", style="CardMuted.TLabel"
        ).grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 5))''',
'generic closing title')

# Título do painel de distribuição 3+1/Meta.
one(
'''            text="ESTADO DO RESET + 3+1",
            style="Section.TLabel",''',
'''            text="DISTRIBUIÇÃO DE DEZENAS • 3+1 / META 2:1",
            style="Section.TLabel",''',
'ratio state title')

one(
'''            hc_state_head, text="RANKING DO HISTÓRICO CONCENTRADO", style="Section.TLabel"
        ).pack(side="left")''',
'''            hc_state_head, text="RANKING DO FECHAMENTO", style="Section.TLabel"
        ).pack(side="left")''',
'closing ranking title')

# Métodos disponíveis: Meta entra em todas as modalidades automáticas.
pattern = re.compile(r'''        if kind == "Fechamento de Grupo":\n.*?        else:\n            methods = \["Manual"\]\n''', re.S)
replacement = '''        if kind == "Fechamento de Grupo":
            methods = [
                "Histórico • Concentrado",
                "★ META • GP-H Meta v0.1",
            ]
        elif kind == "Centena":
            methods = [
                "Oficial • Reset + 3+1",
                "★ META • GP-H Meta v0.1",
                "Oficial • Reset + Histórica",
                "Especial • Seca do Dia 1º",
                "Experimental • Puxada Combinada",
                "Experimental • Similaridade do Dia",
                "Manual",
            ]
        elif kind == "Milhar":
            methods = [
                "Oficial • Reset + Histórica",
                "★ META • GP-H Meta v0.1",
                "Especial • Seca do Dia 1º",
                "Experimental • Puxada Combinada",
                "Experimental • Similaridade do Dia",
                "Manual",
            ]
        elif kind == "Grupo":
            methods = [
                "Oficial • Reset",
                "★ META • GP-H Meta v0.1",
                "Experimental • Puxada Combinada",
                "Experimental • Similaridade do Dia",
                "Manual",
            ]
        elif kind in GROUP_COMBO_SIZES or kind in PASSE_MODALITIES:
            methods = [
                "Oficial • Reset combinações",
                "★ META • GP-H Meta v0.1",
                "Experimental • Puxada Combinada",
                "Experimental • Similaridade combinações",
                "Manual",
            ]
        elif kind in DEZENA_COMBO_SIZES or kind in INVERTED_MODALITIES or kind == "Dezena":
            methods = [
                "Oficial • Reset + Histórica",
                "★ META • GP-H Meta v0.1",
                "Experimental • Puxada Combinada",
                "Experimental • Similaridade do Dia",
                "Manual",
            ]
        else:
            methods = ["Manual"]
'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit(f'lista de métodos: esperado 1 bloco, alterados {n}')

# Mostra/oculta cartão Meta e cria badge próprio.
one(
'''        if kind == "Grupo" and self.play_total.get() == "20":
            self.play_total.set("5")''',
'''        is_meta = method.startswith("★ META")
        if is_meta:
            self.play_meta_card.pack(fill="x", pady=(0, 6), before=self.play_stake_card)
            if kind == "Fechamento de Grupo":
                self.play_meta_animals_label.grid_remove()
                self.play_meta_animals_spin.grid_remove()
                self.play_meta_status.configure(
                    text="No Fechamento, a quantidade de bichos é definida no cartão Fechamento configurável abaixo."
                )
            else:
                self.play_meta_animals_label.grid()
                self.play_meta_animals_spin.grid()
                self.play_meta_status.configure(
                    text="Escolha quantos bichos do topo do Meta entrarão no jogo. Sobras de quantidade favorecem os primeiros do ranking."
                )
        else:
            self.play_meta_card.pack_forget()

        if kind == "Grupo" and self.play_total.get() == "20":
            self.play_total.set("5")''',
'meta card visibility')

one(
'''        # Etiqueta visual de origem do método.
        if method.startswith("Oficial"):
            badge = ("OFICIAL", "#124A7A", "#DCEEFF")
            help_text = "Reset é o seletor oficial. Métodos oficiais geram apenas para a próxima rodada operacional."''',
'''        # Etiqueta visual de origem do método.
        if method.startswith("★ META"):
            badge = ("META • ADAPTATIVO", "#0B6273", "#E7FDFF")
            help_text = (
                "GP-H Meta v0.1 usa o ranking aprendido com snapshots auditados. "
                "A estrutura do cérebro permanece congelada e a previsão usada no jogo é congelada antes do resultado."
            )
        elif method.startswith("Oficial"):
            badge = ("OFICIAL", "#124A7A", "#DCEEFF")
            help_text = "Reset é o seletor oficial. Métodos oficiais geram apenas para a próxima rodada operacional."''',
'meta badge')

one(
'''        self.play_generate_btn.configure(
            text=(
                "INSERIR NÚMEROS" if method == "Manual" else
                "GERAR FECHAMENTO" if method == "Histórico • Concentrado" else
                "GERAR JOGO"
            )
        )''',
'''        self.play_generate_btn.configure(
            text=(
                "INSERIR NÚMEROS" if method == "Manual" else
                "GERAR COM META" if method.startswith("★ META") else
                "GERAR FECHAMENTO" if method == "Histórico • Concentrado" else
                "GERAR JOGO"
            )
        )''',
'meta generate button')

one(
'''                    hint += " — oficial/experimental ficam bloqueados para preservar o teste prospectivo."''',
'''                    hint += " — métodos automáticos ficam bloqueados para preservar o teste prospectivo."''',
'target hint')

# Meta pode usar o mesmo painel de transparência das dezenas do 3+1.
one(
'''            not generation
            or generation.get("strategy") != "Oficial 3+1"
            or not generation.get("animals")
        ):''',
'''            not generation
            or generation.get("strategy") not in ("Oficial 3+1", "Meta 2:1")
            or not generation.get("animals")
        ):''',
'ratio panel condition')

one(
'''                text=(
                    f"Aplicado: 3× {animal.get('main_dezena')} + "
                    f"1× {animal.get('extra_dezena')}"
                ),''',
'''                text=(
                    f"Aplicado: {int(animal.get('main_count', 3))}× {animal.get('main_dezena')} + "
                    f"{int(animal.get('extra_count', 1))}× {animal.get('extra_dezena')}"
                ),''',
'ratio panel dynamic counts')

# Meta no play_generate: usa SEMPRE a leitura congelada da rodada atual.
one(
'''            if method.startswith("Experimental"):
                if "Puxada" in method:
                    pull = self.db.method_convergencia_g5(''',
'''            meta_payload = None
            if method.startswith("★ META"):
                if kind == "Fechamento de Grupo":
                    try:
                        top_animals = max(2, min(15, int(self.play_hc_base_animals.get())))
                    except Exception:
                        raise ValueError("Informe uma quantidade válida de bichos no Fechamento.")
                else:
                    try:
                        top_animals = max(1, min(25, int(self.play_meta_animals.get())))
                    except Exception:
                        raise ValueError("Informe uma quantidade válida de bichos do Meta.")

                snapshot, _created = self.db.freeze_decision_snapshot()
                snap_target = {
                    "data": snapshot.get("target_data"),
                    "sorteio": snapshot.get("target_sorteio"),
                    "hora": snapshot.get("target_hora"),
                }
                if (
                    snap_target.get("data"), snap_target.get("sorteio"), snap_target.get("hora")
                ) != (
                    target.get("data"), target.get("sorteio"), target.get("hora")
                ):
                    raise ValueError("O snapshot Meta congelado não corresponde à rodada selecionada.")

                snapshot, _meta_created = self.db.freeze_meta_snapshot(snapshot=snapshot)
                meta_payload = copy.deepcopy(snapshot.get("meta") or {})
                if not meta_payload.get("available"):
                    reason = meta_payload.get("reason") or meta_payload.get("status") or "Meta indisponível"
                    raise ValueError(f"GP-H Meta v0.1 ainda não pode gerar esta rodada: {reason}")

                ranking = list(meta_payload.get("ranking") or [])
                if len(ranking) < top_animals:
                    raise ValueError(
                        f"O Meta disponibilizou {len(ranking)} bichos no ranking; foram pedidos {top_animals}."
                    )
                groups = [int(r["grupo"]) for r in ranking[:top_animals]]
                selector = "GP-H Meta v0.1"
                if hasattr(self, "play_meta_status"):
                    names = ", ".join(BICHOS[g].title() for g in groups[:8])
                    suffix = "..." if len(groups) > 8 else ""
                    self.play_meta_status.configure(
                        text=(
                            f"Top {len(groups)} congelado para esta rodada • treino: "
                            f"{int(meta_payload.get('training_snapshots') or 0)} snapshots • {names}{suffix}"
                        )
                    )

            elif method.startswith("Experimental"):
                if "Puxada" in method:
                    pull = self.db.method_convergencia_g5(''',
'meta selector in play_generate')

# Fechamento completo também pode partir do Meta.
one(
'''            if not groups:
                raise ValueError(
                    "O método não produziu bichos suficientes."
                )

            if kind == "Grupo":''',
'''            if not groups:
                raise ValueError(
                    "O método não produziu bichos suficientes."
                )

            if kind == "Fechamento de Grupo" and method.startswith("★ META"):
                requests = self.play_hc_requested_counts()
                if sum(requests.values()) <= 0:
                    raise ValueError("Escolha pelo menos uma Dupla, Terno, Quadra ou Quina.")
                top_animals = len(groups)
                minimum = self.play_hc_minimum_needed()
                if minimum is None or top_animals < minimum:
                    raise ValueError(
                        f"O fechamento pedido exige pelo menos {minimum or 'mais'} bichos; "
                        f"o Meta está usando {top_animals}."
                    )
                meta_rank = [dict(r) for r in (meta_payload.get("ranking") or [])[:top_animals]]
                generation = self.db.generate_historical_concentrated_bundle(
                    meta_rank, top_animals=top_animals, requests=requests, scope="1º–5º"
                )
                generation["strategy"] = "Meta • Fechamento"
                generation["selector"] = selector
                generation["meta_bundle"] = True
                generation["meta_ranking"] = meta_rank
                generation["intended_target"] = target
                generation["target_mode"] = "ALVO_ESPECIFICO"
                for sub in generation.get("bundle_generations") or []:
                    sub["strategy"] = "Meta • " + str(sub.get("kind") or "Fechamento")
                    sub["selector"] = selector
                    sub["intended_target"] = dict(target)
                    sub["target_mode"] = "ALVO_ESPECIFICO"
                    sub["meta_ranking"] = copy.deepcopy(meta_rank)
                self.play_generation = generation
                self.play_generation_groups = list(generation.get("groups") or groups)
                self._shadow_freeze_async(target, latest)
                self.play_render_generation()
                self.play_financial_refresh()
                return

            if kind == "Grupo":''',
'meta closing')

# Centena Meta ganha regra 2:1; demais modalidades reaproveitam os geradores existentes.
one(
'''            elif (
                kind == "Centena"
                and method == "Oficial • Reset + 3+1"
            ):
                generation = self.db.generate_centenas_3plus1(''',
'''            elif kind == "Centena" and method.startswith("★ META"):
                generation = self.db.generate_centenas_meta_21(
                    groups=groups,
                    total=total,
                    previous_draw=latest,
                )
                generation["selector"] = selector
                generation["strategy"] = "Meta 2:1"
                generation["meta_ranking"] = copy.deepcopy((meta_payload or {}).get("ranking") or [])
                generation["meta_training_snapshots"] = int((meta_payload or {}).get("training_snapshots") or 0)

            elif (
                kind == "Centena"
                and method == "Oficial • Reset + 3+1"
            ):
                generation = self.db.generate_centenas_3plus1(''',
'meta centena branch')

# Metadados Meta também seguem nas demais modalidades.
one(
'''            # A fórmula interna pode ter um escopo estatístico próprio
            # (ex.: 3+1 usa histórico 1º–5º; Seca usa histórico de 1º),''',
'''            if method.startswith("★ META") and meta_payload is not None:
                generation["meta_ranking"] = copy.deepcopy(meta_payload.get("ranking") or [])
                generation["meta_training_snapshots"] = int(meta_payload.get("training_snapshots") or 0)
                generation["meta_model_version"] = meta_payload.get("model_version")

            # A fórmula interna pode ter um escopo estatístico próprio
            # (ex.: 3+1 usa histórico 1º–5º; Seca usa histórico de 1º),''',
'meta generation metadata')

# Painel do fechamento: histórico mostra indicações; Meta mostra score do modelo.
one(
'''            label = ttk.Label(
                rows_host,
                text=(
                    f"{letter}  {BICHOS[int(row['grupo'])]} · G{int(row['grupo']):02d}  "
                    f"• {int(row.get('indication_count') or 0)} indicação(ões)  "
                    f"• soma {float(row.get('sum_prob') or 0.0)*100:.2f}%"
                ),
                style="Card.TLabel" if idx <= 3 else "CardMuted.TLabel",
            )''',
'''            if generation.get("meta_bundle"):
                detail_text = f"• score Meta {float(row.get('score') or 0.0):.3f}"
            else:
                detail_text = (
                    f"• {int(row.get('indication_count') or 0)} indicação(ões)  "
                    f"• soma {float(row.get('sum_prob') or 0.0)*100:.2f}%"
                )
            label = ttk.Label(
                rows_host,
                text=(
                    f"{letter}  {BICHOS[int(row['grupo'])]} · G{int(row['grupo']):02d}  "
                    f"{detail_text}"
                ),
                style="Card.TLabel" if idx <= 3 else "CardMuted.TLabel",
            )''',
'meta closing ranking rows')

# Origem explícita no rascunho para facilitar auditoria humana.
one(
'''                "origem_jogada": (
                    "Manual"
                    if generation.get("strategy") == "Manual"
                    else "Gerada"
                ),''',
'''                "origem_jogada": (
                    "Manual"
                    if generation.get("strategy") == "Manual"
                    else "Gerada • GP-H Meta"
                    if generation.get("selector") == "GP-H Meta v0.1"
                    else "Gerada"
                ),''',
'meta ticket origin')

# Sobre/novidades.
one(
'''            "• v0.46.7 — nova tela Jogos do dia reúne todas as extrações de uma data em cartões com horário grande e 1º–5º prêmio.\\\n"''',
'''            "• v0.46.8 — GP-H Meta v0.1 passa a ser jogável em todas as modalidades automáticas; Centena usa distribuição flexível 2:1 e quantidade de bichos configurável.\\\n"
            "• v0.46.7 — nova tela Jogos do dia reúne todas as extrações de uma data em cartões com horário grande e 1º–5º prêmio.\\\n"''',
'about history')

p.write_text(s, encoding='utf-8')

# Documentação consolidada.
doc = Path('source/DOCUMENTACAO_GP-H.txt')
d = doc.read_text(encoding='utf-8')
entry = '''REVISÃO v0.46.8 — GP-H META v0.1 JOGÁVEL / DISTRIBUIÇÃO FLEXÍVEL\n- O GP-H Meta v0.1 sai da condição exclusivamente sombra no módulo Jogar e passa a poder gerar apostas reais, sem alterar seu cérebro: mesmas 20 características, regressão logística L2 nativa, mínimo de 20 snapshots, janela prospectiva de até 160 e proteções anti-lookahead.\n- A previsão usada no bilhete é sempre a leitura Meta congelada ANTES do resultado da rodada; se já houver leitura congelada, ela é reutilizada.\n- O Meta entra como seletor em Grupo, Dupla/Terno/Quadra/Quina de Grupo, Fechamento, Passe, Dezena, Duque/Terno de Dezena, invertidas, Centena e Milhar (incluindo Milhar/Centena).\n- O usuário escolhe quantos bichos do ranking Meta utilizar; sobras na distribuição de quantidade favorecem os bichos mais bem ranqueados.\n- Centena Meta usa a nova distribuição aproximada 2:1 entre duas dezenas ativas: 4=3+1, 5=3+2, 6=4+2, 8=5+3 e 9=6+3. A máquina de congelamento do 3+1 é reutilizada sem mudança: principal congelada desloca a dupla ativa para 2ª+3ª dezena.\n- Para preservar exatamente a regra 2:1 em duas dezenas, o gerador limita a 15 Centenas por bicho; acima disso orienta aumentar os bichos ou reduzir a quantidade, em vez de quebrar silenciosamente a matemática.\n- O 3+1 oficial do Reset permanece intacto e separado. Bilhetes Meta são gravados com seletor GP-H Meta v0.1 para auditoria real independente.\n- Nenhuma fórmula de Reset, Puxada, Similaridade, Histórico Concentrado, Decisão A/B/C/D ou do cérebro Meta existente foi recalibrada nesta versão.\n\n'''
if not d.startswith('REVISÃO v0.46.8'):
    d = entry + d
doc.write_text(d, encoding='utf-8')
