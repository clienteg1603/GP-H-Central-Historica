from pathlib import Path

src = Path('source/gph_central.py')
text = src.read_text(encoding='utf-8')

# Versão e resumo.
text = text.replace('GP-H Central Histórica v0.46.6', 'GP-H Central Histórica v0.46.7', 1)
text = text.replace('APP_VERSION = "0.46.6"', 'APP_VERSION = "0.46.7"', 1)
text = text.replace(
    '- Guarda 1º ao 5º prêmio.\n',
    '- Guarda 1º ao 5º prêmio.\n- Nova tela Jogos do dia reúne todas as extrações de uma data em cartões.\n',
    1,
)

# Consultas read-only específicas da nova tela.
anchor = '''    def connect(self):\n        con = sqlite3.connect(self.path)\n        con.row_factory = sqlite3.Row\n        return con\n\n    def init_schema(self):\n'''
insert = '''    def connect(self):\n        con = sqlite3.connect(self.path)\n        con.row_factory = sqlite3.Row\n        return con\n\n    def latest_result_date(self):\n        """Última data que possui ao menos um prêmio registrado."""\n        with self.connect() as con:\n            row = con.execute("SELECT MAX(data) FROM resultados").fetchone()\n        return row[0] if row and row[0] else None\n\n    def day_draws(self, data_value):\n        """Agrupa os prêmios de uma data por extração, em ordem cronológica."""\n        data_value = str(data_value or "").strip()\n        if not data_value:\n            return []\n        with self.connect() as con:\n            rows = con.execute(\n                """\n                SELECT data, sorteio, hora, premio, milhar, centena, dezena, grupo, bicho\n                FROM resultados\n                WHERE data=?\n                ORDER BY substr(hora,1,2), substr(hora,4,2), sorteio, premio\n                """,\n                (data_value,),\n            ).fetchall()\n\n        draws = []\n        current = None\n        for row in rows:\n            key = (row["sorteio"], row["hora"])\n            if current is None or current["key"] != key:\n                current = {\n                    "key": key,\n                    "data": row["data"],\n                    "sorteio": row["sorteio"],\n                    "hora": row["hora"],\n                    "prizes": [],\n                }\n                draws.append(current)\n            current["prizes"].append(dict(row))\n        for draw in draws:\n            draw.pop("key", None)\n        return draws\n\n    def init_schema(self):\n'''
if anchor not in text:
    raise SystemExit('Âncora Database.connect não encontrada')
text = text.replace(anchor, insert, 1)

# Preserva a nova tela ao trocar tema/pacote visual.
text = text.replace(
    '''        if previous_page == "base":\n            self.show_base_config()\n        self.status.configure(text=f"Tema aplicado: {theme_name}.")\n''',
    '''        if previous_page == "base":\n            self.show_base_config()\n        elif previous_page == "games_day":\n            self.show_games_day(getattr(self, "games_day_selected_date", None))\n        self.status.configure(text=f"Tema aplicado: {theme_name}.")\n''',
    1,
)
text = text.replace(
    '''        if previous_page == "base":\n            self.show_base_config()\n        elif previous_page == "home_animals":\n''',
    '''        if previous_page == "base":\n            self.show_base_config()\n        elif previous_page == "games_day":\n            self.show_games_day(getattr(self, "games_day_selected_date", None))\n        elif previous_page == "home_animals":\n''',
    1,
)

# Menu OPERAÇÃO.
nav_anchor = '''        for label, command, icon_key in [\n            ("Início", self.show_home, "home"),\n            ("Jogar", self.show_play_page, "ticket"),\n'''
nav_insert = '''        for label, command, icon_key in [\n            ("Início", self.show_home, "home"),\n            ("Jogos do dia", self.show_games_day, "results"),\n            ("Jogar", self.show_play_page, "ticket"),\n'''
if nav_anchor not in text:
    raise SystemExit('Âncora do menu OPERAÇÃO não encontrada')
text = text.replace(nav_anchor, nav_insert, 1)
text = text.replace(
    'name in ("Início", "Jogar", "Decisão", "Resultados")',
    'name in ("Início", "Jogos do dia", "Jogar", "Decisão", "Resultados")',
    1,
)

