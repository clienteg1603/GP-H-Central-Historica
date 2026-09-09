from pathlib import Path
import ast
import importlib.util
import sys

src_path = Path('source/gph_central.py')
doc_path = Path('source/DOCUMENTACAO_GP-H.txt')
before_source = src_path.read_text(encoding='utf-8')
s = before_source


def one(old, new, label):
    global s
    n = s.count(old)
    if n != 1:
        raise SystemExit(f'{label}: esperado 1 trecho, encontrado {n}')
    s = s.replace(old, new, 1)


one('GP-H Central Histórica v0.46.8', 'GP-H Central Histórica v0.46.9', 'doc version')
one('APP_VERSION = "0.46.8"', 'APP_VERSION = "0.46.9"', 'app version')

marker = '\n    def freeze_meta_snapshot(self, snapshot=None, force=False):\n'
if s.count(marker) != 1:
    raise SystemExit('marcador freeze_meta_snapshot não único')

formation_method = r'''

    def meta_play_formation_prediction(self, target, base_draw, signals, training_limit=160):
        """Ranking jogável do Meta antes da maturidade mínima de 20 snapshots.

        Esta camada NÃO altera o Meta sombra nem sua trava científica de 20
        snapshots. Ela usa exatamente as mesmas características, exemplos,
        regressão logística L2 e corte temporal do Meta, mas permite que a tela
        Jogar use o aprendizado disponível desde o primeiro snapshot auditado.
        Até 19 snapshots o resultado é explicitamente rotulado EM FORMAÇÃO.
        """
        target = dict(target or {})
        base_draw = dict(base_draw or {})
        signals = signals or {}
        if not target or not base_draw:
            return {"available": False, "status": "SEM DADOS", "reason": "Alvo/base indisponível."}
        if self.get_draw(target.get("data"), target.get("sorteio"), target.get("hora")):
            return {
                "available": False,
                "status": "BLOQUEADO",
                "reason": "Resultado-alvo já existe; Meta em formação não é reconstruído retroativamente.",
            }

        records = self._meta_training_records(before_target=target, limit=training_limit)
        n = len(records)
        same_hour = sum(
            1 for r in records
            if str(r.get("target_hora") or "") == str(target.get("hora") or "")
        )
        if n < 1:
            return {
                "available": False,
                "status": "SEM AMOSTRA AUDITADA",
                "training_snapshots": 0,
                "same_hour_snapshots": 0,
                "minimum_play_snapshots": 1,
                "minimum_maturity_snapshots": 20,
                "reason": "O GP-H Meta precisa de pelo menos 1 snapshot auditado anterior para iniciar o modo jogável em formação.",
                "model_version": "META_LOGIT_NATIVE_V1",
                "lookahead_safe": True,
                "play_only": True,
            }

        try:
            historical = self.method_historico_concentrado_v01(
                base_draw.get("data"), base_draw.get("sorteio"), base_draw.get("hora"), top_n=5
            )
        except Exception:
            historical = {"selected": []}

        examples = self._meta_examples(records, focus_target=target)
        model = self._meta_fit_logit(examples)
        if not model:
            return {
                "available": False,
                "status": "SEM MODELO",
                "training_snapshots": n,
                "reason": "Ajuste logístico do Meta em formação indisponível.",
                "lookahead_safe": True,
                "play_only": True,
            }

        ranking = []
        for group in range(1, 26):
            x = self._meta_feature_vector(group, signals, historical, base_draw)
            ranking.append({
                "grupo": group,
                "bicho": BICHOS[group],
                "score": round(self._meta_model_score(model, x), 3),
                "features": [round(v, 6) for v in x],
            })
        ranking.sort(key=lambda r: (-r["score"], r["grupo"]))
        for idx, row in enumerate(ranking, start=1):
            row["rank"] = idx

        return {
            "available": True,
            "status": "EM FORMAÇÃO",
            "objective": "1º–5º",
            "model_version": "META_LOGIT_NATIVE_V1",
            "training_snapshots": n,
            "training_examples": len(examples),
            "same_hour_snapshots": same_hour,
            "minimum_play_snapshots": 1,
            "minimum_maturity_snapshots": 20,
            "formation_progress_pct": round(min(100.0, (n / 20.0) * 100.0), 1),
            "groups": [r["grupo"] for r in ranking[:5]],
            "animals": [r["bicho"] for r in ranking[:5]],
            "scores": [r["score"] for r in ranking[:5]],
            "ranking": ranking,
            "input_groups": {
                "Reset Cobertura": list((signals.get("Reset Cobertura") or {}).get("groups") or [])[:5],
                "Puxada Combinada": list((signals.get("Puxada Combinada") or {}).get("groups") or [])[:5],
                "Similaridade": list((signals.get("Similaridade") or {}).get("groups") or [])[:5],
                "Histórico Concentrado": [int(r.get("grupo")) for r in (historical.get("selected") or [])[:5]],
            },
            "model": {**model, "feature_names": list(self._meta_feature_names())},
            "lookahead_safe": True,
            "play_only": True,
            "shadow_gate_preserved": True,
            "note": "Ranking preliminar jogável. Mesma arquitetura do Meta; maturidade oficial continua em 20 snapshots auditados.",
        }
'''
s = s.replace(marker, formation_method + marker, 1)

