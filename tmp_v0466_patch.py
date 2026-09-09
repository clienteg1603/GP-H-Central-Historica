from pathlib import Path
import ast

SRC = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')
text = SRC.read_text(encoding='utf-8')
doc = DOC.read_text(encoding='utf-8')

# Proteção: esta correção é somente do cliente de atualização.
tree_before = ast.parse(text)
def class_dump(tree, name):
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(name)
db_before = class_dump(tree_before, 'Database')

assert 'APP_VERSION = "0.46.5"' in text
assert 'GP-H Central Histórica v0.46.5' in text
text = text.replace('GP-H Central Histórica v0.46.5', 'GP-H Central Histórica v0.46.6', 1)
text = text.replace('APP_VERSION = "0.46.5"', 'APP_VERSION = "0.46.6"', 1)
text = text.replace('text="v0.46.5"', 'text="v0.46.6"', 1)

old_const = '''DEFAULT_PROGRAM_UPDATE_MANIFEST_URL = os.environ.get("GPH_UPDATE_MANIFEST_URL", "https://raw.githubusercontent.com/clienteg1603/GP-H-Central-Historica/main/update_manifest.json").strip()\nPROGRAM_UPDATE_MAX_MANIFEST_BYTES = 1024 * 1024\n'''
new_const = '''DEFAULT_PROGRAM_UPDATE_MANIFEST_URL = os.environ.get("GPH_UPDATE_MANIFEST_URL", "https://raw.githubusercontent.com/clienteg1603/GP-H-Central-Historica/main/update_manifest.json").strip()\nOFFICIAL_PROGRAM_UPDATE_MANIFEST_URLS = (\n    "https://raw.githubusercontent.com/clienteg1603/GP-H-Central-Historica/main/update_manifest.json",\n    "https://github.com/clienteg1603/GP-H-Central-Historica/raw/refs/heads/main/update_manifest.json",\n)\nPROGRAM_UPDATE_MAX_MANIFEST_BYTES = 1024 * 1024\n'''
assert text.count(old_const) == 1
text = text.replace(old_const, new_const, 1)

start = text.index('def _fetch_json_url(url, timeout=12):')
end = text.index('\n\ndef _resolve_update_url', start)
old_fetch = text[start:end]
new_fetch = r'''def _is_transient_program_update_error(exc):
    """Erros de rede que merecem nova tentativa sem incomodar o usuário."""
    if isinstance(exc, urllib.error.HTTPError):
        return int(getattr(exc, "code", 0) or 0) in {408, 425, 429, 500, 502, 503, 504}
    if isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError)):
        return True
    text = str(exc or "").lower()
    return any(token in text for token in (
        "backend.max_conn_reached", "timed out", "timeout", "temporarily unavailable",
        "connection reset", "connection aborted", "remote end closed",
    ))


def _fetch_json_url_once(url, timeout=12):
    url = _validate_update_manifest_url(url)
    if re.match(r"^https?://", url, flags=re.I):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"GP-H-Central/{APP_VERSION}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            length = resp.headers.get("Content-Length")
            if length and int(length) > PROGRAM_UPDATE_MAX_MANIFEST_BYTES:
                raise ValueError("Manifesto de atualização maior que o limite permitido.")
            raw = resp.read(PROGRAM_UPDATE_MAX_MANIFEST_BYTES + 1)
            if len(raw) > PROGRAM_UPDATE_MAX_MANIFEST_BYTES:
                raise ValueError("Manifesto de atualização maior que o limite permitido.")
    elif url.startswith("file://"):
        from urllib.parse import urlparse, unquote
        raw = Path(unquote(urlparse(url).path)).read_bytes()
    else:
        raw = Path(url).expanduser().read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Manifesto de atualização inválido.")
    return data


def _fetch_json_url(url, timeout=12, attempts=3):
    """Busca JSON com retry curto para congestionamentos/erros temporários."""
    try:
        attempts = max(1, min(5, int(attempts)))
    except Exception:
        attempts = 3
    delays = (0.35, 0.80, 1.40, 2.00)
    last_error = None
    for attempt in range(attempts):
        try:
            return _fetch_json_url_once(url, timeout=timeout)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts - 1 or not _is_transient_program_update_error(exc):
                raise
            time.sleep(delays[min(attempt, len(delays) - 1)])
    raise last_error or RuntimeError("Não foi possível consultar o servidor de atualização.")


def _program_update_manifest_candidates(url):
    """Mantém servidor customizado intacto; só cria fallback para o oficial GP-H."""
    url = _validate_update_manifest_url(url)
    candidates = [url]
    normalized = url.rstrip("/")
    official = {item.rstrip("/") for item in OFFICIAL_PROGRAM_UPDATE_MANIFEST_URLS}
    if normalized in official:
        for item in OFFICIAL_PROGRAM_UPDATE_MANIFEST_URLS:
            if item.rstrip("/") != normalized and item not in candidates:
                candidates.append(item)
    return candidates


def _fetch_program_update_manifest(url, timeout=12):
    """Consulta o manifesto oficial com retry e rota alternativa automática."""
    last_error = None
    for candidate in _program_update_manifest_candidates(url):
        try:
            return _fetch_json_url(candidate, timeout=timeout, attempts=3), candidate
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError("Não foi possível consultar o servidor de atualização.")
'''
text = text[:start] + new_fetch + text[end:]

old_worker = '''                manifest = _fetch_json_url(url)\n                release = _release_from_manifest(manifest, channel=channel, manifest_url=url)\n                result = (True, release, None)\n'''
new_worker = '''                manifest, used_manifest_url = _fetch_program_update_manifest(url)\n                release = _release_from_manifest(manifest, channel=channel, manifest_url=used_manifest_url)\n                result = (True, release, None)\n'''
assert text.count(old_worker) == 1, text.count(old_worker)
text = text.replace(old_worker, new_worker, 1)

revision = '''REVISÃO v0.46.6 — ATUALIZADOR RESILIENTE / HTTP 503\n- Corrigido o comportamento em que “Buscar nova versão” desistia após uma única falha temporária e o usuário acabava fechando/reabrindo a Central para provocar outra tentativa.\n- Erros transitórios de rede (408/425/429/500/502/503/504, timeout, conexão resetada e Backend.max_conn_reached) agora recebem até 3 tentativas automáticas com pequenas esperas progressivas.\n- Quando o manifesto oficial em raw.githubusercontent.com continuar indisponível, a Central tenta automaticamente uma segunda rota oficial pelo github.com/raw.\n- Servidores personalizados configurados pelo usuário não são redirecionados para o GitHub: retry ocorre no próprio endereço configurado.\n- A mensagem de erro só aparece depois que todas as tentativas/rotas aplicáveis falharem.\n- Nenhum método de banco, Meta, Reset, Puxada, Similaridade, Histórico, 3+1, ranking ou Decisão foi alterado.\n\n'''
doc = revision + doc

ast.parse(text)
tree_after = ast.parse(text)
assert class_dump(tree_after, 'Database') == db_before, 'Database foi alterado'
assert 'def _fetch_program_update_manifest(' in text
assert 'manifest, used_manifest_url = _fetch_program_update_manifest(url)' in text

SRC.write_text(text, encoding='utf-8')
DOC.write_text(doc, encoding='utf-8')
print('v0.46.6 patch aplicado; Database AST idêntico.')