# Nova página antes da Pesquisa.
show_search_anchor = '''    def show_search(self):\n        self._set_active_nav("Pesquisa")\n'''
show_games_day = r'''    def show_games_day(self, selected_date=None):
        """Visão diária: uma extração por cartão, sempre com os cinco prêmios visíveis."""
        self._set_active_nav("Jogos do dia")
        self._clear_content()
        self._page = "games_day"

        latest = self.db.latest_result_date()
        if selected_date is None:
            selected_date = getattr(self, "games_day_selected_date", None) or latest or date.today().isoformat()

        def parse_day(value):
            value = str(value or "").strip()
            for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    pass
            return None

        chosen = parse_day(selected_date) or date.today()
        day_iso = chosen.isoformat()
        self.games_day_selected_date = day_iso

        self._page_title(
            "Jogos do dia",
            "Veja todas as extrações da data selecionada, com 1º ao 5º prêmio em cartões separados.",
        )
        body = self._make_scrollable_page_body(self.content, "games_day")

        controls = ttk.Frame(body, style="Card.TFrame", padding=10)
        controls.pack(fill="x", pady=(0, 10))

        ttk.Button(
            controls, text="← Dia anterior",
            command=lambda: self.show_games_day((chosen - timedelta(days=1)).isoformat()),
        ).pack(side="left")
        ttk.Button(
            controls, text="Próximo dia →",
            command=lambda: self.show_games_day((chosen + timedelta(days=1)).isoformat()),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            controls, text="Hoje",
            command=lambda: self.show_games_day(date.today().isoformat()),
        ).pack(side="left", padx=(12, 0))
        if latest:
            ttk.Button(
                controls, text="Último disponível",
                command=lambda: self.show_games_day(latest),
            ).pack(side="left", padx=(6, 0))

        ttk.Label(controls, text="Data", style="Card.TLabel").pack(side="left", padx=(18, 5))
        self.games_day_date_var = tk.StringVar(value=chosen.strftime("%d/%m/%Y"))

        def calendar_changed(*_):
            picked = parse_day(self.games_day_date_var.get())
            if picked and picked.isoformat() != self.games_day_selected_date:
                self.show_games_day(picked.isoformat())

        calendar_field = CalendarField(
            controls, self.games_day_date_var, width=11, on_change=calendar_changed
        )
        calendar_field.pack(side="left")

        ttk.Button(
            controls, text="Recarregar",
            command=lambda: self.show_games_day(self.games_day_selected_date),
        ).pack(side="right")
        ttk.Button(
            controls, text="Buscar atualização", style="Accent.TButton",
            command=self.start_update_search,
        ).pack(side="right", padx=(0, 7))

        draws = self.db.day_draws(day_iso)
        total_prizes = sum(len(d["prizes"]) for d in draws)

        summary = ttk.Frame(body)
        summary.pack(fill="x", pady=(0, 8))
        ttk.Label(
            summary,
            text=chosen.strftime("%d/%m/%Y"),
            font=(UI_FONT_SEMIBOLD, 14),
        ).pack(side="left")
        ttk.Label(
            summary,
            text=(
                f"{len(draws)} extração" + ("" if len(draws) == 1 else "ões") +
                f" • {total_prizes} prêmio" + ("" if total_prizes == 1 else "s")
            ),
            style="Sub.TLabel",
        ).pack(side="right")

        if not draws:
            empty = ttk.Frame(body, style="Card.TFrame", padding=18)
            empty.pack(fill="x")
            ttk.Label(
                empty,
                text="Nenhuma extração registrada nesta data.",
                style="Card.TLabel",
                font=(UI_FONT_SEMIBOLD, 11),
            ).pack(anchor="w")
            ttk.Label(
                empty,
                text="Use Buscar atualização ou escolha outra data.",
                style="CardMuted.TLabel",
            ).pack(anchor="w", pady=(3, 0))
            return

        grid = tk.Frame(body, bg=self.colors["bg"])
        grid.pack(fill="both", expand=True)
        for col in range(3):
            grid.grid_columnconfigure(col, weight=1, uniform="gamesdaycols")

        for idx, draw in enumerate(draws):
            card = tk.Frame(
                grid,
                bg=self.colors["card"],
                highlightbackground=self.colors["border"],
                highlightthickness=1,
                padx=9,
                pady=8,
            )
            card.grid(row=idx // 3, column=idx % 3, sticky="nsew", padx=4, pady=4)

            head = tk.Frame(card, bg=self.colors["card"])
            head.pack(fill="x", pady=(0, 7))
            tk.Label(
                head,
                text=draw["hora"],
                bg=self.colors["card"],
                fg=self.colors["text"],
                font=(UI_FONT_SEMIBOLD, 20),
            ).pack(side="left")
            tk.Label(
                head,
                text=draw["sorteio"],
                bg=self.colors["card"],
                fg=self.colors["muted"],
                font=(UI_FONT_SEMIBOLD, 9),
            ).pack(side="right", pady=(7, 0))

            prize_map = {int(r["premio"]): r for r in draw["prizes"]}
            for prize_no in range(1, 6):
                r = prize_map.get(prize_no)
                row = tk.Frame(
                    card,
                    bg=self.colors["card2"],
                    highlightbackground=self.colors["border"],
                    highlightthickness=1,
                    padx=6,
                    pady=4,
                )
                row.pack(fill="x", pady=(0, 4))
                tk.Label(
                    row,
                    text=f"{prize_no}º",
                    bg=self.colors["accent"],
                    fg="white",
                    font=(UI_FONT_SEMIBOLD, 8),
                    width=3,
                    padx=2,
                    pady=2,
                ).pack(side="left", padx=(0, 6))

                if r:
                    ident = tk.Frame(row, bg=self.colors["card2"])
                    ident.pack(side="left", fill="x", expand=True)
                    tk.Label(
                        ident,
                        text=f"{str(r['bicho']).title()} • Grupo {int(r['grupo']):02d}",
                        bg=self.colors["card2"], fg=self.colors["text"],
                        font=(UI_FONT_SEMIBOLD, 8), anchor="w",
                    ).pack(fill="x")
                    tk.Label(
                        ident,
                        text=f"Cent. {r['centena']} • Dez. {r['dezena']}",
                        bg=self.colors["card2"], fg=self.colors["muted"],
                        font=(UI_FONT_FAMILY, 7), anchor="w",
                    ).pack(fill="x")
                    tk.Label(
                        row,
                        text=str(r["milhar"]),
                        bg=self.colors["card2"], fg=self.colors["accent"],
                        font=("Consolas", 14, "bold"),
                    ).pack(side="right", padx=(5, 1))
                else:
                    tk.Label(
                        row,
                        text="Ainda não disponível",
                        bg=self.colors["card2"], fg=self.colors["muted"],
                        font=(UI_FONT_FAMILY, 8), anchor="w",
                    ).pack(side="left", fill="x", expand=True)


    def show_search(self):
        self._set_active_nav("Pesquisa")
'''
if show_search_anchor not in text:
    raise SystemExit('Âncora show_search não encontrada')
