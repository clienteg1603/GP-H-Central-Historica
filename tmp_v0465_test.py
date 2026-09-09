import ast
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

CUR = Path('source/gph_central.py')
BASE = Path('/tmp/gph_main_v0464.py')

# Database inteiro precisa ficar igual à v0.46.4.
def class_dump(path, name):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(name)

assert class_dump(BASE, 'Database') == class_dump(CUR, 'Database')

data_dir = Path(tempfile.mkdtemp(prefix='gph_v0465_'))
os.environ['GPH_DATA_DIR'] = str(data_dir)
(data_dir / 'atualizacoes_programa').mkdir(parents=True, exist_ok=True)
(data_dir / 'atualizacoes_programa' / 'settings.json').write_text(
    json.dumps({'auto_check': False, 'channel': 'test'}), encoding='utf-8'
)

spec = importlib.util.spec_from_file_location('gph_v0465_module', CUR.resolve())
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
mod.App._maximize_main_window = lambda self: None
for name in ('showinfo','showwarning','showerror'):
    setattr(mod.messagebox, name, lambda *a, **k: None)
mod.messagebox.askyesno = lambda *a, **k: False

# Evita diálogo de criação de perfil em ambiente temporário.
profile = mod.build_account_profile('Teste', code='GPH-ABCD-2345', remember_login=True)
mod.save_account_profile(profile)

app = mod.App()
app.state('normal')
app.geometry('1050x700+0+0')
end = time.time() + 0.45
while time.time() < end:
    app.update()
    time.sleep(0.01)

assert app.minsize()[1] == 700, app.minsize()
assert len(app.home_cards) == 25
assert not hasattr(app, '_home_responsive_state')

# compact=True deve nascer diretamente em medium; nada de troca após Configure.
first = app.home_cards[0]
lab = first._gph_animal_label
grp = first._gph_animal_group
assert str(lab.cget('image')) == str(app.animal_images_medium[grp])
initial_image = str(lab.cget('image'))

# Sequência rápida de resize: imagem deve permanecer exatamente a mesma.
for value in ('1300x760+0+0','1600x900+0+0','1200x730+0+0','1050x700+0+0'):
    app.geometry(value)
    app.update()
    time.sleep(0.025)
for _ in range(15):
    app.update(); time.sleep(0.01)
assert str(lab.cget('image')) == initial_image

# Quinta linha deve estar fisicamente inteira no menor tamanho permitido.
canvas = app._smart_scroll_canvases['home']
canvas_top = canvas.winfo_rooty()
canvas_bottom = canvas_top + canvas.winfo_height()
last_bottom = max(c.winfo_rooty() + c.winfo_height() for c in app.home_cards[20:25])
assert last_bottom <= canvas_bottom + 3, (canvas.winfo_height(), last_bottom - canvas_top)

# Fora do Windows, o método DWM deve ser inofensivo.
assert app._disable_windows_window_transitions() in (False, True)

app.destroy()
print('SMOKE v0.46.5 OK | 25 bichos inteiros | imagem estática | Database idêntico')
