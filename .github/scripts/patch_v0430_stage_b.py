from pathlib import Path
import ast

SRC=Path('source/gph_central.py')
DOC=Path('source/DOCUMENTACAO_GP-H.txt')
text=SRC.read_text(encoding='utf-8')
doc=DOC.read_text(encoding='utf-8')


def fn_dump(source, name):
    tree=ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name==name:
            return ast.dump(node,include_attributes=False)
    raise AssertionError(f'função não encontrada: {name}')

critical=[
    '_meta_feature_names','_meta_feature_vector','_meta_fit_logit','_meta_model_score',
    '_meta_training_records','_meta_examples','_meta_temporal_holdout','meta_shadow_prediction',
    'meta_walk_forward','method_reset_coverage_v1','method_convergencia_g5','method_similarity_day',
    'method_historico_concentrado_v01','generate_historical_concentrated_bundle',
    'generate_centenas_3plus1','centena_31_freeze_state','decision_contextual_evidence',
    'decision_contextual_audit_summary','audit_decision_snapshots','decision_walk_forward',
    'freeze_decision_contextual','freeze_meta_snapshot','meta_shadow_summary','historical_pulls',
    '_decision_build_self_audit'
]
before={name:fn_dump(text,name) for name in critical}

text=text.replace('GP-H Central Histórica v0.42.1','GP-H Central Histórica v0.43.0',1)
text=text.replace('APP_VERSION = "0.42.1"','APP_VERSION = "0.43.0"',1)
text=text.replace('text="v0.42.1 • cérebro v0.1 congelado"','text="v0.43 • cérebro v0.1 congelado"',1)

