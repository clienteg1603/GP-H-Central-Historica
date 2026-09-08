from pathlib import Path

path = Path("source/gph_central.py")
text = path.read_text(encoding="utf-8")

if 'APP_VERSION = "0.36.2"' in text:
    raise SystemExit("v0.36.2 ja aplicada")
if 'APP_VERSION = "0.36.1"' not in text:
    raise SystemExit("Base esperada v0.36.1 nao encontrada")

text = text.replace("GP-H Central Histórica v0.36.1", "GP-H Central Histórica v0.36.2", 1)
text = text.replace('APP_VERSION = "0.36.1"', 'APP_VERSION = "0.36.2"', 1)


def replace_between(src, start_marker, end_marker, replacement):
    a = src.find(start_marker)
    if a < 0:
        raise SystemExit(f"Marcador inicial nao encontrado: {start_marker}")
    b = src.find(end_marker, a + len(start_marker))
    if b < 0:
        raise SystemExit(f"Marcador final nao encontrado: {end_marker}")
    return src[:a] + replacement + src[b:]


# 1) Banco: exclusão explícita de bilhete + jogos + itens.
db_method = r'''    def delete_ticket(self, ticket_id):
        """Exclui um bilhete registrado e todos os jogos/itens ligados a ele."""
        ticket_id = int(ticket_id)
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM bilhetes WHERE id=?",
                (ticket_id,),
            ).fetchone()
            if row is None:
                return {
                    "deleted": False,
                    "ticket_id": ticket_id,
                    "games_deleted": 0,
                }

            game_ids = [
                int(r["id"])
                for r in con.execute(
                    "SELECT id FROM jogos_congelados WHERE bilhete_id=? ORDER BY id",
                    (ticket_id,),
                ).fetchall()
            ]

            if game_ids:
                con.executemany(
                    "DELETE FROM jogos_itens WHERE jogo_id=?",
                    [(gid,) for gid in game_ids],
                )
                con.execute(
                    "DELETE FROM jogos_congelados WHERE bilhete_id=?",
                    (ticket_id,),
                )

            con.execute(
                "DELETE FROM bilhetes WHERE id=?",
                (ticket_id,),
            )

        return {
            "deleted": True,
            "ticket_id": ticket_id,
            "games_deleted": len(game_ids),
            "ticket": dict(row),
        }

'''
marker_db = "    def play_round_summaries(self, limit=200):\n"
if "    def delete_ticket(self, ticket_id):\n" not in text:
    idx = text.find(marker_db)
    if idx < 0:
        raise SystemExit("play_round_summaries nao encontrado")
    text = text[:idx] + db_method + text[idx:]


# 2) A seleção de vários horários passa a ser SOMENTE preparação do rascunho.
new_multi = r'''    def play_register_ticket_multi(self):
        """Seleciona rodadas para o rascunho; não registra nada no banco."""
        if not self.play_ticket_draft:
            messagebox.showinfo(
                "Vários horários",
                "Adicione pelo menos uma modalidade ao bilhete antes de escolher os horários.",
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

        existing_targets = getattr(self, "play_ticket_multi_targets", []) or []
        existing_keys = {target_key(target) for target in existing_targets}

        dialog = tk.Toplevel(self)
        dialog.title("Selecionar vários horários")
        dialog.transient(self)
        dialog.grab_set()
        dialog.minsize(510, 390)
        dialog.geometry("560x470")

        body = ttk.Frame(dialog, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="Escolha as rodadas deste bilhete.",
            style="Section.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            body,
            text=(
                "CONTINUAR apenas prepara os horários no bilhete em montagem. "
                "Nada será registrado até você clicar em REGISTRAR BILHETE."
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

        if existing_keys:
            for idx, (_label, target) in enumerate(options):
                if target_key(target) in existing_keys:
                    listbox.selection_set(idx)
        else:
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
        self.play_ticket_multi_targets = [dict(target) for _label, target in selected]
        self.play_refresh_ticket()
        self.status.configure(
            text=(
                f"Bilhete preparado para {len(selected)} rodada(s). "
                "Ainda não foi registrado."
            )
        )
        messagebox.showinfo(
            "Horários preparados",
            (
                f"{len(selected)} rodada(s) foram adicionadas ao bilhete em montagem.\n\n"
                "Nenhum bilhete foi registrado ainda.\n"
                "Revise o bilhete e clique em REGISTRAR BILHETE quando quiser confirmar."
            ),
            parent=self,
        )

'''
text = replace_between(
    text,
    "    def play_register_ticket_multi(self):\n",
    "    def play_register_ticket(self):\n",
    new_multi,
)


