from pathlib import Path

src = Path("source/gph_central.py")
text = src.read_text(encoding="utf-8")

if 'APP_VERSION = "0.36.4"' in text:
    raise SystemExit("v0.36.4 ja aplicada")
if 'APP_VERSION = "0.36.3"' not in text:
    raise SystemExit("Base esperada v0.36.3 nao encontrada")

text = text.replace("GP-H Central Histórica v0.36.3", "GP-H Central Histórica v0.36.4", 1)
text = text.replace('APP_VERSION = "0.36.3"', 'APP_VERSION = "0.36.4"', 1)

# Corrige texto antigo que ainda dizia que o congelamento durava uma rodada.
old_rule = '''                    "Oficial 3+1: 5 bichos × 4 Centenas. "
                    "3 na principal + 1 na segunda; "
                    "com congelamento da principal por 1 rodada."
'''
new_rule = '''                    "Oficial 3+1: 5 bichos × 4 Centenas. "
                    "3 na principal + 1 na segunda; "
                    "se a principal congelar, usa 3 da segunda + 1 da terceira "
                    "até o mesmo bicho reaparecer."
'''
if old_rule not in text:
    raise SystemExit("Texto antigo da regra 3+1 nao encontrado")
text = text.replace(old_rule, new_rule, 1)

# Painel visual, criado junto da tela mas exibido somente após gerar um Oficial 3+1.
old_info = '''        self.gen_summary_label.pack(
            side="right", padx=(8, 0)
        )

        table = ttk.Frame(body)
        table.pack(fill="both", expand=True)
'''
new_info = '''        self.gen_summary_label.pack(
            side="right", padx=(8, 0)
        )

        self.gen_31_state_frame = ttk.Frame(
            body, style="Card.TFrame", padding=(9, 7)
        )
        state_head = ttk.Frame(
            self.gen_31_state_frame, style="Card.TFrame"
        )
        state_head.pack(fill="x", pady=(0, 5))
        ttk.Label(
            state_head,
            text="ESTADO DO RESET + 3+1",
            style="Section.TLabel",
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")
        self.gen_31_state_note = ttk.Label(
            state_head,
            text="",
            style="CardMuted.TLabel",
            wraplength=760,
        )
        self.gen_31_state_note.pack(
            side="left", fill="x", expand=True, padx=(12, 0)
        )
        self.gen_31_state_rows = ttk.Frame(
            self.gen_31_state_frame, style="Card.TFrame"
        )
        self.gen_31_state_rows.pack(fill="x")

        table = ttk.Frame(body)
        self.gen_table_frame = table
        table.pack(fill="both", expand=True)
'''
if old_info not in text:
    raise SystemExit("Bloco de resumo/tabela do Gerador nao encontrado")
text = text.replace(old_info, new_info, 1)

# Métodos de renderização do estado, antes de generator_resolve_groups.
marker = '''    def generator_resolve_groups(self):
'''
if marker not in text:
    raise SystemExit("generator_resolve_groups nao encontrado")

helpers = r'''    def generator_hide_31_state(self):
        frame = getattr(self, "gen_31_state_frame", None)
        if frame is not None:
            try:
                frame.pack_forget()
            except Exception:
                pass

    def generator_format_31_event(self, event, action):
        if not event:
            return "sem evento ativo"

        raw_date = str(event.get("data") or "")
        try:
            date_txt = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            date_txt = raw_date or "data não identificada"

        draw_txt = " ".join(
            part for part in (
                str(event.get("sorteio") or "").strip(),
                str(event.get("hora") or "").strip(),
            )
            if part
        )
        dezenas = [str(v).zfill(2) for v in (event.get("dezenas") or [])]
        dez_txt = "/".join(dezenas)

        pieces = [f"{action} em {date_txt}"]
        if draw_txt:
            pieces.append(draw_txt)
        if dez_txt:
            pieces.append(f"dezena(s) {dez_txt}")
        return " • ".join(pieces)

    def generator_render_31_state(self, generation):
        self.generator_hide_31_state()

        if (
            not generation
            or generation.get("strategy") != "Oficial 3+1"
            or not generation.get("animals")
        ):
            return

        rows_host = getattr(self, "gen_31_state_rows", None)
        frame = getattr(self, "gen_31_state_frame", None)
        table = getattr(self, "gen_table_frame", None)
        if rows_host is None or frame is None or table is None:
            return

        for child in rows_host.winfo_children():
            child.destroy()

        previous_draw = generation.get("previous_draw") or {}
        base_text = "estado reconstruído até a extração-base"
        if previous_draw:
            try:
                d = datetime.strptime(
                    previous_draw.get("data", ""), "%Y-%m-%d"
                ).strftime("%d/%m/%Y")
            except Exception:
                d = str(previous_draw.get("data") or "")
            draw_txt = " ".join(
                part for part in (
                    str(previous_draw.get("sorteio") or "").strip(),
                    str(previous_draw.get("hora") or "").strip(),
                )
                if part
            )
            base_text = f"Estado reconstruído até {draw_txt} • {d}".strip(" •")

        self.gen_31_state_note.configure(
            text=(
                base_text
                + " • principal sai livre = congela • mesmo bicho reaparece = libera"
            )
        )

        for animal in generation.get("animals") or []:
            frozen = bool(animal.get("frozen"))
            status = "CONGELADA" if frozen else "LIVRE"
            status_prefix = "[LOCK]" if frozen else "[OK]"

            row = ttk.Frame(
                rows_host, style="Card.TFrame", padding=(5, 3)
            )
            row.pack(fill="x", pady=(0, 2))
            row.grid_columnconfigure(0, weight=18)
            row.grid_columnconfigure(1, weight=15)
            row.grid_columnconfigure(2, weight=28)
            row.grid_columnconfigure(3, weight=20)
            row.grid_columnconfigure(4, weight=34)

            ttk.Label(
                row,
                text=f"{animal.get('bicho', '')} • G{int(animal.get('grupo') or 0):02d}",
                style="Card.TLabel",
                font=("Segoe UI Semibold", 9),
            ).grid(row=0, column=0, sticky="w", padx=(0, 8))

            ttk.Label(
                row,
                text=f"{status_prefix} {status}",
                style="Card.TLabel",
                font=("Segoe UI Semibold", 9),
            ).grid(row=0, column=1, sticky="w", padx=(0, 8))

            rank_text = (
                f"Principal {animal.get('principal')} • 2ª {animal.get('segunda')} "
                f"• 3ª {animal.get('terceira')}"
            )
            if animal.get("principal_tied"):
                rank_text += " • empate técnico"
            ttk.Label(
                row,
                text=rank_text,
                style="CardMuted.TLabel",
            ).grid(row=0, column=2, sticky="w", padx=(0, 8))

            ttk.Label(
                row,
                text=(
                    f"Jogo: 3× {animal.get('main_dezena')} + "
                    f"1× {animal.get('extra_dezena')}"
                ),
                style="Card.TLabel",
                font=("Segoe UI Semibold", 9),
            ).grid(row=0, column=3, sticky="w", padx=(0, 8))

            if frozen:
                event_text = self.generator_format_31_event(
                    animal.get("freeze_trigger"), "congelada"
                )
            else:
                released = animal.get("freeze_released_by")
                event_text = (
                    self.generator_format_31_event(released, "liberada")
                    if released
                    else "sem congelamento ativo"
                )

            ttk.Label(
                row,
                text=event_text,
                style="CardMuted.TLabel",
                wraplength=420,
            ).grid(row=0, column=4, sticky="w")

        frame.pack(
            fill="x", pady=(0, 5), before=table
        )

'''
text = text.replace(marker, helpers + marker, 1)

