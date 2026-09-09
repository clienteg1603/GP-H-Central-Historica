from pathlib import Path
import re

path = Path('source/gph_central.py')
text = path.read_text(encoding='utf-8')
original = text

# Versão patch: somente correções de interface da Home.
text = text.replace('GP-H Central Histórica v0.46.1', 'GP-H Central Histórica v0.46.2', 1)
text, n = re.subn(r'APP_VERSION\s*=\s*"0\.46\.1"', 'APP_VERSION = "0.46.2"', text, count=1)
if n != 1:
    raise SystemExit('APP_VERSION 0.46.1 não encontrado')

# Estado de hover compartilhado: evita recriar popup ao cruzar filhos do mesmo cartão.
old = '''        self._hover_popup = None\n        self._hover_after_id = None\n        self._install_smart_scroll_policy()'''
new = '''        self._hover_popup = None\n        self._hover_after_id = None\n        self._hover_card = None\n        self._install_smart_scroll_policy()'''
if old not in text:
    raise SystemExit('Bloco de estado visual não encontrado')
text = text.replace(old, new, 1)

# A Home passa a guardar o Canvas para garantir que, em janela baixa, a grade inteira
# continue no scrollregion em vez de cortar a quinta linha.
old = '''        body = self._make_scrollable_page_body(self.content, "home")\n\n        summary = self.db.home_summary()'''
new = '''        body = self._make_scrollable_page_body(self.content, "home")\n        home_canvas = getattr(body, "_gph_scroll_canvas", None)\n\n        summary = self.db.home_summary()'''
if old not in text:
    raise SystemExit('Início da Home não encontrado')
text = text.replace(old, new, 1)

# Reescreve apenas o cartão visual; nenhuma consulta/cálculo de banco é tocada.
start = text.find('    def _make_animal_card(self, parent, info, compact=False):')
end = text.find('    def _cancel_hover_hide(self):', start)
if start < 0 or end < 0:
    raise SystemExit('Função _make_animal_card não encontrada')

new_func = r'''    def _make_animal_card(self, parent, info, compact=False):
        """Cartão do bicho com hover estável, sem mudança de geometria."""
        card_bg = self.colors["card"]
        band_bg = self.colors["band"]

        # A moldura fica fisicamente com 1 px o tempo todo. Em repouso ela usa
        # a mesma cor do cartão e fica invisível; no hover muda apenas a cor.
        # Assim o tamanho do widget nunca oscila quando o mouse entra/sai.
        card = tk.Frame(
            parent,
            bg=card_bg,
            highlightbackground=card_bg,
            highlightthickness=1,
            bd=0,
            cursor="hand2",
        )

        visual = tk.Frame(card, bg=card_bg, bd=0)
        visual.pack(fill="both", expand=True)
        image = (
            self.animal_images_large.get(info["grupo"])
            if compact
            else self.animal_images_large.get(info["grupo"])
        )
        if image is not None:
            animal = tk.Label(visual, image=image, bg=card_bg, bd=0)
        else:
            animal = tk.Label(
                visual,
                text=BICHO_ICONS.get(info["grupo"], "●"),
                bg=card_bg,
                fg=self.colors["text"],
                font=("Segoe UI Emoji", 28 if compact else 30),
                bd=0,
            )
        animal.pack(expand=True, pady=(1 if compact else 3, 0))

        band = tk.Frame(card, bg=band_bg, bd=0)
        band.pack(fill="x", side="bottom")
        title = tk.Label(
            band,
            text=f"{info['grupo']:02d} · {info['bicho']}",
            bg=band_bg,
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 8 if compact else 9),
            anchor="center",
        )
        title.pack(fill="x", pady=(2, 0))
        dezenas = tk.Label(
            band,
            text="  ".join(info["dezenas"]),
            bg=band_bg,
            fg=self.colors["accent"],
            font=("Segoe UI Semibold", 8),
            anchor="center",
        )
        dezenas.pack(fill="x", pady=(0, 2 if compact else 3))

        hover_state = {"active": False, "leave_after": None}

        def _cancel_card_leave():
            after_id = hover_state.get("leave_after")
            if after_id:
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
                hover_state["leave_after"] = None

        def _pointer_inside_card():
            try:
                px, py = self.winfo_pointerxy()
                x0, y0 = card.winfo_rootx(), card.winfo_rooty()
                return (
                    x0 <= px < x0 + max(1, card.winfo_width())
                    and y0 <= py < y0 + max(1, card.winfo_height())
                )
            except Exception:
                return False

        def _set_hover_visual(active):
            hover_state["active"] = bool(active)
            bg = self.colors["hover"] if active else card_bg
            card.configure(
                highlightbackground=(
                    self.colors["accent_hover"] if active else card_bg
                ),
                bg=bg,
            )
            visual.configure(bg=bg)
            animal.configure(bg=bg)

        def enter(_event=None):
            _cancel_card_leave()
            self._cancel_hover_hide()

            # Entrar da imagem para a faixa/nome/dezenas continua sendo o mesmo
            # cartão. Não redesenha e, principalmente, não destrói/recria tooltip.
            if hover_state["active"]:
                return

            _set_hover_visual(True)
            if getattr(self, "_hover_card", None) is not card:
                self._hover_card = card
                self._show_animal_hover(card, info)

        def finish_leave():
            hover_state["leave_after"] = None
            if _pointer_inside_card():
                return
            _set_hover_visual(False)
            if getattr(self, "_hover_card", None) is card:
                self._hover_card = None
                self._schedule_hover_hide()

        def leave(_event=None):
            # Leave/Enter também acontecem ao cruzar subwidgets no Tk. Um atraso
            # curtíssimo permite que a entrada no próximo filho cancele a saída.
            _cancel_card_leave()
            hover_state["leave_after"] = self.after(65, finish_leave)

        def click(_event=None):
            _cancel_card_leave()
            self._hide_animal_hover()
            AnimalQuickDetailsDialog(self, self.db, info["grupo"])

        for widget in (card, visual, animal, band, title, dezenas):
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)
            widget.bind("<Button-1>", click)

        return card


'''
text = text[:start] + new_func + text[end:]

