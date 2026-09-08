from pathlib import Path
import ast

SRC=Path('source/gph_central.py')
DOC=Path('source/DOCUMENTACAO_GP-H.txt')
text=SRC.read_text(encoding='utf-8')

if 'APP_VERSION = "0.41.0"' not in text:
    raise SystemExit('v0.42.0 deve partir exatamente da v0.41.0')

CRITICAL={
    'centena_31_freeze_state','generate_centenas_3plus1','historical_pulls',
    'method_reset_coverage_v1','method_convergencia_g5','method_similarity_day',
    'method_historico_concentrado_v01','generate_historical_concentrated_bundle',
    'decision_contextual_evidence','decision_walk_forward',
    '_meta_feature_names','_meta_feature_vector','_meta_fit_logit','_meta_model_score',
    '_meta_training_records','_meta_examples','_meta_temporal_holdout',
    'meta_shadow_prediction','freeze_meta_snapshot','_meta_audit_payload','meta_shadow_summary',
}

def func_ast(src,names):
    tree=ast.parse(src); out={}
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names:
            out[n.name]=ast.dump(n,include_attributes=False)
    missing=names-set(out)
    if missing:
        raise SystemExit('Funções críticas ausentes: '+', '.join(sorted(missing)))
    return out

before=func_ast(text,CRITICAL)
tree=ast.parse(text)

def class_method(class_name, method_name):
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
    return next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==method_name)