calibration_method=r'''
    def decision_confidence_calibration(self, limit=240, min_bucket=8):
        """
        Etapa B — calibração observacional dos níveis da Decisão Contextual.

        Mede somente leituras congeladas ANTES do resultado. O índice continua
        sendo evidência (0–100), não probabilidade. Esta rotina não altera pesos,
        limiares, rótulos nem qualquer método; apenas verifica se níveis mais fortes
        vêm acompanhados de melhor desempenho prospectivo.
        """
        try:
            limit=max(1,min(5000,int(limit)))
        except Exception:
            limit=240
        try:
            min_bucket=max(3,min(50,int(min_bucket)))
        except Exception:
            min_bucket=8

        with self.connect() as con:
            rows=con.execute(
                "SELECT * FROM decision_snapshots "
                "WHERE status='AUDITADO' AND contextual_json IS NOT NULL "
                "AND TRIM(contextual_json)<>'' AND contextual_audit_json IS NOT NULL "
                "AND TRIM(contextual_audit_json)<>'' "
                "ORDER BY target_data DESC,target_hora DESC,id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        parsed=[self._decision_row_to_dict(row) for row in rows]
        levels=("AMOSTRA INSUFICIENTE","BAIXA","MODERADA","FORTE")
        buckets={level:[] for level in levels}
        all_valid=[]

        for row in parsed:
            audit=row.get("contextual_audit") or {}
            contextual=row.get("contextual") or {}
            classification=audit.get("classification") or "SEM_DADOS"
            if classification not in ("CORRETA_EXCLUSIVA","CORRETA_EMPATE","INCORRETA"):
                continue
            status=str(audit.get("context_status") or contextual.get("status") or "SEM DADOS").upper()
            best=contextual.get("best") or {}
            idx=audit.get("leader_index")
            if idx is None:
                idx=best.get("index")
            lead=audit.get("lead_index")
            if lead is None:
                lead=contextual.get("lead")
            rec={
                "status":status,
                "success":classification in ("CORRETA_EXCLUSIVA","CORRETA_EMPATE"),
                "exclusive":classification=="CORRETA_EXCLUSIVA",
                "incorrect":classification=="INCORRETA",
                "leader_index":float(idx) if idx is not None else None,
                "lead_index":float(lead) if lead is not None else None,
                "leader_hits":int(audit.get("leader_hits")) if audit.get("leader_hits") is not None else None,
                "classification":classification,
                "target_data":row.get("target_data"),
                "target_sorteio":row.get("target_sorteio"),
                "target_hora":row.get("target_hora"),
            }
            all_valid.append(rec)
            buckets.setdefault(status,[]).append(rec)

        def wilson(successes,n,z=1.96):
            if n<=0:
                return (None,None)
            p=successes/n
            den=1.0+(z*z)/n
            center=(p+(z*z)/(2*n))/den
            margin=(z*((p*(1-p)/n+(z*z)/(4*n*n))**0.5))/den
            return (max(0.0,center-margin)*100.0,min(1.0,center+margin)*100.0)

        def mean(values):
            values=[float(v) for v in values if v is not None]
            return sum(values)/len(values) if values else None

        ordered_levels=list(levels)+sorted(k for k in buckets if k not in levels)
        out=[]
        for level in ordered_levels:
            values=buckets.get(level) or []
            if not values and level not in levels:
                continue
            n=len(values)
            success=sum(1 for r in values if r["success"])
            sole=sum(1 for r in values if r["exclusive"])
            incorrect=sum(1 for r in values if r["incorrect"])
            low,high=wilson(success,n)
            out.append({
                "level":level,"rounds":n,
                "best_or_tied":success,
                "best_or_tied_rate":success/n*100.0 if n else None,
                "sole_correct":sole,
                "sole_correct_rate":sole/n*100.0 if n else None,
                "incorrect":incorrect,
                "incorrect_rate":incorrect/n*100.0 if n else None,
                "ci95_low":low,"ci95_high":high,
                "avg_leader_index":mean(r["leader_index"] for r in values),
                "avg_lead_index":mean(r["lead_index"] for r in values),
                "avg_leader_hits":mean(r["leader_hits"] for r in values),
                "sample_status":"SUFICIENTE" if n>=min_bucket else ("PEQUENA" if n else "SEM DADOS"),
            })

        evaluated=len(all_valid)
        successes=sum(1 for r in all_valid if r["success"])
        overall_low,overall_high=wilson(successes,evaluated)

        # Correlação descritiva índice × desfecho binário. Não é causalidade,
        # não é probabilidade e não recebe significância estatística artificial.
        pairs=[(r["leader_index"],1.0 if r["success"] else 0.0) for r in all_valid if r["leader_index"] is not None]
        corr=None
        if len(pairs)>=8:
            xs=[p[0] for p in pairs]; ys=[p[1] for p in pairs]
            mx=sum(xs)/len(xs); my=sum(ys)/len(ys)
            vx=sum((x-mx)**2 for x in xs); vy=sum((y-my)**2 for y in ys)
            if vx>0 and vy>0:
                corr=sum((x-mx)*(y-my) for x,y in pairs)/(vx*vy)**0.5

        by_level={r["level"]:r for r in out}
        check=[]
        for level in ("BAIXA","MODERADA","FORTE"):
            row=by_level.get(level) or {}
            if int(row.get("rounds") or 0)>=min_bucket and row.get("best_or_tied_rate") is not None:
                check.append((level,float(row["best_or_tied_rate"])))
        monotonic=None
        if len(check)>=2:
            monotonic=all(check[i][1] <= check[i+1][1]+1e-12 for i in range(len(check)-1))

        if evaluated < 20 or len(check) < 2:
            verdict="EM FORMAÇÃO"
            note=(
                f"Ainda há pouca amostra para julgar a escala de confiança: {evaluated} decisão(ões) avaliável(is) "
                f"e {len(check)} nível(is) com pelo menos {min_bucket} casos."
            )
        elif monotonic:
            verdict="ORDEM COERENTE"
            note=(
                "Nos níveis com amostra mínima, a taxa de melhor/empate não diminuiu ao passar de BAIXA para MODERADA/FORTE. "
                "Isso apoia a ordenação atual, mas ainda não transforma o índice em probabilidade."
            )
        else:
            verdict="ORDEM AINDA NÃO COERENTE"
            note=(
                "Os níveis com amostra mínima ainda não mostram crescimento ordenado da taxa de melhor/empate. "
                "A Etapa B apenas registra isso; nenhum limiar é alterado automaticamente."
            )

        strong=by_level.get("FORTE") or {}
        low=by_level.get("BAIXA") or {}
        strong_vs_low=None
        if int(strong.get("rounds") or 0)>=min_bucket and int(low.get("rounds") or 0)>=min_bucket:
            strong_vs_low=float(strong.get("best_or_tied_rate") or 0)-float(low.get("best_or_tied_rate") or 0)

        return {
            "evaluated":evaluated,"best_or_tied":successes,
            "best_or_tied_rate":successes/evaluated*100.0 if evaluated else None,
            "overall_ci95_low":overall_low,"overall_ci95_high":overall_high,
            "levels":out,"min_bucket":min_bucket,
            "sufficient_levels":len(check),"monotonic":monotonic,
            "index_outcome_corr":corr,"strong_vs_low_pp":strong_vs_low,
            "verdict":verdict,"note":note,
            "primary_metric":"melhor_ou_empatada",
            "lookahead_safe":True,"changes_decision":False,
        }

'''
anchor='    def audit_decision_snapshots(self):\n'
assert anchor in text
assert 'def decision_confidence_calibration(' not in text
text=text.replace(anchor,calibration_method+anchor,1)

