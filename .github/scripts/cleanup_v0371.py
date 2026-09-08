from pathlib import Path
import ast
import re

SOURCE = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')

text = SOURCE.read_text(encoding='utf-8')
original = text
original_lines = len(text.splitlines())


def parse(src):
    return ast.parse(src)


def remove_spans(src, spans):
    lines = src.splitlines(keepends=True)
    for start, end, label in sorted(spans, key=lambda x: x[0], reverse=True):
        print(f'REMOVENDO {label}: linhas {start}-{end} ({end-start+1})')
        del lines[start-1:end]
    return ''.join(lines)


def top_class_spans(src, names):
    tree = parse(src)
    found = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in names:
            found[node.name] = (node.lineno, node.end_lineno, f'class {node.name}')
    missing = set(names) - set(found)
    if missing:
        raise SystemExit(f'Classes esperadas não encontradas: {sorted(missing)}')
    return list(found.values())

# 1) Classes antigas comprovadamente sem qualquer chamada atual.
# A auditoria da v0.37.0 mostrou que cada uma aparecia apenas na própria definição.
definite_orphans = {
    'GameGeneratorDialog',
    'MethodsLabDialog',
    'HistoricalPullsDialog',
    'StatisticsDialog',
}
text = remove_spans(text, top_class_spans(text, definite_orphans))

# 2) show_generator_page já redirecionava antes de todo o bloco legado.
# Substitui a função inteira pelo comportamento que já era efetivamente executado.
tree = parse(text)
app = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'App'), None)
if app is None:
    raise SystemExit('Classe App não encontrada')
show_gen = next((n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == 'show_generator_page'), None)
if show_gen is None:
    raise SystemExit('show_generator_page não encontrado')
replacement = (
    '    def show_generator_page(self):\n'
    '        """Compatibilidade: a antiga tela Gerador foi absorvida por Jogar."""\n'
    '        return self.show_play_page()\n\n'
)
lines = text.splitlines(keepends=True)
print(f'COMPACTANDO show_generator_page: linhas {show_gen.lineno}-{show_gen.end_lineno}')
lines[show_gen.lineno-1:show_gen.end_lineno] = [replacement]
text = ''.join(lines)

# 3) O conjunto generator_* era o controlador exclusivo da tela removida.
# Só é retirado se NÃO existir nenhuma referência a esses métodos fora do próprio conjunto.
tree = parse(text)
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'App')
gen_methods = [n for n in app.body if isinstance(n, ast.FunctionDef) and n.name.startswith('generator_')]
gen_names = {n.name for n in gen_methods}
if gen_methods:
    protected_ranges = [(n.lineno, n.end_lineno) for n in gen_methods]
    raw_lines = text.splitlines()
    external = []
    for name in sorted(gen_names):
        for i, line in enumerate(raw_lines, 1):
            if name not in line:
                continue
            if any(a <= i <= b for a, b in protected_ranges):
                continue
            external.append((name, i, line.strip()))
    if external:
        print('generator_* mantido: existem referências externas:')
        for item in external:
            print(' ', item)
    else:
        text = remove_spans(text, [(n.lineno, n.end_lineno, f'método {n.name}') for n in gen_methods])
        print(f'REMOVIDOS {len(gen_methods)} métodos generator_* sem referência externa.')

# 4) ManualGroupSelectorDialog só era usado pelos dois geradores antigos.
# Remove apenas se, após a limpeza acima, restar somente a definição.
tree = parse(text)
manual_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ManualGroupSelectorDialog'), None)
if manual_node is not None:
    refs = [m.start() for m in re.finditer(r'\bManualGroupSelectorDialog\b', text)]
    if len(refs) == 1:
        text = remove_spans(text, [(manual_node.lineno, manual_node.end_lineno, 'class ManualGroupSelectorDialog')])
    else:
        print(f'ManualGroupSelectorDialog mantido: {len(refs)} referências restantes.')