# ---------------------------------------------------------------------------
# 1) Motor de avaliação Walk-Forward do Meta. NÃO altera o Meta v0.1 vivo.
# ---------------------------------------------------------------------------
anchor=class_method('Database','_meta_temporal_holdout')
meta_wf=r'''
    def meta_walk_forward(self, window=30, progress_callback=None, cancel_event=None):
        """
        Walk-Forward rigoroso do GP-H Meta v0.1, exclusivamente diagnóstico.

        Reconstrói sinais históricos com os métodos atuais e cutoff da própria
        extração-base. Para cada rodada avaliada:
          1) usa somente registros anteriores como treino;
          2) reaplica EXATAMENTE o cérebro Meta v0.1 congelado;
          3) prevê Top 5;
          4) só então usa o resultado-alvo para medir desempenho;
          5) avança uma rodada e repete.

        Não alimenta o Meta prospectivo, não calibra score, não muda pesos e não
        promove método. A janela de avaliação é limitada a 60 por custo do treino
        nativo repetido; cada ajuste pode usar até 160 rodadas anteriores.
        """
        try:
            window=max(5,min(60,int(window)))
        except Exception:
            window=30
        min_train=20
        training_limit=160
        benchmark_names=(
            "Reset Cobertura","Puxada Combinada","Similaridade","Histórico Concentrado"
        )
        method_order=("GP-H Meta v0.1",)+benchmark_names

        draws=self._draws_in_order()
        key_to_index={(d["data"],d["sorteio"],d["hora"]):i for i,d in enumerate(draws)}
        candidates=[]
        for i,base in enumerate(draws):
            if i < 35 or not self._is_operational_draw(base) or len(base.get("prizes") or []) < 5:
                continue
            expected=self._reset_expected_target(base)
            target_index=key_to_index.get((expected["data"],expected["sorteio"],expected["hora"]))
            if target_index is None or target_index <= i:
                continue
            target=draws[target_index]
            if len(target.get("prizes") or []) < 5:
                continue
            candidates.append((i,base,target_index,target))

        # Reconstrói só o necessário para a janela móvel do cérebro (160), a
        # janela pedida e uma folga para casos indisponíveis.
        source=candidates[-min(len(candidates),training_limit+window+40):]
        reconstructed=[]
        cancelled=False
        total_rebuild=len(source)

        def notify(done,total,phase,base=None):
            if progress_callback:
                try:
                    info={"phase":phase}
                    if base:
                        info.update({"data":base.get("data"),"sorteio":base.get("sorteio"),"hora":base.get("hora")})
                    progress_callback(done,total,info)
                except Exception:
                    pass

        def metric_entry(result,target_unique,positional=None):
            predicted=[int(r["grupo"]) for r in (result or {}).get("selected") or [] if r.get("grupo")]
            pred_unique=set(predicted)
            return {
                "available":bool(predicted),
                "groups":predicted,
                "animals":[BICHOS.get(g,str(g)) for g in predicted],
                "coverage_hits":len(pred_unique & target_unique),
                "position_hits":positional,
                "random_expected":len(pred_unique)*len(target_unique)/25.0 if pred_unique else 0.0,
                "lookahead_safe":bool((result or {}).get("lookahead_safe",True)),
            }

        for pos,(_base_index,base,_target_index,target) in enumerate(source,start=1):
            if cancel_event is not None and cancel_event.is_set():
                cancelled=True; break
            notify(pos-1,total_rebuild,"RECONSTRUINDO",base)
            target_groups=[int(p["grupo"]) for p in target.get("prizes") or []]
            target_unique=set(target_groups)
            signals={}; benchmarks={}; errors={}
            reset=pull=sim=hist=None
            try:
                reset=self.method_reset_coverage_v1(base["data"],base["sorteio"],base["hora"],top_n=5)
                signals["Reset Cobertura"]=self._decision_signal_payload(reset,"reset")
                benchmarks["Reset Cobertura"]=metric_entry(reset,target_unique)
            except Exception as exc:
                errors["Reset Cobertura"]=str(exc)
            try:
                pull=self.method_convergencia_g5(base["data"],base["sorteio"],base["hora"],top_n=5)
                signals["Puxada Combinada"]=self._decision_signal_payload(pull,"pull")
                benchmarks["Puxada Combinada"]=metric_entry(pull,target_unique)
            except Exception as exc:
                errors["Puxada Combinada"]=str(exc)
            try:
                sim=self.method_similarity_day(base["data"],base["sorteio"],base["hora"],top_days=12)
                signals["Similaridade"]=self._decision_signal_payload(sim,"similarity")
                slots=[int(r["grupo"]) for r in (sim.get("selected") or []) if r.get("grupo")]
                positional=sum(1 for a,b in zip(slots,target_groups) if int(a)==int(b))
                benchmarks["Similaridade"]=metric_entry(sim,target_unique,positional)
            except Exception as exc:
                errors["Similaridade"]=str(exc)
            try:
                hist=self.method_historico_concentrado_v01(base["data"],base["sorteio"],base["hora"],top_n=5)
                benchmarks["Histórico Concentrado"]=metric_entry(hist,target_unique)
            except Exception as exc:
                hist={"selected":[]}
                errors["Histórico Concentrado"]=str(exc)

            required=("Reset Cobertura","Puxada Combinada","Similaridade")
            if all((signals.get(name) or {}).get("available") for name in required):
                reconstructed.append({
                    "base":{"data":base["data"],"sorteio":base["sorteio"],"hora":base["hora"]},
                    "target":{"data":target["data"],"sorteio":target["sorteio"],"hora":target["hora"]},
                    "target_data":target["data"],"target_hora":target["hora"],
                    "signals":signals,"historical":hist or {"selected":[]},
                    "base_draw":base,"result_groups":target_groups,
                    "benchmarks":benchmarks,"errors":errors,
                })
            notify(pos,total_rebuild,"RECONSTRUINDO",base)

        if cancelled:
            return {
                "window":window,"requested_rounds":window,"reconstructed_rounds":len(reconstructed),
                "simulated_rounds":0,"cancelled":True,"summary":[],"details":[],
                "meta_head_to_head":[],"random_baseline":{},"lookahead_safe":True,
                "model_version":"META_LOGIT_NATIVE_V1","brain_frozen":True,
            }

        if len(reconstructed) <= min_train:
            return {
                "window":window,"requested_rounds":window,"reconstructed_rounds":len(reconstructed),
                "simulated_rounds":0,"cancelled":False,"summary":[],"details":[],
                "meta_head_to_head":[],"random_baseline":{},"lookahead_safe":True,
                "model_version":"META_LOGIT_NATIVE_V1","brain_frozen":True,
                "note":f"A reconstrução produziu {len(reconstructed)} rodada(s) válidas; o Meta exige pelo menos {min_train} anteriores para começar.",
            }

        eval_start=max(min_train,len(reconstructed)-window)
        details=[]
        eval_total=len(reconstructed)-eval_start
        for offset,idx in enumerate(range(eval_start,len(reconstructed)),start=1):
            if cancel_event is not None and cancel_event.is_set():
                cancelled=True; break
            current=reconstructed[idx]
            target=current["target"]
            prior=reconstructed[max(0,idx-training_limit):idx]
            base=current["base_draw"]
            notify(offset-1,eval_total,"TREINANDO META",base)

            examples=self._meta_examples(prior,focus_target=target)
            model=self._meta_fit_logit(examples)
            methods={name:copy.deepcopy(current["benchmarks"].get(name,{"available":False})) for name in benchmark_names}
            if model:
                ranking=[]
                for group in range(1,26):
                    x=self._meta_feature_vector(group,current["signals"],current["historical"],current["base_draw"])
                    ranking.append((self._meta_model_score(model,x),group))
                ranking.sort(key=lambda item:(-item[0],item[1]))
                groups=[int(g) for _score,g in ranking[:5]]
                target_unique=set(int(g) for g in current["result_groups"])
                methods["GP-H Meta v0.1"]={
                    "available":True,"groups":groups,
                    "animals":[BICHOS.get(g,str(g)) for g in groups],
                    "scores":[round(float(score),3) for score,_g in ranking[:5]],
                    "coverage_hits":len(set(groups)&target_unique),"position_hits":None,
                    "random_expected":5.0*len(target_unique)/25.0,
                    "training_rounds":len(prior),"training_examples":len(examples),
                    "model_version":"META_LOGIT_NATIVE_V1","lookahead_safe":True,
                }
            else:
                methods["GP-H Meta v0.1"]={
                    "available":False,"groups":[],"animals":[],"coverage_hits":None,
                    "position_hits":None,"random_expected":0.0,"training_rounds":len(prior),
                    "error":"Modelo não pôde ser ajustado.","lookahead_safe":True,
                }
            details.append({
                "base":copy.deepcopy(current["base"]),"target":copy.deepcopy(current["target"]),
                "target_groups":list(current["result_groups"]),
                "target_animals":[BICHOS.get(int(g),str(g)) for g in current["result_groups"]],
                "methods":methods,
            })
            notify(offset,eval_total,"TREINANDO META",base)

        summary=[]
        for method in method_order:
            records=[row["methods"].get(method,{"available":False}) for row in details]
            met=self._walk_forward_metric_summary(records); met["method"]=method
            summary.append(met)
        summary.sort(key=lambda r:(-r["avg_coverage"],-r["pct_2plus"],-r["pct_3plus"],r["method"]))

        # Baseline analítico: Top 5 aleatório entre 25 grupos. As probabilidades
        # 2+/3+ são hipergeométricas e respeitam repetições no resultado real.
        random_rows=[]
        denom=float(comb(25,5))
        for row in details:
            k=len(set(int(g) for g in row.get("target_groups") or []))
            probs={x:0.0 for x in range(6)}
            for x in range(0,6):
                if x<=k and 5-x<=25-k:
                    probs[x]=(comb(k,x)*comb(25-k,5-x))/denom
            random_rows.append({
                "expected":5.0*k/25.0,
                "p1":sum(v for x,v in probs.items() if x>=1),
                "p2":sum(v for x,v in probs.items() if x>=2),
                "p3":sum(v for x,v in probs.items() if x>=3),
                "p4":sum(v for x,v in probs.items() if x>=4),
                "p5":probs.get(5,0.0),
            })
        rn=len(random_rows)
        random_baseline={
            "method":"Acaso esperado","rounds":rn,
            "avg_coverage":sum(r["expected"] for r in random_rows)/rn if rn else 0.0,
            "pct_1plus":sum(r["p1"] for r in random_rows)/rn*100.0 if rn else 0.0,
            "pct_2plus":sum(r["p2"] for r in random_rows)/rn*100.0 if rn else 0.0,
            "pct_3plus":sum(r["p3"] for r in random_rows)/rn*100.0 if rn else 0.0,
            "pct_4plus":sum(r["p4"] for r in random_rows)/rn*100.0 if rn else 0.0,
            "pct_5":sum(r["p5"] for r in random_rows)/rn*100.0 if rn else 0.0,
            "uplift_vs_random":0.0,
        }

        paired=[row for row in details if all((row["methods"].get(m) or {}).get("available") for m in method_order)]
        paired_summary=[]
        for method in method_order:
            vals=[int(row["methods"][method].get("coverage_hits") or 0) for row in paired]
            paired_summary.append({
                "method":method,"rounds":len(vals),
                "avg_coverage":sum(vals)/len(vals) if vals else 0.0,
                "pct_2plus":sum(v>=2 for v in vals)/len(vals)*100.0 if vals else 0.0,
                "pct_3plus":sum(v>=3 for v in vals)/len(vals)*100.0 if vals else 0.0,
            })
        paired_summary.sort(key=lambda r:(-r["avg_coverage"],-r["pct_2plus"],-r["pct_3plus"],r["method"]))

        meta_head_to_head=[]
        for method in benchmark_names:
            vals=[]
            for row in details:
                m=row["methods"].get("GP-H Meta v0.1") or {}
                b=row["methods"].get(method) or {}
                if m.get("available") and b.get("available"):
                    vals.append((int(m.get("coverage_hits") or 0),int(b.get("coverage_hits") or 0)))
            meta_head_to_head.append({
                "method":method,"rounds":len(vals),
                "meta_wins":sum(a>b for a,b in vals),"ties":sum(a==b for a,b in vals),
                "meta_losses":sum(a<b for a,b in vals),
                "avg_diff":sum(a-b for a,b in vals)/len(vals) if vals else 0.0,
            })

        split=max(1,len(details)//2) if details else 0
        robustness=[]
        for method in method_order:
            first=[r["methods"].get(method,{"available":False}) for r in details[:split]]
            second=[r["methods"].get(method,{"available":False}) for r in details[split:]]
            fm=self._walk_forward_metric_summary(first); sm=self._walk_forward_metric_summary(second)
            robustness.append({
                "method":method,"first_rounds":fm["rounds"],"second_rounds":sm["rounds"],
                "first_avg":fm["avg_coverage"],"second_avg":sm["avg_coverage"],
                "delta":sm["avg_coverage"]-fm["avg_coverage"],
            })

        date_from=details[0]["target"]["data"] if details else None
        date_to=details[-1]["target"]["data"] if details else None
        return {
            "window":window,"requested_rounds":window,"reconstructed_rounds":len(reconstructed),
            "simulated_rounds":len(details),"cancelled":cancelled,
            "min_training_rounds":min_train,"training_limit":training_limit,
            "methods":list(method_order),"summary":summary,"paired_rounds":len(paired),
            "paired_summary":paired_summary,"best_paired":paired_summary[0] if paired_summary else None,
            "meta_head_to_head":meta_head_to_head,"random_baseline":random_baseline,
            "robustness":robustness,"details":details,"date_from":date_from,"date_to":date_to,
            "model_version":"META_LOGIT_NATIVE_V1","brain_frozen":True,
            "lookahead_safe":all(
                bool(sig.get("lookahead_safe",True))
                for row in details for sig in row.get("methods",{}).values() if sig.get("available")
            ),
            "note":"Walk-Forward diagnóstico. O cérebro Meta v0.1 permanece congelado e o resultado de cada rodada entra somente depois da previsão.",
        }
'''

