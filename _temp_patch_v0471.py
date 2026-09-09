from pathlib import Path
import re

SRC = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')
s = SRC.read_text(encoding='utf-8')

# Versão.
old = 'APP_VERSION = "0.47.0"'
new = 'APP_VERSION = "0.47.1"'
assert old in s, 'versão-base 0.47.0 não encontrada'
s = s.replace(old, new, 1)

# A rota Contents API usa conteúdo base64.
if not re.search(r'^import base64\s*$', s, flags=re.M):
    m = re.search(r'^(?:from\s+\S+\s+import\s+|import\s+)', s, flags=re.M)
    assert m, 'bloco de imports não encontrado'
    s = s[:m.start()] + 'import base64\n' + s[m.start():]

# Terceira rota oficial independente da família raw.
api_url = 'https://api.github.com/repos/clienteg1603/GP-H-Central-Historica/contents/update_manifest.json?ref=main'
if api_url not in s:
    marker = '''OFFICIAL_PROGRAM_UPDATE_MANIFEST_URLS = (\n    "https://raw.githubusercontent.com/clienteg1603/GP-H-Central-Historica/main/update_manifest.json",\n    "https://github.com/clienteg1603/GP-H-Central-Historica/raw/refs/heads/main/update_manifest.json",\n)'''
    replacement = '''OFFICIAL_PROGRAM_UPDATE_MANIFEST_URLS = (\n    "https://raw.githubusercontent.com/clienteg1603/GP-H-Central-Historica/main/update_manifest.json",\n    "https://github.com/clienteg1603/GP-H-Central-Historica/raw/refs/heads/main/update_manifest.json",\n    "https://api.github.com/repos/clienteg1603/GP-H-Central-Historica/contents/update_manifest.json?ref=main",\n)'''
    assert marker in s, 'tupla de rotas oficiais não encontrada'
    s = s.replace(marker, replacement, 1)

# Decodifica de forma estrita a resposta da Contents API oficial.
old_decode = '''    data = json.loads(raw.decode("utf-8"))\n    if not isinstance(data, dict):\n        raise ValueError("Manifesto de atualização inválido.")\n    return data'''
new_decode = '''    data = json.loads(raw.decode("utf-8"))\n\n    # v0.47.1 — terceira rota oficial pelo GitHub Contents API. Ela devolve\n    # um envelope JSON cujo campo content contém o manifesto em base64. Essa\n    # decodificação é aceita somente para a URL oficial conhecida.\n    if (\n        isinstance(data, dict)\n        and "api.github.com/repos/clienteg1603/GP-H-Central-Historica/contents/update_manifest.json" in url\n        and str(data.get("encoding") or "").lower() == "base64"\n        and data.get("content")\n    ):\n        try:\n            inner_raw = base64.b64decode(str(data["content"]).encode("ascii"))\n            data = json.loads(inner_raw.decode("utf-8"))\n        except Exception as exc:\n            raise ValueError("Resposta alternativa do servidor de atualização inválida.") from exc\n\n    if not isinstance(data, dict):\n        raise ValueError("Manifesto de atualização inválido.")\n    return data'''
assert old_decode in s, 'final de _fetch_json_url_once não encontrado'
s = s.replace(old_decode, new_decode, 1)

# Mensagem amigável: não deixa detalhes internos como Backend.max_conn_reached vazarem para a UI.
anchor = '''def _fetch_json_url_once(url, timeout=12):'''
assert anchor in s, '_fetch_json_url_once não encontrada'
helper = '''def _program_update_user_error(exc):\n    """Transforma falhas técnicas do servidor em uma mensagem útil ao usuário."""\n    if _is_transient_program_update_error(exc):\n        return (\n            "Servidor de atualização temporariamente ocupado. "\n            "A Central tentou novamente e também consultou rotas alternativas. "\n            "Tente novamente em alguns instantes."\n        )\n    if isinstance(exc, urllib.error.HTTPError):\n        code = int(getattr(exc, "code", 0) or 0)\n        return f"O servidor de atualização respondeu HTTP {code}. Tente novamente mais tarde."\n    if isinstance(exc, urllib.error.URLError):\n        return "Não foi possível acessar o servidor de atualização. Verifique sua conexão e tente novamente."\n    text = str(exc or "").strip()\n    return text or "Não foi possível consultar o servidor de atualização."\n\n\n'''
if 'def _program_update_user_error(exc):' not in s:
    s = s.replace(anchor, helper + anchor, 1)

