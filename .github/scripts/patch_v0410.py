from pathlib import Path
import ast, re

SRC=Path('source/gph_central.py')
DOC=Path('source/DOCUMENTACAO_GP-H.txt')
text=SRC.read_text(encoding='utf-8')
if 'APP_VERSION = "0.40.0"' not in text:
    raise SystemExit('v0.41.0 deve partir exatamente da v0.40.0')

# Trava de motores oficiais: Meta é SOMBRA e não pode mudar nenhum deles.
CRITICAL={
    'method_reset_coverage_v1','method_convergencia_g5','method_similarity_day',
    'method_historico_concentrado_v01','decision_contextual_evidence',
    'generate_centenas_3plus1','centena_31_freeze_state',
    'generate_historical_concentrated_bundle','historical_pulls',
}
def function_dumps(src):
    tree=ast.parse(src); out={}
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in CRITICAL:
            out[n.name]=ast.dump(n,include_attributes=False)
    miss=CRITICAL-set(out)
    if miss: raise SystemExit(f'Funções críticas ausentes: {sorted(miss)}')
    return out
before= function_dumps(text)

# math.exp sem dependência externa.
text=text.replace('from math import comb\n','from math import comb, exp\n',1)

# ---------------------------------------------------------------------
# Schema v0.41.0 — Meta dentro de decision_snapshots.
# ---------------------------------------------------------------------
anchor='''            for column, sql_type in (\n                ("contextual_json", "TEXT"),\n                ("contextual_frozen_at", "TEXT"),\n                ("contextual_audit_json", "TEXT"),\n            ):\n                if column not in decision_columns:\n                    con.execute(f"ALTER TABLE decision_snapshots ADD COLUMN {column} {sql_type}")\n\n            # v0.30.0 — Laboratório Sombra.\n'''
insert='''            for column, sql_type in (\n                ("contextual_json", "TEXT"),\n                ("contextual_frozen_at", "TEXT"),\n                ("contextual_audit_json", "TEXT"),\n            ):\n                if column not in decision_columns:\n                    con.execute(f"ALTER TABLE decision_snapshots ADD COLUMN {column} {sql_type}")\n\n            # v0.41.0 — GP-H Meta v0.1 em SOMBRA. A primeira leitura do\n            # meta-modelo também é congelada antes do resultado. Bases antigas\n            # não recebem backfill: treinamento histórico usa somente sinais\n            # que já estavam congelados e reconstruções cutoff-safe.\n            decision_columns = {\n                str(row[1]) for row in con.execute("PRAGMA table_info(decision_snapshots)").fetchall()\n            }\n            for column, sql_type in (\n                ("meta_json", "TEXT"),\n                ("meta_frozen_at", "TEXT"),\n                ("meta_audit_json", "TEXT"),\n            ):\n                if column not in decision_columns:\n                    con.execute(f"ALTER TABLE decision_snapshots ADD COLUMN {column} {sql_type}")\n\n            # v0.30.0 — Laboratório Sombra.\n'''
if anchor not in text: raise SystemExit('âncora schema contextual não encontrada')
text=text.replace(anchor,insert,1)

# Parser de snapshot.
old='''            "contextual_json": {},\n            "contextual_audit_json": {},\n            "result_groups_json": [],\n'''
new='''            "contextual_json": {},\n            "contextual_audit_json": {},\n            "meta_json": {},\n            "meta_audit_json": {},\n            "result_groups_json": [],\n'''
if old not in text: raise SystemExit('parser decision snapshot não encontrado')
text=text.replace(old,new,1)