# 5) Versão e notas. Nenhuma regra de negócio é alterada.
if 'GP-H Central Histórica v0.37.0' not in text or 'APP_VERSION = "0.37.0"' not in text:
    raise SystemExit('Marcadores de versão 0.37.0 não encontrados')
text = text.replace('GP-H Central Histórica v0.37.0', 'GP-H Central Histórica v0.37.1', 1)
text = text.replace('APP_VERSION = "0.37.0"', 'APP_VERSION = "0.37.1"', 1)

release_anchor = '            "• v0.37.0 — Decisão Contextual cruza horário, recente, estabilidade, Walk-Forward opcional, dia, convergência e geral sem trocar o método oficial.\\n"\n'
release_new = (
    '            "• v0.37.1 — limpeza estrutural: remove Gerador legado inalcançável e diálogos órfãos, sem alterar métodos, apostas ou interface ativa.\\n"\n'
    + release_anchor
)
if release_anchor not in text:
    raise SystemExit('Âncora do histórico de versões não encontrada')
text = text.replace(release_anchor, release_new, 1)

# Validações de preservação das partes críticas.
required = [
    'def generate_centenas_3plus1(',
    'def centena_31_freeze_state(',
    'def show_play_page(',
    'def show_decision_page(',
    'def decision_contextual_evidence(',
    'def show_results(',
    'def show_statistics_page(',
    'def show_pulls_page(',
    'def show_methods_page(',
    'def _make_scrollable_page_body(',
    'def _install_smart_scroll_policy(',
]
for marker in required:
    if marker not in text:
        raise SystemExit(f'Marcador crítico desapareceu: {marker}')

# Deve continuar existindo apenas o redirecionamento de compatibilidade.
tree = parse(text)
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'App')
show_gen = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == 'show_generator_page')
if len(show_gen.body) != 2 or not isinstance(show_gen.body[-1], ast.Return):
    raise SystemExit('show_generator_page não ficou como redirecionamento mínimo')

for dead in definite_orphans:
    if re.search(rf'^class {re.escape(dead)}\b', text, re.M):
        raise SystemExit(f'Classe órfã ainda presente: {dead}')

# Não deve sobrar a antiga página visual do Gerador.
if 'self._set_active_nav("Gerador")' in text or 'self._page = "generator"' in text:
    raise SystemExit('Restos ativos da antiga página Gerador ainda encontrados')

SOURCE.write_text(text, encoding='utf-8')

# Documentação consolidada.
doc = DOC.read_text(encoding='utf-8')
revision = '''REVISÃO v0.37.1 — LIMPEZA ESTRUTURAL / SEM ALTERAÇÃO FUNCIONAL
- Removido o corpo inalcançável da antiga página Gerador; show_generator_page permanece apenas como redirecionamento de compatibilidade para Jogar.
- Removidas classes antigas comprovadamente órfãs, sem chamadas na aplicação atual: GameGeneratorDialog, MethodsLabDialog, HistoricalPullsDialog e StatisticsDialog.
- O controlador generator_* da antiga página é removido somente quando a validação comprova ausência total de referências externas; ManualGroupSelectorDialog também só é removido se ficar sem uso após essa limpeza.
- Jogar continua sendo o único ponto ativo da interface para geração e registro de apostas.
- Reset + 3+1, congelamento persistente, Decisão Contextual, Puxadas, Similaridade, histórico, bilhetes, financeiro, sincronização e atualização online permanecem sem alteração de lógica.
- Esta versão inicia a fase de organização/polimento; não adiciona método novo nem muda o visual ativo.

'''
if not doc.startswith('REVISÃO v0.37.0'):
    raise SystemExit('Topo inesperado da DOCUMENTACAO_GP-H.txt')
DOC.write_text(revision + doc, encoding='utf-8')

new_lines = len(text.splitlines())
print(f'LINHAS ANTES: {original_lines}')
print(f'LINHAS DEPOIS: {new_lines}')
print(f'REDUÇÃO: {original_lines-new_lines}')
print('v0.37.1 estrutural preparada com sucesso.')