# Download: hoje cada URL é tentada uma única vez. Passa a repetir apenas falhas transitórias.
start = s.index('def _download_update_file(')
end = s.index('\ndef _read_local_update_package', start)
old_download = s[start:end]
new_download = '''def _download_update_file(urls, destination, timeout=60, attempts=3):\n    urls = [str(v).strip() for v in urls if str(v).strip()]\n    if not urls:\n        raise ValueError("Nenhum endereço de download foi informado.")\n    try:\n        attempts = max(1, min(5, int(attempts)))\n    except Exception:\n        attempts = 3\n    delays = (0.50, 1.00, 1.75, 2.50)\n    destination = Path(destination)\n    last_error = None\n\n    for url in urls:\n        url_attempts = attempts if re.match(r"^https?://", url, flags=re.I) else 1\n        for attempt in range(url_attempts):\n            try:\n                if re.match(r"^https?://", url, flags=re.I):\n                    if re.match(r"^http://", url, flags=re.I) and not _is_local_update_url(url):\n                        raise ValueError("Download remoto sem HTTPS foi bloqueado.")\n                    req = urllib.request.Request(url, headers={"User-Agent": f"GP-H-Central/{APP_VERSION}"})\n                    with urllib.request.urlopen(req, timeout=timeout) as resp, destination.open("wb") as out:\n                        length = resp.headers.get("Content-Length")\n                        if length and int(length) > PROGRAM_UPDATE_MAX_PACKAGE_BYTES:\n                            raise ValueError("Pacote de atualização maior que o limite permitido.")\n                        total = 0\n                        while True:\n                            chunk = resp.read(1024 * 1024)\n                            if not chunk:\n                                break\n                            total += len(chunk)\n                            if total > PROGRAM_UPDATE_MAX_PACKAGE_BYTES:\n                                raise ValueError("Pacote de atualização maior que o limite permitido.")\n                            out.write(chunk)\n                elif url.startswith("file://"):\n                    from urllib.parse import urlparse, unquote\n                    src = Path(unquote(urlparse(url).path))\n                    shutil.copy2(src, destination)\n                else:\n                    shutil.copy2(Path(url), destination)\n                return url\n            except Exception as exc:\n                last_error = exc\n                try:\n                    destination.unlink(missing_ok=True)\n                except Exception:\n                    pass\n                if (\n                    attempt >= url_attempts - 1\n                    or not _is_transient_program_update_error(exc)\n                ):\n                    break\n                time.sleep(delays[min(attempt, len(delays) - 1)])\n\n    raise last_error or RuntimeError("Não foi possível baixar a atualização.")\n'''
s = s[:start] + new_download + s[end:]

# O worker preserva o erro técnico internamente, mas a UI recebe texto amigável.
old_worker = '''            except Exception as exc:\n                result = (False, None, str(exc))\n            self.sync_queue.put(("program_update_check_done", result, manual))'''
new_worker = '''            except Exception as exc:\n                result = (False, None, _program_update_user_error(exc))\n            self.sync_queue.put(("program_update_check_done", result, manual))'''
assert old_worker in s, 'worker de verificação do programa não encontrado'
s = s.replace(old_worker, new_worker, 1)

SRC.write_text(s, encoding='utf-8', newline='\n')

# Documentação consolidada.
d = DOC.read_text(encoding='utf-8')
entry = '''REVISÃO v0.47.1 — ATUALIZADOR / FALLBACK INDEPENDENTE\n\n- A consulta de atualização mantém as tentativas automáticas e ganha uma terceira rota oficial pela API do GitHub, independente das duas rotas raw usadas anteriormente.\n- Erros transitórios como HTTP 503 e Backend.max_conn_reached não são mais exibidos como detalhes técnicos ao usuário; somente após todas as rotas falharem aparece uma mensagem simples de servidor temporariamente ocupado.\n- O download do pacote também repete automaticamente falhas transitórias antes de desistir ou avançar para um espelho.\n- Verificação SHA-256, backup, rollback e preservação dos dados continuam inalterados.\n- Nenhum método de Meta, Reset, Puxada, Similaridade, Histórico Concentrado, 3+1 ou Decisão foi alterado.\n\n'''
if not d.startswith('REVISÃO v0.47.1'):
    d = entry + d
DOC.write_text(d, encoding='utf-8', newline='\n')
