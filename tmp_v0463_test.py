import ast
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

BASE = Path('/tmp/gph_main_v0462.py')
NEW = Path('source/gph_central.py')


def class_methods(path, class_name):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return {
        node.name: ast.dump(node, include_attributes=False)
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

base_db = class_methods(BASE, 'Database')
new_db = class_methods(NEW, 'Database')
missing = sorted(set(base_db) - set(new_db))
changed = sorted(name for name in base_db if name in new_db and base_db[name] != new_db[name])
if missing or changed:
    raise AssertionError(f'Database alterado. missing={missing} changed={changed}')
print(f'Database protegido: {len(base_db)} métodos AST-idênticos')

os.environ['GPH_DATA_DIR'] = tempfile.mkdtemp(prefix='gph_v0463_data_')
spec = importlib.util.spec_from_file_location('gph_v0463_module', NEW.resolve())
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
assert mod.APP_VERSION == '0.46.3'

root = Path(tempfile.mkdtemp(prefix='gph_v0463_sync_'))
target = root / 'devices' / 'abc.json'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text('{"old": true}', encoding='utf-8')

real_replace = mod.os.replace
real_sleep = mod.time.sleep
try:
    # Cenário 1: Dropbox bloqueia rename/replace em todas as tentativas,
    # mas permite abrir o arquivo final para escrita. O fallback deve concluir.
    calls = {'n': 0}
    def denied_replace(src, dst):
        calls['n'] += 1
        raise PermissionError(5, 'Acesso negado')
    mod.os.replace = denied_replace
    mod.time.sleep = lambda *_args, **_kwargs: None
    mod._atomic_write_json(target, {'novo': 123, 'texto': 'ok'})
    got = json.loads(target.read_text(encoding='utf-8'))
    assert got == {'novo': 123, 'texto': 'ok'}, got
    assert calls['n'] == 7, calls
    assert not list(target.parent.glob('abc.json.tmp-*'))
    print('Fallback após WinError 5: OK')

    # Cenário 2: bloqueio transitório desaparece na terceira tentativa.
    calls = {'n': 0}
    def transient_replace(src, dst):
        calls['n'] += 1
        if calls['n'] < 3:
            raise PermissionError(5, 'Acesso negado')
        return real_replace(src, dst)
    mod.os.replace = transient_replace
    mod._atomic_write_json(target, {'transitorio': True})
    assert json.loads(target.read_text(encoding='utf-8')) == {'transitorio': True}
    assert calls['n'] == 3, calls
    assert not list(target.parent.glob('abc.json.tmp-*'))
    print('Retry de bloqueio transitório: OK')
finally:
    mod.os.replace = real_replace
    mod.time.sleep = real_sleep

print('Smoke v0.46.3 OK')