old = '''                snapshot, _meta_created = self.db.freeze_meta_snapshot(snapshot=snapshot)\n                meta_payload = copy.deepcopy(snapshot.get("meta") or {})\n                if not meta_payload.get("available"):\n                    reason = meta_payload.get("reason") or meta_payload.get("status") or "Meta indisponível"\n                    raise ValueError(f"GP-H Meta v0.1 ainda não pode gerar esta rodada: {reason}")\n'''
new = '''                snapshot, _meta_created = self.db.freeze_meta_snapshot(snapshot=snapshot)\n                meta_payload = copy.deepcopy(snapshot.get("meta") or {})\n                if not meta_payload.get("available"):\n                    if meta_payload.get("status") == "AMOSTRA INSUFICIENTE":\n                        meta_base = self.db.get_draw(\n                            snapshot.get("base_data"),\n                            snapshot.get("base_sorteio"),\n                            snapshot.get("base_hora"),\n                        ) or latest\n                        formation = self.db.meta_play_formation_prediction(\n                            target=snap_target,\n                            base_draw=meta_base,\n                            signals=snapshot.get("signals") or {},\n                        )\n                        if formation.get("available"):\n                            meta_payload = formation\n                        else:\n                            reason = formation.get("reason") or formation.get("status") or "Meta em formação indisponível"\n                            raise ValueError(f"GP-H Meta v0.1 ainda não pode gerar esta rodada: {reason}")\n                    else:\n                        reason = meta_payload.get("reason") or meta_payload.get("status") or "Meta indisponível"\n                        raise ValueError(f"GP-H Meta v0.1 ainda não pode gerar esta rodada: {reason}")\n'''
one(old, new, 'fallback jogável em formação')

old = '''                if hasattr(self, "play_meta_status"):\n                    names = ", ".join(BICHOS[g].title() for g in groups[:8])\n                    suffix = "..." if len(groups) > 8 else ""\n                    self.play_meta_status.configure(\n                        text=(\n                            f"Top {len(groups)} congelado para esta rodada • treino: "\n                            f"{int(meta_payload.get('training_snapshots') or 0)} snapshots • {names}{suffix}"\n                        )\n                    )\n'''
new = '''                if hasattr(self, "play_meta_status"):\n                    names = ", ".join(BICHOS[g].title() for g in groups[:8])\n                    suffix = "..." if len(groups) > 8 else ""\n                    n_train = int(meta_payload.get("training_snapshots") or 0)\n                    if meta_payload.get("status") == "EM FORMAÇÃO":\n                        status_text = (\n                            f"META EM FORMAÇÃO • Top {len(groups)} • treino: {n_train}/20 snapshots • "\n                            f"{names}{suffix}"\n                        )\n                    else:\n                        status_text = (\n                            f"{meta_payload.get('status') or 'META'} • Top {len(groups)} congelado para esta rodada • "\n                            f"treino: {n_train} snapshots • {names}{suffix}"\n                        )\n                    self.play_meta_status.configure(text=status_text)\n'''
one(old, new, 'texto de status Meta')

one(
    'Ranking aprendido continuamente com rodadas auditadas. O cérebro permanece congelado em estrutura; somente os dados de treino avançam.',
    'Pode jogar desde o primeiro snapshot auditado. Até 20, fica marcado como META EM FORMAÇÃO; a arquitetura do cérebro e o corte anti-lookahead permanecem os mesmos.',
    'descrição cartão Meta',
)

src_path.write_text(s, encoding='utf-8')
compile(s, str(src_path), 'exec')