# Antes de sair da show_home, fixa a altura natural da página e atualiza o
# scrollregion. Em janela grande não aparece rolagem; em janela menor a roda e
# a barra passam a alcançar inclusive Touro/Tigre/Urso/Veado/Vaca.
marker = '\n    def show_home_animals(self):'
if marker not in text:
    raise SystemExit('Fim da Home não encontrado')
scroll_guard = r'''
        # A página vive dentro de Canvas. Mantemos a altura natural do conteúdo
        # mesmo quando a janela fica menor; o Canvas então rola em vez de cortar.
        if home_canvas is not None:
            def _home_refresh_scrollregion(_event=None):
                def apply():
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
                self.after_idle(apply)

            home_canvas.bind(
                "<Configure>", _home_refresh_scrollregion, add="+"
            )
            _home_refresh_scrollregion()

'''
text = text.replace(marker, '\n' + scroll_guard + marker, 1)

# Documentação consolidada.
doc_path = Path('source/DOCUMENTACAO_GP-H.txt')
doc = doc_path.read_text(encoding='utf-8')
entry = '''REVISÃO v0.46.2 — HOME RESPONSIVA / HOVER ESTÁVEL\n- Corrigido o tremor dos cartões ao mover rapidamente o mouse: cruzar imagem, faixa, nome e dezenas não recria mais o tooltip nem altera a geometria do cartão.\n- A moldura do hover mantém 1 px físico constante e muda apenas de cor, eliminando deslocamento visual.\n- Home passa a preservar a altura natural do conteúdo dentro do Canvas; ao reduzir a janela, a quinta linha de bichos continua acessível por rolagem em vez de ser cortada.\n- Nenhum cálculo de Meta, Reset, Puxada, Similaridade, Histórico Concentrado, 3+1, ranking numérico ou Decisão foi alterado.\n\n'''
if not doc.startswith('REVISÃO v0.46.2'):
    doc = entry + doc
    doc_path.write_text(doc, encoding='utf-8')

if text == original:
    raise SystemExit('Nenhuma alteração aplicada')
path.write_text(text, encoding='utf-8')
print('Patch v0.46.2 aplicado')
