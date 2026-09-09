import ast
import importlib.util
import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

CUR = Path('source/gph_central.py')
BASE = Path('/tmp/gph_main_v0465.py')

def class_dump(path, name):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(name)

assert class_dump(CUR, 'Database') == class_dump(BASE, 'Database')

os.environ['GPH_DATA_DIR'] = tempfile.mkdtemp(prefix='gph_v0466_')
spec = importlib.util.spec_from_file_location('gph_v0466_module', CUR.resolve())
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

class FakeResp:
    def __init__(self, payload):
        self.payload = payload
        self.headers = {}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, _n=-1):
        return self.payload

orig_urlopen = mod.urllib.request.urlopen
orig_sleep = mod.time.sleep
mod.time.sleep = lambda *_a, **_k: None

# 503 duas vezes, sucesso na terceira: o usuário não deve precisar reiniciar.
calls = {'n': 0}
def flaky(req, timeout=12):
    calls['n'] += 1
    if calls['n'] < 3:
        raise urllib.error.HTTPError(req.full_url, 503, 'Backend.max_conn_reached', {}, None)
    return FakeResp(b'{"schema": 1, "ok": true}')
mod.urllib.request.urlopen = flaky
result = mod._fetch_json_url('https://example.invalid/update_manifest.json', attempts=3)
assert result['ok'] is True
assert calls['n'] == 3, calls

# Erro 404 não é transitório: não fica martelando o servidor.
calls['n'] = 0
def not_found(req, timeout=12):
    calls['n'] += 1
    raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)
mod.urllib.request.urlopen = not_found
try:
    mod._fetch_json_url('https://example.invalid/update_manifest.json', attempts=3)
    raise AssertionError('404 deveria falhar')
except urllib.error.HTTPError as exc:
    assert exc.code == 404
assert calls['n'] == 1, calls

# Fallback só para o servidor oficial.
primary, fallback = mod.OFFICIAL_PROGRAM_UPDATE_MANIFEST_URLS
seen = []
orig_fetch = mod._fetch_json_url
def fake_fetch(url, timeout=12, attempts=3):
    seen.append(url)
    if url == primary:
        raise urllib.error.HTTPError(url, 503, 'Backend.max_conn_reached', {}, None)
    return {'schema': 1, 'app': mod.APP_NAME, 'channels': {}}
mod._fetch_json_url = fake_fetch
manifest, used = mod._fetch_program_update_manifest(primary)
assert used == fallback, (used, fallback)
assert seen == [primary, fallback], seen

custom = 'https://updates.exemplo.com/manifest.json'
assert mod._program_update_manifest_candidates(custom) == [custom]

mod._fetch_json_url = orig_fetch
mod.urllib.request.urlopen = orig_urlopen
mod.time.sleep = orig_sleep

text = CUR.read_text(encoding='utf-8')
assert 'manifest, used_manifest_url = _fetch_program_update_manifest(url)' in text
assert 'APP_VERSION = "0.46.6"' in text
print('UPDATER v0.46.6 OK | retry 503 | fallback oficial | custom preservado | Database idêntico')
