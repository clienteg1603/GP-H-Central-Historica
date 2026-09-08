from pathlib import Path
import ast
import re

SOURCE = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')

text = SOURCE.read_text(encoding='utf-8')
original = text

if 'APP_VERSION = "0.37.1"' not in text:
    raise SystemExit('A limpeza visual só pode partir exatamente da v0.37.1')

CRITICAL_FUNCTIONS = {
    'generate_centenas_3plus1',
    'centena_31_freeze_state',
    'decision_contextual_evidence',
    'method_reset_coverage_v1',
    'play_generate',
}

def critical_ast(src):
    tree = ast.parse(src)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in CRITICAL_FUNCTIONS:
            found[node.name] = ast.dump(node, include_attributes=False)
    missing = CRITICAL_FUNCTIONS - set(found)
    if missing:
        raise SystemExit(f'Funções críticas não encontradas: {sorted(missing)}')
    return found

critical_before = critical_ast(text)

# ------------------------------------------------------------------
# 1) Fundação visual permanente
# ------------------------------------------------------------------
anchor = 'THEME_PALETTES = {'
if 'UI_FONT_SIZES = {' not in text:
    constants = '''# ------------------------------------------------------------------
# PADRÃO PERMANENTE DE INTERFACE — tipografia, espaçamento e densidade
# ------------------------------------------------------------------
UI_FONT_FAMILY = "Segoe UI"
UI_FONT_SEMIBOLD = "Segoe UI Semibold"
UI_FONT_MONO = "Consolas"
UI_TEXT_ON_ACCENT = "#FFFFFF"
UI_FONT_SIZES = {
    "page": 17,
    "hero": 18,
    "kpi": 15,
    "section": 11,
    "body": 9,
    "secondary": 8,
    "table": 9,
    "table_heading": 9,
}
UI_SPACING = {
    "micro": 4,
    "small": 8,
    "normal": 12,
    "large": 16,
    "section": 24,
}
UI_CARD_PADDING = UI_SPACING["normal"]
UI_CARD_PADDING_COMPACT = UI_SPACING["small"]
UI_TABLE_ROWHEIGHT = 28

'''
    if anchor not in text:
        raise SystemExit('Âncora THEME_PALETTES não encontrada')
    text = text.replace(anchor, constants + anchor, 1)

# ------------------------------------------------------------------
# 2) Um único núcleo de estilos globais
# ------------------------------------------------------------------
tree = ast.parse(text)
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'App')
style_fn = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == '_build_style')

