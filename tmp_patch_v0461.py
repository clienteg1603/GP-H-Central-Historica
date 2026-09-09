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

# Protege o cérebro estatístico/operacional. A v0.46.1 é somente UI/consulta.
protected = [
    'method_reset_coverage_v1', 'method_convergencia_g5', 'method_similarity_day',
    'method_historico_concentrado_v01', 'generate_historical_concentrated_bundle',
    'generate_centenas_3plus1', 'centena_31_freeze_state',
    'decision_contextual_evidence', 'decision_contextual_audit_summary',
    'decision_confidence_calibration', 'decision_walk_forward',
    'decision_adaptive_context', 'decision_adaptive_audit_summary',
    'decision_operational_recommendation', 'decision_operational_audit_summary',
    'meta_shadow_prediction', 'meta_walk_forward', 'freeze_meta_snapshot',
    'historical_pulls', 'number_rankings_for_group', 'generate_historical_numbers',
]
before = {name: fn_dump(text, name) for name in protected}

assert 'APP_VERSION = "0.46.0"' in text
text = text.replace('GP-H Central Histórica v0.46.0', 'GP-H Central Histórica v0.46.1', 1)
text = text.replace('APP_VERSION = "0.46.0"', 'APP_VERSION = "0.46.1"', 1)

# ---------------------------------------------------------------------------
# AnimalQuickDetailsDialog: transforma o clique no bicho em consulta direta
# dos números fortes usando EXATAMENTE number_rankings_for_group existente.
# ---------------------------------------------------------------------------
new_class = r'''class AnimalQuickDetailsDialog(tk.Toplevel):
    """Resumo do bicho com consulta direta dos números historicamente mais fortes."""

    def __init__(self, master, db: Database, grupo: int):
        super().__init__(master)
        self.db = db
        self.grupo = int(grupo)
        self.scope_var = tk.StringVar(value="1º–5º")
        self.number_trees = {}

        self.title(f"{BICHOS[self.grupo]} — Grupo {self.grupo:02d}")
        fit_toplevel_to_screen(
            self, 1060, 690, min_width=900, min_height=580, parent=master
        )
        self.resizable(True, True)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 8))
        image = None
        try:
            image = master.animal_images_medium.get(self.grupo)
        except Exception:
            image = None
        if image is not None:
            ttk.Label(header, image=image).pack(side="left", padx=(0, 10))

        head_text = ttk.Frame(header)
        head_text.pack(side="left", fill="x", expand=True)
        ttk.Label(
            head_text,
            text=f"{BICHOS[self.grupo]} — Grupo {self.grupo:02d}",
            style="Title.TLabel",
        ).pack(anchor="w")

        dezenas = [f"{((self.grupo - 1) * 4 + i) % 100:02d}" for i in range(1, 5)]
        ttk.Label(
            head_text,
            text="Dezenas do grupo: " + " • ".join(dezenas),
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        stats = self.db.stats_by_animal()
        row = next((r for r in stats["rows"] if r["grupo"] == self.grupo), None)
        if row:
            ttk.Label(
                head_text,
                text=(
                    f"{row['ocorrencias']} ocorrências na base • "
                    f"{row['p1']} em 1º prêmio • "
                    f"1º {row['p1']}  |  2º {row['p2']}  |  3º {row['p3']}  |  "
                    f"4º {row['p4']}  |  5º {row['p5']}"
                ),
                style="CardMuted.TLabel",
            ).pack(anchor="w", pady=(2, 0))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        strong_tab = ttk.Frame(notebook, padding=10)
        recent_tab = ttk.Frame(notebook, padding=10)
        notebook.add(strong_tab, text="Números fortes")
        notebook.add(recent_tab, text="Ocorrências recentes")

        controls = ttk.Frame(strong_tab)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(
            controls,
            text="NÚMEROS MAIS FORTES",
            style="Section.TLabel",
        ).pack(side="left")
        ttk.Label(
            controls,
            text="Escopo:",
            style="CardMuted.TLabel",
        ).pack(side="right", padx=(10, 5))
        scope_cb = ttk.Combobox(
            controls,
            textvariable=self.scope_var,
            values=["1º–5º", "1º"],
            width=10,
            state="readonly",
        )
        scope_cb.pack(side="right")
        scope_cb.bind("<<ComboboxSelected>>", self._refresh_number_rankings)

        ttk.Label(
            strong_tab,
            text=(
                "Ranking histórico já usado pelo gerador da Central: maior frequência primeiro; "
                "a ocorrência mais recente desempata. Isso é força histórica, não probabilidade de acerto."
            ),
            style="CardMuted.TLabel",
            wraplength=980,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        rankings = ttk.Frame(strong_tab)
        rankings.pack(fill="both", expand=True)
        for col in range(3):
            rankings.grid_columnconfigure(col, weight=1, uniform="rankcols")
        rankings.grid_rowconfigure(0, weight=1)

        specs = [
            ("Dezena", 4, "DEZENAS", 0),
            ("Centena", 10, "CENTENAS", 1),
            ("Milhar", 10, "MILHARES", 2),
        ]
        for kind, limit, title, col in specs:
            box = ttk.Frame(rankings, style="Card.TFrame", padding=8)
            box.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 4, 4 if col < 2 else 0))
            ttk.Label(box, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 5))

            table = ttk.Frame(box, style="Card.TFrame")
            table.pack(fill="both", expand=True)
            cols = ("rank", "numero", "ocorrencias", "ultima")
            tree = ttk.Treeview(table, columns=cols, show="headings", height=max(5, limit))
            tree.heading("rank", text="#")
            tree.heading("numero", text=kind)
            tree.heading("ocorrencias", text="Ocorr.")
            tree.heading("ultima", text="Última")
            tree.column("rank", width=34, anchor="center", stretch=False)
            tree.column("numero", width=76, anchor="center", stretch=False)
            tree.column("ocorrencias", width=68, anchor="center", stretch=False)
            tree.column("ultima", width=155, anchor="w")
            tree.tag_configure("leader", font=(UI_FONT_SEMIBOLD, UI_FONT_SIZES["table"]))

            y = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=y.set)
            tree.grid(row=0, column=0, sticky="nsew")
            y.grid(row=0, column=1, sticky="ns")
            table.rowconfigure(0, weight=1)
            table.columnconfigure(0, weight=1)
            self.number_trees[kind] = (tree, limit)

        self._refresh_number_rankings()

        ttk.Label(
            recent_tab,
            text="15 ocorrências mais recentes",
            style="Section.TLabel",
        ).pack(anchor="w", pady=(0, 6))
        frame = ttk.Frame(recent_tab)
        frame.pack(fill="both", expand=True)
        cols = ("data", "sorteio", "hora", "premio", "milhar", "centena", "dezena")
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        for c, label, width in [
            ("data", "Data", 95), ("sorteio", "Sorteio", 90), ("hora", "Hora", 70),
            ("premio", "Prêmio", 65), ("milhar", "Milhar", 80),
            ("centena", "Centena", 80), ("dezena", "Dezena", 70),
        ]:
            tree.heading(c, text=label)
            tree.column(c, width=width, anchor="center")
        y = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=y.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        for r in self.db.animal_recent_occurrences(self.grupo, limit=15):
            d = datetime.strptime(r["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            tree.insert("", "end", values=(
                d, r["sorteio"], r["hora"], f'{r["premio"]}º',
                r["milhar"], r["centena"], r["dezena"],
            ))

        footer = ttk.Frame(outer, padding=(0, 10, 0, 0))
        footer.pack(fill="x")
        ttk.Label(
            footer,
            text="Dica: na Home, basta clicar em qualquer bicho para abrir esta consulta.",
            style="CardMuted.TLabel",
        ).pack(side="left")
        ttk.Button(
            footer,
            text="Detalhes completos",
            command=lambda: AnimalDetailsDialog(self, self.db, self.grupo),
        ).pack(side="right", padx=(6, 0))
        ttk.Button(footer, text="Fechar", command=self.destroy).pack(side="right")

    @staticmethod
    def _format_ranking_last(value):
        if not value:
            return "—"
        parts = str(value).split("|")
        if len(parts) < 4:
            return str(value)
        raw_date, hora, sorteio, premio = parts[:4]
        try:
            shown_date = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d/%m")
        except Exception:
            shown_date = raw_date
        return f"{shown_date} • {sorteio} {hora} • {premio}º"

    def _refresh_number_rankings(self, _event=None):
        scope = self.scope_var.get() or "1º–5º"
        for kind, (tree, limit) in self.number_trees.items():
            for item in tree.get_children():
                tree.delete(item)
            ranking = self.db.number_rankings_for_group(
                self.grupo,
                kind=kind,
                scope=scope,
            )
            for pos, row in enumerate(ranking[:limit], start=1):
                tree.insert(
                    "",
                    "end",
                    tags=("leader",) if pos == 1 else (),
                    values=(
                        pos,
                        row["numero"],
                        row["ocorrencias"],
                        self._format_ranking_last(row.get("ultima")),
                    ),
                )
'''