# ---------------------------------------------------------------------
# Motor Meta nativo. Inserido antes do congelamento contextual.
# ---------------------------------------------------------------------
meta_code=r'''    # ========================================================
    # GP-H META v0.1 — v0.41.0
    # Meta-aprendizado SOMBRA, sem alterar qualquer método oficial.
    # Modelo: regressão logística L2 nativa, determinística e sem dependências.
    # ========================================================
    @staticmethod
    def _meta_feature_names():
        return (
            "reset_sel", "reset_rank", "reset_strength",
            "pull_sel", "pull_rank", "pull_sources", "pull_strength",
            "sim_sel", "sim_rank", "sim_strength",
            "hist_sel", "hist_rank", "hist_indications", "hist_strength",
            "agreement", "agreement_2plus", "agreement_3plus", "agreement_4",
            "base_present", "base_repeat",
        )

    @staticmethod
    def _meta_squash(value, scale):
        try:
            value=max(0.0,float(value)); scale=max(1e-9,float(scale))
        except Exception:
            return 0.0
        return value/(value+scale)

    @staticmethod
    def _meta_sigmoid(z):
        z=max(-35.0,min(35.0,float(z)))
        return 1.0/(1.0+exp(-z))

    @staticmethod
    def _meta_round_key(data, hora, fallback=0):
        try:
            day=datetime.strptime(str(data),"%Y-%m-%d").toordinal()
        except Exception:
            day=0
        m=re.search(r"(\d{1,2})(?::(\d{2}))?",str(hora or ""))
        minutes=(int(m.group(1))*60 + int(m.group(2) or 0)) if m else int(fallback or 0)
        return day,minutes,int(fallback or 0)

    @staticmethod
    def _meta_selected_position(groups, group):
        try:
            return [int(g) for g in (groups or [])].index(int(group))
        except Exception:
            return None

    def _meta_feature_vector(self, group, signals, historical, base_draw):
        group=int(group)
        signals=signals or {}
        features=[]

        reset=signals.get("Reset Cobertura") or {}
        pos=self._meta_selected_position(reset.get("groups"),group)
        rsel=1.0 if pos is not None else 0.0
        rrank=(5-pos)/5.0 if pos is not None and pos < 5 else 0.0
        rscores=reset.get("scores") or []
        rstrength=self._meta_squash(rscores[pos] if pos is not None and pos < len(rscores) else 0,50.0)
        features += [rsel,rrank,rstrength]

        pull=signals.get("Puxada Combinada") or {}
        pos=self._meta_selected_position(pull.get("groups"),group)
        psel=1.0 if pos is not None else 0.0
        prank=(5-pos)/5.0 if pos is not None and pos < 5 else 0.0
        psrc=pull.get("source_counts") or []
        pprob=pull.get("sum_prob") or []
        psources=min(1.0,max(0.0,float(psrc[pos] if pos is not None and pos < len(psrc) else 0))/5.0)
        pstrength=self._meta_squash(pprob[pos] if pos is not None and pos < len(pprob) else 0,60.0)
        features += [psel,prank,psources,pstrength]

        sim=signals.get("Similaridade") or {}
        pos=self._meta_selected_position(sim.get("groups"),group)
        ssel=1.0 if pos is not None else 0.0
        srank=(5-pos)/5.0 if pos is not None and pos < 5 else 0.0
        shares=sim.get("weighted_shares") or []
        sstrength=self._meta_squash(shares[pos] if pos is not None and pos < len(shares) else 0,30.0)
        features += [ssel,srank,sstrength]

        hrows=(historical or {}).get("selected") or []
        hpos=None; hrow={}
        for i,row in enumerate(hrows[:5]):
            try:
                if int(row.get("grupo")) == group:
                    hpos=i; hrow=row; break
            except Exception:
                pass
        hsel=1.0 if hpos is not None else 0.0
        hrank=(5-hpos)/5.0 if hpos is not None and hpos < 5 else 0.0
        hind=min(1.0,max(0.0,float(hrow.get("indication_count") or 0))/5.0) if hrow else 0.0
        hstrength=self._meta_squash(hrow.get("sum_prob") or 0,60.0) if hrow else 0.0
        features += [hsel,hrank,hind,hstrength]

        agreement=int(rsel+psel+ssel+hsel)
        features += [agreement/4.0, float(agreement>=2), float(agreement>=3), float(agreement>=4)]

        base_groups=[]
        for p in (base_draw or {}).get("prizes") or []:
            try: base_groups.append(int(p.get("grupo")))
            except Exception: pass
        count=base_groups.count(group)
        features += [float(count>0), min(1.0,max(0,count-1)/2.0)]
        return [float(v) for v in features]

    @classmethod
    def _meta_fit_logit(cls, examples, epochs=240, l2=0.025):
        examples=list(examples or [])
        if not examples:
            return None
        n_features=len(examples[0][0])
        if any(len(x)!=n_features for x,_,_ in examples):
            raise ValueError("Exemplos Meta com dimensões incompatíveis.")
        pos=sum(1 for _,y,_ in examples if int(y)==1)
        neg=len(examples)-pos
        if not pos or not neg:
            return None
        positive_weight=min(4.0,max(1.0,neg/max(1,pos)))
        w=[0.0]*n_features
        bias=0.0
        lr=0.18
        for epoch in range(max(40,int(epochs))):
            gb=0.0; gw=[0.0]*n_features; total=0.0
            for x,y,sample_weight in examples:
                y=1.0 if int(y) else 0.0
                sw=max(0.05,float(sample_weight or 1.0))*(positive_weight if y else 1.0)
                z=bias+sum(a*b for a,b in zip(w,x))
                p=cls._meta_sigmoid(z)
                err=p-y
                gb += sw*err
                for j,val in enumerate(x): gw[j] += sw*err*val
                total += sw
            total=max(total,1e-9)
            bias -= lr*(gb/total)
            for j in range(n_features):
                w[j] -= lr*((gw[j]/total) + float(l2)*w[j])
            lr=max(0.025,lr*0.992)
        return {
            "schema":1,
            "kind":"native_logit_l2",
            "intercept":round(bias,9),
            "coefficients":[round(v,9) for v in w],
            "positive_weight":round(positive_weight,6),
            "examples":len(examples),
            "positive_examples":pos,
        }

    @classmethod
    def _meta_model_score(cls, model, features):
        if not model:
            return 0.0
        z=float(model.get("intercept") or 0.0)
        coefs=model.get("coefficients") or []
        z += sum(float(a)*float(b) for a,b in zip(coefs,features))
        return cls._meta_sigmoid(z)*100.0

    def _meta_training_records(self, before_target=None, limit=160):
        """Monta exemplos somente de snapshots já auditados e anteriores ao alvo."""
        with self.connect() as con:
            rows=con.execute(
                "SELECT * FROM decision_snapshots WHERE status='AUDITADO' "
                "AND result_groups_json IS NOT NULL AND TRIM(result_groups_json)<>'' "
                "ORDER BY target_data ASC,id ASC"
            ).fetchall()
        cutoff=None
        if before_target:
            cutoff=self._meta_round_key(before_target.get("data"),before_target.get("hora"),10**9)
        parsed=[]
        for row in rows:
            d=self._decision_row_to_dict(row)
            if cutoff and self._meta_round_key(d.get("target_data"),d.get("target_hora"),d.get("id") or 0) >= cutoff:
                continue
            result_groups=[int(g) for g in (d.get("result_groups") or []) if str(g).isdigit()]
            if not result_groups:
                continue
            signals=d.get("signals") or {}
            if not all((signals.get(name) or {}).get("available") for name in ("Reset Cobertura","Puxada Combinada","Similaridade")):
                continue
            base=self.get_draw(d.get("base_data"),d.get("base_sorteio"),d.get("base_hora"))
            if not base:
                continue
            try:
                historical=self.method_historico_concentrado_v01(
                    d.get("base_data"),d.get("base_sorteio"),d.get("base_hora"),top_n=5
                )
            except Exception:
                historical={"selected":[]}
            parsed.append({
                "target_data":d.get("target_data"),"target_hora":d.get("target_hora"),
                "signals":signals,"historical":historical,"base_draw":base,
                "result_groups":result_groups,
            })
        return parsed[-max(1,int(limit)):]

    def _meta_examples(self, records, focus_target=None):
        records=list(records or [])
        total=max(1,len(records))
        focus_hour=str((focus_target or {}).get("hora") or "")
        focus_weekday=self._decision_weekday_label((focus_target or {}).get("data")) if focus_target else ""
        examples=[]
        for idx,rec in enumerate(records):
            # Recência suave + contexto do alvo. O peso é aplicado apenas ao
            # treinamento atual; os sinais de cada rodada continuam congelados.
            recency=0.75+0.50*((idx+1)/total)
            weight=recency
            if focus_hour and str(rec.get("target_hora") or "") == focus_hour:
                weight += 0.60
            if focus_weekday and self._decision_weekday_label(rec.get("target_data")) == focus_weekday:
                weight += 0.20
            winners=set(int(g) for g in rec.get("result_groups") or [])
            for group in range(1,26):
                x=self._meta_feature_vector(group,rec.get("signals"),rec.get("historical"),rec.get("base_draw"))
                examples.append((x,1 if group in winners else 0,weight))
        return examples

    def _meta_temporal_holdout(self, records):
        records=list(records or [])
        if len(records) < 24:
            return {"available":False,"rounds":0,"note":"Mínimo de 24 snapshots para holdout temporal preliminar."}
        split=max(16,int(len(records)*0.80))
        if len(records)-split < 4:
            split=len(records)-4
        train,test=records[:split],records[split:]
        model=self._meta_fit_logit(self._meta_examples(train,focus_target=None))
        if not model:
            return {"available":False,"rounds":0,"note":"Modelo não pôde ser ajustado no bloco de treino."}
        hits=[]; random_expected=[]; benchmarks={name:[] for name in ("Reset Cobertura","Puxada Combinada","Similaridade","Histórico Concentrado")}
        for rec in test:
            ranking=[]
            for group in range(1,26):
                x=self._meta_feature_vector(group,rec.get("signals"),rec.get("historical"),rec.get("base_draw"))
                ranking.append((self._meta_model_score(model,x),group))
            ranking.sort(key=lambda t:(-t[0],t[1]))
            top={g for _,g in ranking[:5]}
            result=set(int(g) for g in rec.get("result_groups") or [])
            hits.append(len(top & result))
            random_expected.append(5.0*len(result)/25.0)
            for name in ("Reset Cobertura","Puxada Combinada","Similaridade"):
                groups=set(int(g) for g in ((rec.get("signals") or {}).get(name) or {}).get("groups") or [])
                benchmarks[name].append(len(groups & result))
            hgroups=set(int(r.get("grupo")) for r in (rec.get("historical") or {}).get("selected") or [])
            benchmarks["Histórico Concentrado"].append(len(hgroups & result))
        n=len(hits)
        return {
            "available":True,"rounds":n,
            "avg_coverage":round(sum(hits)/n,4),
            "pct_2plus":round(sum(v>=2 for v in hits)/n*100.0,2),
            "pct_3plus":round(sum(v>=3 for v in hits)/n*100.0,2),
            "random_expected":round(sum(random_expected)/n,4),
            "uplift_vs_random":round((sum(hits)-sum(random_expected))/n,4),
            "benchmarks":{k:round(sum(v)/len(v),4) if v else None for k,v in benchmarks.items()},
            "note":"Holdout temporal preliminar: bloco final nunca participa do treino. O Walk-Forward completo fica para a fase seguinte.",
        }

    def meta_shadow_prediction(self, target, base_draw, signals, training_limit=160):
        target=dict(target or {}); base_draw=dict(base_draw or {}); signals=signals or {}
        if not target or not base_draw:
            return {"available":False,"status":"SEM DADOS","reason":"Alvo/base indisponível."}
        if self.get_draw(target.get("data"),target.get("sorteio"),target.get("hora")):
            return {"available":False,"status":"BLOQUEADO","reason":"Resultado-alvo já existe; Meta não é reconstruído retroativamente."}
        records=self._meta_training_records(before_target=target,limit=training_limit)
        n=len(records)
        same_hour=sum(1 for r in records if str(r.get("target_hora") or "") == str(target.get("hora") or ""))
        if n < 20:
            return {
                "available":False,"status":"AMOSTRA INSUFICIENTE","training_snapshots":n,
                "same_hour_snapshots":same_hour,"minimum_snapshots":20,
                "reason":"O GP-H Meta começa somente com 20 snapshots auditados anteriores.",
                "model_version":"META_LOGIT_NATIVE_V1","lookahead_safe":True,
            }
        try:
            historical=self.method_historico_concentrado_v01(
                base_draw.get("data"),base_draw.get("sorteio"),base_draw.get("hora"),top_n=5
            )
        except Exception:
            historical={"selected":[]}
        examples=self._meta_examples(records,focus_target=target)
        model=self._meta_fit_logit(examples)
        if not model:
            return {"available":False,"status":"SEM MODELO","training_snapshots":n,"reason":"Ajuste logístico indisponível."}
        ranking=[]
        for group in range(1,26):
            x=self._meta_feature_vector(group,signals,historical,base_draw)
            ranking.append({
                "grupo":group,"bicho":BICHOS[group],
                "score":round(self._meta_model_score(model,x),3),
                "features":[round(v,6) for v in x],
            })
        ranking.sort(key=lambda r:(-r["score"],r["grupo"]))
        for idx,row in enumerate(ranking,start=1): row["rank"]=idx
        holdout=self._meta_temporal_holdout(records)
        status="SOMBRA ATIVA" if n>=30 and same_hour>=6 else "EXPERIMENTAL"
        return {
            "available":True,"status":status,"objective":"1º–5º",
            "model_version":"META_LOGIT_NATIVE_V1","training_snapshots":n,
            "training_examples":len(examples),"same_hour_snapshots":same_hour,
            "groups":[r["grupo"] for r in ranking[:5]],
            "animals":[r["bicho"] for r in ranking[:5]],
            "scores":[r["score"] for r in ranking[:5]],
            "ranking":ranking,"holdout":holdout,
            "input_groups":{
                "Reset Cobertura":list((signals.get("Reset Cobertura") or {}).get("groups") or [])[:5],
                "Puxada Combinada":list((signals.get("Puxada Combinada") or {}).get("groups") or [])[:5],
                "Similaridade":list((signals.get("Similaridade") or {}).get("groups") or [])[:5],
                "Histórico Concentrado":[int(r.get("grupo")) for r in (historical.get("selected") or [])[:5]],
            },
            "model":{**model,"feature_names":list(self._meta_feature_names())},
            "lookahead_safe":True,
            "note":"Score interno de ranking; NÃO é probabilidade calibrada e NÃO altera o Reset + 3+1 oficial.",
        }

    def freeze_meta_snapshot(self, snapshot=None, force=False):
        """Congela o primeiro GP-H Meta da rodada; jamais recria depois do resultado."""
        snapshot=snapshot or self.latest_decision_snapshot()
        if not snapshot:
            raise ValueError("Não há snapshot prospectivo para congelar o GP-H Meta.")
        target={"data":snapshot.get("target_data"),"sorteio":snapshot.get("target_sorteio"),"hora":snapshot.get("target_hora")}
        if not all(target.values()):
            raise ValueError("Snapshot sem rodada-alvo completa.")
        if self.get_draw(target["data"],target["sorteio"],target["hora"]):
            return snapshot,False
        if (snapshot.get("meta") or {}) and not force:
            return snapshot,False
        base=self.get_draw(snapshot.get("base_data"),snapshot.get("base_sorteio"),snapshot.get("base_hora"))
        if not base:
            raise ValueError("Extração-base do GP-H Meta não encontrada.")
        payload=self.meta_shadow_prediction(target,base,snapshot.get("signals") or {})
        frozen_at=datetime.now().isoformat(timespec="seconds")
        payload=copy.deepcopy(payload or {})
        payload.update({"schema":1,"frozen_at":frozen_at,"frozen_app_version":APP_VERSION,"frozen_mode":"META_SOMBRA_AUTO"})
        with self.connect() as con:
            row=con.execute("SELECT * FROM decision_snapshots WHERE id=?",(int(snapshot["id"]),)).fetchone()
            if row is None: raise ValueError("Snapshot de Decisão não encontrado.")
            current=self._decision_row_to_dict(row)
            if (current.get("meta") or {}) and not force:
                return current,False
            if self.get_draw(target["data"],target["sorteio"],target["hora"]):
                return current,False
            con.execute(
                "UPDATE decision_snapshots SET meta_json=?,meta_frozen_at=? WHERE id=?",
                (json.dumps(payload,ensure_ascii=False),frozen_at,int(snapshot["id"])),
            )
            row=con.execute("SELECT * FROM decision_snapshots WHERE id=?",(int(snapshot["id"]),)).fetchone()
        return self._decision_row_to_dict(row),True

    @staticmethod
    def _meta_audit_payload(meta,result_groups):
        meta=meta or {}; result_groups=[int(g) for g in (result_groups or [])]
        groups=[int(g) for g in (meta.get("groups") or [])]
        result_set=set(result_groups)
        ranking={int(r.get("grupo")):int(r.get("rank") or 99) for r in (meta.get("ranking") or []) if r.get("grupo")}
        if not meta.get("available") or not groups:
            return {"schema":1,"available":False,"classification":"SEM_DADOS","result_groups":result_groups}
        hits=len(set(groups)&result_set)
        ranks=sorted(ranking[g] for g in result_set if g in ranking)
        return {
            "schema":1,"available":True,"groups":groups,"coverage_hits":hits,
            "first_prize_hit":bool(result_groups and result_groups[0] in set(groups)),
            "result_groups":result_groups,"best_result_rank":ranks[0] if ranks else None,
            "result_ranks":ranks,"random_expected":round(5.0*len(result_set)/25.0,4),
            "classification":f"{hits}/5","status":meta.get("status"),
        }

    def meta_shadow_summary(self, limit=120):
        with self.connect() as con:
            rows=con.execute(
                "SELECT * FROM decision_snapshots WHERE status='AUDITADO' "
                "AND meta_json IS NOT NULL AND TRIM(meta_json)<>'' "
                "AND meta_audit_json IS NOT NULL AND TRIM(meta_audit_json)<>'' "
                "ORDER BY target_data DESC,id DESC LIMIT ?",(max(1,int(limit)),)
            ).fetchall()
        parsed=[self._decision_row_to_dict(r) for r in rows]
        valid=[]; recent=[]
        for row in parsed:
            audit=row.get("meta_audit") or {}; meta=row.get("meta") or {}
            if not audit.get("available"): continue
            valid.append((row,audit,meta))
            if len(recent)<12:
                recent.append({
                    "data":row.get("target_data"),"sorteio":row.get("target_sorteio"),"hora":row.get("target_hora"),
                    "hits":int(audit.get("coverage_hits") or 0),"status":meta.get("status"),
                    "groups":meta.get("groups") or [],
                })
        n=len(valid)
        if not n:
            return {"rounds":0,"avg_coverage":None,"pct_2plus":None,"pct_3plus":None,"first_rate":None,"random_expected":None,"uplift_vs_random":None,"recent":[]}
        hits=[int(a.get("coverage_hits") or 0) for _,a,_ in valid]
        rnd=[float(a.get("random_expected") or 0.0) for _,a,_ in valid]
        first=[bool(a.get("first_prize_hit")) for _,a,_ in valid]
        return {
            "rounds":n,"avg_coverage":sum(hits)/n,
            "pct_2plus":sum(v>=2 for v in hits)/n*100.0,"pct_3plus":sum(v>=3 for v in hits)/n*100.0,
            "first_rate":sum(first)/n*100.0,"random_expected":sum(rnd)/n,
            "uplift_vs_random":sum(hits)/n-sum(rnd)/n,"recent":recent,
        }

'''
marker='    def freeze_decision_contextual(self, snapshot=None, force=False):\n'
if marker not in text: raise SystemExit('freeze_decision_contextual não encontrado')
text=text.replace(marker,meta_code+marker,1)