new_style = '''    def _build_style(self):
        """Aplica o padrão visual global da Central.

        Regra permanente: novas telas devem preferir estes estilos e constantes
        em vez de criar tamanhos, cores e densidades isoladas.
        """
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        c = self.colors
        bg, card, card2 = c["bg"], c["card"], c["card2"]
        text, muted, border = c["text"], c["muted"], c["border"]
        accent, accent_hover = c["accent"], c["accent_hover"]
        body = UI_FONT_SIZES["body"]
        secondary = UI_FONT_SIZES["secondary"]
        section = UI_FONT_SIZES["section"]

        # Superfícies
        style.configure("TFrame", background=bg)
        style.configure("Card.TFrame", background=card)
        style.configure("Card2.TFrame", background=card2)
        style.configure("Toolbar.TFrame", background=card2)

        # Tipografia semântica
        style.configure("TLabel", background=bg, foreground=text, font=(UI_FONT_FAMILY, body))
        style.configure("Title.TLabel", background=bg, foreground=text, font=(UI_FONT_SEMIBOLD, UI_FONT_SIZES["page"]))
        style.configure("Sub.TLabel", background=bg, foreground=muted, font=(UI_FONT_FAMILY, body))
        style.configure("Muted.TLabel", background=bg, foreground=muted, font=(UI_FONT_FAMILY, secondary))
        style.configure("Card.TLabel", background=card, foreground=text, font=(UI_FONT_FAMILY, body))
        style.configure("CardMuted.TLabel", background=card, foreground=muted, font=(UI_FONT_FAMILY, secondary))
        style.configure("Card2.TLabel", background=card2, foreground=text, font=(UI_FONT_FAMILY, body))
        style.configure("Card2Muted.TLabel", background=card2, foreground=muted, font=(UI_FONT_FAMILY, secondary))
        style.configure("Section.TLabel", background=card, foreground=text, font=(UI_FONT_SEMIBOLD, section))
        style.configure("CardTitle.TLabel", background=card, foreground=text, font=(UI_FONT_SEMIBOLD, section))
        style.configure("Kpi.TLabel", background=card, foreground=text, font=(UI_FONT_SEMIBOLD, UI_FONT_SIZES["kpi"]))
        style.configure("KpiCaption.TLabel", background=card, foreground=muted, font=(UI_FONT_FAMILY, secondary))
        style.configure("Recommendation.TLabel", background=card, foreground=text, font=(UI_FONT_SEMIBOLD, section))
        style.configure("Success.TLabel", background=card, foreground=c["success"], font=(UI_FONT_SEMIBOLD, 10))
        style.configure("Danger.TLabel", background=card, foreground=c["danger"], font=(UI_FONT_SEMIBOLD, 10))
        style.configure("Warning.TLabel", background=card, foreground=c["warning"], font=(UI_FONT_SEMIBOLD, 10))

        # Botões
        style.configure(
            "TButton", font=(UI_FONT_SEMIBOLD, body), padding=(UI_SPACING["normal"], 6),
            background=card2, foreground=text, bordercolor=border,
            focusthickness=1, focuscolor=accent, relief="flat",
        )
        style.map(
            "TButton",
            background=[("active", c["hover"]), ("pressed", c["band"])],
            foreground=[("disabled", muted), ("!disabled", text)],
        )
        style.configure(
            "Accent.TButton", font=(UI_FONT_SEMIBOLD, body), padding=(UI_SPACING["normal"], 7),
            background=accent, foreground=UI_TEXT_ON_ACCENT, bordercolor=accent, relief="flat",
        )
        style.map(
            "Accent.TButton",
            background=[("active", accent_hover), ("pressed", accent), ("!disabled", accent)],
            foreground=[("!disabled", UI_TEXT_ON_ACCENT)],
        )
        style.configure(
            "Quiet.TButton", font=(UI_FONT_FAMILY, body), padding=(UI_SPACING["small"], 5),
            background=card2, foreground=muted, bordercolor=border,
        )
        style.map("Quiet.TButton", background=[("active", c["hover"])])

        # Abas internas
        style.configure(
            "Subnav.TButton", font=(UI_FONT_SEMIBOLD, body), padding=(UI_SPACING["normal"], 6),
            background=card2, foreground=text, bordercolor=border, relief="flat",
        )
        style.map(
            "Subnav.TButton",
            background=[("active", c["hover"]), ("pressed", c["band"])],
            foreground=[("!disabled", text)],
        )
        style.configure(
            "SubnavActive.TButton", font=(UI_FONT_SEMIBOLD, body), padding=(UI_SPACING["normal"], 6),
            background=c["selection"], foreground=text, bordercolor=accent, relief="flat",
        )
        style.map(
            "SubnavActive.TButton",
            background=[("active", c["selection"]), ("pressed", c["selection"]), ("!disabled", c["selection"])],
            foreground=[("!disabled", text)],
        )

        # Tabelas: leitura confortável e padrão único em toda a Central.
        style.configure(
            "Treeview", font=(UI_FONT_FAMILY, UI_FONT_SIZES["table"]), rowheight=UI_TABLE_ROWHEIGHT,
            background=c["tree"], fieldbackground=c["tree"], foreground=text,
            bordercolor=border, lightcolor=border, darkcolor=border,
        )
        style.map(
            "Treeview",
            background=[("selected", c["selection"])],
            foreground=[("selected", text)],
        )
        style.configure(
            "Treeview.Heading", font=(UI_FONT_SEMIBOLD, UI_FONT_SIZES["table_heading"]),
            background=card2, foreground=text, relief="flat",
        )
        style.map("Treeview.Heading", background=[("active", c["hover"])])

        # Campos e controles
        style.configure(
            "TEntry", font=(UI_FONT_FAMILY, body), padding=5,
            fieldbackground=c["entry"], foreground=text, insertcolor=text, bordercolor=border,
        )
        style.configure(
            "TCombobox", font=(UI_FONT_FAMILY, body), padding=4,
            fieldbackground=c["entry"], background=card2, foreground=text,
            arrowcolor=muted, bordercolor=border,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", c["entry"])],
            foreground=[("readonly", text)],
            selectbackground=[("readonly", c["selection"])],
        )
        style.configure(
            "TSpinbox", font=(UI_FONT_FAMILY, body), padding=4,
            fieldbackground=c["entry"], foreground=text, arrowcolor=muted, bordercolor=border,
        )
        style.configure("TCheckbutton", font=(UI_FONT_FAMILY, body), background=bg, foreground=text)
        style.configure(
            "TScrollbar", background=card2, troughcolor=bg, bordercolor=bg,
            arrowcolor=muted, darkcolor=card2, lightcolor=card2,
        )
        style.map("TScrollbar", background=[("active", c["hover"]), ("pressed", accent)])

'''
lines = text.splitlines(keepends=True)
lines[style_fn.lineno - 1:style_fn.end_lineno] = [new_style]
text = ''.join(lines)

