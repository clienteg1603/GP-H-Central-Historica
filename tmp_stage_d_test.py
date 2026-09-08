import os
import sys
import tempfile
from pathlib import Path
import importlib.util

os.environ['GPH_DATA_DIR'] = tempfile.mkdtemp(prefix='gph_stage_d_')
path = Path('source/gph_central.py').resolve()
spec = importlib.util.spec_from_file_location('gph_stage_d_module', path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
fn = mod.Database.decision_operational_recommendation


def ctx(status, active=True, leader='Reset Cobertura', lead=8.0, index=72.0):
    return {
        'status': status,
        'lead': lead,
        'best': {'method': leader, 'index': index},
        'evidence_leader': leader,
        'base_evidence_leader': 'Reset Cobertura',
        'adaptive': {
            'schema': 1,
            'active': active,
            'state': 'ATIVA' if active else 'EM FORMAÇÃO',
            'base_leader': 'Reset Cobertura',
            'final_leader': leader,
            'changed_leader': leader != 'Reset Cobertura',
        },
    }

strong = fn(ctx('FORTE', True, 'Puxada Combinada', 9.1, 74.2))['operational']
assert strong['action_code'] == 'PRIORIZAR'
assert strong['actionable'] is True
assert strong['recommended_method'] == 'Puxada Combinada'
assert strong['leader_source'] == 'ADAPTATIVO'

moderate = fn(ctx('MODERADA', True, 'Similaridade', 4.6, 69.0))['operational']
assert moderate['action_code'] == 'PRIORIZAR_COM_CAUTELA'
assert moderate['actionable'] is True
assert moderate['recommended_method'] == 'Similaridade'

low = fn(ctx('BAIXA', True, 'Reset Cobertura', 1.1, 64.0))['operational']
assert low['action_code'] == 'SEM_VANTAGEM_CLARA'
assert low['actionable'] is False
assert low['recommended_method'] is None

forming = fn(ctx('FORTE', False, 'Reset Cobertura', 10.0, 76.0))['operational']
assert forming['action_code'] == 'EVIDENCIA_INSUFICIENTE'
assert forming['actionable'] is False
assert forming['reference_leader'] == 'Reset Cobertura'
assert forming['leader_source'] == 'BASE'

insufficient = fn(ctx('AMOSTRA INSUFICIENTE', True, 'Reset Cobertura', 0.0, 50.0))['operational']
assert insufficient['action_code'] == 'EVIDENCIA_INSUFICIENTE'
assert insufficient['actionable'] is False

original = ctx('MODERADA', True, 'Puxada Combinada', 5.0, 70.0)
out = fn(original)
assert out['best']['method'] == original['best']['method']
assert out['best']['index'] == original['best']['index']
assert out['status'] == original['status']
assert out['lead'] == original['lead']
assert out['operational']['changes_decision'] is False
assert out['operational']['changes_official_game'] is False
assert out['operational']['changes_meta'] is False
assert out['operational']['lookahead_safe'] is True

print('Smoke test Etapa D OK')