# 3) REGISTRAR BILHETE é o único ponto que efetivamente grava, inclusive multi-horário.
new_register = r'''    def play_register_ticket(self):
        if not self.play_ticket_draft:
            messagebox.showinfo(
                "Bilhete",
                "O bilhete está vazio.",
                parent=self,
            )
            return

        base_target = self.play_ticket_draft[0]["generation"].get(
            "intended_target"
        )
        multi_targets = [
            dict(target)
            for target in (getattr(self, "play_ticket_multi_targets", []) or [])
            if target
        ]
        targets = multi_targets or ([dict(base_target)] if base_target else [])
        if not targets:
            messagebox.showerror(
                "Bilhete",
                "Não foi possível identificar a rodada do bilhete.",
                parent=self,
            )
            return

        total_per_ticket = sum(
            len(e["generation"]["rows"])
            * float(e["stake_per_item"])
            for e in self.play_ticket_draft
        )
        grand_total = total_per_ticket * len(targets)

        lines = []
        for entry in self.play_ticket_draft:
            generation = entry["generation"]
            kind = generation["kind"]
            if generation.get("submodalidade"):
                kind += f"/{generation['submodalidade']}"
            lines.append(
                f"• {kind} • {generation['scope']} • "
                f"{len(generation['rows'])} palpites • "
                f"{self._money(len(generation['rows']) * float(entry['stake_per_item']))}"
            )

        if multi_targets:
            target_lines = "\n".join(
                f"• {self._format_target(target)}"
                for target in targets
            )
            confirm_text = (
                f"MESMO BILHETE EM {len(targets)} RODADAS:\n\n"
                f"{target_lines}\n\n"
                + "\n".join(lines)
                + (
                    f"\n\nVALOR POR RODADA: {self._money(total_per_ticket)}\n"
                    f"TOTAL GERAL: {self._money(grand_total)}\n\n"
                    "Registrar agora todos esses bilhetes como jogadas REAIS?"
                )
            )
        else:
            confirm_text = (
                f"{self._format_target(targets[0])}\n\n"
                + "\n".join(lines)
                + (
                    f"\n\nTOTAL DO BILHETE: {self._money(total_per_ticket)}\n\n"
                    "Registrar todas como jogadas REAIS?"
                )
            )

        if not messagebox.askyesno(
            "Registrar bilhete",
            confirm_text,
            parent=self,
        ):
            return

        base_draw = self.db.latest_operational_draw()
        registered = []
        game_ids = []
        try:
            for target in targets:
                entries = copy.deepcopy(self.play_ticket_draft)
                for entry in entries:
                    entry["generation"]["intended_target"] = dict(target)
                    if multi_targets:
                        entry["origem_jogada"] = "Bilhete multi-horário"
                report = self.db.register_ticket(
                    entries,
                    base_draw=base_draw,
                )
                registered.append(int(report["ticket_id"]))
                game_ids.extend(report["game_ids"])
        except Exception as exc:
            # Multi-horário deve ser tudo ou nada. Se alguma rodada falhar,
            # remove os bilhetes já criados nesta tentativa.
            for ticket_id in registered:
                try:
                    self.db.delete_ticket(ticket_id)
                except Exception:
                    pass
            self._update_results_nav_badge()
            messagebox.showerror(
                "Bilhete",
                (
                    "Não foi possível concluir o registro. "
                    "Os bilhetes desta tentativa foram desfeitos.\n\n"
                    f"{exc}"
                ),
                parent=self,
            )
            return

        self.play_ticket_draft.clear()
        self.play_ticket_multi_targets = []
        self._update_results_nav_badge()

        if multi_targets:
            messagebox.showinfo(
                "Bilhetes registrados",
                (
                    f"{len(registered)} bilhetes separados foram registrados.\n"
                    f"{len(game_ids)} modalidade(s) no total.\n"
                    f"Total apostado: {self._money(grand_total)}."
                ),
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Bilhete registrado",
                (
                    f"Bilhete #{registered[0]} registrado.\n"
                    f"{len(game_ids)} modalidade(s).\n"
                    f"Total apostado: {self._money(total_per_ticket)}."
                ),
                parent=self,
            )

        self.play_show_games(
            select_ticket_id=registered[0]
        )

'''
text = replace_between(
    text,
    "    def play_register_ticket(self):\n",
    "    def play_controls_changed(self, _event=None):\n",
    new_register,
)


