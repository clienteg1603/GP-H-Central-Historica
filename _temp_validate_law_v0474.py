from __future__ import annotations

import ast
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

BEFORE = Path('/tmp/gph_before_v0474.py').read_text(encoding='utf-8')
AFTER = Path('source/gph_central.py').read_text(encoding='utf-8')


def class_methods(source, cls_name):
    tree=ast.parse(source)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls_name)
    return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}

b=class_methods(BEFORE,'Database'); a=class_methods(AFTER,'Database')
added=set(a)-set(b); removed=set(b)-set(a)
changed={name for name in set(a)&set(b) if a[name]!=b[name]}
assert added=={'generate_gph_law_numbers'}, (added,removed,changed)
assert not removed, removed
assert changed=={'generate_centenas_meta_21','generate_dry_day_numbers'}, changed
print('OK: Database só alterou os dois geradores previstos e adicionou a Lei GP-H')

# Proteções explícitas mais importantes.
for name in (
    'method_reset_coverage_v1','method_convergencia_g5','method_similarity_day',
    'method_historico_concentrado_v01','_meta_feature_vector','_meta_fit_logit',
    '_meta_examples','meta_shadow_prediction','meta_play_formation_prediction',
    'centena_31_freeze_state','generate_group_combinations','build_decision_reading',
):
    assert b[name]==a[name], name
print('OK: Meta/Reset/Puxada/Similaridade/Histórico/Decisão/congelamento/combo AST-idênticos')

assert 'APP_VERSION = "0.47.4"' in AFTER
assert 'Oficial • Reset + Lei GP-H' in AFTER
assert 'self.play_total_spin.configure(state="disabled")' not in ast.get_source_segment(
    AFTER,
    next(n for n in ast.walk(ast.parse(AFTER)) if isinstance(n,ast.FunctionDef) and n.name=='play_controls_changed')
)

os.environ['GPH_DISABLE_STARTUP_DIALOGS']='1'
spec=importlib.util.spec_from_file_location('gph_law_test',Path('source/gph_central.py'))
mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
Database=mod.Database

with tempfile.TemporaryDirectory() as td:
    db=Database(Path(td)/'law.sqlite3')

    def fake_rank(group, kind='Centena', scope='1º–5º', date_to=None):
        group=int(group)
        start=(group-1)*4+1
        dezenas=[f'{d%100:02d}' for d in range(start,start+4)]
        if kind=='Dezena':
            return [
                {'numero':d,'ocorrencias':100-i*10,'ultima':f'2026-08-{20-i:02d}|09:00|PPT|1'}
                for i,d in enumerate(dezenas)
            ]
        width=3 if kind=='Centena' else 4
        limit=1000 if kind=='Centena' else 10000
        out=[]
        for dpos,d in enumerate(dezenas):
            nums=[n for n in range(limit) if n%100==int(d)]
            for pos,n in enumerate(nums):
                out.append({'numero':f'{n:0{width}d}','ocorrencias':10000-dpos*100-pos,'ultima':'2026-08-20|09:00|PPT|1'})
        out.sort(key=lambda r:(-r['ocorrencias'],int(r['numero'])))
        return out

    db.number_rankings_for_group=fake_rank
    db.centena_31_freeze_state=lambda g,p,previous_draw=None: {
        'frozen': int(g)==1, 'trigger': {'teste':True} if int(g)==1 else None, 'released_by':None
    }
    previous={'data':'2026-09-09','sorteio':'CORUJA','hora':'21:00','prizes':[]}

    r=db.generate_gph_law_numbers([1,2,3,4,5],'Centena',20,previous)
    assert r['counts']=={1:4,2:4,3:4,4:4,5:4}
    assert [(x['main_count'],x['extra_count']) for x in r['animals']]==[(3,1)]*5
    assert r['animals'][0]['frozen'] is True
    assert r['animals'][0]['main_dezena']==r['animals'][0]['segunda']
    assert r['animals'][0]['extra_dezena']==r['animals'][0]['terceira']
    assert all(row['dezena_base'] in {r['animals'][0]['segunda'],r['animals'][0]['terceira']} for row in r['rows'] if row['grupo']==1)
    print('OK: 20 Centenas / 5 bichos => 4 por bicho => 3+1; congelamento muda para 2ª+3ª')

    r=db.generate_gph_law_numbers([2,3,4],'Centena',10,previous)
    assert r['counts']=={2:4,3:3,4:3}
    assert [(x['main_count'],x['extra_count']) for x in r['animals']]==[(3,1),(2,1),(2,1)]
    print('OK: 10 Centenas / 3 bichos => 4+3+3 com 3+1 / 2+1 / 2+1')

    r=db.generate_gph_law_numbers([2,3,4,5],'Centena',30,previous)
    assert r['counts']=={2:8,3:8,4:7,5:7}
    assert [(x['main_count'],x['extra_count']) for x in r['animals']]==[(5,3),(5,3),(5,2),(5,2)]
    print('OK: 30 Centenas / 4 bichos => 8+8+7+7 com proporção acordada')

    r=db.generate_gph_law_numbers([2,3,4],'Milhar',10,previous)
    assert r['counts']=={2:4,3:3,4:3}
    assert all(len(row['numero'])==4 for row in r['rows'])
    assert [(x['main_count'],x['extra_count']) for x in r['animals']]==[(3,1),(2,1),(2,1)]
    print('OK: Milhar usa a mesma Lei GP-H e a mesma divisão por dezenas')

    try:
        db.generate_gph_law_numbers([2],'Centena',20,previous)
    except ValueError as exc:
        assert 'até 15' in str(exc)
    else:
        raise AssertionError('limite 2:1 de Centena deveria bloquear 20 em um único bicho')

    combos=db.generate_group_combinations([15,21,2,9,4],'Terno de Grupo',total=5)
    got=[row['numero'] for row in combos['rows']]
    assert got==['15-21-02','15-21-09','15-02-09','21-02-09','15-21-04'],got
    print('OK: fechamento v0.47.3 preservado — líder em 4/5, não 5/5')

    db.method_dry_day_first_prize=lambda **kw: {'selected':[{'grupo':2},{'grupo':3},{'grupo':4}]}
    seca=db.generate_dry_day_numbers('2026-09-09','Centena',total=6,top_animals=3,previous_draw=previous)
    assert seca['groups']==[2,3,4]
    assert seca['generation_law']=='GP-H v1'
    assert seca['selector_scope']=='1º'
    print('OK: Seca preserva seletor 1º prêmio e também passa pela Lei GP-H')

# Integração da tela: todos os seletores automáticos numéricos passam pelo gerador comum.
tree=ast.parse(AFTER)
play=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='play_generate')
seg=ast.get_source_segment(AFTER,play) or ''
assert 'generate_gph_law_numbers' in seg
assert 'top_n=requested_animals' in seg
assert 'groups = groups[:requested_animals]' in seg
assert 'top_animals=requested_animals' in seg
assert 'generate_centenas_3plus1(' not in seg
assert 'generate_centenas_meta_21(' not in seg
print('OK: Jogar roteia Meta/Reset/Puxada/Similaridade/Seca para a Lei comum onde aplicável')
