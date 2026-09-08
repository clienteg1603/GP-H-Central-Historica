from pathlib import Path
import ast
p=Path('source/gph_central.py')
text=p.read_text(encoding='utf-8')
tree=ast.parse(text)

wanted={
    'method_convergencia_g5','generate_group_combinations','play_family_changed',
    'play_variant_changed','play_controls_changed','play_generate'
}
for node in ast.walk(tree):
    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in wanted:
        print('\n###',node.name,'lines',node.lineno,'-',node.end_lineno)
        print('\n'.join(text.splitlines()[node.lineno-1:node.end_lineno]))
