from pathlib import Path
import ast
import re

SRC = Path('source/gph_central.py')
s = SRC.read_text(encoding='utf-8')
lines = s.splitlines()
print('LINES', len(lines), 'CHARS', len(s))

terms = [
    'Decisão', 'Decisao', 'decisão', 'decisao', 'Laboratório', 'Laboratorio',
    'Auditoria', 'audit', 'Walk-Forward', 'consist', 'Campeão', 'Campeao',
    'challenger', 'desafiante', 'terno', 'coverage', 'cobertura', 'snapshot',
]

print('\n=== LINHAS-CHAVE ===')
seen = set()
for i, line in enumerate(lines, 1):
    low = line.lower()
    if any(t.lower() in low for t in terms):
        if i in seen:
            continue
        seen.add(i)
        print(f'{i}: {line[:240]}')

print('\n=== CLASSES / METODOS RELEVANTES ===')
tree = ast.parse(s)
for node in tree.body:
    if isinstance(node, ast.ClassDef):
        methods = []
        for m in node.body:
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seg = ast.get_source_segment(s, m) or ''
                low = (m.name + '\n' + seg).lower()
                if any(t.lower() in low for t in terms):
                    methods.append((m.name, m.lineno, getattr(m, 'end_lineno', m.lineno)))
        if methods:
            print('CLASS', node.name, node.lineno, getattr(node, 'end_lineno', node.lineno))
            for item in methods:
                print('  METHOD', *item)

# Imprime trechos em torno de métodos candidatos da UI/decisão.
print('\n=== TRECHOS DE METODOS CANDIDATOS ===')
patterns = [
    r'^\s*def\s+.*decis', r'^\s*def\s+.*audit', r'^\s*def\s+.*lab',
    r'^\s*def\s+.*walk', r'^\s*def\s+.*consist', r'^\s*def\s+.*shadow',
    r'^\s*def\s+.*sombra', r'^\s*def\s+.*terno',
]
for i, line in enumerate(lines, 1):
    if any(re.search(p, line, re.I) for p in patterns):
        start = max(1, i - 4)
        end = min(len(lines), i + 55)
        print(f'--- {start}:{end} ---')
        for j in range(start, end + 1):
            print(f'{j}: {lines[j-1]}')

# Localiza criação de abas/nav labels na área decisão.
print('\n=== CONTEXTO DE LABELS ===')
for label in ['Decisão', 'Laboratório Sombra', 'Walk-Forward', 'Índice de Consistência', 'Campeão', 'Desafiante']:
    for i, line in enumerate(lines, 1):
        if label.lower() in line.lower():
            start = max(1, i - 18); end = min(len(lines), i + 28)
            print(f'--- {label} @ {i} / {start}:{end} ---')
            for j in range(start, end + 1):
                print(f'{j}: {lines[j-1]}')
            break
