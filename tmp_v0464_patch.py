from pathlib import Path
import ast

SRC = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')
text = SRC.read_text(encoding='utf-8')
doc = DOC.read_text(encoding='utf-8')

assert 'APP_VERSION = "0.46.3"' in text
text = text.replace('GP-H Central Histórica v0.46.3', 'GP-H Central Histórica v0.46.4', 1)
text = text.replace('APP_VERSION = "0.46.3"', 'APP_VERSION = "0.46.4"', 1)

# 1) Scrollbar: permitir que páginas sensíveis a resize reservem a largura da barra.
old = '''        def update_bar(first=None, last=None):
            try:
                if first is None or last is None:
                    first, last = canvas.yview()
                need = float(first) > 0.0 or float(last) < 1.0
                managed = bool(bar.winfo_manager())
                if need and not managed:
                    bar.pack(side="right", fill="y")
                elif not need and managed:
                    bar.pack_forget()
            except (tk.TclError, ValueError, TypeError):
                pass
'''
new = '''        def update_bar(first=None, last=None):
            try:
                if first is None or last is None:
                    first, last = canvas.yview()
                keep_reserved = bool(getattr(canvas, "_gph_keep_scrollbar", False))
                need = keep_reserved or float(first) > 0.0 or float(last) < 1.0
                managed = bool(bar.winfo_manager())
                if need and not managed:
                    bar.pack(side="right", fill="y")
                elif not need and managed:
                    bar.pack_forget()
            except (tk.TclError, ValueError, TypeError):
                pass
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)

# 2) A Home informa imediatamente que quer o gutter estável da scrollbar.
old = '''        body = self._make_scrollable_page_body(self.content, "home")
        home_canvas = getattr(body, "_gph_scroll_canvas", None)

        summary = self.db.home_summary()
'''
new = '''        body = self._make_scrollable_page_body(self.content, "home")
        home_canvas = getattr(body, "_gph_scroll_canvas", None)
        if home_canvas is not None:
            # Reserva a largura da barra na Home. Durante maximizar/restaurar o
            # Windows dispara vários Configure seguidos; retirar/recolocar a
            # barra mudava a largura do Canvas no meio da animação e causava
            # o tremor visual observado no Windows real.
            home_canvas._gph_keep_scrollbar = True

        summary = self.db.home_summary()
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)

# 3) Guardar a referência do Label da imagem para trocar large/medium sem
# destruir/recriar cartões (isso é o que torna a adaptação suave).
old = '''        animal.pack(expand=True, pady=(1 if compact else 3, 0))

        band = tk.Frame(card, bg=band_bg, bd=0)
'''
new = '''        animal.pack(expand=True, pady=(1 if compact else 3, 0))
        card._gph_animal_label = animal
        card._gph_animal_group = int(info["grupo"])
        card._gph_compact_card = bool(compact)

        band = tk.Frame(card, bg=band_bg, bd=0)
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)

# 4) Substituir o antigo height fixo por densidade responsiva e debounce.
old = '''
        # A página vive dentro de Canvas. Depois que todos os cartões existem,
        # congelamos apenas a ALTURA NATURAL solicitada pela Home. O Canvas pode
        # ficar menor que ela e então passa a rolar. Não prendemos <Configure>,
        # evitando ciclos de pack/unpack da própria barra de rolagem.
        if home_canvas is not None:
            def _home_set_natural_height():
                try:
                    body.update_idletasks()
                    natural_height = max(
                        720,
                        int(header.winfo_reqheight())
                        + int(main.winfo_reqheight())
                        + 10,
                    )
                    body.configure(height=natural_height)
                    bbox = home_canvas.bbox("all")
                    if bbox:
                        home_canvas.configure(scrollregion=bbox)
                except (tk.TclError, ValueError, TypeError):
                    pass
            self.after_idle(_home_set_natural_height)
