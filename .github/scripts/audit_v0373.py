from pathlib import Path
import ast, re
p=Path('source/gph_central.py')
text=p.read_text(encoding='utf-8')
tree=ast.parse(text)
print('VERSION', re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text).group(1))
print('LINES', len(text.splitlines()))
print('GPHPlayWheel refs', text.count('GPHPlayWheel'))
print('_play_mousewheel refs', text.count('_play_mousewheel'))
print('_play_install_wheel_bindtag refs', text.count('_play_install_wheel_bindtag'))
print('_install_smart_scroll_policy refs', text.count('_install_smart_scroll_policy'))
print('--- TOPLEVEL CLASSES / geometry ---')
for node in tree.body:
    if not isinstance(node, ast.ClassDef):
        continue
    bases=[]
    for b in node.bases:
        try: bases.append(ast.unparse(b))
        except: pass
    is_top=any('Toplevel' in b for b in bases)
    if not is_top: continue
    geoms=[]; mins=[]; override=False
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr=='geometry':
                try: geoms.append((n.lineno, ast.unparse(n.args[0]) if n.args else ''))
                except: geoms.append((n.lineno,'?'))
            elif n.func.attr=='minsize':
                try: mins.append((n.lineno, ','.join(ast.unparse(a) for a in n.args)))
                except: mins.append((n.lineno,'?'))
            elif n.func.attr=='overrideredirect': override=True
    print(node.name, 'lines', node.lineno, node.end_lineno, 'geometry', geoms[:6], 'minsize', mins[:4], 'override', override)
print('--- Toplevel constructions inside functions ---')
for n in ast.walk(tree):
    if isinstance(n, ast.Call):
        try: fname=ast.unparse(n.func)
        except: fname=''
        if fname.endswith('Toplevel'):
            parent=n
            # find enclosing function/class by line scan later
            print('Toplevel call line', n.lineno, fname)
print('--- geometry call lines ---')
for n in ast.walk(tree):
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr=='geometry':
        try: arg=ast.unparse(n.args[0]) if n.args else ''
        except: arg='?'
        print(n.lineno, arg)
