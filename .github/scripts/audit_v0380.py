from pathlib import Path
import ast, re, collections
p=Path('source/gph_central.py')
text=p.read_text(encoding='utf-8')
tree=ast.parse(text)
app=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='App')
methods={n.name:n for n in app.body if isinstance(n,ast.FunctionDef)}
print('VERSION', re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text).group(1))
print('LINES', len(text.splitlines()))
TARGETS=['show_home','show_play_page','show_decision_page','show_results','show_search','show_statistics_page','show_pulls_page','show_methods_page','show_base_config']
for name in TARGETS:
    n=methods.get(name)
    print('\n###',name,'lines',getattr(n,'lineno',None),getattr(n,'end_lineno',None))
    if not n: continue
    calls=collections.Counter()
    strings=[]
    for x in ast.walk(n):
        if isinstance(x,ast.Call):
            try: fn=ast.unparse(x.func)
            except: fn='?'
            calls[fn]+=1
        elif isinstance(x,ast.Constant) and isinstance(x.value,str):
            s=' '.join(x.value.split())
            if 2 <= len(s) <= 140 and not s.startswith('#'):
                strings.append(s)
    print('widgets', {k:v for k,v in calls.items() if any(t in k for t in ['Label','Button','Treeview','Combobox','Entry','Text','Frame','Notebook'])})
    print('strings:')
    for s in strings:
        print('  -',repr(s))

# String literals repeated across target methods
seen=collections.defaultdict(set)
for name in TARGETS:
    n=methods.get(name)
    if not n: continue
    for x in ast.walk(n):
        if isinstance(x,ast.Constant) and isinstance(x.value,str):
            s=' '.join(x.value.split())
            if 4<=len(s)<=80 and not any(ch in s for ch in ['{','}','\\n']):
                seen[s].add(name)
print('\n### REPEATED VISIBLE-ish STRINGS')
for s,names in sorted(seen.items(), key=lambda kv:(-len(kv[1]),kv[0].lower())):
    if len(names)>=2:
        print(len(names), sorted(names), repr(s))

print('\n### NAV BLOCK')
ui=methods.get('_build_ui')
if ui:
    for x in ast.walk(ui):
        if isinstance(x,ast.Constant) and isinstance(x.value,str) and x.value in ['Início','Jogar','Decisão','Resultados','Pesquisa','Estatísticas','Puxadas','Métodos','Base / Configurações','Configurações']:
            print(x.lineno, repr(x.value))

print('\n### BASE CONFIG HEADINGS')
base=methods.get('show_base_config')
if base:
    for x in ast.walk(base):
        if isinstance(x,ast.Constant) and isinstance(x.value,str):
            s=' '.join(x.value.split())
            if len(s)<=100 and (s.isupper() or any(k in s.lower() for k in ['aparência','atualiza','backup','conta','perfil','base','sincron','dados'])):
                print(x.lineno, repr(s))
