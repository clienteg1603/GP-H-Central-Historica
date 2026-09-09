import ast
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

SOURCE = Path('source/gph_central.py')
BASELINE = Path('/tmp/gph_v0469_before.py')

before_s = BASELINE.read_text(encoding='utf-8')
after_s = SOURCE.read_text(encoding='utf-8')

# Interface: botões manuais de auditoria saíram, automação continua.
for text in ('text="Auditar este jogo"', 'text="Auditar agora"', 'text="Auditar jogos"'):
    assert text not in after_s, text
assert 'text="Excluir esta modalidade"' in after_s
assert 'APP_VERSION = "0.47.0"' in after_s


def function_source(source, name):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ''
    raise AssertionError(f'função {name} ausente')

for fname in ('after_web_update', 'after_manual_saved'):
    seg = function_source(after_s, fname)
    assert 'audit_frozen_games' in seg, f'{fname} perdeu auditoria automática'

# Proteção do cérebro/métodos sensíveis.
protected = {
    '_meta_feature_names','_meta_feature_vector','_meta_examples',
    '_meta_fit_logit','_meta_model_score','_meta_training_records',
    'meta_shadow_prediction','meta_play_formation_prediction','freeze_meta_snapshot',
    'meta_walk_forward','method_reset_coverage_v1','method_convergencia_g5',
    'method_similarity_day','method_historico_concentrado_v01',
    'generate_centenas_3plus1','generate_centenas_meta_21','centena_31_freeze_state',
    'decision_adaptive_context','decision_operational_recommendation',
    'audit_frozen_games','refresh_ticket_totals','delete_ticket',
}

def db_methods(source):
    tree = ast.parse(source)
    out = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == 'Database':
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[item.name] = ast.dump(item, include_attributes=False)
    return out

a = db_methods(before_s)
b = db_methods(after_s)
missing = sorted(x for x in protected if x not in a or x not in b)
changed = sorted(x for x in protected if x in a and x in b and a[x] != b[x])
assert not missing and not changed, (missing, changed)
assert 'delete_ticket_game' in b
print(f'OK: {len(protected)} métodos protegidos AST-idênticos')

# Teste real em SQLite da exclusão parcial.
os.environ['GPH_DISABLE_STARTUP_DIALOGS'] = '1'
spec = importlib.util.spec_from_file_location('gph_v0470_test', SOURCE)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def generic_insert(con, table, overrides):
    info = con.execute(f'PRAGMA table_info({table})').fetchall()
    cols = []
    vals = []
    for row in info:
        name = row['name']
        ctype = str(row['type'] or '').upper()
        notnull = bool(row['notnull'])
        default = row['dflt_value']
        pk = bool(row['pk'])
        if pk and name == 'id':
            continue
        if name in overrides:
            value = overrides[name]
        elif notnull and default is None:
            if 'INT' in ctype:
                value = 0
            elif any(x in ctype for x in ('REAL','FLOA','DOUB','NUM')):
                value = 0.0
            else:
                value = ''
        else:
            continue
        cols.append(name)
        vals.append(value)
    marks = ','.join('?' for _ in cols)
    cur = con.execute(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({marks})",
        vals,
    )
    return int(cur.lastrowid)

with tempfile.TemporaryDirectory() as td:
    db = mod.Database(Path(td) / 'test.db')
    with db.connect() as con:
        ticket_id = generic_insert(con, 'bilhetes', {
            'alvo_data':'2026-09-09','alvo_sorteio':'CORUJA','alvo_hora':'21:00',
            'status':'PENDENTE','total_apostado':60.0,'retorno_real':0.0,
            'resultado_liquido':0.0,
        })
        games = []
        for idx, (tipo, valor) in enumerate((('Centena',10.0),('Milhar',20.0),('Grupo',30.0)), start=1):
            gid = generic_insert(con, 'jogos_congelados', {
                'bilhete_id':ticket_id,
                'base_data':'2026-09-09','base_sorteio':'PTM','base_hora':'11:00',
                'alvo_data':'2026-09-09','alvo_sorteio':'CORUJA','alvo_hora':'21:00',
                'tipo':tipo,'escopo':'1º–5º','estrategia':'Teste v0.47.0',
                'status':'PENDENTE','total_itens':1,'jogado':1,
                'valor_unitario':valor,'valor_total':valor,
                'retorno_real':0.0,'resultado_liquido':0.0,
            })
            games.append(gid)
            generic_insert(con, 'jogos_itens', {
                'jogo_id':gid,'ordem':1,'grupo':idx,'bicho':'TESTE',
                'numero':str(100+idx),'regra':'Teste',
            })

    # Recalcula para garantir estado inicial coerente.
    db.refresh_ticket_totals(ticket_id)
    detail = db.ticket_details(ticket_id)
    assert len(db.games_for_ticket(ticket_id)) == 3
    assert abs(float(detail['total_apostado']) - 60.0) < 1e-9

    r1 = db.delete_ticket_game(ticket_id, games[0])
    assert r1['deleted'] and not r1['ticket_deleted'], r1
    assert r1['remaining_games'] == 2, r1
    assert len(db.games_for_ticket(ticket_id)) == 2
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM jogos_itens WHERE jogo_id=?',(games[0],)).fetchone()[0] == 0
        t = con.execute('SELECT total_apostado FROM bilhetes WHERE id=?',(ticket_id,)).fetchone()
        assert t is not None and abs(float(t[0]) - 50.0) < 1e-9, t

    r2 = db.delete_ticket_game(ticket_id, games[1])
    assert r2['remaining_games'] == 1 and not r2['ticket_deleted'], r2
    r3 = db.delete_ticket_game(ticket_id, games[2])
    assert r3['ticket_deleted'] and r3['remaining_games'] == 0, r3
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM bilhetes WHERE id=?',(ticket_id,)).fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM jogos_congelados WHERE bilhete_id=?',(ticket_id,)).fetchone()[0] == 0

print('OK: bilhete 3 modalidades -> exclui 1, preserva 2, recalcula R$ 50; última remove bilhete vazio')
print('OK: auditoria automática preservada e botões manuais removidos')
