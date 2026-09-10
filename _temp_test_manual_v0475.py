from __future__ import annotations

import ast
import copy
import importlib.util
import os
import sys
from pathlib import Path

BEFORE = Path('/tmp/gph_before_manual_v0475.py').read_text(encoding='utf-8')
AFTER_PATH = Path('source/gph_central.py')
AFTER = AFTER_PATH.read_text(encoding='utf-8')

assert 'APP_VERSION = "0.47.5"' in AFTER
assert '("manual_builder", "Jogo manual", self.play_show_manual_builder),' not in AFTER
assert '("new", "Nova aposta", self.play_show_new),' in AFTER
assert '("games", "Bilhetes", self.play_show_games),' in AFTER
assert '("summary", "Financeiro", self.play_show_summary),' in AFTER
assert 'def _merge_manual_generation(existing, incoming):' in AFTER
print('OK: aba redundante Jogo manual removida; Nova aposta/Bilhetes/Financeiro preservados')


def class_methods(source, class_name):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return {n.name: ast.dump(n, include_attributes=False) for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

# Database não deve sofrer qualquer alteração nesta manutenção de interface.
bt = ast.parse(BEFORE)
at = ast.parse(AFTER)
bdb = next(n for n in bt.body if isinstance(n, ast.ClassDef) and n.name == 'Database')
adb = next(n for n in at.body if isinstance(n, ast.ClassDef) and n.name == 'Database')
assert ast.dump(bdb, include_attributes=False) == ast.dump(adb, include_attributes=False)
print('OK: Database completo AST-idêntico')

os.environ['GPH_DISABLE_STARTUP_DIALOGS'] = '1'
spec = importlib.util.spec_from_file_location('gph_manual_v0475', AFTER_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

App = next(
    obj for obj in vars(mod).values()
    if isinstance(obj, type) and hasattr(obj, '_merge_manual_generation')
)
merge = App._merge_manual_generation

target = {'data':'2026-09-10','sorteio':'PTM','hora':'11:00'}
def gen(kind, scope, nums, target=target, sub=None):
    return {
        'kind': kind,
        'scope': scope,
        'submodalidade': sub,
        'strategy': 'Manual',
        'selector': 'Manual',
        'intended_target': copy.deepcopy(target),
        'target_mode': 'ALVO_ESPECIFICO',
        'rows': [{'numero': n, 'bicho':'Teste'} for n in nums],
    }

first = gen('Centena', '1º–5º', ['123'])
second = gen('Centena', '1º–5º', ['456'])
merged, added, accumulated = merge(first, second)
assert accumulated is True
assert added == 1
assert [r['numero'] for r in merged['rows']] == ['123','456']
# Garante que a função não mutou a geração anterior.
assert [r['numero'] for r in first['rows']] == ['123']
print('OK: segunda entrada manual soma ao primeiro palpite em vez de substituir')

third = gen('Centena', '1º–5º', ['789','012'])
merged2, added2, accumulated2 = merge(merged, third)
assert accumulated2 is True and added2 == 2
assert [r['numero'] for r in merged2['rows']] == ['123','456','789','012']
print('OK: entradas consecutivas continuam acumulando')

dup = gen('Centena', '1º–5º', ['456','999'])
merged3, added3, accumulated3 = merge(merged2, dup)
assert accumulated3 is True and added3 == 1
assert [r['numero'] for r in merged3['rows']] == ['123','456','789','012','999']
assert sum(1 for r in merged3['rows'] if r['numero']=='456') == 1
print('OK: duplicado é ignorado e novo palpite é preservado')

other_target = {'data':'2026-09-10','sorteio':'PT','hora':'14:00'}
replaced, added4, accumulated4 = merge(merged3, gen('Centena','1º–5º',['777'],target=other_target))
assert accumulated4 is False and added4 == 1
assert [r['numero'] for r in replaced['rows']] == ['777']
print('OK: mudança de rodada não mistura palpites incompatíveis')

other_kind, _, acc_kind = merge(merged3, gen('Milhar','1º–5º',['1234'],sub='Milhar'))
assert acc_kind is False and [r['numero'] for r in other_kind['rows']] == ['1234']
print('OK: mudança de modalidade/submodalidade não mistura listas')

# Confere que play_manual_input usa a mesclagem e recalcula quantidade pelo total acumulado.
tree = ast.parse(AFTER)
manual_node = None
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == 'play_manual_input':
        manual_node = node
        break
assert manual_node is not None
seg = ast.get_source_segment(AFTER, manual_node) or ''
assert 'self._merge_manual_generation(' in seg
assert 'self.play_total.set(str(len(generation.get("rows") or [])))' in seg
print('OK: fluxo real de Nova aposta > Manual usa a lista acumulada')