# ------------------------------------------------------------------
# 3) Legibilidade mínima: nenhum texto explícito abaixo de 8 pt.
# ------------------------------------------------------------------
# Literais simples: qualquer família de fonte explícita com 6/7 pt sobe para 8.
def bump_small_font(match):
    prefix, size, suffix = match.groups()
    return prefix + str(max(8, int(size))) + suffix

text = re.sub(
    r'(font=\((?:"[^"]+"|\'[^\']+\'),\s*)([0-7])(\s*[,\)])',
    bump_small_font,
    text,
)
# Casos condicionais usados nos cartões compactos.
text = re.sub(
    r'(font=\((?:"[^"]+"|\'[^\']+\'),\s*)([0-7])(\s+if\s+)',
    bump_small_font,
    text,
)

# ------------------------------------------------------------------
# 4) Densidade base da aplicação usa a escala global.
# ------------------------------------------------------------------
text = text.replace(
    'self.content = ttk.Frame(right, padding=(14, 11))',
    'self.content = ttk.Frame(right, padding=(UI_SPACING["large"], UI_SPACING["normal"]))',
    1,
)
text = text.replace(
    'status_bar = ttk.Frame(right, padding=(18, 4, 18, 8))',
    'status_bar = ttk.Frame(right, padding=(UI_SPACING["large"], UI_SPACING["micro"], UI_SPACING["large"], UI_SPACING["small"]))',
    1,
)

# ------------------------------------------------------------------
# 5) Versão e histórico visível
# ------------------------------------------------------------------
text = text.replace('GP-H Central Histórica v0.37.1', 'GP-H Central Histórica v0.37.2', 1)
text = text.replace('APP_VERSION = "0.37.1"', 'APP_VERSION = "0.37.2"', 1)
about_anchor = '            "• v0.37.1 — limpeza estrutural: remove Gerador legado inalcançável e diálogos órfãos, sem alterar métodos, apostas ou interface ativa.\\n"\n'
about_new = (
    '            "• v0.37.2 — padrão global de interface: tipografia, fonte mínima, tabelas, controles, espaçamento e cores semânticas centralizados.\\n"\n'
    + about_anchor
)
if about_anchor not in text:
    raise SystemExit('Âncora do histórico Sobre não encontrada')
text = text.replace(about_anchor, about_new, 1)

# ------------------------------------------------------------------
# 6) Validações
# ------------------------------------------------------------------
ast.parse(text)
critical_after = critical_ast(text)
for name in CRITICAL_FUNCTIONS:
    if critical_before[name] != critical_after[name]:
        raise SystemExit(f'LÓGICA CRÍTICA ALTERADA INDEVIDAMENTE: {name}')

if 'APP_VERSION = "0.37.2"' not in text:
    raise SystemExit('Versão 0.37.2 não aplicada')
