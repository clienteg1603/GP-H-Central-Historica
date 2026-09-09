from pathlib import Path

p = Path('source/gph_central.py')
s = p.read_text(encoding='utf-8')


def one(old, new, label):
    global s
    n = s.count(old)
    if n != 1:
        raise SystemExit(f'{label}: esperado 1 trecho, encontrado {n}')
    s = s.replace(old, new, 1)


one('APP_VERSION = "0.46.9"', 'APP_VERSION = "0.47.0"', 'app version')

# ---------------------------------------------------------------------------
# Banco: exclusão de UMA modalidade de um bilhete, preservando as demais.
# ---------------------------------------------------------------------------
marker = '\n    def delete_ticket(self, ticket_id):\n'
if s.count(marker) != 1:
    raise SystemExit('marcador delete_ticket não encontrado de forma única')

method = r'''

    def delete_ticket_game(self, ticket_id, game_id):
        """Exclui somente uma modalidade de um bilhete e recalcula o restante."""
        ticket_id = int(ticket_id)
        game_id = int(game_id)

        with self.connect() as con:
            ticket = con.execute(
                "SELECT * FROM bilhetes WHERE id=?",
                (ticket_id,),
            ).fetchone()
            if ticket is None:
                return {
                    "deleted": False,
                    "reason": "ticket_not_found",
                    "ticket_id": ticket_id,
                    "game_id": game_id,
                }

            game = con.execute(
                "SELECT * FROM jogos_congelados WHERE id=? AND bilhete_id=?",
                (game_id, ticket_id),
            ).fetchone()
            if game is None:
                return {
                    "deleted": False,
                    "reason": "game_not_found",
                    "ticket_id": ticket_id,
                    "game_id": game_id,
                }

            items_deleted = int(con.execute(
                "SELECT COUNT(*) FROM jogos_itens WHERE jogo_id=?",
                (game_id,),
            ).fetchone()[0])
            con.execute(
                "DELETE FROM jogos_itens WHERE jogo_id=?",
                (game_id,),
            )
            con.execute(
                "DELETE FROM jogos_congelados WHERE id=? AND bilhete_id=?",
                (game_id, ticket_id),
            )

        # refresh_ticket_totals usa uma nova conexão; por isso roda fora da
        # transação acima. Se era a última modalidade, ele remove o bilhete.
        ticket_after = self.refresh_ticket_totals(ticket_id)
        remaining_games = (
            len(self.games_for_ticket(ticket_id))
            if ticket_after is not None
            else 0
        )

        return {
            "deleted": True,
            "ticket_id": ticket_id,
            "game_id": game_id,
            "game": dict(game),
            "items_deleted": items_deleted,
            "remaining_games": remaining_games,
            "ticket_deleted": ticket_after is None,
            "ticket": ticket_after,
        }
'''
s = s.replace(marker, method + marker, 1)

# ---------------------------------------------------------------------------
# UI: auditoria continua automática, mas saem os três botões redundantes.
# ---------------------------------------------------------------------------
one(
'''        ttk.Button(\n            footer, text="Auditar este jogo", command=self.audit_this\n        ).pack(side="left")\n\n''',
'',
'botão Auditar este jogo',
)

one(
'''        ttk.Button(\n            buttons,\n            text="Auditar agora",\n            command=lambda gid=game_id: self.play_audit_game(gid),\n        ).pack(side="left", padx=(5,0))\n\n''',
'''        if game.get("bilhete_id"):\n            ttk.Button(\n                buttons,\n                text="Excluir esta modalidade",\n                command=lambda tid=int(game["bilhete_id"]), gid=int(game_id): (\n                    self.play_delete_game_from_ticket(tid, gid)\n                ),\n            ).pack(side="left", padx=(5,0))\n\n''',
'botão Auditar agora -> Excluir modalidade',
)

one(
'''        ttk.Button(\n            actions,\n            text="Auditar jogos",\n            command=self.results_audit_games,\n        ).pack(side="left", padx=(5, 0))\n\n''',
'',
'botão Auditar jogos',
)

one(
'"Atualize os resultados, acompanhe jogos congelados e audite o desempenho prospectivo.",',
'"Atualize os resultados e acompanhe os jogos; a auditoria é feita automaticamente após cada resultado.",',
'descrição Resultados',
)

# ---------------------------------------------------------------------------
# UI: ação parcial de exclusão no próprio detalhe da modalidade.
# ---------------------------------------------------------------------------
marker = '\n    def play_audit_game(self, game_id):\n'
if s.count(marker) != 1:
    raise SystemExit('marcador play_audit_game não encontrado de forma única')