ui_method=r'''
    def _decision_build_confidence_calibration(self, body):
        """Etapa B: mede se BAIXA/MODERADA/FORTE realmente se separam na prática."""
        calibration=self.db.decision_confidence_calibration(limit=240,min_bucket=8)
        card=ttk.Frame(body,style="Card.TFrame",padding=10)
        card.pack(fill="x",pady=(0,8))
        head=ttk.Frame(card,style="Card.TFrame"); head.pack(fill="x")
        ttk.Label(head,text="CALIBRAÇÃO DA CONFIANÇA — ETAPA B",style="CardTitle.TLabel").pack(side="left")
        ttk.Label(head,text="mede a escala; não altera os níveis",style="CardMuted.TLabel").pack(side="right")

        evaluated=int(calibration.get("evaluated") or 0)
        verdict=calibration.get("verdict") or "EM FORMAÇÃO"
        corr=calibration.get("index_outcome_corr")
        corr_text="—" if corr is None else f"{float(corr):+.2f}"
        rate=calibration.get("best_or_tied_rate")
        rate_text="—" if rate is None else f"{float(rate):.1f}%"
        defs=(
            ("ESTADO",verdict),
            ("DECISÕES",evaluated),
            ("MELHOR/EMPATE",rate_text),
            ("CORR. ÍNDICE × RESULTADO",corr_text),
        )
        kpis=ttk.Frame(card,style="Card.TFrame"); kpis.pack(fill="x",pady=(7,7))
        for idx,(title,value) in enumerate(defs):
            box=ttk.Frame(kpis,style="Card2.TFrame",padding=8)
            box.pack(side="left",fill="x",expand=True,padx=(0,6 if idx<3 else 0))
            ttk.Label(box,text=title,style="CardMuted.TLabel").pack(anchor="w")
            ttk.Label(box,text=str(value),style="Card.TLabel",font=(UI_FONT_SEMIBOLD,UI_FONT_SIZES["kpi"]),wraplength=240).pack(anchor="w")

        rows=[r for r in calibration.get("levels") or [] if int(r.get("rounds") or 0)>0]
        if rows:
            cols=("level","n","best","sole","error","ci","index","hits")
            tree=ttk.Treeview(card,columns=cols,show="headings",height=max(3,min(6,len(rows))))
            heads={
                "level":"Nível congelado","n":"N","best":"Melhor/empate","sole":"Exclusiva",
                "error":"Erro","ci":"IC95% melhor/empate","index":"Índice médio","hits":"Acertos médios",
            }
            widths={"level":180,"n":55,"best":110,"sole":95,"error":85,"ci":155,"index":95,"hits":110}
            for col in cols:
                tree.heading(col,text=heads[col])
                tree.column(col,width=widths[col],anchor="w" if col=="level" else "center")
            for row in rows:
                low=row.get("ci95_low"); high=row.get("ci95_high")
                ci="—" if low is None or high is None else f"{float(low):.0f}–{float(high):.0f}%"
                tree.insert("","end",values=(
                    row.get("level"),int(row.get("rounds") or 0),
                    "—" if row.get("best_or_tied_rate") is None else f"{float(row['best_or_tied_rate']):.1f}%",
                    "—" if row.get("sole_correct_rate") is None else f"{float(row['sole_correct_rate']):.1f}%",
                    "—" if row.get("incorrect_rate") is None else f"{float(row['incorrect_rate']):.1f}%",
                    ci,
                    "—" if row.get("avg_leader_index") is None else f"{float(row['avg_leader_index']):.1f}",
                    "—" if row.get("avg_leader_hits") is None else f"{float(row['avg_leader_hits']):.2f}/5",
                ))
            tree.pack(fill="x",pady=(0,5))
        else:
            ttk.Label(
                card,text="A coleta prospectiva ainda não possui decisões suficientes para preencher os níveis de confiança.",
                style="CardMuted.TLabel",wraplength=1050,
            ).pack(anchor="w",pady=(2,5))

        diff=calibration.get("strong_vs_low_pp")
        extra=""
        if diff is not None:
            extra=f" • FORTE − BAIXA: {float(diff):+.1f} pp"
        ttk.Label(
            card,
            text=(calibration.get("note") or "")+extra,
            style="CardMuted.TLabel",wraplength=1050,justify="left",
        ).pack(anchor="w")
        ttk.Label(
            card,
            text=(
                "Métrica principal: a decisão escolhida terminou melhor ou empatada entre os três métodos. "
                "Vitória exclusiva e erro continuam separados. IC95% mostra a incerteza da amostra. "
                "A Etapa B não converte o índice em probabilidade e não recalibra limiares automaticamente."
            ),
            style="CardMuted.TLabel",wraplength=1050,justify="left",
        ).pack(anchor="w",pady=(2,0))

'''
ui_anchor='    def _decision_build_stage2(self, body, snapshot):\n'
assert ui_anchor in text
assert 'def _decision_build_confidence_calibration(' not in text
text=text.replace(ui_anchor,ui_method+ui_anchor,1)

