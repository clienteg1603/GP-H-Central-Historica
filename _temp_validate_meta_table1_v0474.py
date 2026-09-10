from __future__ import annotations

import ast
import importlib.util
import math
import os
import sys
import tempfile
from pathlib import Path

BEFORE_PATH=Path('/tmp/gph_before_meta_v0474.py')
AFTER_PATH=Path('source/gph_central.py')
BEFORE=BEFORE_PATH.read_text(encoding='utf-8')
AFTER=AFTER_PATH.read_text(encoding='utf-8')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod
    spec.loader.exec_module(mod)
    return mod


def methods(source,cls_name):
    tree=ast.parse(source)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls_name)
    return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}

bm=methods(BEFORE,'Database'); am=methods(AFTER,'Database')
added=set(am)-set(bm); removed=set(bm)-set(am)
changed={n for n in set(am)&set(bm) if am[n]!=bm[n]}
allowed={'_meta_feature_vector','meta_walk_forward_evaluation','meta_shadow_prediction','meta_play_formation_prediction'}
assert not added, added
assert not removed, removed
assert changed <= allowed, changed
assert '_meta_feature_vector' in changed
print('OK: Database mudou somente o vetor Meta e rotinas Meta que carregam rótulo/model_version')

for name in (
    'method_reset_coverage_v1','method_convergencia_g5','method_similarity_day',
    'method_historico_concentrado_v01','build_decision_reading','_meta_fit_logit',
    '_meta_examples','centena_31_freeze_state','generate_group_combinations',
    'generate_gph_law_numbers','generate_centenas_meta_21','generate_dry_day_numbers',
):
    assert bm[name]==am[name], name
print('OK: seletores, Decisão, treinador Meta, congelamento e Lei GP-H permanecem AST-idênticos')

os.environ['GPH_DISABLE_STARTUP_DIALOGS']='1'
before=load('gph_before_meta',BEFORE_PATH)
after=load('gph_after_meta',AFTER_PATH)

signals={
    'Reset Cobertura':{'groups':[13,2,20,5,7],'scores':[90,70,60,50,40]},
    'Puxada Combinada':{'groups':[13,6,21,4,9],'source_counts':[4,3,2,2,1],'sum_prob':[80,60,40,30,20]},
    'Similaridade':{'groups':[4,13,25,2,8],'weighted_shares':[30,25,20,15,10]},
}
historical={'selected':[
    {'grupo':13,'indication_count':4,'sum_prob':70},
    {'grupo':5,'indication_count':3,'sum_prob':50},
    {'grupo':7,'indication_count':2,'sum_prob':35},
    {'grupo':2,'indication_count':2,'sum_prob':30},
    {'grupo':20,'indication_count':1,'sum_prob':20},
]}
base={'prizes':[{'grupo':1},{'grupo':2},{'grupo':3},{'grupo':4},{'grupo':5}]}
old_db=before.Database.__new__(before.Database)
new_db=after.Database.__new__(after.Database)
old_vec=old_db._meta_feature_vector(13,signals,historical,base)
new_vec=new_db._meta_feature_vector(13,signals,historical,base)
assert len(old_vec)==20,len(old_vec)
assert len(new_vec)==21,len(new_vec)
assert new_vec[:20]==old_vec,(old_vec,new_vec[:20])
assert math.isclose(new_vec[20],0.8,rel_tol=0,abs_tol=1e-12),new_vec[20]
print('OK: primeiras 20 características são idênticas; Tabela 1 entrou somente como 21ª (13 => 4/5 = 0,8)')

# Repetição da extração-base conta novamente, sem qualquer acesso ao resultado futuro.
base_repeat={'prizes':[{'grupo':1},{'grupo':1},{'grupo':3},{'grupo':4},{'grupo':5}]}
v_repeat=new_db._meta_feature_vector(13,signals,historical,base_repeat)
assert math.isclose(v_repeat[20],0.8,abs_tol=1e-12)
print('OK: repetição da base alimenta o sinal Tabela 1 como definido no estudo')

# O treinador existente é dimensionalmente genérico e passa a devolver 21 coeficientes sem reescrita.
examples=[]
for i in range(50):
    x=[0.0]*21
    x[i%21]=(i%5)/4.0
    examples.append((x,1 if i%6==0 else 0,1.0))
model=after.Database._meta_fit_logit(examples,epochs=45)
assert model and len(model['coefficients'])==21
print('OK: treinador logístico existente aceita 21 características sem alteração')

assert 'META_TABLE1_PULLS = {' in AFTER
assert 'META_LOGIT_NATIVE_V2_TABLE1' in AFTER
assert 'GP-H META v0.2' in AFTER
assert '★ META • GP-H Meta v0.2' in AFTER
assert 'selector = "GP-H Meta v0.2"' in AFTER
# Histórico embutido continua registrando corretamente as versões antigas.
assert '• v0.42.0 — Walk-Forward rigoroso do GP-H Meta v0.1' in AFTER
assert '• v0.41.0 — GP-H Meta v0.1 em sombra' in AFTER
print('OK: Meta novo identificado como v0.2 sem reescrever o histórico v0.1')

# A Lei Universal já validada nesta release precisa continuar presente na integração final.
assert 'def generate_gph_law_numbers(' in AFTER
assert 'Oficial • Reset + Lei GP-H' in AFTER
assert 'generation_law": "GP-H v1"' in AFTER
print('OK: Lei de Geração GP-H universal continua presente após admissão da Tabela 1')
