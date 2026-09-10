from pathlib import Path
import ast
import importlib.util
import sys

BEFORE = Path('/tmp/gph_before_coverage_v0478.py')
AFTER = Path('source/gph_central.py')

before = BEFORE.read_text(encoding='utf-8')
after = AFTER.read_text(encoding='utf-8')

assert 'APP_VERSION = "0.47.8"' in after
assert 'def _coverage_candidate_rows(self):' in after
assert 'raw_rows = self._coverage_candidate_rows()' in after
assert 'audit_source = "result_lookup"' in after
assert 'self.get_draw(' in after
assert '"result_lookup_rounds"' in after
assert 'histórico Meta existente + novas rodadas' in after

# O cérebro Meta deve permanecer byte-a-byte igual ao baseline v0.47.7.
def meta_methods(text):
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    out = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == 'Database':
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if method.name.startswith('_meta') or method.name.startswith('meta_'):
                        out[method.name] = ''.join(lines[method.lineno-1:method.end_lineno])
    return out

b = meta_methods(before)
a = meta_methods(after)
assert b and b.keys() == a.keys(), 'métodos Meta mudaram'
for name in b:
    assert b[name] == a[name], f'cérebro Meta alterado em {name}'

# Importa módulo patchado para testar helpers puros.
spec = importlib.util.spec_from_file_location('gph_cov_v0478_test', AFTER)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
Database = mod.Database

# Auditoria congelada continua correta e não infla repetição.
x = Database._coverage_frozen_audit({'groups':[1,2,3,4,5]}, [2,2,5,9,10])
assert x['available'] and x['coverage_hits'] == 2

# Regra da meta > 50% segue estrita.
rows = [{'coverage_hits':2 if i < 11 else 1, 'best_terno':None, 'best_core_terno':None} for i in range(20)]
s = Database._coverage_evolution_summary(rows, 20, target_pct=50)
assert s['pct_2plus'] == 55.0 and s['goal_met'] is True
rows50 = [{'coverage_hits':2 if i < 10 else 1, 'best_terno':None, 'best_core_terno':None} for i in range(20)]
assert Database._coverage_evolution_summary(rows50, 20, target_pct=50)['goal_met'] is False

# Garante que o painel não volta a depender da função que exige status AUDITADO.
tree = ast.parse(after)
fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'decision_coverage_evolution')
src = ''.join(after.splitlines(keepends=True)[fn.lineno-1:fn.end_lineno])
assert '_decision_audited_rows' not in src
assert '_coverage_candidate_rows' in src
assert 'get_draw' in src
assert 'meta_shadow_prediction' not in src
assert '_meta_fit' not in src
assert '_meta_train' not in src

# A consulta candidata não filtra status=AUDITADO.
fn2 = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_coverage_candidate_rows')
src2 = ''.join(after.splitlines(keepends=True)[fn2.lineno-1:fn2.end_lineno])
assert "status='AUDITADO'" not in src2
assert 'SELECT * FROM decision_snapshots' in src2

# Ternos continuam condicionados ao registro real, não reconstruídos.
assert 'SELECT * FROM jogos_congelados' in src
assert '_decision_groups_from_item' in src

print('OK: v0.47.8 remove filtro AUDITADO do bootstrap, usa resultado real e preserva Meta/Ternos.')