# ---------------------------------------------------------------------
# Auditoria da Decisão também audita Meta.
# ---------------------------------------------------------------------
old='''                contextual_audit = (\n                    self._decision_contextual_audit_payload(contextual, signals, result_groups)\n                    if contextual else None\n                )\n                con.execute(\n                    "UPDATE decision_snapshots SET status='AUDITADO',signals_json=?,"\n                    "contextual_audit_json=?,result_groups_json=?,audited_at=? WHERE id=?",\n                    (\n                        json.dumps(signals, ensure_ascii=False),\n                        json.dumps(contextual_audit, ensure_ascii=False) if contextual_audit else None,\n                        json.dumps(result_groups),\n                        datetime.now().isoformat(timespec="seconds"),\n                        int(row["id"]),\n                    ),\n                )\n'''
new='''                contextual_audit = (\n                    self._decision_contextual_audit_payload(contextual, signals, result_groups)\n                    if contextual else None\n                )\n                try:\n                    meta = json.loads(row["meta_json"] or "{}")\n                except Exception:\n                    meta = {}\n                meta_audit = self._meta_audit_payload(meta, result_groups) if meta else None\n                con.execute(\n                    "UPDATE decision_snapshots SET status='AUDITADO',signals_json=?,"\n                    "contextual_audit_json=?,meta_audit_json=?,result_groups_json=?,audited_at=? WHERE id=?",\n                    (\n                        json.dumps(signals, ensure_ascii=False),\n                        json.dumps(contextual_audit, ensure_ascii=False) if contextual_audit else None,\n                        json.dumps(meta_audit, ensure_ascii=False) if meta_audit else None,\n                        json.dumps(result_groups),\n                        datetime.now().isoformat(timespec="seconds"),\n                        int(row["id"]),\n                    ),\n                )\n'''
if old not in text: raise SystemExit('auditoria decision anchor não encontrada')
text=text.replace(old,new,1)

