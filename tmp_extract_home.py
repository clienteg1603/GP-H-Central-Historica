from pathlib import Path
import ast

path = Path('source/gph_central.py')
text = path.read_text(encoding='utf-8')
lines = text.splitlines()
tree = ast.parse(text)
want = {'_make_scrollable_page_body','show_home','_smart_scroll_bindings','_bind_smart_scroll','_smart_wheel'}
out=[]
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in want:
        out.append(f'### {node.name} lines {node.lineno}-{node.end_lineno}\n')
        out.extend(lines[node.lineno-1:node.end_lineno])
        out.append('\n')
Path('tmp_home_excerpt.txt').write_text('\n'.join(out), encoding='utf-8')
print('extraído', [x for x in want if any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==x for n in ast.walk(tree))])
