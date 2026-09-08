from pathlib import Path

src = Path("source/gph_central.py")
text = src.read_text(encoding="utf-8")

if 'APP_VERSION = "0.36.5"' in text:
    raise SystemExit("v0.36.5 ja aplicada")
if 'APP_VERSION = "0.36.4"' not in text:
    raise SystemExit("Base esperada v0.36.4 nao encontrada")

text = text.replace("GP-H Central Histórica v0.36.4", "GP-H Central Histórica v0.36.5", 1)
text = text.replace('APP_VERSION = "0.36.4"', 'APP_VERSION = "0.36.5"', 1)

old_ui = '''        # 4) PALPITES
        generation_card = ttk.Frame(self.play_body, style="Card.TFrame", padding=(10, 8))
        generation_card.pack(fill="x", pady=(0, 6))
'''
new_ui = '''        # 4) ESTADO DO RESET + 3+1 (oculto até gerar o método oficial)
        self.play_31_state_card = ttk.Frame(
            self.play_body, style="Card.TFrame", padding=(10, 8)
        )
        state_head = ttk.Frame(self.play_31_state_card, style="Card.TFrame")
        state_head.pack(fill="x", pady=(0, 4))
        ttk.Label(
            state_head,
            text="ESTADO DO RESET + 3+1",
            style="Section.TLabel",
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")
        self.play_31_state_note = ttk.Label(
            state_head,
            text="",
            style="CardMuted.TLabel",
            wraplength=820,
            justify="left",
        )
        self.play_31_state_note.pack(
            side="left", fill="x", expand=True, padx=(12, 0)
        )
        self.play_31_state_rows = ttk.Frame(
            self.play_31_state_card, style="Card.TFrame"
        )
        self.play_31_state_rows.pack(fill="x")

        # 5) PALPITES
        generation_card = ttk.Frame(self.play_body, style="Card.TFrame", padding=(10, 8))
        self.play_generation_card = generation_card
        generation_card.pack(fill="x", pady=(0, 6))
'''
if old_ui not in text:
    raise SystemExit("Bloco PALPITES da tela Jogar nao encontrado")
text = text.replace(old_ui, new_ui, 1)

marker = '''    def play_generate(self):
'''
if marker not in text:
    raise SystemExit("play_generate nao encontrado")

helpers = r'''    def play_hide_31_state(self):
        card = getattr(self, "play_31_state_card", None)
        if card is not None:
            try:
                card.pack_forget()
            except Exception:
                pass

    def play_render_31_state(self, generation):
        self.play_hide_31_state()

        if (
            not generation
            or generation.get("strategy") != "Oficial 3+1"
            or not generation.get("animals")
        ):
            return

        card = getattr(self, "play_31_state_card", None)
        rows_host = getattr(self, "play_31_state_rows", None)
        note = getattr(self, "play_31_state_note", None)
        before = getattr(self, "play_generation_card", None)
        if card is None or rows_host is None or note is None or before is None:
            return

        for child in rows_host.winfo_children():
            child.destroy()

        base = generation.get("previous_draw") or {}
        if base:
            try:
                date_txt = datetime.strptime(
                    str(base.get("data") or ""), "%Y-%m-%d"
                ).strftime("%d/%m/%Y")
            except Exception:
                date_txt = str(base.get("data") or "")
            draw_txt = " ".join(
                part for part in (
                    str(base.get("sorteio") or "").strip(),
                    str(base.get("hora") or "").strip(),
                )
                if part
            )
            base_txt = f"Base: {draw_txt} • {date_txt}".strip(" •")
        else:
            base_txt = "Estado reconstruído até a extração-base"

        note.configure(
            text=(
                base_txt
                + " • principal livre que sai = congela • nova aparição do bicho = libera"
            )
        )

        for animal in generation.get("animals") or []:
            frozen = bool(animal.get("frozen"))
            state = "CONGELADA" if frozen else "LIVRE"

            row = ttk.Frame(rows_host, style="Card.TFrame", padding=(4, 3))
            row.pack(fill="x", pady=(0, 1))
            row.grid_columnconfigure(0, weight=15)
            row.grid_columnconfigure(1, weight=11)
            row.grid_columnconfigure(2, weight=25)
            row.grid_columnconfigure(3, weight=18)
            row.grid_columnconfigure(4, weight=31)

            ttk.Label(
                row,
                text=f"{animal.get('bicho', '')} • G{int(animal.get('grupo') or 0):02d}",
                style="Card.TLabel",
                font=("Segoe UI Semibold", 9),
            ).grid(row=0, column=0, sticky="w", padx=(0, 8))

            ttk.Label(
                row,
                text=state,
                style="Card.TLabel",
                font=("Segoe UI Semibold", 9),
            ).grid(row=0, column=1, sticky="w", padx=(0, 8))

            rank_txt = (
                f"Principal {animal.get('principal')} • 2ª {animal.get('segunda')} "
                f"• 3ª {animal.get('terceira')}"
            )
            if animal.get("principal_tied"):
                rank_txt += " • empate técnico"
            ttk.Label(
                row,
                text=rank_txt,
                style="CardMuted.TLabel",
                wraplength=340,
                justify="left",
            ).grid(row=0, column=2, sticky="w", padx=(0, 8))

            ttk.Label(
                row,
                text=(
                    f"Aplicado: 3× {animal.get('main_dezena')} + "
                    f"1× {animal.get('extra_dezena')}"
                ),
                style="Card.TLabel",
                font=("Segoe UI Semibold", 9),
            ).grid(row=0, column=3, sticky="w", padx=(0, 8))

            if frozen:
                event_txt = self.generator_format_31_event(
                    animal.get("freeze_trigger"), "congelou"
                )
                event_txt += " • aguardando nova aparição do bicho"
            else:
                released = animal.get("freeze_released_by")
                event_txt = (
                    self.generator_format_31_event(released, "liberou")
                    if released
                    else "sem congelamento ativo"
                )

            ttk.Label(
                row,
                text=event_txt,
                style="CardMuted.TLabel",
                wraplength=430,
                justify="left",
            ).grid(row=0, column=4, sticky="w")

        card.pack(fill="x", pady=(0, 6), before=before)
        self.after_idle(self._play_finalize_layout)

'''
text = text.replace(marker, helpers + marker, 1)