# ---------------------------------------------------------------------
# Sync: Meta acompanha decision_snapshots e primeira leitura continua canônica.
# ---------------------------------------------------------------------
text=text.replace(
'''            "contextual_json","contextual_frozen_at","contextual_audit_json",\n            "result_groups_json","audited_at","note",\n''',
'''            "contextual_json","contextual_frozen_at","contextual_audit_json",\n            "meta_json","meta_frozen_at","meta_audit_json",\n            "result_groups_json","audited_at","note",\n''',1)

ctx_merge='''                if remote_ctx and (not local_ctx or remote_ctx_at < local_ctx_at):\n                    changes["contextual_json"] = remote.get("contextual_json")\n                    changes["contextual_frozen_at"] = remote.get("contextual_frozen_at")\n\n                if str(remote.get("status") or "") == "AUDITADO" and str(local["status"] or "") != "AUDITADO":\n'''
ctx_new='''                if remote_ctx and (not local_ctx or remote_ctx_at < local_ctx_at):\n                    changes["contextual_json"] = remote.get("contextual_json")\n                    changes["contextual_frozen_at"] = remote.get("contextual_frozen_at")\n\n                # GP-H Meta: a primeira leitura congelada entre PCs também é canônica.\n                local_meta = str(local["meta_json"] or "").strip()\n                remote_meta = str(remote.get("meta_json") or "").strip()\n                local_meta_at = str(local["meta_frozen_at"] or "9999")\n                remote_meta_at = str(remote.get("meta_frozen_at") or "9999")\n                if remote_meta and (not local_meta or remote_meta_at < local_meta_at):\n                    changes["meta_json"] = remote.get("meta_json")\n                    changes["meta_frozen_at"] = remote.get("meta_frozen_at")\n\n                if str(remote.get("status") or "") == "AUDITADO" and str(local["status"] or "") != "AUDITADO":\n'''
if ctx_merge not in text: raise SystemExit('merge contextual anchor não encontrado')
text=text.replace(ctx_merge,ctx_new,1)
text=text.replace(
'''                    for k in ("status","signals_json","contextual_audit_json","result_groups_json","audited_at"):\n''',
'''                    for k in ("status","signals_json","contextual_audit_json","meta_audit_json","result_groups_json","audited_at"):\n''',1)
merge_tail='''                    changes["contextual_audit_json"] = remote.get("contextual_audit_json")\n\n                if changes:\n'''
merge_tail_new='''                    changes["contextual_audit_json"] = remote.get("contextual_audit_json")\n                if (\n                    str(local["status"] or "") == "AUDITADO"\n                    and not str(local["meta_audit_json"] or "").strip()\n                    and str(remote.get("meta_audit_json") or "").strip()\n                ):\n                    changes["meta_audit_json"] = remote.get("meta_audit_json")\n\n                if changes:\n'''
if merge_tail not in text: raise SystemExit('merge audit tail não encontrado')
text=text.replace(merge_tail,merge_tail_new,1)