lines=text.splitlines(True)
insert_at=anchor.end_lineno
lines[insert_at:insert_at]=[meta_wf+'\n']
text=''.join(lines)

# Reparse after database insertion, then replace only the Meta UI card.
tree=ast.parse(text)
def method_node(class_name, method_name):
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
    return next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==method_name)

old_ui=method_node('App','_decision_build_meta')
new_ui=r'''    def _decision_build_meta(self, body, snapshot):
        meta=(snapshot or {}).get("meta") or {}
        summary=self.db.meta_shadow_summary(limit=120)
        card=ttk.Frame(body,style="Card.TFrame",padding=11)
        card.pack(fill="x",pady=(0,8))
        head=ttk.Frame(card,style="Card.TFrame"); head.pack(fill="x")
        ttk.Label(head,text="GP-H META v0.1 — SOMBRA",style="CardTitle.TLabel").pack(side="left")
        ttk.Label(head,text=meta.get("status") or "AGUARDANDO",style="CardMuted.TLabel").pack(side="right")

        if not meta:
            ttk.Label(card,text="A leitura Meta ainda não foi congelada para esta rodada.",style="CardMuted.TLabel").pack(anchor="w",pady=(6,0))
        elif not meta.get("available"):
            n=int(meta.get("training_snapshots") or 0); minimum=int(meta.get("minimum_snapshots") or 20)
            ttk.Label(card,text=f"Aprendizado em formação: {n}/{minimum} snapshots auditados.",style="Card.TLabel",font=("Segoe UI Semibold",12)).pack(anchor="w",pady=(6,2))
            ttk.Label(card,text=meta.get("reason") or "Aguardando amostra suficiente.",style="CardMuted.TLabel",wraplength=1060).pack(anchor="w")
        else:
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
        ).pack(anchor="w",pady=(4,0))

        ttk.Separator(card,orient="horizontal").pack(fill="x",pady=(10,8))
        wf_head=ttk.Frame(card,style="Card.TFrame"); wf_head.pack(fill="x")
        ttk.Label(wf_head,text="WALK-FORWARD RIGOROSO DO META",style="CardTitle.TLabel").pack(side="left")
        ttk.Label(wf_head,text="v0.42 • cérebro v0.1 congelado",style="CardMuted.TLabel").pack(side="right")
        ttk.Label(
            card,
            text="Treina somente nas rodadas anteriores, prevê a próxima sem ver o resultado e avança no tempo. Compara Meta, Reset, Puxada, Similaridade, Histórico Concentrado e o acaso esperado.",
            style="CardMuted.TLabel",wraplength=1060,
        ).pack(anchor="w",pady=(3,6))

        controls=ttk.Frame(card,style="Card.TFrame"); controls.pack(fill="x")
        ttk.Label(controls,text="Rodadas avaliadas",style="CardMuted.TLabel").pack(side="left")
        if not hasattr(self,"meta_wf_window"):
            self.meta_wf_window=tk.StringVar(value="30")
        ttk.Combobox(controls,textvariable=self.meta_wf_window,values=["20","30","60"],width=6,state="readonly").pack(side="left",padx=(5,8))
        self.meta_wf_run_btn=ttk.Button(controls,text="SIMULAR META",command=self._meta_walk_forward_start)
        self.meta_wf_run_btn.pack(side="left")
        self.meta_wf_cancel_btn=ttk.Button(controls,text="Cancelar",command=self._meta_walk_forward_cancel)
        self.meta_wf_cancel_btn.pack(side="left",padx=(6,0))
        self.meta_wf_export_btn=ttk.Button(controls,text="Exportar CSV",command=self._meta_walk_forward_export)
        self.meta_wf_export_btn.pack(side="right")

        self.meta_wf_progress=ttk.Progressbar(card,mode="determinate",maximum=100)
        self.meta_wf_progress.pack(fill="x",pady=(8,3))
        self.meta_wf_status=ttk.Label(card,text="Escolha 20, 30 ou 60 rodadas e clique em SIMULAR META.",style="CardMuted.TLabel",wraplength=1060)
        self.meta_wf_status.pack(anchor="w")

        cols=("method","rounds","avg","p2","p3","uplift")
        self.meta_wf_tree=ttk.Treeview(card,columns=cols,show="headings",height=6)
        heads={"method":"Método","rounds":"N","avg":"Cobertura","p2":"2+","p3":"3+","uplift":"vs. acaso"}
        widths={"method":230,"rounds":55,"avg":100,"p2":85,"p3":85,"uplift":95}
        for c in cols:
            self.meta_wf_tree.heading(c,text=heads[c]); self.meta_wf_tree.column(c,width=widths[c],anchor="w" if c=="method" else "center")
        self.meta_wf_tree.pack(fill="x",pady=(7,3))

        ttk.Label(card,text="Meta × cada método nas mesmas rodadas",style="Card.TLabel",font=("Segoe UI Semibold",9)).pack(anchor="w",pady=(6,2))
        hcols=("method","rounds","wins","ties","losses","diff")
        self.meta_wf_h2h_tree=ttk.Treeview(card,columns=hcols,show="headings",height=4)
        hheads={"method":"Comparado com","rounds":"N","wins":"Meta melhor","ties":"Empate","losses":"Meta pior","diff":"Δ média"}
        hwidths={"method":230,"rounds":55,"wins":90,"ties":75,"losses":85,"diff":85}
        for c in hcols:
            self.meta_wf_h2h_tree.heading(c,text=hheads[c]); self.meta_wf_h2h_tree.column(c,width=hwidths[c],anchor="w" if c=="method" else "center")
        self.meta_wf_h2h_tree.pack(fill="x",pady=(0,3))
        self.meta_wf_note=ttk.Label(card,text="",style="CardMuted.TLabel",wraplength=1060)
        self.meta_wf_note.pack(anchor="w")

        running=bool(getattr(self,"_meta_wf_running",False))
        if running:
            self.meta_wf_run_btn.configure(state="disabled"); self.meta_wf_cancel_btn.configure(state="normal")
            st=getattr(self,"_meta_wf_progress_state",None) or (0,1,"Preparando…")
            done,total,label=st
            self.meta_wf_progress.configure(value=(done/max(1,total))*100.0); self.meta_wf_status.configure(text=label)
        else:
            self.meta_wf_cancel_btn.configure(state="disabled")
        result=getattr(self,"meta_walk_forward_last_result",None)
        if result:
            self._meta_walk_forward_render(result)
        else:
            self.meta_wf_export_btn.configure(state="disabled")

    def _meta_walk_forward_ui_alive(self):
        try:
            return self._page=="decision" and self.meta_wf_tree.winfo_exists()
        except Exception:
            return False

    def _meta_walk_forward_start(self):
        if getattr(self,"_meta_wf_running",False):
            return
        try: window=int(self.meta_wf_window.get())
        except Exception: window=30
        self._meta_wf_running=True
        self._meta_wf_cancel_event=threading.Event(); self._meta_wf_queue=queue.Queue()
        self._meta_wf_progress_state=(0,1,"Preparando o histórico do Meta…")
        if self._meta_walk_forward_ui_alive():
            self.meta_wf_run_btn.configure(state="disabled"); self.meta_wf_cancel_btn.configure(state="normal")
            self.meta_wf_export_btn.configure(state="disabled"); self.meta_wf_progress.configure(value=0)
            self.meta_wf_status.configure(text="Reconstruindo sinais históricos sem look-ahead…")
        q=self._meta_wf_queue; cancel_event=self._meta_wf_cancel_event
        def progress(done,total,info):
            phase=info.get("phase") or "PROCESSANDO"
            suffix=f"{info.get('data') or '—'} {info.get('sorteio') or ''} {info.get('hora') or ''}".strip()
            q.put(("progress",done,total,f"{phase} • {done}/{total} • {suffix}"))
        def worker():
            try:
                q.put(("done",self.db.meta_walk_forward(window=window,progress_callback=progress,cancel_event=cancel_event)))
            except Exception as exc:
                q.put(("error",str(exc)))
        threading.Thread(target=worker,daemon=True,name="GPH-MetaWalkForward").start()
        self.after(120,self._meta_walk_forward_poll)

    def _meta_walk_forward_cancel(self):
        event=getattr(self,"_meta_wf_cancel_event",None)
        if event is not None: event.set()
        if self._meta_walk_forward_ui_alive(): self.meta_wf_status.configure(text="Cancelamento solicitado…")

    def _meta_walk_forward_poll(self):
        q=getattr(self,"_meta_wf_queue",None)
        if q is None: return
        finished=False
        while True:
            try: msg=q.get_nowait()
            except queue.Empty: break
            kind=msg[0]
            if kind=="progress":
                _k,done,total,label=msg; self._meta_wf_progress_state=(done,total,label)
                if self._meta_walk_forward_ui_alive():
                    self.meta_wf_progress.configure(value=(done/max(1,total))*100.0); self.meta_wf_status.configure(text=label)
            elif kind=="done":
                self.meta_walk_forward_last_result=msg[1]; self._meta_wf_running=False; finished=True
                if self._meta_walk_forward_ui_alive(): self._meta_walk_forward_render(msg[1])
            elif kind=="error":
                self._meta_wf_running=False; finished=True
                if self._meta_walk_forward_ui_alive():
                    self.meta_wf_status.configure(text="Falha no Walk-Forward Meta: "+str(msg[1]))
                    self.meta_wf_run_btn.configure(state="normal"); self.meta_wf_cancel_btn.configure(state="disabled")
        if getattr(self,"_meta_wf_running",False) and not finished:
            self.after(120,self._meta_walk_forward_poll)

    def _meta_walk_forward_render(self, result):
        if not self._meta_walk_forward_ui_alive(): return
        for tree in (self.meta_wf_tree,self.meta_wf_h2h_tree):
            for item in tree.get_children(): tree.delete(item)
        for row in result.get("summary") or []:
            self.meta_wf_tree.insert("","end",values=(
                row.get("method"),int(row.get("rounds") or 0),f"{float(row.get('avg_coverage') or 0):.2f}/5",
                f"{float(row.get('pct_2plus') or 0):.1f}%",f"{float(row.get('pct_3plus') or 0):.1f}%",
                f"{float(row.get('uplift_vs_random') or 0):+.2f}",
            ))
        rb=result.get("random_baseline") or {}
        if rb:
            self.meta_wf_tree.insert("","end",values=(
                "Acaso esperado",int(rb.get("rounds") or 0),f"{float(rb.get('avg_coverage') or 0):.2f}/5",
                f"{float(rb.get('pct_2plus') or 0):.1f}%",f"{float(rb.get('pct_3plus') or 0):.1f}%","+0.00",
            ))
        for row in result.get("meta_head_to_head") or []:
            self.meta_wf_h2h_tree.insert("","end",values=(
                row.get("method"),int(row.get("rounds") or 0),int(row.get("meta_wins") or 0),
                int(row.get("ties") or 0),int(row.get("meta_losses") or 0),f"{float(row.get('avg_diff') or 0):+.2f}",
            ))
        n=int(result.get("simulated_rounds") or 0)
        if result.get("cancelled"):
            status=f"Simulação cancelada • {n} rodada(s) concluída(s)."
        elif n:
            status=f"Walk-Forward concluído • {n} rodada(s) avaliadas • {result.get('date_from') or '—'} a {result.get('date_to') or '—'}."
        else:
            status=result.get("note") or "Nenhuma rodada pôde ser avaliada."
        self.meta_wf_progress.configure(value=100 if not result.get("cancelled") else self.meta_wf_progress["value"])
        self.meta_wf_status.configure(text=status)
        self.meta_wf_note.configure(text=(
            f"Treino mínimo {int(result.get('min_training_rounds') or 20)} • até {int(result.get('training_limit') or 160)} rodadas anteriores por previsão. "
            "O cérebro META_LOGIT_NATIVE_V1 é o mesmo da v0.41; este simulador só mede desempenho e não alimenta nem altera o Meta prospectivo."
        ))
        self.meta_wf_run_btn.configure(state="normal"); self.meta_wf_cancel_btn.configure(state="disabled")
        self.meta_wf_export_btn.configure(state="normal" if n else "disabled")

    def _meta_walk_forward_export(self):
        result=getattr(self,"meta_walk_forward_last_result",None)
        if not result or not result.get("details"):
            messagebox.showinfo("Walk-Forward Meta","Execute uma simulação primeiro.",parent=self); return
        path=filedialog.asksaveasfilename(
            parent=self,defaultextension=".csv",filetypes=[("CSV","*.csv")],
            initialdir=str(EXPORT_DIR),initialfile="gph_meta_walk_forward.csv",
        )
        if not path: return
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f,delimiter=";")
            w.writerow(["Base","Alvo","Método","Grupos previstos","Acertos","Treino anterior"])
            for row in result.get("details") or []:
                base=f"{row['base'].get('data')} {row['base'].get('sorteio')} {row['base'].get('hora')}"
                target=f"{row['target'].get('data')} {row['target'].get('sorteio')} {row['target'].get('hora')}"
                for method,sig in (row.get("methods") or {}).items():
                    if not sig.get("available"): continue
                    w.writerow([
                        base,target,method," ".join(f"{int(g):02d}" for g in sig.get("groups") or []),
                        sig.get("coverage_hits"),sig.get("training_rounds","")
                    ])
        messagebox.showinfo("Walk-Forward Meta",f"Relatório exportado em:\n{path}",parent=self)
'''