# Toda mudança de controle invalida a leitura visual anterior até gerar novamente.
old_refresh = '''        official = (
            kind == "Centena"
            and strategy == "Oficial 3+1"
        )
        dry = (
'''
new_refresh = '''        official = (
            kind == "Centena"
            and strategy == "Oficial 3+1"
        )
        self.generator_hide_31_state()
        dry = (
'''
if old_refresh not in text:
    raise SystemExit("Bloco official/dry nao encontrado")
text = text.replace(old_refresh, new_refresh, 1)

# Ao gerar, esconde qualquer leitura antiga antes de recalcular.
old_generate = '''    def generator_generate(self):
        try:
            kind = self.gen_kind.get()
            strategy = self.gen_strategy.get()
'''
new_generate = '''    def generator_generate(self):
        try:
            self.generator_hide_31_state()
            kind = self.gen_kind.get()
            strategy = self.gen_strategy.get()
'''
if old_generate not in text:
    raise SystemExit("Inicio de generator_generate nao encontrado")
text = text.replace(old_generate, new_generate, 1)

# Exibe o painel depois de montar o resumo oficial.
old_summary_end = '''                self.gen_summary_label.configure(
                    text=summary
                )

            else:
'''
new_summary_end = '''                self.gen_summary_label.configure(
                    text=summary
                )
                self.generator_render_31_state(
                    self.gen_current_generation
                )

            else:
'''
if old_summary_end not in text:
    raise SystemExit("Fim do resumo Oficial 3+1 nao encontrado")
text = text.replace(old_summary_end, new_summary_end, 1)

src.write_text(text, encoding="utf-8")

# Documentação consolidada.
doc = Path("source/DOCUMENTACAO_GP-H.txt")
if doc.exists():
    d = doc.read_text(encoding="utf-8")
    revision = '''REVISÃO v0.36.4 — RESET + 3+1 / AUDITORIA VISUAL\n- O Gerador passa a mostrar um painel auditável dos 5 bichos sempre que o Oficial 3+1 é gerado.\n- Cada bicho mostra estado LIVRE/CONGELADA, principal, 2ª, 3ª, aplicação 3×+1× e o evento que acionou ou liberou o congelamento quando disponível.\n- O painel é reconstruído junto com o jogo e desaparece ao alterar os controles, evitando exibir estado antigo como se fosse atual.\n- Corrigido texto visual legado que ainda dizia “congelamento por 1 rodada”; a regra oficial permanece persistente até o mesmo bicho reaparecer.\n- Nenhuma fórmula, ranking, seletor de bicho, resultado histórico, financeiro ou método concorrente foi alterado.\n\n'''
    if not d.startswith("REVISÃO v0.36.4"):
        d = revision + d
    d = d.replace("VERSÃO ATUAL: v0.36.3", "VERSÃO ATUAL: v0.36.4", 1)
    doc.write_text(d, encoding="utf-8")

upd = Path("source/ATUALIZACOES_PROGRAMA_v0.35.txt")
if upd.exists():
    u = upd.read_text(encoding="utf-8")
    u = u.replace("GP-H CENTRAL HISTÓRICA v0.36.3", "GP-H CENTRAL HISTÓRICA v0.36.4", 1)
    note = '''\nNovidades v0.36.4:\n- Painel auditável do Reset + 3+1 no Gerador.\n- Mostra LIVRE/CONGELADA, ranking das três dezenas, aplicação 3×+1× e evento do estado.\n- Texto legado de “congelamento por 1 rodada” corrigido para a regra persistente oficial.\n'''
    if "Novidades v0.36.4:" not in u:
        u += note
    upd.write_text(u, encoding="utf-8")

print("Patch v0.36.4 aplicado")
