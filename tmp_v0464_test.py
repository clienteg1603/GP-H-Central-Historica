import ast
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

BASE = Path('/tmp/gph_main_v0463.py')
CUR = Path('source/gph_central.py')

# Proteção máxima nesta correção visual: a classe Database inteira deve ficar
# estruturalmente idêntica à v0.46.3 da main.
def class_dump(path, name):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(name)

assert class_dump(BASE, 'Database') == class_dump(CUR, 'Database'), 'Database foi alterado'

# Ambiente isolado para o smoke UI.
data_dir = Path(tempfile.mkdtemp(prefix='gph_v0464_'))
os.environ['GPH_DATA_DIR'] = str(data_dir)
(data_dir / 'atualizacoes_programa').mkdir(parents=True, exist_ok=True)
(data_dir / 'atualizacoes_programa' / 'settings.json').write_text(
    json.dumps({'auto_check': False, 'channel': 'test'}), encoding='utf-8'
)
# Perfil válido evita qualquer diálogo modal de primeiro uso durante o Xvfb.
(data_dir / 'account_profile.json').write_text(json.dumps({
    'profile_name': 'Teste UI',
    'profile_code': 'GPH-TEST-1234',
    'remember_login': True,
    'device_id': '00000000-0000-4000-8000-000000000001',
    'device_name': 'TESTE-XVFB',
    'sync_enabled': False,
    'sync_folder': None,
}, ensure_ascii=False), encoding='utf-8')

spec = importlib.util.spec_from_file_location('gph_v0464_module', CUR.resolve())
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

# Não queremos a maximização automática do produto no teste: precisamos medir
# explicitamente janela pequena e grande.
mod.App._maximize_main_window = lambda self: None
for name in ('showinfo','showwarning','showerror'):
    setattr(mod.messagebox, name, lambda *a, **k: None)
mod.messagebox.askyesno = lambda *a, **k: False
mod.simpledialog.askstring = lambda *a, **k: None

app = mod.App()
app.state('normal')


def settle(seconds=0.28):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.01)


def geometry(value):
    app.geometry(value)
    settle()
    canvas = app._smart_scroll_canvases['home']
    return canvas

# Menor tamanho permitido: a grade deve adaptar para medium e a quinta linha
# precisa ficar fisicamente dentro da área visível, sem ser cortada.
canvas = geometry('1050x650+0+0')
assert getattr(app, '_home_density_mode', None) == 'compact', getattr(app, '_home_density_mode', None)
assert len(app.home_cards) == 25
canvas_top = canvas.winfo_rooty()
canvas_bottom = canvas_top + canvas.winfo_height()
last_bottom = max(c.winfo_rooty() + c.winfo_height() for c in app.home_cards[20:25])
assert last_bottom <= canvas_bottom + 3, (canvas.winfo_height(), last_bottom - canvas_top)
assert canvas._gph_scrollbar.winfo_manager() == 'pack', 'scrollbar/gutter da Home não ficou reservado'

# Janela confortável: mantém os bichos grandes.
canvas = geometry('1600x900+0+0')
assert getattr(app, '_home_density_mode', None) == 'large', getattr(app, '_home_density_mode', None)
assert canvas._gph_scrollbar.winfo_manager() == 'pack'

# Simula a sequência que o Windows produz em Maximizar/Restaurar: vários
# Configure em pouco tempo. O debounce deve terminar em um único estado estável.
for value in ('1500x880+0+0','1300x760+0+0','1120x680+0+0','1050x650+0+0'):
    app.geometry(value)
    app.update()
    time.sleep(0.018)
settle(0.35)
canvas = app._smart_scroll_canvases['home']
assert getattr(app, '_home_density_mode', None) == 'compact'
state = getattr(app, '_home_responsive_state', {})
assert state.get('after') is None, state

# Sem novo resize, largura/altura do Canvas não podem ficar oscilando por
# pack/unpack de scrollbar.
sizes=[]
for _ in range(16):
    app.update()
    sizes.append((canvas.winfo_width(), canvas.winfo_height()))
    time.sleep(0.015)
assert len(set(sizes)) == 1, sizes

# Última linha continua inteira depois da sequência rápida.
canvas_top = canvas.winfo_rooty()
canvas_bottom = canvas_top + canvas.winfo_height()
last_bottom = max(c.winfo_rooty() + c.winfo_height() for c in app.home_cards[20:25])
assert last_bottom <= canvas_bottom + 3, (canvas.winfo_height(), last_bottom - canvas_top)

app.destroy()
print('SMOKE HOME v0.46.4 OK | Database AST idêntico | resize estável | 25 bichos visíveis')
