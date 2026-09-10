from __future__ import annotations

import base64
import gzip
import importlib.util
import json
import math
import os
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

os.environ['GPH_DISABLE_STARTUP_DIALOGS'] = '1'

SOURCE = Path('source/gph_central.py')
spec = importlib.util.spec_from_file_location('gph_admission', SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
Database = mod.Database
PrizeRow = mod.PrizeRow

# Tabela 1 enviada pelo usuário — exatamente a puxada antiga, sem acréscimos.
TABLE1 = {
    1:[25,2,13,19,20], 2:[10,1,13,19,20], 3:[11,12,21,24,10,9],
    4:[6,12,14,16,5,13], 5:[13,14,8,17,18,19], 6:[7,17,12,21,22,23],
    7:[6,10,25], 8:[5,12,23], 9:[15,18,3,14], 10:[7,2,3],
    11:[3,6,21], 12:[6,23,22,16,3], 13:[5,1,2,19,20],
    14:[5,16,22,9], 15:[9,18,4,17], 16:[12,14,22,23],
    17:[5,6,20,15], 18:[9,20,15,5], 19:[1,2,13,20],
    20:[1,2,13,19,24], 21:[25,3,6], 22:[14,16,6], 23:[16,12,8,6],
    24:[20,3,6], 25:[21,1,7],
}

raw = base64.b64decode(Path('_temp_history_groups_v0474.b64').read_text().strip())
history = json.loads(gzip.decompress(raw).decode('utf-8'))
assert isinstance(history, list) and len(history) >= 1000


def infer_hour(date_s: str, sorteio: str, slot: int) -> str:
    s = str(sorteio or '').upper()
    known = {
        'PPT':'09:00', 'PTM':'11:00', 'PT':'14:00', 'PTV':'16:00',
        'PTN':'18:00', 'CORUJA':'21:00', 'CORUJINHA':'21:00',
    }
    if s in known:
        return known[s]
    if 'FEDERAL' in s:
        wd = datetime.strptime(date_s, '%Y-%m-%d').weekday()
        return '11:00' if wd == 6 else '20:00'
    fallback = {1:'09:00',2:'11:00',3:'14:00',4:'16:00',5:'18:00',6:'21:00'}
    return fallback.get(int(slot), f'{8+int(slot)*2:02d}:00')


def draw_rows(item):
    date_s, slot, sorteio, groups = item
    dt = datetime.strptime(date_s, '%Y-%m-%d')
    hour = infer_hour(date_s, sorteio, slot)
    rows=[]
    for prize, g in enumerate(groups, start=1):
        g=int(g)
        start=(g-1)*4+1
        dez=start % 100
        value=(prize*100 + dez) % 10000
        milhar=f'{value:04d}'
        rows.append(PrizeRow(
            data=date_s,
            dia_semana=dt.strftime('%A'),
            sorteio=str(sorteio),
            hora=hour,
            premio=prize,
            milhar=milhar,
            centena=milhar[-3:],
            dezena=milhar[-2:],
            grupo=g,
            bicho=mod.BICHOS[g],
            fonte='teste_meta_tabela1',
            grupo_publicado=g,
            bicho_publicado=mod.BICHOS[g],
        ))
    return rows


def key_for(item):
    date_s, slot, sorteio, _groups = item
    return date_s, str(sorteio), infer_hour(date_s, sorteio, slot)


def table1_strengths(base_groups):
    counts=Counter(int(g) for g in base_groups)
    scores={g:0 for g in range(1,26)}
    for source,mult in counts.items():
        for target in TABLE1.get(source,[]):
            scores[int(target)] += int(mult)
    denom=max(1, sum(counts.values()))
    return {g:scores[g]/denom for g in scores}

# Janela suficientemente grande para três blocos prospectivos, mantendo todo o
# histórico anterior dentro do DB para os seletores. O DB é alimentado em ordem,
# logo nenhum método consegue consultar o futuro.
TRANSITIONS_TO_BUILD = 360
start = max(0, len(history)-TRANSITIONS_TO_BUILD-1)

with tempfile.TemporaryDirectory() as td:
    db=Database(Path(td)/'admission.sqlite3')
    # Semente histórica: tudo até a primeira base da janela.
    for item in history[:start+1]:
        db.upsert_rows(draw_rows(item))

    records=[]
    failures=Counter()
    for idx in range(start, len(history)-1):
        base_item=history[idx]
        next_item=history[idx+1]
        d,s,h=key_for(base_item)
        base_draw=db.get_draw(d,s,h)
        if not base_draw:
            failures['base_missing'] += 1
            db.upsert_rows(draw_rows(next_item))
            continue
        try:
            reset=db.method_reset_coverage_v1(d,s,h,top_n=5)
            pull=db.method_convergencia_g5(d,s,h,top_n=5)
            sim=db.method_similarity_day(d,s,h,top_days=12)
            hist=db.method_historico_concentrado_v01(d,s,h,top_n=5)
            signals={
                'Reset Cobertura': db._decision_signal_payload(reset,'reset'),
                'Puxada Combinada': db._decision_signal_payload(pull,'pull'),
                'Similaridade': db._decision_signal_payload(sim,'similarity'),
            }
            strengths=table1_strengths(base_item[3])
            x20=[]; x21=[]
            for g in range(1,26):
                x=list(db._meta_feature_vector(g,signals,hist,base_draw))
                assert len(x)==20
                x20.append(x)
                x21.append(x+[float(strengths[g])])
            nd,ns,nh=key_for(next_item)
            records.append({
                'target_data':nd,'target_hora':nh,
                'winners':set(int(g) for g in next_item[3]),
                'x20':x20,'x21':x21,
            })
        except Exception as exc:
            failures[type(exc).__name__+':'+str(exc)[:80]] += 1
        db.upsert_rows(draw_rows(next_item))

print('RECORDS_BUILT',len(records),'FAILURES',sum(failures.values()))
if failures:
    print('FAILURE_TOP',failures.most_common(6))
assert len(records) >= 240, f'poucos registros válidos: {len(records)}'

# Implementação vetorizada da mesma regressão logística L2 usada pelo Meta.
# O treino continua começando do zero a cada rodada walk-forward.
import numpy as np

def weekday_label(date_s):
    return datetime.strptime(date_s,'%Y-%m-%d').weekday()


def fit_model(prior, focus, key):
    total=max(1,len(prior))
    X=[]; y=[]; sw=[]
    focus_hour=focus['target_hora']; focus_wd=weekday_label(focus['target_data'])
    for idx,rec in enumerate(prior):
        recency=0.75+0.50*((idx+1)/total)
        weight=recency
        if rec['target_hora']==focus_hour: weight += 0.60
        if weekday_label(rec['target_data'])==focus_wd: weight += 0.20
        winners=rec['winners']
        feats=rec[key]
        for g in range(1,26):
            X.append(feats[g-1]); y.append(1.0 if g in winners else 0.0); sw.append(weight)
    X=np.asarray(X,dtype=np.float64); y=np.asarray(y,dtype=np.float64); sw=np.asarray(sw,dtype=np.float64)
    pos=float(np.sum(y==1)); neg=float(len(y)-pos)
    if pos<=0 or neg<=0: return None
    positive_weight=min(4.0,max(1.0,neg/max(1.0,pos)))
    sw=sw*np.where(y==1,positive_weight,1.0)
    w=np.zeros(X.shape[1],dtype=np.float64); bias=0.0; lr=0.18
    for _epoch in range(240):
        z=np.clip(bias + X.dot(w),-60.0,60.0)
        p=1.0/(1.0+np.exp(-z))
        err=p-y
        totalw=max(float(sw.sum()),1e-9)
        gb=float(np.sum(sw*err))
        gw=X.T.dot(sw*err)
        bias -= lr*(gb/totalw)
        w -= lr*((gw/totalw)+0.025*w)
        lr=max(0.025,lr*0.992)
    return bias,w


def top5(model, feats):
    bias,w=model
    X=np.asarray(feats,dtype=np.float64)
    z=np.clip(bias+X.dot(w),-60.0,60.0)
    p=1.0/(1.0+np.exp(-z))
    # Mesmo desempate operacional: maior score; grupo menor só no empate.
    order=sorted(range(25), key=lambda i:(-float(p[i]),i+1))[:5]
    return {i+1 for i in order}

# Usa os 120 primeiros registros válidos como formação e mede os 180 seguintes.
# Limita a memória de treino a 180 snapshots anteriores — mais do que o Meta real
# possuía quando esta admissão foi solicitada — sem permitir o futuro.
EVAL_COUNT=min(180, len(records)-120)
eval_start=len(records)-EVAL_COUNT
wins=losses=ties=0
hits20=hits21=0
window_stats=[]
rounds=[]
for pos in range(eval_start,len(records)):
    current=records[pos]
    prior=records[max(0,pos-180):pos]
    assert len(prior)>=20
    m20=fit_model(prior,current,'x20')
    m21=fit_model(prior,current,'x21')
    assert m20 is not None and m21 is not None
    p20=top5(m20,current['x20']); p21=top5(m21,current['x21'])
    h20=len(p20 & current['winners']); h21=len(p21 & current['winners'])
    hits20 += h20; hits21 += h21
    if h21>h20: wins += 1
    elif h21<h20: losses += 1
    else: ties += 1
    rounds.append((h20,h21))

# Três janelas contíguas, definidas antes da decisão de admissão.
chunks=np.array_split(np.arange(len(rounds)),3)
window_wins=0
for wi,indices in enumerate(chunks,1):
    a=sum(rounds[int(i)][0] for i in indices)
    b=sum(rounds[int(i)][1] for i in indices)
    if b>a: window_wins += 1
    window_stats.append((wi,a,b,b-a))

net=hits21-hits20
admit = bool(net>0 and window_wins>=2 and wins>losses)
print('TABLE1_ADMISSION')
print('eval_rounds=',len(rounds))
print('meta20_hits=',hits20,'meta21_hits=',hits21,'net=',net)
print('round_wins=',wins,'losses=',losses,'ties=',ties)
print('windows=',window_stats,'window_wins=',window_wins)
print('DECISION=', 'ADMITIR' if admit else 'REJEITAR')

# Sanidade: em nenhum ponto a característica altera as primeiras 20.
assert all(len(x)==20 for r in records for x in r['x20'])
assert all(x21[:20]==x20 for r in records for x20,x21 in zip(r['x20'],r['x21']))

Path('/tmp/table1_admission_result.json').write_text(json.dumps({
    'records_built':len(records),'eval_rounds':len(rounds),'meta20_hits':hits20,
    'meta21_hits':hits21,'net':net,'wins':wins,'losses':losses,'ties':ties,
    'windows':window_stats,'window_wins':window_wins,'admit':admit,
},ensure_ascii=False,indent=2),encoding='utf-8')
