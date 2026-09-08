import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source'))
import gph_central as mod


def insert_audit(db, idx, date_iso, hour, reset_hits, pull_hits, sim_hits, base_leader='Reset Cobertura', base_status='BAIXA'):
    hits = {
        'Reset Cobertura': int(reset_hits),
        'Puxada Combinada': int(pull_hits),
        'Similaridade': int(sim_hits),
    }
    best_hits = max(hits.values())
    winners = sorted(k for k, v in hits.items() if v == best_hits)
    leader_hits = hits[base_leader]
    if leader_hits == best_hits and len(winners) == 1:
        classification = 'CORRETA_EXCLUSIVA'
    elif leader_hits == best_hits:
        classification = 'CORRETA_EMPATE'
    else:
        classification = 'INCORRETA'
    contextual = {
        'status': base_status,
        'evidence_leader': base_leader,
        'best': {'method': base_leader, 'index': 70.0},
        'lead': 2.0,
    }
    audit = {
        'schema': 1,
        'leader': base_leader,
        'context_status': base_status,
        'leader_index': 70.0,
        'lead_index': 2.0,
        'hits': hits,
        'leader_hits': leader_hits,
        'best_hits': best_hits,
        'best_methods': winners,
        'classification': classification,
        'is_best_or_tied': leader_hits == best_hits,
        'is_sole_best': classification == 'CORRETA_EXCLUSIVA',
    }
    with db.connect() as con:
        con.execute(
            "INSERT INTO decision_snapshots "
            "(base_data,base_sorteio,base_hora,target_data,target_sorteio,target_hora,status,"
            "confidence_score,confidence_label,recommendation,components_json,signals_json,"
            "contextual_json,contextual_frozen_at,contextual_audit_json,result_groups_json,audited_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                date_iso, 'TESTE', '09:00', date_iso, 'TESTE', hour, 'AUDITADO',
                70.0, base_status, 'teste', '{}', '{}',
                json.dumps(contextual, ensure_ascii=False), '2026-01-01T00:00:00',
                json.dumps(audit, ensure_ascii=False), '[1,2,3,4,5]', '2026-01-01T00:01:00',
            ),
        )


def main():
    db = mod.Database(Path(tempfile.mkdtemp()) / 'stage_c.db')

    # 36 rodadas anteriores. Puxada é consistentemente superior, de modo que
    # um empate técnico no índice-base deve ser resolvido pela camada C.
    for i in range(1, 37):
        day = f"2026-01-{i:02d}" if i <= 31 else f"2026-02-{i-31:02d}"
        if i % 6 == 0:
            insert_audit(db, i, day, '11:00', 2, 2, 1, base_leader='Reset Cobertura', base_status='MODERADA')
        else:
            insert_audit(db, i, day, '11:00', 1, 2, 1, base_leader='Reset Cobertura', base_status='BAIXA')

    # Uma auditoria POSTERIOR ao alvo com resultado oposto não pode entrar.
    insert_audit(db, 99, '2026-03-20', '11:00', 5, 0, 5, base_leader='Reset Cobertura', base_status='FORTE')

    base_context = {
        'target': {'data': '2026-03-10', 'sorteio': 'TESTE', 'hora': '11:00'},
        'rows': [
            {'method': 'Reset Cobertura', 'index': 70.0, 'hour_rounds': 24, 'hour_avg': 1.50, 'overall_avg': 1.45, 'trend_status': 'ESTÁVEL'},
            {'method': 'Puxada Combinada', 'index': 68.5, 'hour_rounds': 24, 'hour_avg': 1.55, 'overall_avg': 1.50, 'trend_status': 'ESTÁVEL'},
            {'method': 'Similaridade', 'index': 61.0, 'hour_rounds': 24, 'hour_avg': 1.20, 'overall_avg': 1.25, 'trend_status': 'ESTÁVEL'},
        ],
        'best': {'method': 'Reset Cobertura', 'index': 70.0, 'hour_rounds': 24, 'hour_avg': 1.50, 'overall_avg': 1.45, 'trend_status': 'ESTÁVEL'},
        'lead': 1.5,
        'status': 'BAIXA',
        'recommendation': 'base',
    }

    before = db.connect().execute('SELECT COUNT(*) FROM decision_snapshots').fetchone()[0]
    out = db.decision_adaptive_context(
        base_context,
        target={'data': '2026-03-10', 'sorteio': 'TESTE', 'hora': '11:00'},
        limit=120,
        min_total=30,
        min_method_rounds=20,
        max_adjustment=3.0,
    )
    after = db.connect().execute('SELECT COUNT(*) FROM decision_snapshots').fetchone()[0]

    assert before == after == 37
    ad = out['adaptive']
    assert ad['schema'] == 1
    assert ad['active'] is True
    assert ad['state'] == 'ATIVA'
    assert ad['training_rounds'] == 36, ad['training_rounds']
    assert ad['lookahead_safe'] is True
    assert ad['changes_official_game'] is False
    assert ad['base_leader'] == 'Reset Cobertura'
    assert ad['final_leader'] == 'Puxada Combinada'
    assert ad['changed_leader'] is True
    assert out['base_evidence_leader'] == 'Reset Cobertura'
    assert out['evidence_leader'] == 'Puxada Combinada'

    rows = {r['method']: r for r in ad['methods']}
    assert rows['Puxada Combinada']['applied_adjustment'] > 0
    assert rows['Reset Cobertura']['applied_adjustment'] < 0
    assert abs(rows['Puxada Combinada']['applied_adjustment']) <= 3.0
    assert abs(rows['Reset Cobertura']['applied_adjustment']) <= 3.0

    # Com amostra insuficiente, a mesma função precisa preservar 100% a base.
    forming = db.decision_adaptive_context(
        base_context,
        target={'data': '2026-01-20', 'sorteio': 'TESTE', 'hora': '11:00'},
        limit=120,
        min_total=30,
        min_method_rounds=20,
    )
    assert forming['adaptive']['active'] is False
    assert forming['adaptive']['state'] == 'EM FORMAÇÃO'
    assert forming['evidence_leader'] == 'Reset Cobertura'
    assert all(abs(float(r['applied_adjustment'])) < 1e-12 for r in forming['adaptive']['methods'])

    assert mod.APP_VERSION == '0.44.0'
    print('TESTE ETAPA C v0.44.0 OK')
    print(ad['state'], ad['training_rounds'], ad['base_leader'], '->', ad['final_leader'])


if __name__ == '__main__':
    main()
