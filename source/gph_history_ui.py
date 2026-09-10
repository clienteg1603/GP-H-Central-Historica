"""Interface do laboratório histórico; cálculo em processo separado."""
from __future__ import annotations

import csv
import json
import multiprocessing as mp
import queue
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from gph_history_lab import SELECTORS, SCOPES, history_worker


def percent(value):
    return "—" if value is None else f"{value*100:.1f}%".replace(".", ",")


def band(values):
    return " a ".join(percent(v) for v in values)


def table(parent, columns, height=7):
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True, pady=(5, 4))
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=height)
    for name, title, width in columns:
        tree.heading(name, text=title)
        tree.column(name, width=width, minwidth=45, anchor="w")
    vertical = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    return tree


class HistoryLabUI:
    def __init__(self, app, calendar_factory):
        self.app = app
        self.calendar_factory = calendar_factory
        self.running = False
        self.result = None
        self.frame = None
        self.progress_state = (0, 1, "Escolha o período avaliado e inicie o teste.")
        self.options = None

    def alive(self):
        try:
            return self.frame is not None and bool(self.frame.winfo_exists())
        except tk.TclError:
            return False

    def bounds(self):
        con = sqlite3.connect(Path(self.app.db.path).resolve().as_uri()+"?mode=ro", uri=True)
        try:
            days = []
            for row in con.execute("SELECT DISTINCT data FROM resultados"):
                try:
                    days.append(date.fromisoformat(row[0]).isoformat())
                except (ValueError, TypeError):
                    pass
            hours = [r[0] for r in con.execute("SELECT DISTINCT hora FROM resultados ORDER BY hora")]
            return min(days) if days else None, max(days) if days else None, hours
        finally:
            con.close()

    def build(self, parent):
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="both", expand=True)
        intro = ttk.Frame(self.frame, style="Card.TFrame", padding=11)
        intro.pack(fill="x", pady=(0, 8))
        ttk.Label(intro, text="TESTAR COM O HISTÓRICO EXISTENTE", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(intro, text=(
            "Reconstitui cada rodada com os dados que já existiam antes dela. Todo o histórico anterior "
            "ao período escolhido serve de treino. Centenas: 20 por método. Ternos: cinco jogos dos mesmos cinco bichos."
        ), style="CardMuted.TLabel", wraplength=920).pack(anchor="w", pady=(4, 0))
        low, high, hours = self.bounds()
        self.low, self.high = low, high
        last = date.fromisoformat(high) if high else date.today()
        first = max(date.fromisoformat(low), last-timedelta(days=29)) if low else last
        options = self.options or {"start": first.isoformat(), "end": last.isoformat(),
                                   "selector": next(iter(SELECTORS)), "scope": SCOPES[0], "hour": ""}
        self.start = tk.StringVar(value=date.fromisoformat(options["start"]).strftime("%d/%m/%Y"))
        self.end = tk.StringVar(value=date.fromisoformat(options["end"]).strftime("%d/%m/%Y"))
        self.selector = tk.StringVar(value=options["selector"])
        self.scope = tk.StringVar(value=options["scope"])
        self.hour = tk.StringVar(value=options.get("hour") or "Todos")
        controls = ttk.Frame(self.frame, style="Card.TFrame", padding=10)
        controls.pack(fill="x", pady=(0, 8))
        for col, label in enumerate(("INÍCIO DA AVALIAÇÃO", "FIM", "SELETOR DOS 5 BICHOS")):
            ttk.Label(controls, text=label, style="CardMuted.TLabel").grid(row=0, column=col, sticky="w", padx=(0, 12))
        self.calendar_factory(controls, self.start, width=11).grid(row=1, column=0, sticky="w", padx=(0, 12))
        self.calendar_factory(controls, self.end, width=11).grid(row=1, column=1, sticky="w", padx=(0, 12))
        ttk.Combobox(controls, textvariable=self.selector, values=list(SELECTORS), state="readonly", width=25).grid(row=1, column=2, sticky="w")
        extra = ttk.Frame(controls, style="Card.TFrame")
        extra.grid(row=2, column=0, columnspan=3, sticky="w", pady=(9, 0))
        ttk.Label(extra, text="Centenas", style="CardMuted.TLabel").pack(side="left")
        ttk.Combobox(extra, textvariable=self.scope, values=SCOPES, state="readonly", width=8).pack(side="left", padx=(6, 14))
        ttk.Label(extra, text="Horário", style="CardMuted.TLabel").pack(side="left")
        ttk.Combobox(extra, textvariable=self.hour, values=["Todos", *hours], state="readonly", width=8).pack(side="left", padx=(6, 14))
        ttk.Button(extra, text="Toda a base", command=self.whole_period).pack(side="left")
        actions = ttk.Frame(self.frame)
        actions.pack(fill="x", pady=(0, 6))
        self.run_btn = ttk.Button(actions, text="TESTAR NO HISTÓRICO", style="Accent.TButton", command=self.start_run)
        self.run_btn.pack(side="left")
        self.cancel_btn = ttk.Button(actions, text="Cancelar", command=self.cancel_run)
        self.cancel_btn.pack(side="left", padx=6)
        self.json_btn = ttk.Button(actions, text="Exportar relatório JSON", command=self.export_json)
        self.json_btn.pack(side="left", padx=(0, 6))
        self.csv_btn = ttk.Button(actions, text="Exportar rodadas CSV", command=self.export_csv)
        self.csv_btn.pack(side="left")
        self.progress_bar = ttk.Progressbar(self.frame, maximum=100)
        self.progress_bar.pack(fill="x")
        self.status = ttk.Label(self.frame, text="", style="Sub.TLabel", wraplength=920)
        self.status.pack(anchor="w", pady=(3, 8))
        self.summary = table(self.frame, [("method", "Método", 260), ("n", "Rodadas", 65),
            ("hits", "Acertos¹", 65), ("rate", "Taxa", 65), ("range", "Faixa 95%²", 125),
            ("status", "Diagnóstico", 205)], height=10)
        ttk.Label(self.frame, text=(
            "¹ Rodadas com pelo menos uma Centena ou um Terno 3/3. Controles aleatórios mostram a média de 200 repetições. "
            "² Wilson descritivo; no acaso, faixa das simulações. Ternos sempre usam 1º–5º, mesmo ao avaliar Centenas no 1º."
        ), style="Sub.TLabel", wraplength=920).pack(anchor="w", pady=(0, 8))
        notebook = ttk.Notebook(self.frame)
        notebook.pack(fill="both", expand=True)
        tabs = []
        for title in ("Comparações", "Por horário", "Auditoria dos números", "Base e protocolo"):
            frame = ttk.Frame(notebook, padding=8)
            notebook.add(frame, text=title)
            tabs.append(frame)
        self.evidence = table(tabs[0], [("candidate", "Candidato", 250), ("vs", "Comparado com", 235),
            ("delta", "Diferença", 85), ("interval", "Faixa por dia", 120),
            ("p", "p corrigido", 90), ("half", "1ª / 2ª metade", 140)])
        ttk.Label(tabs[0], text="Diferenças positivas favorecem o candidato. A faixa usa reamostragem por dia; p é corrigido por Holm. Menos de 10 dias: sem inferência.",
                  style="Sub.TLabel", wraplength=920).pack(anchor="w")
        self.hourly = table(tabs[1], [("source", "Fonte", 190), ("draw", "Extração", 110),
            ("method", "Método", 255), ("n", "Rodadas", 65), ("hits", "Acertos", 65), ("rate", "Taxa", 70)])
        self.structural = table(tabs[2], [("draw", "Fonte / extração", 250), ("prize", "Prêmio", 60),
            ("test", "Teste", 250), ("n", "Amostra", 70), ("q", "q corrigido", 85), ("status", "Diagnóstico", 185)])
        ttk.Label(tabs[2], text="Dígitos por posição e prêmio, repetições e dependência entre extrações. q usa BH; testes com células esperadas pequenas ficam inconclusivos. Desvio não implica previsão.",
                  style="Sub.TLabel", wraplength=920).pack(anchor="w")
        self.details = tk.Text(tabs[3], height=12, wrap="word", bg=self.app.colors["card"],
                               fg=self.app.colors["text"], relief="flat", font=("Segoe UI", 10))
        self.details.pack(fill="both", expand=True)
        if self.result:
            self.render()
        else:
            self.write_details("Histórico já explorado: os resultados são experimentais.\n"
                "O laboratório não altera Meta, apostas, financeiro ou snapshots.\n"
                "O mínimo inicial é de 60 extrações completas para treino.\n"
                "O teste usa os resultados já salvos neste computador.")
        self.refresh_state()

    def write_details(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def whole_period(self):
        if self.low and self.high:
            self.start.set(date.fromisoformat(self.low).strftime("%d/%m/%Y"))
            self.end.set(date.fromisoformat(self.high).strftime("%d/%m/%Y"))

    def refresh_state(self):
        if not self.alive():
            return
        self.run_btn.configure(state="disabled" if self.running else "normal")
        self.cancel_btn.configure(state="normal" if self.running else "disabled")
        for btn in (self.json_btn, self.csv_btn):
            btn.configure(state="normal" if self.result and not self.running else "disabled")
        done, total, label = self.progress_state
        self.progress_bar.configure(value=100*done/max(1, total))
        self.status.configure(text=label)

    def start_run(self):
        if self.running:
            return
        try:
            options = {"start": datetime.strptime(self.start.get(), "%d/%m/%Y").date().isoformat(),
                       "end": datetime.strptime(self.end.get(), "%d/%m/%Y").date().isoformat(),
                       "selector": self.selector.get(), "scope": self.scope.get(),
                       "hour": "" if self.hour.get() == "Todos" else self.hour.get()}
            if options["start"] > options["end"]:
                raise ValueError("A data inicial precisa ser anterior ou igual à final.")
        except ValueError as exc:
            messagebox.showerror("Período inválido", str(exc), parent=self.app)
            return
        self.options = options
        ctx = mp.get_context("spawn")
        self.output, self.cancel_event = ctx.Queue(), ctx.Event()
        self.process = ctx.Process(target=history_worker, args=(type(self.app.db), str(self.app.db.path),
                                   options, self.output, self.cancel_event), daemon=True)
        self.running = True
        self.empty_polls = 0
        self.progress_state = (0, 1, "Preparando cópia temporária do histórico…")
        try:
            self.process.start()
        except Exception as exc:
            self.running = False
            self.output.close()
            self.progress_state = (0, 1, f"Não foi possível iniciar: {exc}")
            self.refresh_state()
            return
        self.result = None
        for tree in (self.summary, self.evidence, self.hourly, self.structural):
            tree.delete(*tree.get_children())
        self.write_details("Teste em execução. Os dados e os palpites oficiais permanecem preservados.")
        self.refresh_state()
        self.app.after(120, self.poll)

    def cancel_run(self):
        if self.running:
            self.cancel_event.set()
            self.progress_state = (*self.progress_state[:2], "Cancelando após a rodada atual…")
            self.refresh_state()

    def poll(self):
        terminal = False
        while True:
            try:
                item = self.output.get_nowait()
            except queue.Empty:
                break
            if item[0] == "progress":
                self.progress_state = item[1:]
            elif item[0] == "done":
                self.result = item[1]
                self.running = False
                terminal = True
                result = self.result
                count = len(result["records"])
                state = "Interrompido · resultado parcial" if result["cancelled"] else "Concluído"
                self.progress_state = (1, 1, f"{state} · {count} rodadas comparadas · {len(result['skipped'])} não avaliadas.")
                if self.alive():
                    self.render()
            elif item[0] == "error":
                self.running = False
                terminal = True
                self.progress_state = (0, 1, f"Teste não concluído: {item[1]}")
        if not terminal and not self.process.is_alive():
            self.empty_polls += 1
            if self.empty_polls >= 5:
                terminal = True
                self.running = False
                self.progress_state = (0, 1, "O processo terminou sem entregar o relatório. Tente um período menor.")
        self.refresh_state()
        if terminal:
            self.process.join(timeout=.1)
            self.output.close()
            self.output.cancel_join_thread()
        else:
            self.app.after(120, self.poll)

    def render(self):
        r = self.result
        for tree in (self.summary, self.evidence, self.hourly, self.structural):
            tree.delete(*tree.get_children())
        for s in r["summary"]:
            hits = f"{s['hits']:.1f}" if s["method"].startswith("Acaso") or "aleatória" in s["method"] else str(int(s["hits"]))
            self.summary.insert("", "end", values=(s["method"], s["n"], hits, percent(s["rate"]), band(s["interval"]), s["status"]))
        for e in r["evidence"]:
            self.evidence.insert("", "end", values=(e["candidate"], e["comparator"], percent(e["delta"]), band(e["interval"]),
                "—" if e["p_adjusted"] is None else f"{e['p_adjusted']:.3f}", " / ".join(percent(v) for v in e["halves"])))
        for h in r["hourly"]:
            self.hourly.insert("", "end", values=(h["source"], f"{h['sorteio']} {h['hora']}", h["method"], h["n"], h["hits"], percent(h["rate"])))
        ordered = sorted(r["structural"], key=lambda s: (s["q"] is None, s["q"] if s["q"] is not None else 1, s["test"]))
        for s in ordered:
            self.structural.insert("", "end", values=(f"{s['source']} · {s['sorteio']} {s['hora']}", s["prize"], s["test"], s["n"],
                "—" if s["q"] is None else f"{s['q']:.4f}", s["status"]))
        integrity = r["integrity"]
        text = [r["protocol"], f"Período: {r['options']['start']} a {r['options']['end']} · Centenas {r['options']['scope']}",
                f"{integrity['input_rows']} prêmios lidos · {integrity['valid_draws']} extrações válidas · {len(integrity['excluded'])} excluídas.",
                f"{len(r['records'])} rodadas comparadas · {len(r['skipped'])} não avaliadas.",
                "\nLIMITES E LEITURA", *r["limitations"], "\nQUASE-ACERTOS (separados das vitórias)"]
        text.extend(f"{s['method']}: {s['near2']} rodadas com melhor Terno 2/3." for s in r["summary"] if s["method"] in
                    ("5 Ternos · montagem atual", "5 Ternos · cobertura conjunta"))
        text.extend(["\nPARÂMETROS FIXOS", json.dumps(r["parameters"], ensure_ascii=False), "\nIdentificação da base: " + r["data_sha256"]])
        if not r["records"]:
            text.insert(1, "Não há rodadas elegíveis neste período. Verifique o treino mínimo e os alvos ausentes.")
        if r["skipped"]:
            text.append("\nPrimeiras rodadas não avaliadas:")
            text.extend(f"{s['target']['data']} {s['target']['sorteio']} {s['target']['hora']}: {s['reason']}" for s in r["skipped"][:15])
        self.write_details("\n".join(text))

    def export_json(self):
        if not self.result or self.running:
            return
        path = filedialog.asksaveasfilename(parent=self.app, defaultextension=".json", filetypes=[("Relatório JSON", "*.json")], initialfile="GP-H_pesquisa_historica.json")
        if path:
            try:
                Path(path).write_text(json.dumps(self.result, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("Falha ao exportar", str(exc), parent=self.app)

    def export_csv(self):
        if not self.result or self.running:
            return
        path = filedialog.asksaveasfilename(parent=self.app, defaultextension=".csv", filetypes=[("Rodadas CSV", "*.csv")], initialfile="GP-H_pesquisa_rodadas.csv")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["Data", "Sorteio", "Hora", "Fonte", "Escopo", "Método", "Treino", "Bichos", "Palpites simulados", "Acerto por rodada", "2/3", "Resultado (milhares)"])
                for row in self.result["records"]:
                    for method, scores in row["scores"].items():
                        values = [row["target"][k] for k in ("data", "sorteio", "hora", "source")]
                        values += ["1º–5º" if method.startswith("5 Ternos") else self.result["options"]["scope"], method,
                            row["train_draws"], json.dumps(row["groups"]), json.dumps(row["predictions"].get(method, [])),
                            scores["hit"], scores.get("near2", ""), json.dumps(row["result"])]
                        writer.writerow(["'"+v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v for v in values])
        except OSError as exc:
            messagebox.showerror("Falha ao exportar", str(exc), parent=self.app)