# ---------------------------------------------------------------------
# Auto ciclo e abertura da Decisão congelam Meta antes do resultado.
# ---------------------------------------------------------------------
old='''            snapshot, _created = self.db.freeze_decision_snapshot(force=False)\n            snapshot, _context_created = self.db.freeze_decision_contextual(snapshot, force=False)\n'''
new='''            snapshot, _created = self.db.freeze_decision_snapshot(force=False)\n            snapshot, _context_created = self.db.freeze_decision_contextual(snapshot, force=False)\n            snapshot, _meta_created = self.db.freeze_meta_snapshot(snapshot, force=False)\n'''
if text.count(old)<1: raise SystemExit('show decision freeze anchor não encontrado')
text=text.replace(old,new,1)

auto='''                snapshot, _created = self.db.freeze_decision_snapshot(force=False)\n                self.db.freeze_decision_contextual(snapshot, force=False)\n'''
auto_new='''                snapshot, _created = self.db.freeze_decision_snapshot(force=False)\n                snapshot, _ctx = self.db.freeze_decision_contextual(snapshot, force=False)\n                self.db.freeze_meta_snapshot(snapshot, force=False)\n'''
if auto not in text: raise SystemExit('auto decision anchor não encontrado')
text=text.replace(auto,auto_new,1)