lines=text.splitlines(True)
start=old_ui.lineno-1; end=old_ui.end_lineno
lines[start:end]=[new_ui+'\n']
text=''.join(lines)

# ---------------------------------------------------------------------------
# 2) Versão/documentação. O plano de observação fica registrado no projeto.
# ---------------------------------------------------------------------------
text=text.replace('GP-H Central Histórica v0.41.0','GP-H Central Histórica v0.42.0',1)
text=text.replace('APP_VERSION = "0.41.0"','APP_VERSION = "0.42.0"',1)

# Se houver histórico textual no Sobre, acrescenta sem depender da posição exata.
marker='            "• v0.41.0 —'
if marker in text:
    pos=text.find(marker)
    text=text[:pos]+'            "• v0.42.0 — Walk-Forward rigoroso do GP-H Meta v0.1, sem alterar o cérebro prospectivo.\\n"\n'+text[pos:]

ast.parse(text)
after=func_ast(text,CRITICAL)
for name in CRITICAL:
    if before[name] != after[name]:
        raise SystemExit('REGRESSÃO: função congelada mudou: '+name)
if 'def meta_walk_forward(' not in text or 'def _meta_walk_forward_start(' not in text:
    raise SystemExit('Motor/UI v0.42.0 não foram inseridos')
if 'APP_VERSION = "0.42.0"' not in text:
    raise SystemExit('Versão v0.42.0 não aplicada')