'''
new = '''
        # HOME RESPONSIVA: maximizada mantém as imagens grandes; em alturas
        # menores usa as imagens médias já carregadas. Os widgets NÃO são
        # reconstruídos: apenas a propriedade image dos Labels é trocada.
        # Isso elimina a sequência de redraws/tremor ao restaurar a janela.
        if home_canvas is not None:
            home_state = {"after": None, "mode": None}
            self._home_responsive_state = home_state

            def _home_refresh_region():
                try:
                    body.update_idletasks()
                    bbox = home_canvas.bbox("all")
                    home_canvas.configure(scrollregion=bbox or (0, 0, 0, 0))
                except (tk.TclError, ValueError, TypeError):
                    pass

            def _home_apply_density():
                home_state["after"] = None
                try:
                    if getattr(self, "_page", None) != "home" or not home_canvas.winfo_exists():
                        return
                    viewport_h = max(1, int(home_canvas.winfo_height()))
                    # No Windows, a janela restaurada de 1280x760 costuma deixar
                    # cerca de 640-680 px úteis depois do título/status. Abaixo de
                    # 700 usamos medium para preservar as cinco linhas completas.
                    mode = "compact" if viewport_h < 700 else "large"
                    if mode != home_state["mode"]:
                        images = self.animal_images_medium if mode == "compact" else self.animal_images_large
                        row_min = 70 if mode == "compact" else 88
                        for row_idx in range(5):
                            grid.grid_rowconfigure(row_idx, minsize=row_min)
                        for animal_card in list(getattr(self, "home_cards", ())):
                            label = getattr(animal_card, "_gph_animal_label", None)
                            group = getattr(animal_card, "_gph_animal_group", None)
                            image = images.get(group) if group is not None else None
                            if label is not None and image is not None:
                                label.configure(image=image)
                        home_state["mode"] = mode
                        self._home_density_mode = mode
                    _home_refresh_region()
                except (tk.TclError, ValueError, TypeError):
                    pass

            def _home_schedule_density(_event=None):
                # Um resize de janela gera muitos Configure consecutivos. Esperar
                # o último evita redesenhar a grade dezenas de vezes durante a
                # animação do botão Maximizar/Restaurar.
                self._hide_animal_hover()
                pending = home_state.get("after")
                if pending:
                    try:
                        self.after_cancel(pending)
                    except Exception:
                        pass
                home_state["after"] = self.after(85, _home_apply_density)

            home_canvas.bind("<Configure>", _home_schedule_density, add="+")
            self.after_idle(_home_schedule_density)
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)

# Sintaxe agora; teste de comportamento roda no workflow.
ast.parse(text)
SRC.write_text(text, encoding='utf-8')

entry = '''REVISÃO v0.46.4 — HOME RESPONSIVA / RESTAURAR JANELA\n- Corrigido o tremor ao alternar Maximizar/Restaurar no Windows: a Home reserva a largura da scrollbar e não muda mais a geometria horizontal no meio da animação.\n- Eventos de resize da Home agora são agrupados (debounce curto), evitando dezenas de redesenhos consecutivos enquanto o Windows redimensiona a janela.\n- A grade 5x5 passa a usar imagens grandes quando há altura confortável e imagens médias automaticamente na janela restaurada/baixa, sem destruir nem recriar os cartões.\n- Removido o height mínimo artificial de 720 px da Home; a região rolável passa a seguir o tamanho real do conteúdo. Se ainda não houver espaço físico, a rolagem continua disponível até a 5ª linha.\n- O tooltip é recolhido durante mudança de tamanho para não ficar reposicionando sobre widgets em movimento.\n- Nenhum método de banco, Meta, Reset, Puxada, Similaridade, Histórico Concentrado, 3+1, ranking ou Decisão foi alterado.\n\n'''
if not doc.startswith('REVISÃO v0.46.4'):
    DOC.write_text(entry + doc, encoding='utf-8')

print('Patch v0.46.4 aplicado')
