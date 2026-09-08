from pathlib import Path
import ast, re

SOURCE=Path('source/gph_central.py')
DOC=Path('source/DOCUMENTACAO_GP-H.txt')
text=SOURCE.read_text(encoding='utf-8')

if 'APP_VERSION = "0.37.3"' not in text:
    raise SystemExit('v0.38.0 deve partir exatamente da v0.37.3')

# ------------------------------------------------------------------
# Travas: banco e motores críticos não podem mudar nesta etapa visual.
# ------------------------------------------------------------------
def class_dump(src, class_name):
    tree=ast.parse(src)
    node=next((n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name),None)
    if node is None:
        raise SystemExit(f'Classe {class_name} não encontrada')
    return ast.dump(node, include_attributes=False)

CRITICAL={
    'generate_centenas_3plus1','centena_31_freeze_state','decision_contextual_evidence',
    'method_reset_coverage_v1','play_generate','freeze_generated_game',
    'start_update_search','program_update_check','account_sync_now'
}
def critical_ast(src):
    tree=ast.parse(src); out={}
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in CRITICAL:
            out[n.name]=ast.dump(n,include_attributes=False)
    missing=CRITICAL-set(out)
    if missing:
        raise SystemExit(f'Funções críticas ausentes: {sorted(missing)}')
    return out

database_before=class_dump(text,'Database')
critical_before=critical_ast(text)

# ------------------------------------------------------------------
# 1) Navegação e propósito das telas.
# ------------------------------------------------------------------
text=text.replace('"Base / Configurações"','"Configurações"')
text=text.replace('Base / Configurações → Conta / Perfil','Configurações → Conta e Sync')

replacements={
    '"Central de Decisão",\n            "Visão da rodada, convergência, desempenho prospectivo e Laboratório Sombra em uma única tela. O índice não é probabilidade de prêmio.",':
    '"Decisão da rodada",\n            "Qual leitura tem melhor evidência para a próxima rodada. O índice não é probabilidade de prêmio.",',

    '"Resultados",\n            "Atualizações, jogos congelados e desempenho prospectivo.",':
    '"Resultados",\n            "Atualize os resultados, acompanhe jogos congelados e audite o desempenho prospectivo.",',

    '"Pesquisa",\n            "Bicho, Grupo, Dezena, Centena e Milhar com filtros inteligentes.",':
    '"Pesquisa",\n            "Consulta direta da base por Bicho, Grupo, Dezena, Centena ou Milhar.",',

    '"Estatísticas",\n            "Frequência histórica dos 25 bichos no recorte escolhido.",':
    '"Estatísticas",\n            "Frequência e distribuição histórica dos 25 bichos no recorte escolhido.",',

    '"Puxadas",\n            "Quando o bicho-base aparece, o que costuma vir na extração seguinte?",':
    '"Puxadas",\n            "Relações históricas: dado um bicho-base, o que apareceu na extração seguinte.",',

    '"Métodos",\n            "Escolha o resultado-base, a quantidade e gere os bichos.",':
    '"Métodos",\n            "Área técnica para executar e comparar métodos sobre um resultado-base.",',

    '"Configurações",\n            "Saúde, persistência, backup, importação e revisão da base.",':
    '"Configurações",\n            "Conta, aparência, atualizações e manutenção da base de dados.",',
}
for old,new in replacements.items():
    if old not in text:
        raise SystemExit('Texto de página esperado não encontrado: '+old.splitlines()[0])
    text=text.replace(old,new,1)

# Decisão: títulos deixam mais claro o papel da tela sem alterar dados.
for old,new in (
    ('text="Por que esse índice?"','text="Componentes do índice"'),
    ('text="O que cada método está dizendo"','text="Leituras da rodada"'),
    ('text="Por que estes 5?"','text="Convergência dos 5 bichos"'),
    ('text="Comparação prospectiva dos métodos"','text="Desempenho prospectivo"'),
):
    if old not in text:
        raise SystemExit('Título da Decisão não encontrado: '+old)
    text=text.replace(old,new,1)

# ------------------------------------------------------------------
# 2) Atualização de resultados x atualização do programa: nomes inequívocos.
# ------------------------------------------------------------------
# Home atualiza resultados, não o programa.
text=text.replace('text="Buscar atualização",\n            command=self.start_update_search,',
                  'text="Atualizar resultados",\n            command=self.start_update_search,',1)
# Tela Resultados.
text=text.replace('text="Buscar atualizações", style="Accent.TButton", command=self.start_update_search',
                  'text="Atualizar resultados", style="Accent.TButton", command=self.start_update_search',1)
# Configurações atualiza o programa.
text=text.replace('text="BUSCAR ATUALIZAÇÃO", style="Accent.TButton",',
                  'text="BUSCAR NOVA VERSÃO", style="Accent.TButton",',1)