# ---------------------------------------------------------------------
# UI Meta logo após Decisão Contextual e auditoria da própria decisão.
# ---------------------------------------------------------------------
call='''        self._decision_build_contextual(body, snapshot)\n        self._decision_build_self_audit(body)\n\n        # Componentes transparentes do índice.\n'''
call_new='''        self._decision_build_contextual(body, snapshot)\n        self._decision_build_self_audit(body)\n        self._decision_build_meta(body, snapshot)\n\n        # Componentes transparentes do índice.\n'''
if call not in text: raise SystemExit('chamada UI decision não encontrada')
text=text.replace(call,call_new,1)

ui=r'''    def _decision_build_meta(self, body, snapshot):
        meta=(snapshot or {}).get("meta") or {}
        summary=self.db.meta_shadow_summary(limit=120)
        card=ttk.Frame(body,style="Card.TFrame",padding=11)
        card.pack(fill="x",pady=(0,8))
        head=ttk.Frame(card,style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head,text="GP-H META v0.1 — SOMBRA",style="CardTitle.TLabel").pack(side="left")
        ttk.Label(head,text=meta.get("status") or "AGUARDANDO",style="CardMuted.TLabel").pack(side="right")

        if not meta:
            ttk.Label(card,text="A leitura Meta ainda não foi congelada para esta rodada.",style="CardMuted.TLabel").pack(anchor="w",pady=(6,0))
            return
        if not meta.get("available"):
            n=int(meta.get("training_snapshots") or 0)
            minimum=int(meta.get("minimum_snapshots") or 20)
            ttk.Label(card,text=f"Aprendizado em formação: {n}/{minimum} snapshots auditados.",style="Card.TLabel",font=("Segoe UI Semibold",12)).pack(anchor="w",pady=(6,2))
            ttk.Label(card,text=meta.get("reason") or "Aguardando amostra suficiente.",style="CardMuted.TLabel",wraplength=1060).pack(anchor="w")
            return

        groups=meta.get("groups") or []; animals=meta.get("animals") or []; scores=meta.get("scores") or []
        ttk.Label(
            card,
            text=f"Ranking aprendido para a rodada • {int(meta.get('training_snapshots') or 0)} snapshots de treino • {int(meta.get('same_hour_snapshots') or 0)} no mesmo horário",
            style="Card.TLabel",font=("Segoe UI Semibold",12),wraplength=1060,
        ).pack(anchor="w",pady=(6,6))
        row=ttk.Frame(card,style="Card.TFrame"); row.pack(fill="x")
        for i,(g,a,s) in enumerate(zip(groups,animals,scores),start=1):
            box=ttk.Frame(row,style="Card2.TFrame",padding=8)
            box.pack(side="left",fill="x",expand=True,padx=(0,5 if i<5 else 0))
            ttk.Label(box,text=f"{i}º • {a}",style="Card.TLabel",font=("Segoe UI Semibold",9)).pack(anchor="w")
            ttk.Label(box,text=f"Grupo {int(g):02d} • score {float(s):.1f}",style="CardMuted.TLabel").pack(anchor="w")

        hold=meta.get("holdout") or {}
        if hold.get("available"):
            htxt=(
                f"Holdout temporal preliminar ({int(hold.get('rounds') or 0)} rodadas): "
                f"Meta {float(hold.get('avg_coverage') or 0):.2f}/5 • acaso esperado {float(hold.get('random_expected') or 0):.2f}/5 • "
                f"diferença {float(hold.get('uplift_vs_random') or 0):+.2f}."
            )
        else:
            htxt=hold.get("note") or "Holdout temporal ainda indisponível."
        ttk.Label(card,text=htxt,style="CardMuted.TLabel",wraplength=1060).pack(anchor="w",pady=(7,2))

        rounds=int(summary.get("rounds") or 0)
        if rounds:
            atxt=(
                f"Auditoria prospectiva do Meta: {rounds} rodada(s) • cobertura média {float(summary.get('avg_coverage') or 0):.2f}/5 • "
                f"2+ bichos {float(summary.get('pct_2plus') or 0):.1f}% • 3+ bichos {float(summary.get('pct_3plus') or 0):.1f}% • "
                f"diferença vs acaso {float(summary.get('uplift_vs_random') or 0):+.2f}."
            )
        else:
            atxt="Auditoria prospectiva: começa a acumular somente com previsões Meta congeladas a partir da v0.41.0."
        ttk.Label(card,text=atxt,style="CardMuted.TLabel",wraplength=1060).pack(anchor="w",pady=(1,2))
        ttk.Label(
            card,
            text="O score do Meta é apenas um ranking interno ainda não calibrado; não é porcentagem de chance. O Meta permanece 100% em sombra e não altera o Reset + 3+1 oficial.",
            style="CardMuted.TLabel",wraplength=1060,
        ).pack(anchor="w")

'''
marker='    def _decision_build_self_audit(self, body):\n'
if marker not in text: raise SystemExit('UI self audit marker não encontrado')
text=text.replace(marker,ui+marker,1)