# Protege o cérebro existente: a nova fase é play-only.
protected = {
    '_meta_feature_names','_meta_feature_vector','_meta_examples',
    '_meta_fit_logit','_meta_model_score','_meta_training_records',
    'meta_shadow_prediction','freeze_meta_snapshot','meta_walk_forward',
    'method_reset_coverage_v1','method_convergencia_g5','method_similarity_day',
    'method_historico_concentrado_v01','generate_centenas_3plus1',
    'centena_31_freeze_state','decision_adaptive_context',
    'decision_operational_recommendation',
}

def methods(text):
    tree = ast.parse(text)
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == 'Database':
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[item.name] = ast.dump(item, include_attributes=False)
    return out

a = methods(before_source)
b = methods(s)
missing = sorted(x for x in protected if x not in a or x not in b)
changed = sorted(x for x in protected if x in a and x in b and a[x] != b[x])
if missing or changed:
    raise SystemExit(f'Proteção falhou. Ausentes={missing} Alterados={changed}')
print(f'OK: {len(protected)} métodos sensíveis AST-idênticos')

# Teste funcional com 1 snapshot: play funciona, sombra continua bloqueada.
spec = importlib.util.spec_from_file_location('gph_meta_form_test', src_path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

class Dummy:
    meta_play_formation_prediction = mod.Database.meta_play_formation_prediction
    meta_shadow_prediction = mod.Database.meta_shadow_prediction
    def __init__(self, n): self.n = n
    def get_draw(self, *a, **k): return None
    def _meta_training_records(self, before_target=None, limit=160):
        return [{'target_hora':'11:00'} for _ in range(self.n)]
    def method_historico_concentrado_v01(self, *a, **k): return {'selected':[]}
    def _meta_examples(self, records, focus_target=None):
        out=[]
        for _ in records:
            out.append(([0.10]+[0.0]*19,1,1.0))
            out.append(([0.90]+[0.0]*19,0,1.0))
        return out
    def _meta_fit_logit(self, examples): return mod.Database._meta_fit_logit(examples)
    def _meta_model_score(self, model, x): return mod.Database._meta_model_score(model, x)
    def _meta_feature_vector(self, group, signals, historical, base_draw):
        return [group/25.0]+[0.0]*19
    def _meta_feature_names(self): return tuple(f'f{i}' for i in range(20))

target={'data':'2026-09-10','sorteio':'PTM','hora':'11:00'}
base={'data':'2026-09-10','sorteio':'PPT','hora':'09:00','prizes':[]}
d=Dummy(1)
play=d.meta_play_formation_prediction(target,base,{})
assert play['available'] is True and play['status']=='EM FORMAÇÃO', play
assert play['training_snapshots']==1 and len(play['ranking'])==25, play
shadow=d.meta_shadow_prediction(target,base,{})
assert shadow['available'] is False and shadow['status']=='AMOSTRA INSUFICIENTE', shadow
zero=Dummy(0).meta_play_formation_prediction(target,base,{})
assert zero['available'] is False and zero['status']=='SEM AMOSTRA AUDITADA', zero
print('OK: 1 snapshot joga como EM FORMAÇÃO; Meta sombra continua exigindo 20')

# Documentação.
doc = doc_path.read_text(encoding='utf-8')
entry = '''REVISÃO v0.46.9 — META JOGÁVEL EM FORMAÇÃO\n- Corrige a v0.46.8: o GP-H Meta passa a poder gerar jogo antes dos 20 snapshots, desde que exista pelo menos 1 snapshot auditado anterior.\n- A trava científica do Meta sombra NÃO foi removida: meta_shadow_prediction continua exigindo 20 snapshots para ficar disponível na avaliação oficial.\n- A nova camada play-only META EM FORMAÇÃO usa as mesmas 20 características, a mesma regressão logística L2, os mesmos pesos de exemplo e o mesmo corte temporal/anti-lookahead do Meta.\n- De 1 a 19 snapshots, o jogo mostra claramente META EM FORMAÇÃO e o progresso n/20; a partir de 20, o módulo Jogar volta a usar automaticamente a leitura Meta oficial congelada.\n- Leituras antigas AMOSTRA INSUFICIENTE permanecem preservadas; o Jogar calcula o ranking preliminar prospectivo sem reescrever o snapshot sombra.\n- Reset, Puxada, Similaridade, Histórico Concentrado, 3+1, Decisão, Walk-Forward e meta_shadow_prediction permanecem inalterados.\n\n'''
marker_doc='REVISÃO v0.46.8 —'
if marker_doc not in doc:
    raise SystemExit('marcador documentação v0.46.8 não encontrado')
doc = doc.replace(marker_doc, entry + marker_doc, 1)
doc_path.write_text(doc, encoding='utf-8')
print('PATCH v0.46.9 OK')
