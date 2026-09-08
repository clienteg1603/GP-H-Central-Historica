from pathlib import Path
import ast
import re

SOURCE = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')
text = SOURCE.read_text(encoding='utf-8')
original_lines = len(text.splitlines())

if 'APP_VERSION = "0.37.1"' not in text:
    raise SystemExit('A fase B exige source já em v0.37.1')


def parse(src):
    return ast.parse(src)


def remove_spans(src, spans):
    lines = src.splitlines(keepends=True)
    for start, end, label in sorted(spans, key=lambda x: x[0], reverse=True):
        print(f'REMOVENDO {label}: linhas {start}-{end} ({end-start+1})')
        del lines[start-1:end]
    return ''.join(lines)

# O primeiro passe provou que apenas generator_format_31_event é usado fora
# do controlador legado: a tela Jogar reutiliza esse pequeno formatador.
# Agora fazemos análise de alcançabilidade: raízes são métodos generator_*
# chamados fora do próprio conjunto; preservamos também qualquer helper
# generator_* chamado transitivamente por essas raízes.
tree = parse(text)
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'App')
gen_methods = [n for n in app.body if isinstance(n, ast.FunctionDef) and n.name.startswith('generator_')]
gen_by_name = {n.name: n for n in gen_methods}
gen_names = set(gen_by_name)
ranges = {name: (node.lineno, node.end_lineno) for name, node in gen_by_name.items()}
raw_lines = text.splitlines()

roots = set()
for name, (start, end) in ranges.items():
    for i, line in enumerate(raw_lines, 1):
        if name not in line:
            continue
        if any(a <= i <= b for a, b in ranges.values()):
            continue
        roots.add(name)
        print(f'RAIZ EXTERNA {name}: linha {i}: {line.strip()}')

# Grafo interno self.generator_x(...)
call_graph = {name: set() for name in gen_names}
for name, node in gen_by_name.items():
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr in gen_names:
            call_graph[name].add(sub.attr)

keep = set(roots)
stack = list(roots)
while stack:
    cur = stack.pop()
    for dep in call_graph.get(cur, ()):
        if dep not in keep:
            keep.add(dep)
            stack.append(dep)

remove = [node for name, node in gen_by_name.items() if name not in keep]
print('generator_* preservados:', sorted(keep))
print('generator_* removíveis:', sorted(n.name for n in remove))
if remove:
    text = remove_spans(text, [(n.lineno, n.end_lineno, f'método {n.name}') for n in remove])

# Após retirar o controlador legado, o seletor de grupos antigo deve ficar órfão.
tree = parse(text)
manual = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ManualGroupSelectorDialog'), None)
if manual is not None:
    refs = list(re.finditer(r'\bManualGroupSelectorDialog\b', text))
    print('ManualGroupSelectorDialog referências:', len(refs))
    if len(refs) == 1:
        text = remove_spans(text, [(manual.lineno, manual.end_lineno, 'class ManualGroupSelectorDialog')])
    else:
        raise SystemExit('ManualGroupSelectorDialog ainda tem uso inesperado; limpeza interrompida')

# Invariantes: nenhum controlador antigo deve restar, exceto helpers realmente compartilhados.
tree = parse(text)
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'App')
remaining_gen = sorted(n.name for n in app.body if isinstance(n, ast.FunctionDef) and n.name.startswith('generator_'))
if remaining_gen != sorted(keep):
    raise SystemExit(f'Conjunto generator_* inesperado: {remaining_gen} vs {sorted(keep)}')

# A tela Jogar depende do formatador compartilhado; ele precisa permanecer.
if 'generator_format_31_event' not in keep:
    raise SystemExit('Formatador 3+1 compartilhado não foi reconhecido como raiz ativa')
if text.count('self.generator_format_31_event(') < 2:
    raise SystemExit('Referências ativas do painel 3+1 em Jogar não foram preservadas')

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
    'def show_generator_page(',
]
for marker in required:
    if marker not in text:
        raise SystemExit(f'Marcador crítico desapareceu: {marker}')

for dead in ('GameGeneratorDialog','MethodsLabDialog','HistoricalPullsDialog','StatisticsDialog','ManualGroupSelectorDialog'):
    if re.search(rf'^class {dead}\b', text, re.M):
        raise SystemExit(f'Estrutura órfã ainda presente: {dead}')

if 'self._set_active_nav("Gerador")' in text or 'self._page = "generator"' in text:
    raise SystemExit('Restos da página visual Gerador ainda presentes')

# show_generator_page continua sendo só compatibilidade.
tree = parse(text)
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'App')
show_gen = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == 'show_generator_page')
if len(show_gen.body) != 2 or not isinstance(show_gen.body[-1], ast.Return):
    raise SystemExit('show_generator_page deixou de ser redirecionamento mínimo')

SOURCE.write_text(text, encoding='utf-8')

# Ajusta a descrição da revisão para refletir o resultado final da fase B.
doc = DOC.read_text(encoding='utf-8')
old = '- O controlador generator_* da antiga página é removido somente quando a validação comprova ausência total de referências externas; ManualGroupSelectorDialog também só é removido se ficar sem uso após essa limpeza.\n'
new = '- Removido o controlador generator_* exclusivo da antiga tela; permanece somente generator_format_31_event, pequeno helper ainda reutilizado pelo painel ativo do Reset + 3+1 em Jogar. ManualGroupSelectorDialog também foi removido após ficar comprovadamente órfão.\n'
if old not in doc:
    raise SystemExit('Linha da documentação da fase A não encontrada')
DOC.write_text(doc.replace(old, new, 1), encoding='utf-8')

new_lines = len(text.splitlines())
print(f'LINHAS ANTES FASE B: {original_lines}')
print(f'LINHAS DEPOIS FASE B: {new_lines}')
print(f'REDUÇÃO FASE B: {original_lines-new_lines}')
print('v0.37.1 limpeza estrutural finalizada.')
