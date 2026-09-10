from pathlib import Path
import ast
import re

SRC = Path('source/gph_central.py')
s = SRC.read_text(encoding='utf-8')
lines = s.splitlines()
out = []

def add(txt=''):
    out.append(str(txt))

def snippet(start, end, title):
    start=max(1,start); end=min(len(lines),end)
    add(f'\n===== {title} [{start}:{end}] =====')
    for n in range(start,end+1):
        add(f'{n}: {lines[n-1]}')

add(f'LINES={len(lines)} CHARS={len(s)}')

# Versão, imports e configuração principal.
for pat, title in [
    (r'(?i)version|vers[aã]o', 'VERSAO'),
    (r'(?i)update_manifest|channel|canal', 'UPDATE/CANAL'),
]:
    hits=[]
    for i,line in enumerate(lines,1):
        if re.search(pat,line): hits.append(i)
    add(f'\n## {title} HITS: {hits[:80]}')
    for i in hits[:12]: snippet(i-3,i+6,f'{title} @ {i}')

# Labels visuais e seu contexto.
labels = [
    'Decisão', 'Auditoria', 'Laboratório', 'Laboratorio', 'Laboratório Sombra',
    'Walk-Forward', 'Índice de Consistência', 'Campeão', 'Desafiante',
    'Recomendação da Rodada', 'Meta', 'Ternos', 'terno', 'snapshot', 'canônica', 'canonica'
]
for label in labels:
    hits=[i for i,line in enumerate(lines,1) if label.lower() in line.lower()]
    add(f'\n## LABEL {label!r}: {hits[:100]}')
    for i in hits[:8]: snippet(i-12,i+22,f'{label} @ {i}')

# AST: classes/métodos que tocam decisão/auditoria/lab/terno/snapshot.
tree=ast.parse(s)
keys=('decis','audit','labor','terno','snapshot','consist','walk','sombra','shadow','meta','recomend')
add('\n===== AST RELEVANTE =====')
for node in tree.body:
    if isinstance(node,ast.ClassDef):
        found=[]
        for m in node.body:
            if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)):
                name=m.name.lower()
                if any(k in name for k in keys):
                    found.append((m.name,m.lineno,getattr(m,'end_lineno',m.lineno)))
        if found:
            add(f'CLASS {node.name} {node.lineno}:{getattr(node,"end_lineno",node.lineno)}')
            for rec in found: add('  METHOD %s %s:%s'%rec)
            # Conteúdo completo só dos métodos menores; início/fim dos grandes.
            for name,a,b in found:
                if b-a <= 180:
                    snippet(a,b,f'METHOD {node.name}.{name}')
                else:
                    snippet(a,a+90,f'METHOD {node.name}.{name} INICIO')
                    snippet(b-50,b,f'METHOD {node.name}.{name} FIM')

# Estruturas de persistência/cache e arquivos JSON usados pela decisão.
for pat,title in [
    (r'(?i)json|\.json', 'JSON/PERSISTENCIA'),
    (r'(?i)canonical|can[oô]nic|snapshot|decision|decis[aã]o', 'DADOS DECISAO'),
    (r'(?i)resultado|histor', 'RESULTADOS/HISTORICO'),
]:
    hits=[i for i,line in enumerate(lines,1) if re.search(pat,line)]
    add(f'\n## {title} HITS: {hits[:140]}')
    for i in hits[:20]: snippet(i-4,i+10,f'{title} @ {i}')

Path('_inspection_v0476.txt').write_text('\n'.join(out), encoding='utf-8')
print('RELATORIO', len(out), 'linhas -> _inspection_v0476.txt')
