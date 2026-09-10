from pathlib import Path
import ast
import importlib.util
import sys

BEFORE = Path('/tmp/gph_before_coverage_history_v0477.py')
AFTER = Path('source/gph_central.py')

before = BEFORE.read_text(encoding='utf-8')
after = AFTER.read_text(encoding='utf-8')

assert 'APP_VERSION = "0.47.7"' in after
assert 'def _coverage_frozen_audit(meta, result_groups_json):' in after
assert 'audit = self._coverage_frozen_audit(meta, frozen_result_json)' in after
assert '"historical_bootstrap_rounds"' in after
assert 'histórico congelado + novas rodadas' in after

# O cérebro Meta permanece exatamente igual ao baseline v0.47.6.
def meta_methods(text):
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    out = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == 'Database':
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if method.name.startswith('_meta') or method.name.startswith('meta_'):
                        start = method.lineno - 1
                        end = getattr(method, 'end_lineno', method.lineno)
                        out[method.name] = ''.join(lines[start:end])
    return out

before_meta = meta_methods(before)
after_meta = meta_methods(after)
assert before_meta, 'nenhum método Meta encontrado no baseline'
assert before_meta.keys() == after_meta.keys(), 'conjunto de métodos Meta foi alterado'
for name in before_meta:
    assert before_meta[name] == after_meta[name], f'cérebro Meta alterado em {name}'

# Importa a versão patchada sem abrir a interface.
spec = importlib.util.spec_from_file_location('gph_coverage_history_test', AFTER)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
Database = mod.Database

# Bootstrap usa SOMENTE os grupos já congelados no Meta + resultado posterior.
meta = {'groups':[1,2,3,4,5]}
audit = Database._coverage_frozen_audit(meta, '[2, 2, 5, 9, 10]')
assert audit['available'] is True
assert audit['source'] == 'frozen_history'
assert audit['groups'] == [1,2,3,4,5]
assert audit['result_groups'] == [2,2,5,9,10]
assert audit['coverage_hits'] == 2, audit

# Repetição no resultado não infla a cobertura; mede bichos/grupos distintos cobertos.
audit2 = Database._coverage_frozen_audit({'groups':[7,8,9,10,11]}, [7,7,7,8,25])
assert audit2['coverage_hits'] == 2

# Grupos inválidos/duplicados no core são normalizados sem fabricar informação.
audit3 = Database._coverage_frozen_audit({'groups':[1,1,26,'x',3,4]}, '[1,3,4,25,25]')
assert audit3['groups'] == [1,3]
assert audit3['coverage_hits'] == 2

# Sem snapshot Meta congelado ou sem resultado, não há rodada elegível.
assert Database._coverage_frozen_audit({}, '[1,2,3,4,5]')['available'] is False
assert Database._coverage_frozen_audit({'groups':[1,2,3]}, '[]')['available'] is False
assert Database._coverage_frozen_audit({'groups':[1,2,3]}, 'JSON inválido')['available'] is False

# A régua de >50% continua estritamente diagnóstica e inalterada.
records = []
for i in range(20):
    records.append({'coverage_hits': 2 if i < 11 else 1, 'best_terno': None, 'best_core_terno': None})
summary = Database._coverage_evolution_summary(records, 20, target_pct=50.0)
assert abs(summary['pct_2plus'] - 55.0) < 1e-12
assert summary['goal_met'] is True
strict = [{'coverage_hits':2 if i < 10 else 1, 'best_terno':None, 'best_core_terno':None} for i in range(20)]
assert Database._coverage_evolution_summary(strict, 20, target_pct=50.0)['goal_met'] is False

# Garantias explícitas: histórico não reconstrói Ternos nem recalcula Meta.
fn = next(node for node in ast.walk(ast.parse(after)) if isinstance(node, ast.FunctionDef) and node.name == 'decision_coverage_evolution')
source = ''.join(after.splitlines(keepends=True)[fn.lineno-1:fn.end_lineno])
assert '_coverage_frozen_audit' in source
assert 'meta_shadow_prediction' not in source
assert '_meta_fit' not in source
assert '_meta_train' not in source

print('OK: v0.47.7 bootstrap histórico validado; Meta preservado e Ternos não reconstruídos.')
# trigger final validation
