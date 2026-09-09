from pathlib import Path

path = Path('source/gph_central.py')
text = path.read_text(encoding='utf-8')

old = r'''        # A página vive dentro de Canvas. Mantemos a altura natural do conteúdo
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

new = r'''        # A página vive dentro de Canvas. Depois que todos os cartões existem,
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

if old not in text:
    raise SystemExit('Guard de rolagem anterior não encontrado')
text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
print('Guard de rolagem v0.46.2 ajustado')