# 4) O rascunho mostra claramente a seleção multi-horário e o total geral.
old_target_summary = '''        if hasattr(self, "play_ticket_target_label"):
            if self.play_ticket_draft:
                target = self.play_ticket_draft[0]["generation"].get("intended_target")
                self.play_ticket_target_label.configure(text=self._format_target(target))
            else:
                self.play_ticket_target_label.configure(text="Nenhuma modalidade adicionada")

        self.play_ticket_summary_label.configure(
            text=(
                f"{len(self.play_ticket_draft)} modalidade(s)  •  TOTAL {self._money(total)}"
            )
        )
'''
new_target_summary = '''        multi_targets = getattr(self, "play_ticket_multi_targets", []) or []
        if hasattr(self, "play_ticket_target_label"):
            if self.play_ticket_draft:
                if multi_targets:
                    formatted = [self._format_target(target) for target in multi_targets]
                    self.play_ticket_target_label.configure(
                        text=(
                            f"VÁRIOS HORÁRIOS • {len(formatted)} rodadas selecionadas\n"
                            + "  •  ".join(formatted)
                        )
                    )
                else:
                    target = self.play_ticket_draft[0]["generation"].get("intended_target")
                    self.play_ticket_target_label.configure(text=self._format_target(target))
            else:
                self.play_ticket_target_label.configure(text="Nenhuma modalidade adicionada")

        if multi_targets and self.play_ticket_draft:
            self.play_ticket_summary_label.configure(
                text=(
                    f"{len(self.play_ticket_draft)} modalidade(s)  •  "
                    f"{self._money(total)} por rodada  •  "
                    f"{len(multi_targets)} rodadas  •  "
                    f"TOTAL {self._money(total * len(multi_targets))}"
                )
            )
        else:
            self.play_ticket_summary_label.configure(
                text=(
                    f"{len(self.play_ticket_draft)} modalidade(s)  •  TOTAL {self._money(total)}"
                )
            )
'''
if old_target_summary not in text:
    raise SystemExit("Resumo do bilhete nao encontrado")
text = text.replace(old_target_summary, new_target_summary, 1)

# Limpar/remove também limpa seleção multi quando o rascunho deixa de existir.
old_remove = '''        if 0 <= idx < len(self.play_ticket_draft):
            self.play_ticket_draft.pop(idx)
            self.play_refresh_ticket()
'''
new_remove = '''        if 0 <= idx < len(self.play_ticket_draft):
            self.play_ticket_draft.pop(idx)
            if not self.play_ticket_draft:
                self.play_ticket_multi_targets = []
            self.play_refresh_ticket()
'''
if old_remove not in text:
    raise SystemExit("play_remove_ticket_item nao encontrado")
text = text.replace(old_remove, new_remove, 1)

old_clear = '''            self.play_ticket_draft.clear()
            self.play_refresh_ticket()
'''
new_clear = '''            self.play_ticket_draft.clear()
            self.play_ticket_multi_targets = []
            self.play_refresh_ticket()
'''
# Só a primeira ocorrência após def play_clear_ticket.
clear_pos = text.find("    def play_clear_ticket(self):\n")
if clear_pos < 0:
    raise SystemExit("play_clear_ticket nao encontrado")