call_old='        self._decision_build_self_audit(body)\n        self._decision_build_meta(body, snapshot)\n'
call_new='        self._decision_build_self_audit(body)\n        self._decision_build_confidence_calibration(body)\n        self._decision_build_meta(body, snapshot)\n'
assert call_old in text
text=text.replace(call_old,call_new,1)

header='''REVISÃO v0.43.0 — ETAPA B / CALIBRAÇÃO DA CONFIANÇA DA DECISÃO\n- Retoma a sequência original iniciada na v0.40.0: Etapa A = auditoria prospectiva; Etapa B = medir se os níveis BAIXA/MODERADA/FORTE realmente separam desempenho.\n- Novo painel “CALIBRAÇÃO DA CONFIANÇA — ETAPA B” usa somente Decisões Contextuais congeladas antes do resultado; não há backfill e não há look-ahead.\n- Para cada nível mostra N, taxa de melhor/empate, vitória exclusiva, erro, IC95% de Wilson, índice médio e acertos médios do líder.\n- Mede também correlação descritiva entre índice congelado e desfecho melhor/empate e, quando houver amostra, diferença FORTE − BAIXA.\n- A calibração só considera um nível suficientemente amostrado a partir de 8 casos e permanece “EM FORMAÇÃO” enquanto não houver base adequada; não força conclusão com poucas rodadas.\n- IMPORTANTE: esta etapa NÃO altera pesos, limiares, classificação FORTE/MODERADA/BAIXA, Reset + 3+1 ou qualquer método. Ajuste adaptativo pertence à futura Etapa C.\n- GP-H Meta v0.1 continua congelado exatamente como na v0.41/v0.42. A v0.43.0 não muda suas 20 características, regressão, treinamento, Walk-Forward ou ranking.\n\n'''
if not doc.startswith('REVISÃO v0.43.0'):
    doc=header+doc

ast.parse(text)
after={name:fn_dump(text,name) for name in critical}
changed=[name for name in critical if before[name]!=after[name]]
assert not changed, f'motores/funções críticas alterados: {changed}'
assert 'APP_VERSION = "0.43.0"' in text
assert 'def decision_confidence_calibration(' in text
assert 'def _decision_build_confidence_calibration(' in text
assert 'self._decision_build_confidence_calibration(body)' in text
assert doc.startswith('REVISÃO v0.43.0')

SRC.write_text(text,encoding='utf-8')
DOC.write_text(doc,encoding='utf-8')
print('PATCH v0.43.0 ETAPA B OK')
print('linhas',len(text.splitlines()))
print('motores preservados:',', '.join(critical))
