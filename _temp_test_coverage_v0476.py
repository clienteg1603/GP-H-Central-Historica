from pathlib import Path
import ast
import importlib.util

BEFORE = Path('/tmp/gph_before_coverage_v0476.py')
AFTER = Path('source/gph_central.py')

before = BEFORE.read_text(encoding='utf-8')
after = AFTER.read_text(encoding='utf-8')

assert 'APP_VERSION = "0.47.6"' in after
assert 'def decision_coverage_evolution(self, windows=(20, 30, 60), recent_limit=10):' in after
assert 'def _decision_build_coverage_evolution(self, body):' in after
assert 'self._decision_build_coverage_evolution(body)' in after
assert 'target_pct = 50.0' in after
assert '"changes_meta": False' in after
assert '"target_is_diagnostic_only": True' in after

# O cérebro Meta existente deve permanecer byte-a-byte idêntico em seus métodos.
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

# Importa a versão patchada para testar os helpers puros sem abrir interface.
spec = importlib.util.spec_from_file_location('gph_coverage_test', AFTER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
Database = mod.Database

# Filtro prospectivo: apenas Terno Meta da mesma base.
snapshot = {'base_data':'2026-09-10','base_sorteio':'PTM','base_hora':'11:00'}
valid = {
    'seletor':'GP-H Meta v0.2','tipo':'Terno de Grupo',
    'base_data':'2026-09-10','base_sorteio':'PTM','base_hora':'11:00',
}
assert Database._coverage_terno_matches_snapshot(snapshot, valid)
old_meta = dict(valid, seletor='GP-H Meta v0.1')
assert Database._coverage_terno_matches_snapshot(snapshot, old_meta)
assert not Database._coverage_terno_matches_snapshot(snapshot, dict(valid, seletor='GP-H Reset Cobertura v1'))
assert not Database._coverage_terno_matches_snapshot(snapshot, dict(valid, tipo='Quadra de Grupo'))
assert not Database._coverage_terno_matches_snapshot(snapshot, dict(valid, base_hora='09:00'))
assert not Database._coverage_terno_matches_snapshot(snapshot, dict(valid, base_data=''))

# Janela de 20: 12/20 rodadas com 2+ => 60%, logo a régua >50% é atingida.
records = []
for i in range(20):
    if i < 8:
        coverage = 3
    elif i < 12:
        coverage = 2
    else:
        coverage = 1
    row = {
        'coverage_hits': coverage,
        'best_terno': None,
        'best_core_terno': None,
    }
    records.append(row)

# Das 8 oportunidades com cobertura >=3, 6 possuem Terno do Top 5; 3 convertem 3/3.
for i in range(6):
    records[i]['best_terno'] = 3 if i < 3 else 2
    records[i]['best_core_terno'] = 3 if i < 3 else 2
# Duas oportunidades sem Terno rastreável ficam fora do denominador da conversão.
# Adiciona Ternos em rodadas de cobertura menor para testar Melhor Terno sem afetar conversão.
records[8]['best_terno'] = 2
records[9]['best_terno'] = 1

summary = Database._coverage_evolution_summary(records, 20, target_pct=50.0)
assert summary['rounds'] == 20
assert abs(summary['avg_coverage'] - 2.0) < 1e-12
assert abs(summary['pct_2plus'] - 60.0) < 1e-12
assert summary['goal_met'] is True
assert summary['terno_rounds'] == 8
assert summary['terno_3of3'] == 3
assert abs(summary['terno_3of3_rate'] - 37.5) < 1e-12
assert summary['conversion_opportunities'] == 6
assert summary['conversion_3of3'] == 3
assert abs(summary['conversion_rate'] - 50.0) < 1e-12
assert summary['opportunities_without_core_terno'] == 2
assert summary['latest_best_terno'] == 3

# Regra é estritamente >50%; exatamente 50% não cumpre a meta.
strict = []
for i in range(20):
    strict.append({'coverage_hits': 2 if i < 10 else 1, 'best_terno': None, 'best_core_terno': None})
strict_summary = Database._coverage_evolution_summary(strict, 20, target_pct=50.0)
assert abs(strict_summary['pct_2plus'] - 50.0) < 1e-12
assert strict_summary['goal_met'] is False

# Janelas usam os registros mais recentes na ordem recebida.
windowed = Database._coverage_evolution_summary(records, 10, target_pct=50.0)
assert windowed['rounds'] == 10
assert abs(windowed['pct_2plus'] - 100.0) < 1e-12

# Ausência de Terno jamais vira 0% de conversão artificial.
no_terno = Database._coverage_evolution_summary([
    {'coverage_hits': 4, 'best_terno': None, 'best_core_terno': None},
    {'coverage_hits': 3, 'best_terno': None, 'best_core_terno': None},
], 20)
assert no_terno['conversion_opportunities'] == 0
assert no_terno['conversion_rate'] is None
assert no_terno['opportunities_without_core_terno'] == 2

print('OK: Evolução de Cobertura v0.47.6 validada; cérebro Meta preservado.')