for marker in (
    'UI_FONT_SIZES = {',
    'UI_SPACING = {',
    'UI_TABLE_ROWHEIGHT = 28',
    '"Treeview", font=(UI_FONT_FAMILY, UI_FONT_SIZES["table"]), rowheight=UI_TABLE_ROWHEIGHT',
    '"CardTitle.TLabel"',
    '"Warning.TLabel"',
):
    if marker not in text:
        raise SystemExit(f'Padrão visual ausente: {marker}')

# AST: nenhum tamanho de fonte explícito abaixo de 8 em qualquer widget.
tree = ast.parse(text)
small_fonts = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    for kw in node.keywords:
        if kw.arg != 'font' or not isinstance(kw.value, ast.Tuple):
            continue
        ints = [n.value for n in ast.walk(kw.value) if isinstance(n, ast.Constant) and isinstance(n.value, int)]
        if any(v < 8 for v in ints):
            small_fonts.append((getattr(node, 'lineno', '?'), ints))
if small_fonts:
    raise SystemExit(f'Fontes abaixo de 8 ainda encontradas: {small_fonts[:20]}')

SOURCE.write_text(text, encoding='utf-8')

# Documentação consolidada.
doc = DOC.read_text(encoding='utf-8')
revision = '''REVISÃO v0.37.2 — PADRÃO GLOBAL DE INTERFACE / ETAPA 2
- Criada uma fundação visual permanente com constantes centrais para tipografia, espaçamento, padding de cartões, altura de tabela e texto sobre cor de destaque.
- Escala tipográfica oficial: página 17, hero 18, KPI 15, seção/título de cartão 11, texto normal 9, texto secundário 8, tabela 9 e cabeçalho de tabela 9 Semibold.
- Regra permanente: nenhum texto explícito da interface deve usar fonte abaixo de 8 pt; ocorrências antigas de 6/7 pt foram elevadas para 8 pt.
- Treeviews passam a usar fonte 9, cabeçalho 9 Semibold e altura de linha 28 px para leitura mais confortável.
- Entry, Combobox, Spinbox e Checkbutton passam a obedecer a tipografia global de 9 pt; botões e abas internas também usam o núcleo central de estilos.
- Oficializados estilos que já apareciam isoladamente na interface: Card2.TFrame, CardTitle.TLabel e Muted.TLabel; adicionado Warning.TLabel para o papel semântico de aviso.
- As cores de sucesso, perigo, aviso, destaque, texto e texto secundário continuam vindo exclusivamente da paleta ativa; a atualização não muda as cinco paletas disponíveis.
- Escala oficial de espaçamento para telas atuais e futuras: 4 / 8 / 12 / 16 / 24 px; o conteúdo principal passa a usar 16×12 como respiro-base.
- Esta etapa não reorganiza telas e não unifica ainda os dois motores de rolagem; isso pertence às etapas seguintes.
- Reset + 3+1, congelamento persistente, Reset Cobertura, Decisão Contextual e geração em Jogar são validados por AST antes/depois e permanecem sem alteração lógica.

PADRÃO PERMANENTE DE INTERFACE — TIPOGRAFIA, ESPAÇAMENTO E CORES
- Novas telas devem reutilizar os estilos globais e as constantes UI_FONT_SIZES / UI_SPACING; evitar criar tamanhos, paddings e cores isolados sem necessidade real.
- Fonte mínima visível: 8 pt. Texto normal: 9 pt. Tabelas: 9 pt com linhas de 28 px.
- Títulos de página usam 17 pt; títulos de cartão/seção 11 pt; KPIs 15 pt; hero/destaque principal pode usar 18 pt.
- Espaçamento preferencial: 4 px micro, 8 px pequeno, 12 px padrão, 16 px grande e 24 px para separação forte de seções.
- Cores funcionais devem vir dos papéis da paleta ativa: accent, success, danger, warning, text e muted. Evitar hexadecimais novos espalhados pelas telas.
- Exceções visuais devem ser justificadas pelo componente e não virar um novo padrão paralelo.

'''
if not doc.startswith('REVISÃO v0.37.1'):
    raise SystemExit('Topo inesperado da documentação')
DOC.write_text(revision + doc, encoding='utf-8')

print('v0.37.2 preparada com sucesso')
print('Linhas:', len(text.splitlines()))
print('Funções críticas preservadas:', ', '.join(sorted(CRITICAL_FUNCTIONS)))
