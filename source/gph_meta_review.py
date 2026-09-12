"""Revisão estrutural prospectiva do GP-H Meta — v0.48.5."""
from __future__ import annotations
import json, math
from collections import defaultdict
import tkinter as tk
from tkinter import ttk

MIN_REVIEW_ROUNDS=8
DECISION_ROUNDS=20
MAX_ROUNDS=60


def _load(value, default):
    if isinstance(value, type(default)): return value
    try:
        out=json.loads(value or "")
        return out if isinstance(out,type(default)) else default
    except Exception: return default


def _groups(values, limit=None, unique=True):
    out=[]
    for raw in values or []:
        if isinstance(raw,dict): raw=raw.get("grupo")
        try: g=int(raw)
        except Exception: continue
        if not 1<=g<=25: continue
        if not unique or g not in out: out.append(g)
        if limit and len(out)>=limit: break
    return out


def _result_groups(db,row):
    audit=_load(row.get("meta_audit_json"),{})
    vals=_groups(audit.get("result_groups"),unique=False)
    if vals:return vals
    vals=_groups(_load(row.get("result_groups_json"),[]),unique=False)
    if vals:return vals
    try: draw=db.get_draw(row.get("target_data"),row.get("target_sorteio"),row.get("target_hora"))
    except Exception: draw=None
    return _groups([p.get("grupo") for p in ((draw or {}).get("prizes") or [])[:5] if isinstance(p,dict)],unique=False)


def _ranking(meta):
    out=[]
    for i,item in enumerate(list((meta or {}).get("ranking") or []),1):
        if not isinstance(item,dict): continue
        try:g=int(item.get("grupo"));rank=int(item.get("rank") or i)
        except Exception:continue
        if 1<=g<=25: out.append((rank,g,item.get("score")))
    out.sort()
    if not out: out=[(i,g,None) for i,g in enumerate(_groups((meta or {}).get("groups"),5),1)]
    return out


def _signals(row):
    payload=_load(row.get("signals_json"),{})
    ans={}
    for name,item in payload.items():
        if isinstance(item,dict) and item.get("available") is not False:
            gs=_groups(item.get("groups"))
            if gs: ans[str(name)]=gs
    return ans


def _rand_hits(m): return 5.0*float(m)/25.0

def _rand_2plus(m):
    m=max(0,min(25,int(m))); den=math.comb(25,5)
    p0=math.comb(25-m,5)/den if 25-m>=5 else 0
    p1=m*math.comb(25-m,4)/den if m and 25-m>=4 else 0
    return max(0.0,min(1.0,1-p0-p1))


def collect(db,limit=MAX_ROUNDS):
    con=db.connect()
    try:
        rows=con.execute("""SELECT id,target_data,target_sorteio,target_hora,meta_json,meta_frozen_at,
            meta_audit_json,result_groups_json,signals_json FROM decision_snapshots
            WHERE meta_json IS NOT NULL AND TRIM(meta_json)<>'' AND meta_frozen_at IS NOT NULL
            AND TRIM(meta_frozen_at)<>'' ORDER BY target_data DESC,target_hora DESC,id DESC LIMIT ?""",
            (max(1,int(limit)*3),)).fetchall()
    finally:
        try:con.close()
        except Exception:pass
    out=[]
    for raw in rows:
        row=dict(raw); meta=_load(row.get("meta_json"),{})
        if meta.get("available") is False: continue
        top5=_groups(meta.get("groups"),5)
        if len(top5)!=5: continue
        result=_result_groups(db,row)
        if not result: continue
        actual=set(result); ranking=_ranking(meta); ranks={g:r for r,g,_ in ranking}; top10=[g for r,g,_ in ranking if r<=10]
        signals=_signals(row); support={g:[n for n,gs in signals.items() if g in gs] for g in range(1,26)}
        missed=actual-set(top5); near={g for g in missed if 6<=ranks.get(g,999)<=10}; consensus={g for g in missed if len(support[g])>=2}
        out.append({"data":row.get("target_data"),"sorteio":row.get("target_sorteio"),"hora":row.get("target_hora"),
                    "top5":top5,"actual":sorted(actual),"coverage":len(set(top5)&actual),"top10_hits":len(set(top10)&actual),
                    "missed":sorted(missed),"near":sorted(near),"consensus":sorted(consensus),"signals":signals,
                    "low_support":[g for g in top5 if len(support[g])<=1],"random_hits":_rand_hits(len(actual)),"random_2plus":_rand_2plus(len(actual))})
        if len(out)>=limit:break
    out.reverse();return out