tree = ast.parse(text)
node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AnimalQuickDetailsDialog')
lines = text.splitlines(keepends=True)
replacement = new_class.rstrip() + '\n\n\n'
text = ''.join(lines[:node.lineno-1]) + replacement + ''.join(lines[node.end_lineno:])

# ---------------------------------------------------------------------------
# Polimento visual observado no Windows real.
# ---------------------------------------------------------------------------
repls = [
    ('self.status = ttk.Label(status_bar, text="Pronto.", style="Sub.TLabel")',
     'self.status = ttk.Label(status_bar, text="", style="Sub.TLabel")'),
    ('text=f"v{APP_VERSION}  •  CENTRAL HISTÓRICA",',
     'text=f"v{APP_VERSION}",'),
    ('text="Grupo • Bicho • 4 dezenas",',
     'text="Clique no bicho → números fortes",'),
    ('grid.grid_rowconfigure(row, weight=1, uniform="animalrows", minsize=82)',
     'grid.grid_rowconfigure(row, weight=1, uniform="animalrows", minsize=88)'),
    ('card.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")',
     'card.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")'),
    ('image = self.animal_images_medium.get(info["grupo"]) if compact else self.animal_images_large.get(info["grupo"])',
     'image = self.animal_images_large.get(info["grupo"])'),
]
for old, new in repls:
    if text.count(old) < 1:
        raise AssertionError(f'trecho não encontrado: {old[:60]}')
    text = text.replace(old, new, 1)

