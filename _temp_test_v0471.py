import ast
import base64
import importlib.util
import io
import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

SOURCE = Path('source/gph_central.py')
BASELINE = Path('/tmp/gph_v0470_before.py')
before_s = BASELINE.read_text(encoding='utf-8')
after_s = SOURCE.read_text(encoding='utf-8')

assert 'APP_VERSION = "0.47.1"' in after_s
assert 'api.github.com/repos/clienteg1603/GP-H-Central-Historica/contents/update_manifest.json?ref=main' in after_s
assert 'def _program_update_user_error(exc):' in after_s

# A alteração é exclusivamente do atualizador/UI; todo o Database precisa ficar idêntico.
def class_ast(source, name):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(f'classe {name} ausente')

assert class_ast(before_s, 'Database') == class_ast(after_s, 'Database'), 'Database foi alterado'
print('OK: Database completo AST-idêntico')

os.environ['GPH_DISABLE_STARTUP_DIALOGS'] = '1'
spec = importlib.util.spec_from_file_location('gph_v0471_test', SOURCE)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
mod.time.sleep = lambda _delay: None

manifest = {
    'schema': 1,
    'app': mod.APP_NAME,
    'server_name': 'Teste',
    'channels': {
        'test': {
            'version': '9.9.9',
            'url': 'https://example.invalid/pkg.zip',
            'sha256': 'a' * 64,
            'mirrors': [],
        }
    },
}
manifest_bytes = json.dumps(manifest).encode('utf-8')
api_wrapper = json.dumps({
    'encoding': 'base64',
    'content': base64.b64encode(manifest_bytes).decode('ascii'),
}).encode('utf-8')

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.pos = 0
        self.headers = {'Content-Length': str(len(payload))}
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self, size=-1):
        if size is None or size < 0:
            size = len(self.payload) - self.pos
        if self.pos >= len(self.payload):
            return b''
        chunk = self.payload[self.pos:self.pos + size]
        self.pos += len(chunk)
        return chunk


def http503(url):
    return urllib.error.HTTPError(url, 503, 'Backend.max_conn_reached', {}, None)

original_urlopen = mod.urllib.request.urlopen
try:
    # Caso 1: as duas rotas raw falham 3x cada; Contents API salva a verificação.
    calls = []
    def fallback_urlopen(req, timeout=0):
        url = req.full_url if hasattr(req, 'full_url') else str(req)
        calls.append(url)
        if 'api.github.com/' in url:
            return FakeResponse(api_wrapper)
        raise http503(url)
    mod.urllib.request.urlopen = fallback_urlopen
    got, used = mod._fetch_program_update_manifest(mod.DEFAULT_PROGRAM_UPDATE_MANIFEST_URL)
    assert got['channels']['test']['version'] == '9.9.9'
    assert 'api.github.com/' in used
    primary = [u for u in calls if 'raw.githubusercontent.com' in u]
    secondary = [u for u in calls if 'github.com/clienteg1603/GP-H-Central-Historica/raw/' in u]
    api = [u for u in calls if 'api.github.com/' in u]
    assert len(primary) == 3, calls
    assert len(secondary) == 3, calls
    assert len(api) == 1, calls
    print('OK: 503 nas duas rotas raw -> fallback independente pela API funciona')

    # Caso 2: um 503 isolado é resolvido pelo retry sem trocar de rota.
    calls = []
    def retry_urlopen(req, timeout=0):
        url = req.full_url if hasattr(req, 'full_url') else str(req)
        calls.append(url)
        if len(calls) == 1:
            raise http503(url)
        return FakeResponse(manifest_bytes)
    mod.urllib.request.urlopen = retry_urlopen
    got, used = mod._fetch_program_update_manifest(mod.DEFAULT_PROGRAM_UPDATE_MANIFEST_URL)
    assert got['channels']['test']['version'] == '9.9.9'
    assert 'raw.githubusercontent.com' in used
    assert len(calls) == 2, calls
    print('OK: retry automático resolve 503 temporário na própria rota')

    # Caso 3: se absolutamente tudo falhar, nenhum detalhe Backend.max_conn_reached vaza à tela.
    calls = []
    def all_fail(req, timeout=0):
        url = req.full_url if hasattr(req, 'full_url') else str(req)
        calls.append(url)
        raise http503(url)
    mod.urllib.request.urlopen = all_fail
    try:
        mod._fetch_program_update_manifest(mod.DEFAULT_PROGRAM_UPDATE_MANIFEST_URL)
        raise AssertionError('era esperado erro após todas as rotas')
    except Exception as exc:
        friendly = mod._program_update_user_error(exc)
        assert 'Backend.max_conn_reached' not in friendly
        assert 'HTTP Error 503' not in friendly
        assert 'temporariamente ocupado' in friendly
        assert 'rotas alternativas' in friendly
    assert len(calls) == 9, calls  # 3 rotas x 3 tentativas
    print('OK: todas as rotas indisponíveis -> mensagem amigável, sem erro técnico')

    # Caso 4: o próprio download repete falhas transitórias antes de desistir.
    calls = []
    package = b'GP-H pacote teste v0.47.1'
    def download_urlopen(req, timeout=0):
        url = req.full_url if hasattr(req, 'full_url') else str(req)
        calls.append(url)
        if len(calls) == 1:
            raise http503(url)
        return FakeResponse(package)
    mod.urllib.request.urlopen = download_urlopen
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / 'pkg.zip'
        used = mod._download_update_file(['https://example.invalid/pkg.zip'], dest, attempts=3)
        assert used == 'https://example.invalid/pkg.zip'
        assert dest.read_bytes() == package
    assert len(calls) == 2, calls
    print('OK: download também se recupera de 503 transitório')
finally:
    mod.urllib.request.urlopen = original_urlopen

# Confere que o worker transforma a exceção antes de chegar à fila/UI.
tree = ast.parse(after_s)
worker_segments = []
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == 'worker':
        seg = ast.get_source_segment(after_s, node) or ''
        if 'program_update_check_done' in seg:
            worker_segments.append(seg)
assert len(worker_segments) == 1
assert '_program_update_user_error(exc)' in worker_segments[0]
assert 'result = (False, None, str(exc))' not in worker_segments[0]
print('OK: erro técnico é sanitizado antes da UI')