ui_method = r'''

    def play_delete_game_from_ticket(self, ticket_id, game_id):
        ticket_id = int(ticket_id)
        game_id = int(game_id)

        try:
            analysis = self.db.play_game_analysis(game_id)
            game = analysis["game"]
        except Exception as exc:
            messagebox.showerror(
                "Excluir modalidade",
                str(exc),
                parent=self,
            )
            return

        if int(game.get("bilhete_id") or 0) != ticket_id:
            messagebox.showerror(
                "Excluir modalidade",
                "A modalidade selecionada não pertence a este bilhete.",
                parent=self,
            )
            return

        modality = str(game.get("tipo") or "Jogo")
        if game.get("submodalidade"):
            modality += f" / {game['submodalidade']}"
        scope = str(game.get("escopo") or "")
        if scope:
            modality += f" • {scope}"

        games = self.db.games_for_ticket(ticket_id)
        remaining_after = max(0, len(games) - 1)
        total = float(game.get("valor_total") or 0)
        last_note = (
            "\n\nEsta é a última modalidade; o bilhete também será removido."
            if remaining_after == 0
            else f"\n\nAs outras {remaining_after} modalidade(s) do bilhete serão preservadas."
        )

        if not messagebox.askyesno(
            "Excluir modalidade",
            (
                f"Remover somente esta modalidade do bilhete #{ticket_id}?\n\n"
                f"{modality}\n"
                f"Palpites: {int(game.get('total_itens') or 0)}\n"
                f"Valor registrado: {self._money(total)}"
                f"{last_note}\n\n"
                "Esta ação não pode ser desfeita."
            ),
            parent=self,
        ):
            return

        try:
            report = self.db.delete_ticket_game(ticket_id, game_id)
        except Exception as exc:
            messagebox.showerror(
                "Excluir modalidade",
                str(exc),
                parent=self,
            )
            return

        if not report.get("deleted"):
            messagebox.showinfo(
                "Excluir modalidade",
                "A modalidade já não existe neste bilhete.",
                parent=self,
            )
            self.play_refresh_games()
            return

        self.play_selected_game_id = None
        self._update_results_nav_badge()
        self.play_refresh_games()

        if report.get("ticket_deleted"):
            self.play_selected_ticket_id = None
            feedback = (
                f"Última modalidade removida; o bilhete #{ticket_id} também foi excluído."
            )
        else:
            self.play_selected_ticket_id = ticket_id
            try:
                self.play_select_ticket_across_rounds(ticket_id)
            except Exception:
                pass
            feedback = (
                f"{modality} removida do bilhete #{ticket_id} • "
                f"{int(report.get('remaining_games') or 0)} modalidade(s) permanecem."
            )

        self.status.configure(text=feedback)
'''
s = s.replace(marker, ui_method + marker, 1)

p.write_text(s, encoding='utf-8')

# Documentação consolidada.
doc = Path('source/DOCUMENTACAO_GP-H.txt')
d = doc.read_text(encoding='utf-8')
entry = '''REVISÃO v0.47.0 — AUDITORIA AUTOMÁTICA / EDIÇÃO DO BILHETE\n- A interface deixa de mostrar os botões redundantes “Auditar este jogo”, “Auditar agora” e “Auditar jogos”. A auditoria NÃO foi removida: Atualizar resultados e Adicionar manual já chamam audit_frozen_games() automaticamente após a gravação.\n- As rotinas internas de auditoria permanecem disponíveis para o sistema e diagnóstico; telas analíticas de Auditoria/Desempenho não foram removidas.\n- No detalhe de uma modalidade pertencente a um bilhete registrado, o espaço do antigo botão “Auditar agora” passa a mostrar “Excluir esta modalidade”.\n- A exclusão parcial remove somente o jogo selecionado e seus palpites, preserva as demais modalidades e recalcula automaticamente total apostado, retorno, líquido e status do bilhete.\n- Se a modalidade removida for a última do bilhete, o bilhete vazio também é removido automaticamente.\n- Meta, Reset, Puxada, Similaridade, Histórico Concentrado, 3+1, Decisão, Walk-Forward e seus cálculos não foram alterados.\n\n'''
marker_doc = 'REVISÃO v0.46.9 —'
if marker_doc not in d:
    raise SystemExit('marcador documentação v0.46.9 não encontrado')
d = d.replace(marker_doc, entry + marker_doc, 1)
doc.write_text(d, encoding='utf-8')