# Remove legenda antiga redundante no rodapé do menu.
old_footer = '''        tk.Label(\n            self.sidebar,\n            text="Operação • Estudos • Histórico",\n            bg=self.colors["sidebar"],\n            fg=self.colors["muted"],\n            font=("Segoe UI", 8),\n        ).pack(side="bottom", pady=14)\n\n'''
if text.count(old_footer) != 1:
    raise AssertionError('rodapé antigo do menu não encontrado exatamente uma vez')
text = text.replace(old_footer, '', 1)

# Cartões dos bichos: sem moldura permanente; a borda azul aparece só no hover.
old_card = '''            highlightbackground=self.colors["border"],\n            highlightthickness=1,\n            bd=0,\n            cursor="hand2",\n'''
new_card = '''            highlightbackground=self.colors["border"],\n            highlightthickness=0,\n            bd=0,\n            cursor="hand2",\n'''
# _make_animal_card é a primeira ocorrência com cursor hand2 deste formato.
if text.count(old_card) < 1:
    raise AssertionError('moldura do cartão do bicho não encontrada')
text = text.replace(old_card, new_card, 1)

old_leave = 'card.configure(highlightbackground=self.colors["border"], bg=card_bg)'
new_leave = 'card.configure(highlightbackground=self.colors["border"], highlightthickness=0, bg=card_bg)'
if text.count(old_leave) != 1:
    raise AssertionError('leave do cartão inesperado')