def summarize(records):
    rs=list(records or []); n=len(rs)
    if not n:return {"available":False,"n":0,"decision":"SEM AMOSTRA","detail":"Ainda não há snapshots Meta congelados com resultado real.","records":[],"changes_meta":False,"lookahead_safe":True,"target_is_diagnostic_only":True}
    avg=sum(r["coverage"] for r in rs)/n; rate2=sum(r["coverage"]>=2 for r in rs)/n; rate3=sum(r["coverage"]>=3 for r in rs)/n
    rnd=sum(r["random_hits"] for r in rs)/n; rnd2=sum(r["random_2plus"] for r in rs)/n
    missed=sum(len(r["missed"]) for r in rs); near=sum(len(r["near"]) for r in rs); consensus=sum(len(r["consensus"]) for r in rs); low=sum(len(r["low_support"]) for r in rs)
    comp=defaultdict(lambda:{"rounds":0,"hits":0,"rescues":0})
    for r in rs:
        actual=set(r["actual"]); lost=set(r["missed"])
        for name,gs in r["signals"].items():
            comp[name]["rounds"]+=1;comp[name]["hits"]+=len(set(gs)&actual);comp[name]["rescues"]+=len(set(gs)&lost)
    comps=[]
    for name,v in comp.items(): comps.append({"method":name,**v,"avg_hits":v["hits"]/(v["rounds"] or 1)})
    comps.sort(key=lambda x:(-x["rescues"],-x["avg_hits"],x["method"]))
    near_rate=near/missed if missed else 0; cons_rate=consensus/missed if missed else 0; low_rate=low/(5*n)
    if n<MIN_REVIEW_ROUNDS: decision="AMOSTRA INSUFICIENTE";detail=f"{n} rodada(s): continue coletando sem recalibrar."
    elif n<DECISION_ROUNDS: decision="REVISÃO ESTRUTURAL";detail=f"{n} rodadas permitem diagnóstico, mas ainda não recalibração; meta de decisão permanece {DECISION_ROUNDS}."
    elif rate2>0.50: decision="MANTER";detail="Taxa 2+ superou 50%; preservar o cérebro e observar conversão em Terno."
    elif near_rate>=.35 or cons_rate>=.25: decision="AJUSTE PEQUENO EM LABORATÓRIO";detail="Há sinal de cutoff/balanceamento; testar candidato fora da amostra antes de promover."
    else: decision="RECALIBRAR EM LABORATÓRIO";detail="Cobertura segue fraca após 20+ rodadas; revisar pesos/features apenas em candidato walk-forward."
    return {"available":True,"n":n,"coverage_avg":avg,"rate2":rate2,"rate3":rate3,"random_avg":rnd,"random_rate2":rnd2,
            "missed":missed,"near":near,"near_rate":near_rate,"consensus":consensus,"consensus_rate":cons_rate,"low":low,"low_rate":low_rate,
            "components":comps,"decision":decision,"detail":detail,"records":rs,"changes_meta":False,"lookahead_safe":True,"target_2plus_pct":50.0,"target_is_diagnostic_only":True}


def meta_structural_review(db,limit=MAX_ROUNDS): return summarize(collect(db,limit))
def _pct(x): return f"{100*x:.1f}%".replace(".",",")
def _num(x): return f"{x:.2f}".replace(".",",")
def _gt(gs): return "-".join(f"{g:02d}" for g in gs) if gs else "—"