# ---------------------------------------------------------------------
# Versão / Sobre / documentação.
# ---------------------------------------------------------------------
text=text.replace('GP-H Central Histórica v0.40.0','GP-H Central Histórica v0.41.0',1)
text=text.replace('APP_VERSION = "0.40.0"','APP_VERSION = "0.41.0"',1)
needle='            "• v0.40.0 —'
pos=text.find(needle)
if pos>=0:
    text=text[:pos]+'            "• v0.41.0 — GP-H Meta v0.1 em sombra: modelo logístico nativo aprende com Reset, Puxada, Similaridade e Histórico Concentrado sem alterar o método oficial.\\n"\n'+text[pos:]

# Validações pós-patch.
ast.parse(text)
after=function_dumps(text)
for name in CRITICAL:
    if before[name] != after[name]:
        raise SystemExit(f'MOTOR OFICIAL ALTERADO: {name}')
for required in (
    'APP_VERSION = "0.41.0"','def freeze_meta_snapshot(','def meta_shadow_prediction(',
    'def _decision_build_meta(','meta_json','meta_frozen_at','meta_audit_json',
    'META_LOGIT_NATIVE_V1','GP-H META v0.1 — SOMBRA',
):
    if required not in text: raise SystemExit('ausente: '+required)
SRC.write_text(text,encoding='utf-8')