old_controls = '''    def play_controls_changed(self, _event=None):
        kind = self.play_kind.get()
        method = self.play_method.get()
'''
new_controls = '''    def play_controls_changed(self, _event=None):
        self.play_hide_31_state()
        kind = self.play_kind.get()
        method = self.play_method.get()
'''
if old_controls not in text:
    raise SystemExit("play_controls_changed nao encontrado")
text = text.replace(old_controls, new_controls, 1)

old_generate = '''    def play_generate(self):
        try:
            kind = self.play_kind.get()
'''
new_generate = '''    def play_generate(self):
        try:
            self.play_hide_31_state()
            kind = self.play_kind.get()
'''
if old_generate not in text:
    raise SystemExit("Inicio de play_generate nao encontrado")
text = text.replace(old_generate, new_generate, 1)

old_render = '''    def play_render_generation(self):
        for child in self.play_grid_container.winfo_children():
            child.destroy()
'''
new_render = '''    def play_render_generation(self):
        self.play_render_31_state(self.play_generation)
        for child in self.play_grid_container.winfo_children():
            child.destroy()
'''
if old_render not in text:
    raise SystemExit("play_render_generation nao encontrado")
text = text.replace(old_render, new_render, 1)

old_add = '''        self.play_generation = None
        self.play_refresh_ticket()

        for child in self.play_grid_container.winfo_children():
'''
new_add = '''        self.play_generation = None
        self.play_hide_31_state()
        self.play_refresh_ticket()

        for child in self.play_grid_container.winfo_children():
'''
if old_add not in text:
    raise SystemExit("Limpeza apos adicionar ao bilhete nao encontrada")
text = text.replace(old_add, new_add, 1)

src.write_text(text, encoding="utf-8")

# Documentação consolidada.
doc = Path("source/DOCUMENTACAO_GP-H.txt")
if doc.exists():
    d = doc.read_text(encoding="utf-8")
    revision = '''REVISÃO v0.36.5 — RESET + 3+1 / ESTADO VISÍVEL EM JOGAR\n- O painel auditável do Reset + 3+1 passa a aparecer também na tela Jogar, entre Aposta e Palpites, onde a aposta oficial é realmente montada.\n- Para cada um dos 5 bichos mostra LIVRE/CONGELADA, principal, 2ª, 3ª, regra efetivamente aplicada 3×+1× e evento que congelou ou liberou o estado.\n- Quando congelada, a tela informa que aguarda nova aparição do próprio bicho para liberar.\n- O painel some ao trocar método, modalidade, alvo ou ao adicionar a geração ao bilhete, evitando exibir leitura antiga.\n- O painel do Gerador permanece disponível.\n- Nenhuma fórmula, ranking, seleção dos 5 bichos, histórico, bilhete ou financeiro foi alterado.\n\n'''
    if not d.startswith("REVISÃO v0.36.5"):
        d = revision + d
    d = d.replace("VERSÃO ATUAL: v0.36.4", "VERSÃO ATUAL: v0.36.5", 1)
    doc.write_text(d, encoding="utf-8")

upd = Path("source/ATUALIZACOES_PROGRAMA_v0.35.txt")
if upd.exists():
    u = upd.read_text(encoding="utf-8")
    u = u.replace("GP-H CENTRAL HISTÓRICA v0.36.4", "GP-H CENTRAL HISTÓRICA v0.36.5", 1)
    note = '''\nNovidades v0.36.5:\n- Estado auditável do Reset + 3+1 também na tela Jogar.\n- Mostra os 5 bichos, LIVRE/CONGELADA, principal/2ª/3ª, aplicação 3×+1× e evento do estado antes da aposta.\n- Nenhuma fórmula do método oficial foi alterada.\n'''
    if "Novidades v0.36.5:" not in u:
        u += note
    upd.write_text(u, encoding="utf-8")

print("Patch v0.36.5 aplicado")