# ------------------------------------------------------------------
# 3) Configurações: navegação interna fixa e nomes mais humanos.
# ------------------------------------------------------------------
anchor='''        self._page_title(\n            "Configurações",\n            "Conta, aparência, atualizações e manutenção da base de dados.",\n        )\n\n        base_body = self._make_scrollable_page_body(self.content, "base")\n'''
insert='''        self._page_title(\n            "Configurações",\n            "Conta, aparência, atualizações e manutenção da base de dados.",\n        )\n\n        config_nav = ttk.Frame(self.content)\n        config_nav.pack(fill="x", pady=(0, UI_SPACING["small"]))\n        for idx, (label, key) in enumerate((\n            ("Conta e Sync", "account"),\n            ("Aparência", "appearance"),\n            ("Atualizações", "updates"),\n            ("Base de dados", "data"),\n        )):\n            ttk.Button(\n                config_nav, text=label, style="Subnav.TButton",\n                command=lambda k=key: self._base_scroll_to(k),\n            ).pack(side="left", padx=(0 if idx == 0 else UI_SPACING["micro"], 0))\n\n        base_body = self._make_scrollable_page_body(self.content, "base")\n'''
if anchor not in text:
    raise SystemExit('Âncora do topo de Configurações não encontrada')
text=text.replace(anchor,insert,1)

# Helper da navegação interna.
show_anchor='    def show_base_config(self):\n'
helper='''    def _base_scroll_to(self, key):\n        """Leva a navegação interna de Configurações ao bloco correspondente."""\n        try:\n            canvas = getattr(self, "_smart_scroll_canvases", {}).get("base")\n            widget = getattr(self, "_base_section_widgets", {}).get(key)\n            if canvas is None or widget is None:\n                return\n            self.update_idletasks()\n            bbox = canvas.bbox("all")\n            if not bbox:\n                return\n            content_h = max(1, int(bbox[3] - bbox[1]))\n            viewport_h = max(1, int(canvas.winfo_height()))\n            max_scroll = max(1, content_h - viewport_h)\n            y = max(0, int(widget.winfo_y()) - UI_SPACING["small"])\n            canvas.yview_moveto(min(1.0, max(0.0, y / max_scroll)))\n        except Exception:\n            return\n\n'''
if show_anchor not in text:
    raise SystemExit('show_base_config não encontrado')
text=text.replace(show_anchor,helper+show_anchor,1)

# Termos de Configurações.
text=text.replace('text="Conta / Perfil", style="Section.TLabel"',
                  'text="Conta e Sync", style="Section.TLabel"',1)
text=text.replace('text="Base compartilhada",','text="Local da base de dados",',1)
text=text.replace('text="Diagnóstico / Pré-EXE", style="Section.TLabel"',
                  'text="Diagnóstico da instalação", style="Section.TLabel"',1)

# ------------------------------------------------------------------
# 4) Redundâncias: guia sai de Configurações e vai para Métodos.
# ------------------------------------------------------------------
guide_pat=re.compile(r'''\n        guide_box = ttk\.Frame\(base_body, style="Card\.TFrame", padding=10\).*?\n        health = self\.db\.base_health\(\)''', re.S)
m=guide_pat.search(text)
if not m:
    raise SystemExit('Bloco redundante do guia em Configurações não encontrado')
text=text[:m.start()]+'\n        health = self.db.base_health()'+text[m.end():]

# Métodos: botão de guia no local correto.
method_anchor='''        ttk.Checkbutton(\n            head,\n            text="Escolher outro",\n            variable=self.method_choose_old,\n            command=self.methods_toggle_base,\n        ).pack(side="right", padx=(0, 7))\n'''
method_insert=method_anchor+'''\n        ttk.Button(\n            head,\n            text="Guia dos métodos",\n            style="Quiet.TButton",\n            command=self._show_method_guide,\n        ).pack(side="right", padx=(0, 7))\n'''
if method_anchor not in text:
    raise SystemExit('Cabeçalho de Métodos não encontrado')
text=text.replace(method_anchor,method_insert,1)
text=text.replace('text="Último",\n            command=self.methods_load_latest,',
                  'text="Usar último",\n            command=self.methods_load_latest,',1)

# Cotações já ficam em Jogar; não duplicar a mesma entrada em Configurações.
old='            ("Tabela de prêmios", lambda: PayoutConfigDialog(self, self.db)),\n'
if old not in text:
    raise SystemExit('Entrada duplicada Tabela de prêmios não encontrada')
text=text.replace(old,'',1)

# Ferramentas da base ganham um título próprio.
action_anchor='''        action_specs = [\n            ("Revisar base", self.show_audit),'''
action_insert='''        ttk.Label(\n            actions, text="Ferramentas da base", style="Section.TLabel"\n        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))\n\n        action_specs = [\n            ("Revisar base", self.show_audit),'''
if action_anchor not in text:
    raise SystemExit('Bloco de ferramentas da base não encontrado')
