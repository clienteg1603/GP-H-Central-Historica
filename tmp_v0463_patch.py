from pathlib import Path
import re

path = Path('source/gph_central.py')
text = path.read_text(encoding='utf-8')
original = text

text = text.replace('GP-H Central Histórica v0.46.2', 'GP-H Central Histórica v0.46.3', 1)
text, n = re.subn(r'APP_VERSION\s*=\s*"0\.46\.2"', 'APP_VERSION = "0.46.3"', text, count=1)
if n != 1:
    raise SystemExit('APP_VERSION 0.46.2 não encontrado')

old = '''def _atomic_write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
'''

new = '''def _atomic_write_json(path, data):
    """Grava JSON com tolerância a bloqueios transitórios de Dropbox/OneDrive."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    tmp.write_text(payload, encoding="utf-8")

    last_error = None
    try:
        # Cloud clients e antivírus podem segurar o arquivo final por alguns
        # milissegundos. Repetimos o replace atômico antes de usar fallback.
        for attempt in range(7):
            try:
                os.replace(tmp, path)
                return
            except PermissionError as exc:
                last_error = exc
                if attempt < 6:
                    time.sleep(min(0.10 * (attempt + 1), 0.60))

        # No Windows é comum o provedor permitir escrita, mas negar a operação
        # de DELETE/RENAME exigida por os.replace. Como este arquivo pertence
        # somente a este dispositivo, o fallback seguro é sobrescrevê-lo em
        # fluxo único, com flush/fsync. O SQLite local nunca é tocado aqui.
        for attempt in range(4):
            try:
                with path.open("w", encoding="utf-8", newline="\n") as fh:
                    fh.write(payload)
                    fh.flush()
                    try:
                        os.fsync(fh.fileno())
                    except OSError:
                        pass
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
                return
            except PermissionError as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.20 * (attempt + 1))

        raise last_error or PermissionError(f"Não foi possível gravar {path}")
    finally:
        # Não deixa lixo .tmp permanente quando a tentativa falha.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
'''

if old not in text:
    raise SystemExit('_atomic_write_json original não encontrado')
text = text.replace(old, new, 1)

# Melhora a mensagem para esse erro específico no sync manual.
old_msg = '''        except Exception as exc:
            if not silent:
                messagebox.showerror("Sincronização entre PCs", str(exc), parent=self)
'''
new_msg = '''        except Exception as exc:
            if not silent:
                detail = str(exc)
                if isinstance(exc, PermissionError) or "WinError 5" in detail or "Acesso negado" in detail:
                    detail = (
                        "A pasta compartilhada está temporariamente bloqueando a gravação de um arquivo do GP-H.\n\n"
                        "Isso costuma acontecer enquanto Dropbox/OneDrive está processando o mesmo arquivo. "
                        "A Central tentou novamente automaticamente e não alterou seu banco local.\n\n"
                        "Espere a nuvem terminar de sincronizar e tente novamente.\n\nDetalhe técnico: " + detail
                    )
                messagebox.showerror("Sincronização entre PCs", detail, parent=self)
'''
if old_msg in text:
    text = text.replace(old_msg, new_msg, 1)

path.write_text(text, encoding='utf-8')

doc_path = Path('source/DOCUMENTACAO_GP-H.txt')
doc = doc_path.read_text(encoding='utf-8')
entry = '''REVISÃO v0.46.3 — SINCRONIZAÇÃO / WINERROR 5\n- Corrigida falha de sincronização em pastas Dropbox/OneDrive quando o Windows bloqueia temporariamente a troca atômica do JSON do dispositivo (WinError 5 / Acesso negado).\n- A gravação agora tenta novamente o replace atômico com espera curta e, se o provedor de nuvem permitir escrita mas negar rename/delete, usa fallback de sobrescrita com flush/fsync.\n- Arquivos temporários são limpos após falha; o banco SQLite local não é substituído nem sobrescrito por esse mecanismo.\n- Mensagem de erro de sincronização ficou mais clara para bloqueios de pasta compartilhada.\n- Nenhum cálculo de Meta, Reset, Puxada, Similaridade, Histórico Concentrado, 3+1 ou Decisão foi alterado.\n\n'''
if not doc.startswith('REVISÃO v0.46.3'):
    doc_path.write_text(entry + doc, encoding='utf-8')

if text == original:
    raise SystemExit('Nenhuma alteração aplicada')
print('Patch v0.46.3 aplicado')
