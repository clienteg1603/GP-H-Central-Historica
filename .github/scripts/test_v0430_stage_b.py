import json
import tempfile
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'source'))
import gph_central as mod


def add_row(db, idx, level, classification, leader_index, leader_hits):
    day=f"2026-01-{idx:02d}"
    contextual={
        "status":level,
        "evidence_leader":"Reset Cobertura",
        "best":{"method":"Reset Cobertura","index":leader_index},
        "lead":max(0.0,leader_index-50.0),
    }
    audit={
        "schema":1,
        "leader":"Reset Cobertura",
        "context_status":level,
        "leader_index":leader_index,
        "lead_index":max(0.0,leader_index-50.0),
        "leader_hits":leader_hits,
        "best_hits":leader_hits if classification!='INCORRETA' else leader_hits+1,
        "best_methods":["Reset Cobertura"] if classification!='INCORRETA' else ["Puxada Combinada"],
        "classification":classification,
        "is_best_or_tied":classification!='INCORRETA',
        "is_sole_best":classification=='CORRETA_EXCLUSIVA',
    }
    with db.connect() as con:
        con.execute(
            "INSERT INTO decision_snapshots "
            "(base_data,base_sorteio,base_hora,target_data,target_sorteio,target_hora,status,"
            "confidence_score,confidence_label,recommendation,components_json,signals_json,"
            "contextual_json,contextual_frozen_at,contextual_audit_json,result_groups_json,audited_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                day,'TESTE','09:00',day,'TESTE','11:00','AUDITADO',
                float(leader_index),level,'teste','{}','{}',
                json.dumps(contextual,ensure_ascii=False),'2026-01-01T00:00:00',
                json.dumps(audit,ensure_ascii=False),'[1,2,3,4,5]','2026-01-01T00:01:00',
            ),
        )


def main():
    db=mod.Database(Path(tempfile.mkdtemp())/'stage_b.db')
    idx=1
    # BAIXA: 4/8 = 50%
    for i in range(8):
        add_row(db,idx,'BAIXA','CORRETA_EXCLUSIVA' if i<2 else ('CORRETA_EMPATE' if i<4 else 'INCORRETA'),58+i*0.3,1+(i%2)); idx+=1
    # MODERADA: 6/8 = 75%
    for i in range(8):
        add_row(db,idx,'MODERADA','CORRETA_EXCLUSIVA' if i<4 else ('CORRETA_EMPATE' if i<6 else 'INCORRETA'),68+i*0.3,1+(i%3)); idx+=1
    # FORTE: 7/8 = 87.5%
    for i in range(8):
        add_row(db,idx,'FORTE','CORRETA_EXCLUSIVA' if i<5 else ('CORRETA_EMPATE' if i<7 else 'INCORRETA'),80+i*0.3,2+(i%2)); idx+=1

    before=db.connect().execute('SELECT COUNT(*) FROM decision_snapshots').fetchone()[0]
    out=db.decision_confidence_calibration(limit=240,min_bucket=8)
    after=db.connect().execute('SELECT COUNT(*) FROM decision_snapshots').fetchone()[0]

    assert before==after==24
    assert out['evaluated']==24
    assert out['sufficient_levels']==3
    assert out['monotonic'] is True
    assert out['verdict']=='ORDEM COERENTE'
    rows={r['level']:r for r in out['levels']}
    assert abs(rows['BAIXA']['best_or_tied_rate']-50.0)<1e-9
    assert abs(rows['MODERADA']['best_or_tied_rate']-75.0)<1e-9
    assert abs(rows['FORTE']['best_or_tied_rate']-87.5)<1e-9
    assert abs(out['strong_vs_low_pp']-37.5)<1e-9
    assert out['index_outcome_corr'] is not None
    assert out['lookahead_safe'] is True
    assert out['changes_decision'] is False
    assert mod.APP_VERSION=='0.43.0'
    print('TESTE ETAPA B v0.43.0 OK')
    print(out['verdict'], out['evaluated'], out['strong_vs_low_pp'], out['index_outcome_corr'])


if __name__=='__main__':
    main()