def _build(app,body):
    try:r=meta_structural_review(app.db)
    except Exception as exc:
        c=ttk.Frame(body,style="Card.TFrame",padding=10);c.pack(fill="x",pady=(8,0));ttk.Label(c,text="REVISÃO ESTRUTURAL DO META",style="CardTitle.TLabel").pack(anchor="w");ttk.Label(c,text=str(exc),style="CardMuted.TLabel").pack(anchor="w");return
    c=ttk.Frame(body,style="Card.TFrame",padding=12);c.pack(fill="x",pady=(8,0));h=ttk.Frame(c,style="Card.TFrame");h.pack(fill="x")
    ttk.Label(h,text="REVISÃO ESTRUTURAL DO META",style="CardTitle.TLabel").pack(side="left");ttk.Label(h,text="prospectivo • não altera o cérebro",style="CardMuted.TLabel").pack(side="right")
    ttk.Label(c,text=f"DECISÃO: {r['decision']} — {r['detail']}",style="Card.TLabel",wraplength=1500,justify="left").pack(fill="x",anchor="w",pady=(7,6))
    if not r.get("available"):return
    summary=(f"{r['n']} rodadas • cobertura {_num(r['coverage_avg'])}/5 • Taxa 2+ {_pct(r['rate2'])} • acaso esp. {_num(r['random_avg'])}/5 "
             f"(Taxa 2+ ~{_pct(r['random_rate2'])}) • perdidos em rank 6–10: {r['near']}/{r['missed']} ({_pct(r['near_rate'])}) • "
             f"consenso perdido: {r['consensus']}/{r['missed']} ({_pct(r['consensus_rate'])}) • Top5 com <=1 sinal: {r['low']}/{5*r['n']} ({_pct(r['low_rate'])}).")
    ttk.Label(c,text=summary,style="CardMuted.TLabel",wraplength=1500,justify="left").pack(fill="x",anchor="w",pady=(0,6))
    clues=[]
    if r['coverage_avg']<r['random_avg']:clues.append("cobertura abaixo do acaso esperado")
    if r['near_rate']>=.35:clues.append("muitos bichos reais estão logo fora do Top 5")
    if r['consensus_rate']>=.25:clues.append("há bichos reais com 2+ sinais que o Meta deixou fora")
    if r['low_rate']>=.35:clues.append("muitos selecionados entram com baixa convergência")
    if not clues:clues.append("sem padrão dominante ainda; continuar coleta")
    ttk.Label(c,text="LEITURA: "+" • ".join(clues)+". A régua >50% segue somente diagnóstica.",style="CardMuted.TLabel",wraplength=1500,justify="left").pack(fill="x",anchor="w",pady=(0,6))
    if r['components']:
        tx=" • ".join(f"{x['method']}: {x['rescues']} resgate(s), média {_num(x['avg_hits'])}" for x in r['components'][:5])
        ttk.Label(c,text="RESGATES POR COMPONENTE: "+tx,style="CardMuted.TLabel",wraplength=1500,justify="left").pack(fill="x",anchor="w",pady=(0,7))
    t=ttk.Treeview(c,columns=("alvo","top5","real","cov","near","cons"),show="headings",height=min(10,max(4,len(r['records']))))
    heads=("Alvo","Top 5 congelado","Resultado real","Cobertura","Rank 6–10","Perdidos c/ 2+ sinais")
    for key,title in zip(t['columns'],heads):t.heading(key,text=title);t.column(key,width=170 if key in ('alvo','top5','real') else 120,anchor="w",stretch=True)
    for x in r['records'][-20:]:t.insert("","end",values=(f"{x['data']} • {x['sorteio']} • {x['hora']}",_gt(x['top5']),_gt(x['actual']),f"{x['coverage']}/5",_gt(x['near']),_gt(x['consensus'])))
    t.pack(fill="x",pady=(0,6))
    s=tk.StringVar(value="Somente snapshots congelados antes do resultado entram nesta auditoria.")
    f=ttk.Frame(c,style="Card.TFrame");f.pack(fill="x");ttk.Label(f,textvariable=s,style="CardMuted.TLabel").pack(side="left")
    def copy():
        txt=(f"GP-H Meta — revisão estrutural\nDecisão: {r['decision']}\nRodadas: {r['n']}\nCobertura: {_num(r['coverage_avg'])}/5\nTaxa 2+: {_pct(r['rate2'])}\n"
             f"Acaso: {_num(r['random_avg'])}/5; Taxa 2+ ~{_pct(r['random_rate2'])}\nRank 6–10: {r['near']}/{r['missed']} ({_pct(r['near_rate'])})\n"
             f"Consenso perdido: {r['consensus']}/{r['missed']} ({_pct(r['consensus_rate'])})\nNão altera o cérebro Meta.")
        try:app.clipboard_clear();app.clipboard_append(txt);app.update_idletasks();s.set("Resumo copiado.")
        except Exception as exc:s.set(str(exc))
    ttk.Button(f,text="COPIAR RESUMO",command=copy).pack(side="right")


def install_meta_review(central_module):
    cls=central_module.App
    if getattr(cls,"_meta_review_v0485_installed",False):return
    original=getattr(cls,"_decision_build_coverage_evolution",None)
    if original is None:return
    def wrapped(self,body,*a,**k):
        result=original(self,body,*a,**k)
        try:_build(self,body)
        except Exception:pass
        return result
    cls._decision_build_coverage_evolution=wrapped;cls._meta_review_v0485_installed=True
