import ast
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

BASE = Path('/tmp/gph_main_v0461.py')
NEW = Path('source/gph_central.py')


def class_methods(path, class_name):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    out = {}
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = ast.dump(node, include_attributes=False)
    return out

# O banco/motores estatísticos precisam permanecer byte-estruturalmente iguais em AST.
base_db = class_methods(BASE, 'Database')
new_db = class_methods(NEW, 'Database')
missing = sorted(set(base_db) - set(new_db))
changed = sorted(name for name in base_db if name in new_db and base_db[name] != new_db[name])
if missing or changed:
    raise AssertionError(f'Database alterado. missing={missing} changed={changed}')
print(f'Database protegido: {len(base_db)} métodos AST-idênticos')

# Carrega a aplicação usando pasta temporária, sem tela de login e sem maximização.
os.environ['GPH_DATA_DIR'] = tempfile.mkdtemp(prefix='gph_v0462_')
spec = importlib.util.spec_from_file_location('gph_v0462_module', NEW.resolve())
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
assert mod.APP_VERSION == '0.46.2'

mod.App._ensure_profile_login = lambda self: True
mod.App._maximize_main_window = lambda self: None
app = mod.App()
try:
    app.geometry('1100x650+0+0')
    app.update_idletasks()
    app.update()
    app.show_home()
    app.update_idletasks()
    app.update()

    canvas = app._smart_scroll_canvases.get('home')
    assert canvas is not None, 'Canvas da Home não encontrado'
    bbox = canvas.bbox('all')
    assert bbox is not None
    content_h = bbox[3] - bbox[1]
    viewport_h = canvas.winfo_height()
    assert content_h > viewport_h, (content_h, viewport_h)
    first, last = canvas.yview()
    assert last < 0.999, (first, last, content_h, viewport_h)
    canvas.yview_moveto(1.0)
    app.update_idletasks()
    app.update()
    first2, last2 = canvas.yview()
    assert last2 > 0.995, (first2, last2)
    print(f'Home reduzida rolável: conteúdo={content_h}px viewport={viewport_h}px yview={first2:.3f}-{last2:.3f}')

    cards = getattr(app, 'home_cards', [])
    assert len(cards) == 25
    card = cards[0]
    assert int(card.cget('highlightthickness')) == 1

    # Simula cruzamento rápido entre subwidgets do mesmo cartão. O popup deve ser
    # o mesmo objeto; antes da correção ele era destruído/recriado a cada filho.
    card.event_generate('<Enter>', x=8, y=8)
    app.update_idletasks(); app.update()
    popup1 = app._hover_popup
    assert popup1 is not None

    visual = card.winfo_children()[0]
    animal = visual.winfo_children()[0]
    band = card.winfo_children()[1]
    title = band.winfo_children()[0]
    animal.event_generate('<Leave>')
    title.event_generate('<Enter>')
    app.update_idletasks(); app.update()
    assert app._hover_popup is popup1, 'Tooltip foi recriado ao cruzar filhos do mesmo cartão'
    assert int(card.cget('highlightthickness')) == 1
    print('Hover estável: popup preservado e geometria constante')
finally:
    try:
        app.destroy()
    except Exception:
        pass

print('Smoke v0.46.2 OK')