SRC.write_text(text,encoding='utf-8')

doc=DOC.read_text(encoding='utf-8')
revision='''REVISÃO v0.42.0 — WALK-FORWARD RIGOROSO DO GP-H META\n- O cérebro GP-H Meta v0.1 da v0.41.0 permanece CONGELADO: mesmas 20 características, regressão logística nativa L2, treino mínimo de 20 snapshots e limite prospectivo de 160.\n- A v0.42.0 acrescenta SOMENTE avaliação: para cada rodada histórica avaliada, treina nas rodadas anteriores, prevê o Top 5 sem ver o alvo, mede depois e avança uma rodada.\n- Compara GP-H Meta v0.1, Reset Cobertura, Puxada Combinada, Similaridade, Histórico Concentrado e baseline matemático de Top 5 aleatório.\n- O baseline do acaso usa distribuição hipergeométrica e respeita a quantidade de bichos distintos realmente presentes nos cinco prêmios.\n- O Walk-Forward Meta é diagnóstico, roda em segundo plano, pode ser cancelado, oferece janelas de 20/30/60 rodadas e CSV. Ele não alimenta o Meta prospectivo e não promove método.\n- REGRA DE EVOLUÇÃO CONGELADA: após v0.42.0, usar a Central normalmente por 2–3 dias antes de mudar o cérebro do Meta. Erros técnicos podem ser corrigidos, mas desempenho não deve ser otimizado rodada a rodada. Fazer primeiro checkpoint com a coleta real e preferir 20–30 rodadas prospectivas antes de discutir v0.43 (calibração/confiança/drift).\n- Reset + 3+1 continua oficial.\n\n'''
if not doc.startswith('REVISÃO v0.42.0'):
    doc=revision+doc
DOC.write_text(doc,encoding='utf-8')

print('PATCH v0.42.0 OK')
print('linhas',len(text.splitlines()))
print('cérebro Meta e motores oficiais preservados:',', '.join(sorted(CRITICAL)))