text = text.replace(show_search_anchor, show_games_day, 1)

# Sobre: registra a mudança visual sem misturar com cérebro/métodos.
text = text.replace(
    '            "Atualizações recentes:\\n"\n',
    '            "Atualizações recentes:\\n"\n            "• v0.46.7 — nova tela Jogos do dia reúne todas as extrações de uma data em cartões com horário grande e 1º–5º prêmio.\\n"\n',
    1,
)

src.write_text(text, encoding='utf-8')

# Documentação consolidada.
doc = Path('source/DOCUMENTACAO_GP-H.txt')
doc_text = doc.read_text(encoding='utf-8')
entry = '''REVISÃO v0.46.7 — JOGOS DO DIA\n- Nova tela “Jogos do dia” na seção OPERAÇÃO, logo abaixo de Início.\n- A tela reúne todas as extrações de uma data em cartões independentes, com horário em destaque e 1º ao 5º prêmio visíveis.\n- Navegação por dia anterior/próximo, Hoje, Último disponível e calendário; a página usa o rolamento inteligente global da Central.\n- Cada prêmio mostra bicho, grupo, centena, dezena e milhar; resultados ainda incompletos mantêm as cinco posições visíveis.\n- A consulta usa diretamente a tabela resultados do mesmo banco da Central; não cria segunda base nem duplica histórico.\n- A tela permite Buscar atualização e Recarregar sem alterar jogos, financeiro, métodos ou decisões.\n- Nenhuma fórmula de Meta, Reset, Puxada, Similaridade, Histórico Concentrado, 3+1 ou Decisão foi alterada.\n\n'''
if not doc_text.startswith('REVISÃO v0.46.7'):
    doc.write_text(entry + doc_text, encoding='utf-8')
