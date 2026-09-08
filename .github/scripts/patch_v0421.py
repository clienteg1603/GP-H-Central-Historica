from pathlib import Path
import ast, re

SRC=Path('source/gph_central.py')
DOC=Path('source/DOCUMENTACAO_GP-H.txt')
text=SRC.read_text(encoding='utf-8')
old=text


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
    'decision_walk_forward','freeze_meta_snapshot','meta_shadow_summary','historical_pulls'
]
before={n:fn_dump(text,n) for n in critical}

text=text.replace('import threading\nimport copy', 'import threading\nimport multiprocessing as mp\nimport copy',1)
text=text.replace('GP-H Central Histórica v0.42.0','GP-H Central Histórica v0.42.1',1)
text=text.replace('APP_VERSION = "0.42.0"','APP_VERSION = "0.42.1"',1)
text=text.replace('text="v0.42 • cérebro v0.1 congelado"','text="v0.42.1 • cérebro v0.1 congelado"',1)

start=text.index('    def _meta_walk_forward_start(self):')
end=text.index('    def _meta_walk_forward_render(self, result):',start)
new_block=r'''    def _meta_walk_forward_start(self):
        if getattr(self,"_meta_wf_running",False):
            return
        try:
            window=int(self.meta_wf_window.get())
        except Exception:
            window=30

        self._meta_wf_running=True
        self._meta_wf_progress_state=(0,1,"Preparando o histórico do Meta…")
        self._meta_wf_dead_polls=0
        if self._meta_walk_forward_ui_alive():
            self.meta_wf_run_btn.configure(state="disabled")
            self.meta_wf_cancel_btn.configure(state="normal")
            self.meta_wf_export_btn.configure(state="disabled")
            self.meta_wf_progress.configure(value=0)
            self.meta_wf_status.configure(text="Iniciando processo isolado do Walk-Forward…")

        try:
            # v0.42.1: CPU-bound Meta sai do processo do Tk. Em thread, o treino
            # Python puro disputava o GIL com a interface e causava microtravadas.
            ctx=mp.get_context("spawn")
            self._meta_wf_queue=ctx.Queue()
            self._meta_wf_cancel_event=ctx.Event()
            proc=ctx.Process(
                target=_meta_walk_forward_process_worker,
                args=(str(self.db.path),window,self._meta_wf_queue,self._meta_wf_cancel_event),
                daemon=True,
                name="GPH-MetaWalkForward",
            )
            self._meta_wf_process=proc
            proc.start()
        except Exception as exc:
            self._meta_wf_running=False
            self._meta_wf_process=None
            if self._meta_walk_forward_ui_alive():
                self.meta_wf_status.configure(text="Falha ao iniciar o processo do Walk-Forward: "+str(exc))
                self.meta_wf_run_btn.configure(state="normal")
                self.meta_wf_cancel_btn.configure(state="disabled")
            return
        self.after(120,self._meta_walk_forward_poll)

    def _meta_walk_forward_cancel(self):
        event=getattr(self,"_meta_wf_cancel_event",None)
        if event is not None:
            try:
                event.set()
            except Exception:
                pass
        if self._meta_walk_forward_ui_alive():
            self.meta_wf_status.configure(text="Cancelamento solicitado…")

    def _meta_walk_forward_process_cleanup(self):
        proc=getattr(self,"_meta_wf_process",None)
        if proc is not None:
            try:
                proc.join(timeout=0.15)
            except Exception:
                pass
        self._meta_wf_process=None
        q=getattr(self,"_meta_wf_queue",None)
        if q is not None:
            try:
                q.close()
            except Exception:
                pass
        self._meta_wf_queue=None
        self._meta_wf_cancel_event=None

    def _meta_walk_forward_poll(self):
        q=getattr(self,"_meta_wf_queue",None)
        if q is None:
            return
        finished=False
        while True:
            try:
                msg=q.get_nowait()
            except queue.Empty:
                break
            except (EOFError,OSError):
                break
            kind=msg[0]
            if kind=="progress":
                _k,done,total,label=msg
                self._meta_wf_progress_state=(done,total,label)
                if self._meta_walk_forward_ui_alive():
                    self.meta_wf_progress.configure(value=(done/max(1,total))*100.0)
                    self.meta_wf_status.configure(text=label)
            elif kind=="done":
                self.meta_walk_forward_last_result=msg[1]
                self._meta_wf_running=False
                finished=True
                if self._meta_walk_forward_ui_alive():
                    self._meta_walk_forward_render(msg[1])
            elif kind=="error":
                self._meta_wf_running=False
                finished=True
                if self._meta_walk_forward_ui_alive():
                    self.meta_wf_status.configure(text="Falha no Walk-Forward Meta: "+str(msg[1]))
                    self.meta_wf_run_btn.configure(state="normal")
                    self.meta_wf_cancel_btn.configure(state="disabled")

        proc=getattr(self,"_meta_wf_process",None)
        if finished:
            self._meta_walk_forward_process_cleanup()
            return

        # Se o worker caiu sem conseguir enviar a mensagem de erro, não deixa a
        # interface presa para sempre em "processando". Exit 0 recebe alguns polls
        # extras para a fila terminar de descarregar o resultado.
        if proc is not None and not proc.is_alive():
            exitcode=proc.exitcode
            self._meta_wf_dead_polls=int(getattr(self,"_meta_wf_dead_polls",0))+1
            if exitcode not in (None,0) or self._meta_wf_dead_polls>=5:
                self._meta_wf_running=False
                if self._meta_walk_forward_ui_alive():
                    self.meta_wf_status.configure(text=f"O processo do Walk-Forward encerrou inesperadamente (código {exitcode}).")
                    self.meta_wf_run_btn.configure(state="normal")
                    self.meta_wf_cancel_btn.configure(state="disabled")
                self._meta_walk_forward_process_cleanup()
                return
        else:
            self._meta_wf_dead_polls=0

        if getattr(self,"_meta_wf_running",False):
            self.after(120,self._meta_walk_forward_poll)

'''
text=text[:start]+new_block+text[end:]

