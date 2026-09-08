from pathlib import Path
import ast
p=Path('source/gph_central.py')
text=p.read_text(encoding='utf-8')
tree=ast.parse(text)
funcs=[]
for n in ast.walk(tree):
    if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
        funcs.append((n.name,n.lineno,getattr(n,'end_lineno',n.lineno),[a.arg for a in n.args.args]))
keys=('shadow','decision','historico_concentrado','reset_coverage','similarity','convergencia','draws_in_order','sync_with_shared','build_decision','audit_decision')
for row in sorted(funcs,key=lambda x:x[1]):
    if any(k in row[0] for k in keys):
        print(row)
print('VERSION', next((line for line in text.splitlines() if line.startswith('APP_VERSION =')), '?'))
print('LINES',len(text.splitlines()))
