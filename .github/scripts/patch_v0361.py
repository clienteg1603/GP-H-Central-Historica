from pathlib import Path

path = Path("source/gph_central.py")
text = path.read_text(encoding="utf-8")

if 'APP_VERSION = "0.36.1"' in text:
    raise SystemExit("v0.36.1 ja aplicada")

text = text.replace("GP-H Central Histórica v0.36.0", "GP-H Central Histórica v0.36.1", 1)
text = text.replace('APP_VERSION = "0.36.0"', 'APP_VERSION = "0.36.1"', 1)

old_ui = '''        ttk.Button(
            ticket_actions,
            text="REGISTRAR BILHETE",
            style="Accent.TButton",
            command=self.play_register_ticket,
        ).pack(side="right", padx=(0, 5))
'''
new_ui = '''        ttk.Button(
            ticket_actions,
            text="REGISTRAR BILHETE",
            style="Accent.TButton",
            command=self.play_register_ticket,
        ).pack(side="right", padx=(0, 5))
        ttk.Button(
            ticket_actions,
            text="VÁRIOS HORÁRIOS...",
            command=self.play_register_ticket_multi,
        ).pack(side="right", padx=(0, 5))
'''
if old_ui not in text:
    raise SystemExit("Bloco do botao REGISTRAR BILHETE nao encontrado")
text = text.replace(old_ui, new_ui, 1)

marker = "    def play_register_ticket(self):\n"
if marker not in text:
    raise SystemExit("Metodo play_register_ticket nao encontrado")

method = '''    def play_register_ticket_multi(self):
        """Registra o mesmo bilhete em várias rodadas, sempre como bilhetes separados."""
        if not self.play_ticket_draft:
            messagebox.showinfo(
                "Vários horários",
                "Adicione pelo menos uma modalidade ao bilhete antes de repetir em vários horários.",
                parent=self,
            )
            return

        options = [
            (label, dict(target))
            for label, target in getattr(self, "play_target_map", {}).items()
        ]
        if not options:
            messagebox.showinfo(
                "Vários horários",
                "Não há rodadas futuras disponíveis para selecionar.",
                parent=self,
            )
            return

        def target_key(target):
            target = target or {}
            return (
                target.get("data"),
                target.get("sorteio"),
                target.get("hora"),
            )

        draft_target = self.play_ticket_draft[0]["generation"].get("intended_target")
        draft_key = target_key(draft_target)
        base_idx = 0
        for idx, (_label, target) in enumerate(options):
            if target_key(target) == draft_key:
                base_idx = idx
                break

        dialog = tk.Toplevel(self)
        dialog.title("Registrar em vários horários")
        dialog.transient(self)
        dialog.grab_set()
        dialog.minsize(510, 390)
        dialog.geometry("560x470")

        body = ttk.Frame(dialog, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="Escolha as rodadas que receberão este mesmo bilhete.",
            style="Section.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            body,
            text=(
                "Cada horário será registrado como um bilhete separado. "
                "Os 5 horários a partir da rodada original já vêm marcados."
            ),
            wraplength=500,
            justify="left",
        ).pack(anchor="w", pady=(4, 10))

        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        listbox = tk.Listbox(
            list_frame,
            selectmode="multiple",
            exportselection=False,
            activestyle="none",
            height=12,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.configure(command=listbox.yview)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for label, _target in options:
            listbox.insert("end", label)

        end_default = min(len(options), base_idx + 5)
        for idx in range(base_idx, end_default):
            listbox.selection_set(idx)
        if base_idx < len(options):
            listbox.see(base_idx)

        def on_wheel(event):
            delta = int(-1 * (event.delta / 120)) if event.delta else 0
            if delta:
                listbox.yview_scroll(delta, "units")
            return "break"

        listbox.bind("<MouseWheel>", on_wheel)

        chosen = {"indices": None}

        def confirm():
            indices = list(listbox.curselection())
            if not indices:
                messagebox.showinfo(
                    "Vários horários",
                    "Selecione pelo menos uma rodada.",
                    parent=dialog,
                )
                return
            chosen["indices"] = indices
            dialog.destroy()

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Cancelar", command=dialog.destroy).pack(side="right")
        ttk.Button(
            actions,
            text="CONTINUAR",
            style="Accent.TButton",
            command=confirm,
        ).pack(side="right", padx=(0, 6))

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.wait_window()

        indices = chosen["indices"]
        if not indices:
            return

        selected = [options[idx] for idx in indices]
        total_per_ticket = sum(
            len(entry["generation"]["rows"]) * float(entry["stake_per_item"])
            for entry in self.play_ticket_draft
        )
        grand_total = total_per_ticket * len(selected)
        labels_text = "\n".join(f"• {label}" for label, _target in selected)

        if not messagebox.askyesno(
            "Confirmar vários horários",
            (
                f"Serão registrados {len(selected)} bilhetes separados com o mesmo jogo:\n\n"
                f"{labels_text}\n\n"
                f"Valor por bilhete: {self._money(total_per_ticket)}\n"
                f"Total dos {len(selected)} bilhetes: {self._money(grand_total)}\n\n"
                "Confirmar?"
            ),
            parent=self,
        ):
            return

        base_draw = self.db.latest_operational_draw()
        registered = []
        try:
            for _label, target in selected:
                entries = copy.deepcopy(self.play_ticket_draft)
                for entry in entries:
                    entry["generation"]["intended_target"] = dict(target)
                    entry["origem_jogada"] = "Repetição manual multi-horário"
                report = self.db.register_ticket(entries, base_draw=base_draw)
                registered.append(report["ticket_id"])
        except Exception as exc:
            self._update_results_nav_badge()
            messagebox.showerror(
                "Vários horários",
                (
                    f"Foram registrados {len(registered)} bilhete(s) antes de ocorrer um erro.\n\n"
                    f"{exc}"
                ),
                parent=self,
            )
            return

        self.play_ticket_draft.clear()
        self.play_refresh_ticket()
        self._update_results_nav_badge()
        self.status.configure(
            text=f"{len(registered)} bilhetes registrados em horários diferentes."
        )
        messagebox.showinfo(
            "Bilhetes registrados",
            (
                f"Pronto: {len(registered)} bilhetes separados foram registrados.\n\n"
                f"Total: {self._money(grand_total)}"
            ),
            parent=self,
        )

'''
text = text.replace(marker, method + marker, 1)

old_error = '''                        "A rodada mudou enquanto o bilhete estava sendo montado. "
                        "Registre ou limpe o bilhete anterior antes de continuar."
'''
new_error = '''                        "O bilhete em montagem pertence a outra rodada. "
                        "Para repetir o mesmo jogo em vários horários, use 'VÁRIOS HORÁRIOS...'. "
                        "Caso contrário, registre ou limpe o bilhete anterior."
'''
if old_error in text:
    text = text.replace(old_error, new_error, 1)

path.write_text(text, encoding="utf-8")

docs = Path("source/DOCUMENTACAO_GP-H.txt")
if docs.is_file():
    doc = docs.read_text(encoding="utf-8")
    note = (
        "\n\nv0.36.1 — Bilhete multi-horário\n"
        "- Adicionado 'VÁRIOS HORÁRIOS...' para registrar o mesmo bilhete em várias rodadas, sempre como bilhetes separados.\n"
        "- Os cinco horários a partir da rodada original vêm pré-selecionados.\n"
        "- A nova janela possui rolagem pela roda do mouse.\n"
    )
    if "v0.36.1 — Bilhete multi-horário" not in doc:
        docs.write_text(doc.rstrip() + note, encoding="utf-8")