text=text.replace(action_anchor,action_insert,1)
text=text.replace('            row, col = divmod(idx, 3)\n            btn = ttk.Button(actions, text=text, command=command)',
                  '            row, col = divmod(idx, 3)\n            row += 1\n            btn = ttk.Button(actions, text=text, command=command)',1)

# Mapa dos destinos da navegação interna, montado depois que os widgets existem.
end_anchor='''        ttk.Label(\n            base_body,\n            text=(\n                "“Possível lacuna” é um horário esperado pelo calendário "'''
if end_anchor not in text:
    raise SystemExit('Nota final da base não encontrada')
text=text.replace(end_anchor,''''        self._base_section_widgets = {\n            "account": account_box,\n            "appearance": visual_box,\n            "updates": update_box,\n            "data": health_box,\n        }\n\n'''+end_anchor,1)

# ------------------------------------------------------------------
# 5) Pequeno polimento da Home: usa a tipografia global do título.
# ------------------------------------------------------------------
text=text.replace('''            style="Title.TLabel",\n            font=("Segoe UI Semibold", 16),\n''','''            style="Title.TLabel",\n''',1)

# ------------------------------------------------------------------
# 6) Versão e documentação.
# ------------------------------------------------------------------
text=text.replace('GP-H Central Histórica v0.37.3','GP-H Central Histórica v0.38.0',1)
text=text.replace('APP_VERSION = "0.37.3"','APP_VERSION = "0.38.0"',1)

# Histórico do Sobre: insere v0.38.0 antes da v0.37.3, sem depender da frase inteira.
needle='            "• v0.37.3 —'
pos=text.find(needle)
if pos < 0:
    raise SystemExit('Linha v0.37.3 do Sobre não encontrada')
line_end=text.find('\\n"\n',pos)
if line_end < 0:
    raise SystemExit('Fim da linha v0.37.3 do Sobre não encontrado')
text=text[:pos]+'            "• v0.38.0 — polimento geral: papéis das telas mais claros, Configurações simplificadas, redundâncias removidas e ações ambíguas renomeadas.\\n"\n'+text[pos:]

# ------------------------------------------------------------------
# 7) Validações pós-patch.
# ------------------------------------------------------------------
ast.parse(text)
if class_dump(text,'Database') != database_before:
    raise SystemExit('A classe Database mudou numa atualização exclusivamente visual')
critical_after=critical_ast(text)
for name in CRITICAL:
    if critical_before[name] != critical_after[name]:
        raise SystemExit(f'LÓGICA CRÍTICA ALTERADA: {name}')

assert 'APP_VERSION = "0.38.0"' in text
assert '"Base / Configurações"' not in text
assert '"Configurações", self.show_base_config' in text
assert 'text="BUSCAR NOVA VERSÃO"' in text
assert text.count('text="Atualizar resultados"') >= 2
assert 'text="Guia dos métodos"' in text
assert 'text="Como funcionam os métodos"' not in text[text.find('def show_base_config'):text.find('def _auto_decision_cycle')]
assert '("Tabela de prêmios", lambda: PayoutConfigDialog' not in text
assert 'def _base_scroll_to(self, key):' in text
assert '"account": account_box' in text and '"data": health_box' in text

SOURCE.write_text(text,encoding='utf-8')

doc=DOC.read_text(encoding='utf-8')
revision='''REVISÃO v0.38.0 — POLIMENTO GERAL DAS TELAS / ETAPA 4\n- A navegação lateral passa a usar apenas “Configurações”; o nome antigo “Base / Configurações” foi eliminado da interface.\n- Configurações ganha navegação interna fixa para Conta e Sync, Aparência, Atualizações e Base de dados, usando a rolagem inteligente já padronizada.\n- O guia completo dos métodos sai de Configurações e passa para a própria tela Métodos.\n- “Tabela de prêmios” sai de Configurações porque a mesma função já está disponível como Cotações em Jogar.\n- Atualização de resultados e atualização do programa passam a ter nomes inequívocos: “Atualizar resultados” e “Buscar nova versão”.\n- Decisão, Métodos, Puxadas, Pesquisa, Estatísticas e Resultados recebem títulos/subtítulos mais claros para explicitar a função de cada tela sem fundi-las.\n- Configurações troca termos técnicos antigos por nomes de uso real: Conta e Sync, Local da base de dados e Diagnóstico da instalação.\n- A Home passa a usar a tipografia global de título definida na Etapa 2.\n- Nenhum método, fórmula, banco, congelamento, seletor, geração, sincronização ou atualizador teve lógica alterada; a classe Database e funções críticas foram comparadas via AST antes/depois.\n\n'''
if revision not in doc:
    doc=revision+doc
DOC.write_text(doc,encoding='utf-8')

print('v0.38.0 preparada com sucesso')
print('linhas:',len(text.splitlines()))
print('Database preservada: SIM')
print('funções críticas preservadas:',', '.join(sorted(CRITICAL)))