text = text.replace(old_leave, new_leave, 1)

# Bordas internas da Home: mantém contêineres, reduz efeito "tabela dentro de tabela".
latest_row = '''                    highlightbackground=self.colors["border"],\n                    highlightthickness=1,\n                    bd=0,\n                    padx=7,\n                    pady=3,\n'''
latest_row_new = '''                    highlightbackground=self.colors["border"],\n                    highlightthickness=0,\n                    bd=0,\n                    padx=7,\n                    pady=3,\n'''
if text.count(latest_row) != 1:
    raise AssertionError('linha de último resultado inesperada')
text = text.replace(latest_row, latest_row_new, 1)

delay_box = '''                highlightbackground=self.colors["border"],\n                highlightthickness=1,\n                bd=0,\n                padx=6,\n                pady=5,\n'''
delay_box_new = '''                highlightbackground=self.colors["border"],\n                highlightthickness=0,\n                bd=0,\n                padx=6,\n                pady=5,\n'''
if text.count(delay_box) != 1:
    raise AssertionError('caixa de atraso inesperada')
text = text.replace(delay_box, delay_box_new, 1)

# Sobre: registra o refinamento sem alterar histórico anterior.
about_anchor = '            "Atualizações recentes:\\n"\n'
about_add = (
    '            "Atualizações recentes:\\n"\n'
    '            "• v0.46.1 — clique no bicho abre ranking de Dezenas, Centenas e Milhares fortes; Home recebe polimento de bordas, imagens e status.\\n"\n'
)
if text.count(about_anchor) != 1:
    raise AssertionError('âncora do Sobre inesperada')
text = text.replace(about_anchor, about_add, 1)

# Documentação consolidada.
revision = '''REVISÃO v0.46.1 — HOME + NÚMEROS FORTES POR BICHO\n- Clique em qualquer bicho da Home para consultar diretamente os números historicamente mais fortes daquele grupo.\n- A nova aba “Números fortes” mostra Dezenas, Centenas e Milhares lado a lado, com ranking, ocorrências e última aparição.\n- O usuário pode alternar entre histórico 1º–5º e somente 1º prêmio. A consulta reutiliza exatamente Database.number_rankings_for_group(), já usada pela geração histórica oficial; não cria uma fórmula paralela.\n- Regra do ranking preservada: frequência histórica; recência desempata; menor número é apenas desempate técnico final.\n- Home: imagens dos bichos ganham mais presença, cartões deixam de ter moldura permanente, bordas internas do último resultado/atrasos são suavizadas, versão lateral é encurtada e o status “Pronto.” deixa de ocupar espaço quando não há mensagem.\n- Menu lateral: removida a legenda inferior redundante “Operação • Estudos • Histórico”.\n- Nenhum cálculo de Meta, Reset, Puxada, Similaridade, Histórico Concentrado, 3+1 ou Decisão foi alterado.\n\n'''
if not doc.startswith('REVISÃO v0.46.1'):
    doc = revision + doc

# Sintaxe e proteção dos motores.
ast.parse(text)
after = {name: fn_dump(text, name) for name in protected}
changed = [name for name in protected if before[name] != after[name]]
assert not changed, f'Funções protegidas alteradas: {changed}'

assert 'APP_VERSION = "0.46.1"' in text
assert 'class AnimalQuickDetailsDialog' in text
assert 'NÚMEROS MAIS FORTES' in text
assert 'Clique no bicho → números fortes' in text
assert 'Operação • Estudos • Histórico' not in text

SRC.write_text(text, encoding='utf-8')
DOC.write_text(doc, encoding='utf-8')
print('Patch v0.46.1 aplicado; cérebro protegido permaneceu idêntico por AST.')