clear_match = text.find(old_clear, clear_pos)
if clear_match < 0:
    raise SystemExit("corpo de play_clear_ticket nao encontrado")
text = text[:clear_match] + new_clear + text[clear_match + len(old_clear):]


# 5) Botão e ação para excluir bilhete registrado.
old_copy_button = '''        ttk.Button(
            head_actions,
            text="Copiar bilhete",
            command=self.play_copy_selected_ticket,
        ).pack(side="left")
'''
new_copy_button = '''        ttk.Button(
            head_actions,
            text="Copiar bilhete",
            command=self.play_copy_selected_ticket,
        ).pack(side="left")
        ttk.Button(
            head_actions,
            text="Excluir bilhete",
            command=self.play_delete_selected_ticket,
        ).pack(side="left", padx=(5, 0))
'''
if old_copy_button not in text:
    raise SystemExit("Botao Copiar bilhete nao encontrado")
text = text.replace(old_copy_button, new_copy_button, 1)

ui_delete_method = r'''    def play_delete_selected_ticket(self):
        ticket_id = getattr(self, "play_selected_ticket_id", None)
        if not ticket_id:
            messagebox.showinfo(
                "Excluir bilhete",
                "Selecione um bilhete na lista antes de excluir.",
                parent=self,
            )
            return

        games = self.db.games_for_ticket(ticket_id)
        total = sum(float(game.get("valor_total") or 0) for game in games)
        if not messagebox.askyesno(
            "Excluir bilhete",
            (
                f"Excluir permanentemente o bilhete #{ticket_id}?\n\n"
                f"Modalidades: {len(games)}\n"
                f"Valor registrado: {self._money(total)}\n\n"
                "As jogadas e os palpites ligados a este bilhete também serão removidos.\n"
                "Esta ação não pode ser desfeita."
            ),
            parent=self,
        ):
            return

        try:
            report = self.db.delete_ticket(ticket_id)
        except Exception as exc:
            messagebox.showerror(
                "Excluir bilhete",
                str(exc),
                parent=self,
            )
            return

        if not report.get("deleted"):
            messagebox.showinfo(
                "Excluir bilhete",
                "Esse bilhete já não existe na base.",
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Bilhete excluído",
                (
                    f"Bilhete #{ticket_id} excluído.\n"
                    f"{report.get('games_deleted', 0)} modalidade(s) removida(s)."
                ),
                parent=self,
            )

        self.play_selected_ticket_id = None
        self.play_selected_game_id = None
        self._update_results_nav_badge()
        self.play_refresh_games()
        self.status.configure(text=f"Bilhete #{ticket_id} excluído.")

'''
marker_ui_delete = "    def play_ticket_history_selected(self, _event=None):\n"
if "    def play_delete_selected_ticket(self):\n" not in text:
    idx = text.find(marker_ui_delete)
    if idx < 0:
        raise SystemExit("play_ticket_history_selected nao encontrado")
    text = text[:idx] + ui_delete_method + text[idx:]


path.write_text(text, encoding="utf-8")

docs = Path("source/DOCUMENTACAO_GP-H.txt")
if docs.is_file():
    doc = docs.read_text(encoding="utf-8")
    note = (
        "\n\nv0.36.2 — Bilhete multi-horário seguro e exclusão de bilhetes\n"
        "- 'CONTINUAR' em Vários Horários apenas prepara a seleção; nada é gravado antes de REGISTRAR BILHETE.\n"
        "- O rascunho mostra as rodadas selecionadas, valor por rodada e total geral.\n"
        "- REGISTRAR BILHETE é o único comando que efetiva os bilhetes multi-horário.\n"
        "- Adicionado Excluir bilhete no histórico, com confirmação e remoção de jogos/itens ligados.\n"
    )
    if "v0.36.2 — Bilhete multi-horário seguro" not in doc:
        docs.write_text(doc.rstrip() + note, encoding="utf-8")