worker=r'''

def _meta_walk_forward_process_worker(db_path, window, out_queue, cancel_event):
    """Worker CPU-bound do Meta em processo separado; não toca na interface."""
    try:
        # Prioridade menor preserva fluidez do processo principal mesmo em PCs
        # com poucos núcleos. Isso não altera cálculo, ordem ou dados do modelo.
        try:
            if os.name == "nt":
                import ctypes
                BELOW_NORMAL_PRIORITY_CLASS=0x00004000
                kernel32=ctypes.windll.kernel32
                kernel32.SetPriorityClass(kernel32.GetCurrentProcess(),BELOW_NORMAL_PRIORITY_CLASS)
            else:
                os.nice(5)
        except Exception:
            pass

        db=Database(Path(db_path))
        def progress(done,total,info):
            phase=(info or {}).get("phase") or "PROCESSANDO"
            suffix=f"{(info or {}).get('data') or '—'} {(info or {}).get('sorteio') or ''} {(info or {}).get('hora') or ''}".strip()
            out_queue.put(("progress",done,total,f"{phase} • {done}/{total} • {suffix}"))
        result=db.meta_walk_forward(
            window=window,
            progress_callback=progress,
            cancel_event=cancel_event,
        )
        out_queue.put(("done",result))
    except BaseException as exc:
        try:
            out_queue.put(("error",f"{type(exc).__name__}: {exc}"))
        except Exception:
            pass

'''
marker='\n\nif __name__ == "__main__":\n'
assert marker in text
text=text.replace(marker,worker+marker,1)
text=text.replace('if __name__ == "__main__":\n    try:', 'if __name__ == "__main__":\n    mp.freeze_support()\n    try:',1)

# Documentação: patch técnico, cérebro continua congelado.
doc=DOC.read_text(encoding='utf-8')
header='''REVISÃO v0.42.1 — DESEMPENHO DO WALK-FORWARD META\n- Correção exclusivamente técnica: SIMULAR META deixa de executar o treino CPU-bound em thread do processo da interface e passa a usar processo separado.\n- O worker usa prioridade reduzida quando possível para preservar fluidez da janela principal.\n- Barra de progresso, Cancelar, 20/30/60 rodadas, comparação e CSV permanecem.\n- O cérebro GP-H Meta v0.1 continua congelado: nenhuma característica, peso, regressão, janela de treino, método ou métrica foi alterada.\n- A regra de observação permanece: após a correção técnica, usar normalmente por 2–3 dias e evitar otimização por desempenho antes do checkpoint prospectivo.\n\n'''
if not doc.startswith('REVISÃO v0.42.1'):
    doc=header+doc

ast.parse(text)
after={n:fn_dump(text,n) for n in critical}
changed=[n for n in critical if before[n]!=after[n]]
assert not changed, f'motores críticos alterados: {changed}'
assert 'APP_VERSION = "0.42.1"' in text
assert 'import multiprocessing as mp' in text
assert 'target=_meta_walk_forward_process_worker' in text
assert 'threading.Thread(target=worker,daemon=True,name="GPH-MetaWalkForward")' not in text
assert 'mp.freeze_support()' in text
assert doc.startswith('REVISÃO v0.42.1')

SRC.write_text(text,encoding='utf-8')
DOC.write_text(doc,encoding='utf-8')
print('PATCH v0.42.1 OK')
print('linhas',len(text.splitlines()))
print('cérebro Meta e motores oficiais preservados:',', '.join(critical))