doc=DOC.read_text(encoding='utf-8')
revision='''REVISÃO v0.41.0 — GP-H META v0.1 / MOTOR ADAPTATIVO EM SOMBRA\n- Cria o GP-H Meta v0.1, exclusivamente SOMBRA: ele não altera Reset + 3+1, apostas, recomendações oficiais ou pesos da Decisão Contextual.\n- O Meta usa regressão logística L2 nativa da biblioteca padrão, evitando nova dependência e aumento desnecessário do executável.\n- Cada bicho recebe características dos sinais prospectivos de Reset Cobertura, Puxada Combinada, Similaridade e GP-H Histórico Concentrado v0.1, além de convergência e presença/repetição na extração-base.\n- Treinamento usa somente decision_snapshots já AUDITADOS e anteriores ao alvo. O Histórico Concentrado usado como característica é reconstruído com before_draw_key/cutoff, portanto sem look-ahead.\n- A partir de 20 snapshots auditados o Meta pode ranquear os 25 bichos; abaixo disso fica AMOSTRA INSUFICIENTE. A leitura segue EXPERIMENTAL até ganhar suporte maior no mesmo horário.\n- O treinamento atual dá peso suave à recência, ao mesmo horário e ao mesmo dia da semana.\n- O ranking Top 5, todos os 25 scores, características e coeficientes ficam congelados no decision_snapshot ANTES do resultado. O primeiro congelamento é canônico e sincroniza entre PCs.\n- Depois do resultado o Meta é auditado por cobertura 1º–5º, acerto de 1º, posição do melhor bicho real no ranking e baseline aleatório esperado.\n- A tela Decisão ganha o cartão “GP-H META v0.1 — SOMBRA”, com Top 5, tamanho do treino, holdout temporal preliminar e auditoria prospectiva acumulada.\n- O score do Meta NÃO é probabilidade calibrada. Holdout atual é apenas diagnóstico preliminar; Walk-Forward rigoroso do Meta fica para a próxima fase.\n- Nenhum motor oficial foi alterado; Reset, Puxada, Similaridade, Histórico Concentrado, 3+1 e Decisão Contextual foram travados por comparação AST.\n\n'''
if not doc.startswith(revision): doc=revision+doc
DOC.write_text(doc,encoding='utf-8')
print('PATCH v0.41.0 OK')
print('linhas',len(text.splitlines()))
print('motores oficiais preservados:',', '.join(sorted(CRITICAL)))
