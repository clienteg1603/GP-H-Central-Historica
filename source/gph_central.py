# -*- coding: utf-8 -*-
"""
GP-H Central Histórica v0.36.2
Pesquisa e manutenção do histórico 2026 do Deu no Poste / PT-Rio.

Escopo desta versão:
- Sincroniza resultados de 02/01/2026 até a data atual.
- Guarda 1º ao 5º prêmio.
- Pesquisa por bicho, grupo, dezena, centena ou milhar.
- Filtros por período, sorteio/horário e posição.
- Cadastro manual de resultado.
- Auditoria automática da base após cada atualização.
- Exportação da pesquisa para CSV.
- Perfil local sem senha com código único e sincronização multi-PC por pasta compartilhada.

Somente biblioteca padrão do Python.
"""

from __future__ import annotations

import csv
import calendar
import html
import hashlib
import os
import queue
import shutil
import subprocess
import re
import secrets
import socket
import uuid
import sqlite3
import threading
import copy
import json
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from itertools import combinations, permutations
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import traceback

CRASH_LOG_NAME = "ERRO_GP-H_ULTIMO.txt"

def write_crash_log(exc: BaseException):
    """Grava um relatório de erro fora da pasta da versão sempre que possível."""
    try:
        fallback_root = Path(__file__).resolve().parent
        log_root = Path(globals().get("LOG_DIR", fallback_root))
        log_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") if "datetime" in globals() else str(int(time.time()))
        dated = log_root / f"ERRO_GP-H_{stamp}.txt"
        latest = log_root / CRASH_LOG_NAME
        content = []
        content.append("GP-H CENTRAL HISTÓRICA - RELATÓRIO DE ERRO\n")
        content.append("=" * 55 + "\n\n")
        content.append(f"Versão: {APP_VERSION if 'APP_VERSION' in globals() else 'desconhecida'}\n")
        content.append(f"Python: {sys.version}\n")
        content.append(f"Executável: {sys.executable}\n")
        content.append(f"Pasta do programa: {fallback_root}\n")
        if "DATA_DIR" in globals():
            content.append(f"Pasta de dados: {DATA_DIR}\n")
        content.append("\n")
        import io
        buf = io.StringIO()
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=buf)
        content.append(buf.getvalue())
        text = "".join(content)
        dated.write_text(text, encoding="utf-8")
        latest.write_text(text, encoding="utf-8")
        return dated
    except Exception:
        return None



APP_NAME = "GP-H Central Histórica"
APP_VERSION = "0.36.2"
START_DATE = date(2026, 1, 2)
BASE_URL = "https://brasildeunoposte.com.br/resultado-do-jogo-do-bicho-deu-no-poste-{date}/"
# Ao buscar/atualizar resultados, relê os últimos 7 dias para absorver
# resultados ausentes e correções recentes publicadas pela fonte.
WEB_RESULT_RECHECK_DAYS = 7

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets"
ANIMAL_ASSET_DIR = ASSET_DIR / "bichos"  # legado/fallback
ANIMAL_PACK_DIR = ASSET_DIR / "bichos_packs"
ANIMAL_PACKS = {
    "Natural": "natural",
    "Cartoon Elegante": "cartoon_elegante",
    "Semi-realista": "semi_realista",
    "Minimalista": "minimalista",
}
ANIMAL_SAMPLE_GROUPS = (1, 2, 16, 19)
ICON_ASSET_DIR = ASSET_DIR / "icons"
LOGO_ASSET_DIR = ASSET_DIR / "logo"

# A partir da v0.17.0 o banco principal não fica preso à pasta da versão.
# No Windows ele vive em %LOCALAPPDATA%\GP-H_Central_Historica\dados.
# Isso permite atualizar/extrair novas versões sem começar com banco vazio.
PORTABLE_DATA_DIR = ROOT / "dados"
PORTABLE_DB_PATH = PORTABLE_DATA_DIR / "gph_historico.db"

_DATA_OVERRIDE = os.environ.get("GPH_DATA_DIR")
_LOCAL_APPDATA = os.environ.get("LOCALAPPDATA")

if _DATA_OVERRIDE:
    DATA_DIR = Path(_DATA_OVERRIDE).expanduser().resolve()
elif _LOCAL_APPDATA:
    DATA_DIR = Path(_LOCAL_APPDATA) / "GP-H_Central_Historica" / "dados"
else:
    # Fallback portátil para ambientes sem LOCALAPPDATA (ex.: testes Linux).
    DATA_DIR = ROOT / "dados_compartilhados"

DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "gph_historico.db"

VISUAL_SETTINGS_PATH = DATA_DIR / "visual_settings.json"
LOG_DIR = DATA_DIR / "logs"
AUTO_BACKUP_DIR = DATA_DIR / "backups_automaticos"
EXPORT_DIR = DATA_DIR / "exportacoes"
ACCOUNT_PROFILE_PATH = DATA_DIR / "account_profile.json"

# Atualizações do programa (separadas da busca de RESULTADOS na internet).
PROGRAM_UPDATE_DIR = DATA_DIR / "atualizacoes_programa"
PROGRAM_UPDATE_DOWNLOAD_DIR = PROGRAM_UPDATE_DIR / "downloads"
PROGRAM_UPDATE_BACKUP_DIR = PROGRAM_UPDATE_DIR / "backups"
PROGRAM_UPDATE_SETTINGS_PATH = PROGRAM_UPDATE_DIR / "settings.json"
PROGRAM_UPDATE_LOG_PATH = PROGRAM_UPDATE_DIR / "GP-H_Update_ultimo.log"
# O endereço oficial pode ser embutido na build via variável de ambiente ou
# configurado uma única vez na própria Central. O cliente aceita qualquer
# hospedagem HTTPS estática; o pacote de publicação usa URLs relativas.
DEFAULT_PROGRAM_UPDATE_MANIFEST_URL = os.environ.get("GPH_UPDATE_MANIFEST_URL", "https://raw.githubusercontent.com/clienteg1603/GP-H-Central-Historica/main/update_manifest.json").strip()
PROGRAM_UPDATE_MAX_MANIFEST_BYTES = 1024 * 1024
PROGRAM_UPDATE_MAX_PACKAGE_BYTES = 600 * 1024 * 1024
PROGRAM_UPDATE_CHANNELS = {"Estável": "stable", "Teste": "test"}
PROGRAM_UPDATE_MAIN_EXE = "GP-H Central Historica.exe"
PROGRAM_UPDATE_UPDATER_EXE = "GP-H_Updater.exe"

for _runtime_dir in (DATA_DIR, LOG_DIR, AUTO_BACKUP_DIR, EXPORT_DIR, PROGRAM_UPDATE_DIR, PROGRAM_UPDATE_DOWNLOAD_DIR, PROGRAM_UPDATE_BACKUP_DIR):
    _runtime_dir.mkdir(parents=True, exist_ok=True)


def _version_key(value):
    """Transforma 0.32.1-beta em tupla comparável sem depender de packaging."""
    nums = [int(x) for x in re.findall(r"\d+", str(value or ""))[:4]]
    while len(nums) < 4:
        nums.append(0)
    return tuple(nums)


def _is_newer_version(candidate, current=APP_VERSION):
    return _version_key(candidate) > _version_key(current)


def _program_update_defaults():
    return {
        "channel": "stable",
        "auto_check": True,
        "manifest_url": DEFAULT_PROGRAM_UPDATE_MANIFEST_URL,
        "server_name": "Servidor oficial" if DEFAULT_PROGRAM_UPDATE_MANIFEST_URL else "Não configurado",
        "last_check_at": None,
        "last_error": None,
        "last_available_version": None,
        "last_installed_version": APP_VERSION,
    }


def load_program_update_settings():
    data = _program_update_defaults()
    try:
        if PROGRAM_UPDATE_SETTINGS_PATH.is_file():
            raw = json.loads(PROGRAM_UPDATE_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
    except Exception:
        pass
    if data.get("channel") not in ("stable", "test"):
        data["channel"] = "stable"
    if not data.get("manifest_url") and DEFAULT_PROGRAM_UPDATE_MANIFEST_URL:
        data["manifest_url"] = DEFAULT_PROGRAM_UPDATE_MANIFEST_URL
    return data


def save_program_update_settings(data):
    current = _program_update_defaults()
    if isinstance(data, dict):
        current.update(data)
    PROGRAM_UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PROGRAM_UPDATE_SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, PROGRAM_UPDATE_SETTINGS_PATH)
    return current


def _sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def _is_local_update_url(url):
    try:
        from urllib.parse import urlparse
        parsed = urlparse(str(url or "").strip())
        host = (parsed.hostname or "").lower()
        return parsed.scheme in ("", "file") or host in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return False


def _validate_update_manifest_url(url):
    url = str(url or "").strip()
    if not url:
        raise ValueError("Servidor de atualização ainda não configurado.")
    if re.match(r"^https://", url, flags=re.I):
        return url
    # HTTP é permitido apenas para o servidor local de testes.
    if re.match(r"^http://", url, flags=re.I) and _is_local_update_url(url):
        return url
    if url.startswith("file://") or not re.match(r"^[a-z]+://", url, flags=re.I):
        return url
    raise ValueError("Por segurança, o servidor remoto de atualização deve usar HTTPS.")


def _fetch_json_url(url, timeout=12):
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


def _resolve_update_url(manifest_url, value):
    value = str(value or "").strip()
    if not value:
        return ""
    if re.match(r"^[a-z]+://", value, flags=re.I):
        return value
    manifest_url = str(manifest_url or "").strip()
    if re.match(r"^https?://", manifest_url, flags=re.I):
        from urllib.parse import urljoin
        return urljoin(manifest_url, value)
    if manifest_url.startswith("file://"):
        from urllib.parse import urlparse, unquote
        base = Path(unquote(urlparse(manifest_url).path)).parent
        return str((base / value).resolve())
    return str((Path(manifest_url).expanduser().resolve().parent / value).resolve())


def _release_from_manifest(manifest, channel="stable", manifest_url=""):
    if int(manifest.get("schema") or 0) != 1:
        raise ValueError("Formato do manifesto de atualização não suportado.")
    if str(manifest.get("app") or "").strip() not in ("", APP_NAME):
        raise ValueError("Manifesto pertence a outro aplicativo.")
    channels = manifest.get("channels") or {}
    release = channels.get(channel)
    if not isinstance(release, dict):
        raise ValueError(f"Canal de atualização '{channel}' não encontrado.")
    version = str(release.get("version") or "").strip()
    package_value = str(release.get("url") or "").strip()
    sha = str(release.get("sha256") or "").strip().lower()
    if not version or not package_value or not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("Release sem versão, URL ou SHA-256 válido.")
    out = dict(release)
    out["version"] = version
    out["url"] = _resolve_update_url(manifest_url, package_value)
    mirrors = []
    for item in release.get("mirrors") or []:
        resolved = _resolve_update_url(manifest_url, item)
        if resolved and resolved not in mirrors and resolved != out["url"]:
            mirrors.append(resolved)
    out["mirrors"] = mirrors
    out["sha256"] = sha
    out["channel"] = channel
    out["server_name"] = str(manifest.get("server_name") or "Servidor GP-H")
    return out


def _download_update_file(urls, destination, timeout=60):
    urls = [str(v).strip() for v in urls if str(v).strip()]
    if not urls:
        raise ValueError("Nenhum endereço de download foi informado.")
    destination = Path(destination)
    last_error = None
    for url in urls:
        try:
            if re.match(r"^https?://", url, flags=re.I):
                if re.match(r"^http://", url, flags=re.I) and not _is_local_update_url(url):
                    raise ValueError("Download remoto sem HTTPS foi bloqueado.")
                req = urllib.request.Request(url, headers={"User-Agent": f"GP-H-Central/{APP_VERSION}"})
                with urllib.request.urlopen(req, timeout=timeout) as resp, destination.open("wb") as out:
                    length = resp.headers.get("Content-Length")
                    if length and int(length) > PROGRAM_UPDATE_MAX_PACKAGE_BYTES:
                        raise ValueError("Pacote de atualização maior que o limite permitido.")
                    total = 0
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > PROGRAM_UPDATE_MAX_PACKAGE_BYTES:
                            raise ValueError("Pacote de atualização maior que o limite permitido.")
                        out.write(chunk)
            elif url.startswith("file://"):
                from urllib.parse import urlparse, unquote
                src = Path(unquote(urlparse(url).path))
                shutil.copy2(src, destination)
            else:
                shutil.copy2(Path(url), destination)
            return url
        except Exception as exc:
            last_error = exc
            try:
                destination.unlink(missing_ok=True)
            except Exception:
                pass
    raise last_error or RuntimeError("Não foi possível baixar a atualização.")

def _read_local_update_package(package_path):
    package_path = Path(package_path)
    with zipfile.ZipFile(package_path, "r") as zf:
        raw = zf.read("update_package.json")
    meta = json.loads(raw.decode("utf-8"))
    if int(meta.get("schema") or 0) != 1:
        raise ValueError("Pacote local de atualização incompatível.")
    if not meta.get("version"):
        raise ValueError("Pacote local sem versão.")
    return meta


THEME_PALETTES = {
    "Noturno Azul": {
        "bg":"#07111F","card":"#101E30","card2":"#0D1A2A","sidebar":"#07101C",
        "text":"#EAF2FA","muted":"#8CA0B4","border":"#23364A","accent":"#2F81F7",
        "accent_hover":"#4897FF","entry":"#0B1827","tree":"#0C1928","selection":"#174B7A",
        "band":"#0A1626","hover":"#13253A","tooltip":"#08111D","divider":"#18283A",
        "success":"#34D399","danger":"#FB7185","warning":"#EAB308"
    },
    "Grafite": {
        "bg":"#111315","card":"#1A1D20","card2":"#16191C","sidebar":"#0C0E10",
        "text":"#F0F2F4","muted":"#9AA1A8","border":"#30363D","accent":"#5B8DEF",
        "accent_hover":"#78A4F5","entry":"#15181B","tree":"#15181B","selection":"#294A70",
        "band":"#121416","hover":"#22272B","tooltip":"#0F1113","divider":"#292D31",
        "success":"#4CC38A","danger":"#E26D7A","warning":"#D7A93E"
    },
    "Esmeralda Escura": {
        "bg":"#071612","card":"#10231D","card2":"#0C1D18","sidebar":"#06110E",
        "text":"#EAF7F2","muted":"#8EAAA0","border":"#24463A","accent":"#2FAE82",
        "accent_hover":"#43C498","entry":"#0A1B16","tree":"#0B1C17","selection":"#17634D",
        "band":"#091713","hover":"#15352B","tooltip":"#07130F","divider":"#1B392F",
        "success":"#48D49B","danger":"#F07A86","warning":"#D6B34D"
    },
    "Vinho Escuro": {
        "bg":"#180B12","card":"#29131F","card2":"#211019","sidebar":"#11080D",
        "text":"#F8ECF2","muted":"#B49AA7","border":"#4B2938","accent":"#B84F78",
        "accent_hover":"#CE638B","entry":"#201018","tree":"#211019","selection":"#71324A",
        "band":"#1B0D14","hover":"#361A28","tooltip":"#14090F","divider":"#402332",
        "success":"#53C98B","danger":"#F07186","warning":"#D3A84B"
    },
    "Claro Profissional": {
        "bg":"#EEF2F6","card":"#FFFFFF","card2":"#F5F7FA","sidebar":"#E3E8EE",
        "text":"#18212B","muted":"#697786","border":"#CAD3DD","accent":"#2F6FDB",
        "accent_hover":"#255FC0","entry":"#FFFFFF","tree":"#FFFFFF","selection":"#CFE0F7",
        "band":"#E9EEF4","hover":"#F3F7FC","tooltip":"#FFFFFF","divider":"#C9D2DB",
        "success":"#198754","danger":"#C84557","warning":"#B8860B"
    },
}

def load_visual_settings():
    try:
        if VISUAL_SETTINGS_PATH.is_file():
            data = json.loads(VISUAL_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

def save_visual_settings(data):
    VISUAL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    VISUAL_SETTINGS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ------------------------------------------------------------------
# Perfil local / identidade multi-PC (v0.26.1)
# ------------------------------------------------------------------
_PROFILE_CODE_RE = re.compile(r"^GPH-[A-Z0-9]{4}-[A-Z0-9]{4}$")
_PROFILE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

def normalize_profile_code(value):
    text = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    if text.startswith("GPH"):
        text = text[3:]
    text = text[:8]
    if len(text) == 8:
        return f"GPH-{text[:4]}-{text[4:]}"
    raw = str(value or "").strip().upper()
    return raw

def valid_profile_code(value):
    return bool(_PROFILE_CODE_RE.fullmatch(normalize_profile_code(value)))

def generate_profile_code():
    token = "".join(secrets.choice(_PROFILE_ALPHABET) for _ in range(8))
    return f"GPH-{token[:4]}-{token[4:]}"

def default_device_name():
    name = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME")
    if not name:
        try:
            name = socket.gethostname()
        except Exception:
            name = "Este computador"
    return str(name).strip() or "Este computador"

def load_account_profile():
    try:
        if ACCOUNT_PROFILE_PATH.is_file():
            data = json.loads(ACCOUNT_PROFILE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and valid_profile_code(data.get("profile_code")):
                data["profile_code"] = normalize_profile_code(data.get("profile_code"))
                data.setdefault("profile_name", "Perfil GP-H")
                data.setdefault("remember_login", True)
                data.setdefault("device_id", str(uuid.uuid4()))
                data.setdefault("device_name", default_device_name())
                data.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
                data.setdefault("linked_at", datetime.now().isoformat(timespec="seconds"))
                data.setdefault("last_login_at", None)
                data.setdefault("sync_status", "not_configured")
                data.setdefault("sync_folder", None)
                data.setdefault("sync_enabled", False)
                data.setdefault("sync_auto", True)
                data.setdefault("last_sync_at", None)
                data.setdefault("sync_last_error", None)
                return data
    except Exception:
        pass
    return None

def save_account_profile(data):
    ACCOUNT_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    clean = dict(data)
    clean["profile_code"] = normalize_profile_code(clean.get("profile_code"))
    ACCOUNT_PROFILE_PATH.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return clean

def build_account_profile(name, code=None, remember_login=True, existing=None):
    name = re.sub(r"\s+", " ", str(name or "").strip())
    if len(name) < 2:
        raise ValueError("Informe um nome com pelo menos 2 caracteres.")
    if len(name) > 60:
        raise ValueError("O nome do perfil pode ter no máximo 60 caracteres.")
    if code is None:
        code = generate_profile_code()
    code = normalize_profile_code(code)
    if not valid_profile_code(code):
        raise ValueError("Código inválido. Use o formato GPH-XXXX-XXXX.")
    now = datetime.now().isoformat(timespec="seconds")
    old = existing if isinstance(existing, dict) else {}
    return {
        "profile_name": name,
        "profile_code": code,
        "remember_login": bool(remember_login),
        "device_id": old.get("device_id") or str(uuid.uuid4()),
        "device_name": old.get("device_name") or default_device_name(),
        "created_at": old.get("created_at") or now,
        "linked_at": old.get("linked_at") or now,
        "last_login_at": now,
        "sync_status": old.get("sync_status") or "not_configured",
        "sync_folder": old.get("sync_folder"),
        "sync_enabled": bool(old.get("sync_enabled", False)),
        "sync_auto": bool(old.get("sync_auto", True)),
        "last_sync_at": old.get("last_sync_at"),
        "sync_last_error": old.get("sync_last_error"),
    }



SYNC_FORMAT_VERSION = 1
SYNC_CONTAINER_NAME = "GP-H_Central_Sync"

def _sync_timestamp(value):
    """Converte timestamp ISO/SQLite em datetime comparável; inválido vira mínimo."""
    if not value:
        return datetime.min
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except Exception:
        try:
            return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.min

def _atomic_write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def account_sync_root(profile):
    folder = (profile or {}).get("sync_folder")
    code = normalize_profile_code((profile or {}).get("profile_code"))
    if not folder or not valid_profile_code(code):
        return None
    return Path(folder).expanduser().resolve() / SYNC_CONTAINER_NAME / code

def account_sync_device_file(profile):
    root = account_sync_root(profile)
    device_id = str((profile or {}).get("device_id") or "").strip()
    if root is None or not device_id:
        return None
    return root / "devices" / f"{device_id}.json"

def discover_previous_database_paths():
    """
    Procura bancos portáteis de versões anteriores próximas à pasta atual.
    Não procura o computador inteiro.
    """
    found = []

    def add(path):
        try:
            path = Path(path).resolve()
        except Exception:
            return
        if path == Path(DB_PATH).resolve():
            return
        if path.is_file() and path.suffix.lower() == ".db" and path not in found:
            found.append(path)

    add(PORTABLE_DB_PATH)

    parent = ROOT.parent
    try:
        for folder in parent.iterdir():
            if not folder.is_dir():
                continue

            name = folder.name.lower()
            if (
                "gph_central_historica" not in name
                and "gp-h_central_historica" not in name
            ):
                continue

            add(folder / "dados" / "gph_historico.db")
            add(folder / "dados_compartilhados" / "gph_historico.db")
    except Exception:
        pass

    return found

BICHOS = {
    1: "AVESTRUZ", 2: "ÁGUIA", 3: "BURRO", 4: "BORBOLETA", 5: "CACHORRO",
    6: "CABRA", 7: "CARNEIRO", 8: "CAMELO", 9: "COBRA", 10: "COELHO",
    11: "CAVALO", 12: "ELEFANTE", 13: "GALO", 14: "GATO", 15: "JACARÉ",
    16: "LEÃO", 17: "MACACO", 18: "PORCO", 19: "PAVÃO", 20: "PERU",
    21: "TOURO", 22: "TIGRE", 23: "URSO", 24: "VEADO", 25: "VACA",
}

BICHO_ICONS = {
    1: "🐦", 2: "🦅", 3: "🫏", 4: "🦋", 5: "🐕",
    6: "🐐", 7: "🐏", 8: "🐪", 9: "🐍", 10: "🐇",
    11: "🐎", 12: "🐘", 13: "🐓", 14: "🐈", 15: "🐊",
    16: "🦁", 17: "🐒", 18: "🐖", 19: "🦚", 20: "🦃",
    21: "🐂", 22: "🐅", 23: "🐻", 24: "🦌", 25: "🐄",
}

SORTEIO_ALIASES = {
    "PPT": "PPT",
    "PTM": "PTM",
    "PT": "PT",
    "PTV": "PTV",
    "PTN": "PTN",
    "FEDERAL": "FEDERAL",
    "CORUJA": "CORUJA",
    "CORUJINHA": "CORUJA",
}


# Cotações por R$ 1,00 informadas pelo usuário.
# A cotação não muda entre 1º e 1º–5º; no 1º–5º o valor do palpite
# é dividido pelas cinco posições, exceto modalidades de colocação fixa.
DEFAULT_QUOTES = {
    "Grupo": 18.0,
    "Dupla de Grupo": 16.0,
    "Terno de Grupo": 150.0,
    "Quadra de Grupo": 1000.0,
    "Quina de Grupo": 5000.0,
    "Duque de Dezena": 300.0,
    "Terno de Dezena": 5000.0,
    "Passe vai": 90.0,
    "Milhar": 6000.0,
    "Centena": 600.0,
    "Dezena": 60.0,
    "Milhar Invertida": 6000.0,
    "Centena Invertida": 600.0,
    "Dezena Invertida": 60.0,
    "Passe vai e vem": 90.0,
}

DEFAULT_MILHAR_CENTENA_QUOTES = {
    "centena": 300.0,
    "milhar": 3000.0,
    "ambos": 3300.0,
}

FIXED_PLACEMENT_MODALITIES = {
    "Dupla de Grupo",
    "Terno de Grupo",
    "Quadra de Grupo",
    "Quina de Grupo",
    "Duque de Dezena",
    "Terno de Dezena",
    "Passe vai",
    "Passe vai e vem",
}

GROUP_COMBO_SIZES = {
    "Dupla de Grupo": 2,
    "Terno de Grupo": 3,
    "Quadra de Grupo": 4,
    "Quina de Grupo": 5,
}

DEZENA_COMBO_SIZES = {
    "Duque de Dezena": 2,
    "Terno de Dezena": 3,
}

PASSE_MODALITIES = {
    "Passe vai",
    "Passe vai e vem",
}

INVERTED_MODALITIES = {
    "Dezena Invertida": ("Dezena", 2),
    "Centena Invertida": ("Centena", 3),
    "Milhar Invertida": ("Milhar", 4),
}

PLAY_METHOD_LABELS = {
    "reset": "Oficial • Reset",
    "three_plus_one": "Oficial • Reset + 3+1",
    "dry": "Especial • Seca do Dia 1º",
    "pull": "Experimental • Puxada Combinada",
    "similarity": "Experimental • Similaridade do Dia",
    "manual": "Manual",
}

METHOD_GUIDE = [
    {
        "name": "GP-H Reset Cobertura v1",
        "status": "OFICIAL — seletor principal dos 5 bichos",
        "base": "Usa a extração operacional mais recente como base e prevê a próxima rodada operacional.",
        "history": "Últimas 240 transições anteriores à base (mínimo 35). Passagens iguais de horário recebem peso 3; no salto sábado Coruja → domingo PT esse peso de contexto é desligado.",
        "does": "Para cada bicho presente na base, mede historicamente quais bichos apareceram na extração seguinte. Respeita repetição/multiplicidade do bicho-base, combina as probabilidades das fontes e ordena os 25 grupos por cobertura esperada.",
        "output": "Entrega o ranking e, no uso oficial, os 5 bichos mais fortes. Não olha resultados posteriores à extração-base.",
        "note": "Configuração congelada: last240 | pull | pair3 | probability.",
    },
    {
        "name": "Puxada Combinada",
        "status": "MODELO DE ANÁLISE / comparação",
        "base": "Usa os 5 bichos da extração-base escolhida.",
        "history": "Usa somente transições anteriores à extração-base. Não tem janela fixa de 240; consulta o histórico disponível antes do corte temporal.",
        "does": "Para cada bicho-base considera o estado ×1, ×2 ou ×3+. Se o estado específico tiver suporte menor que 5, recua para Geral. Cada fonte aponta seus 3 alvos mais fortes; a convergência final prioriza quantidade de fontes, soma das probabilidades e lift.",
        "output": "Ranking de bichos por convergência G5, com detalhes de qual bicho-base indicou cada alvo.",
        "note": "É diferente do Reset: o Reset usa janela last240 e ponderação pair3; a Puxada Combinada usa convergência das tabelas de puxadas por estado.",
    },
    {
        "name": "Oficial • Reset + Histórica",
        "status": "OFICIAL — seleção + geração numérica",
        "base": "O Reset escolhe os bichos a partir da última extração operacional; depois a camada Histórica trabalha somente dentro desses grupos.",
        "history": "Para os números, usa o histórico armazenado na base até o momento da geração. A colocação escolhida no bilhete define se o ranking numérico consulta 1º ou 1º–5º.",
        "does": "Ordena Dezenas, Centenas ou Milhares de cada bicho por frequência; depois usa recência e menor número apenas como desempates técnicos. Distribui a quantidade solicitada entre os bichos selecionados.",
        "output": "Números historicamente mais fortes dentro dos grupos escolhidos pelo Reset.",
        "note": "O Reset escolhe o bicho; a camada Histórica escolhe os números desse bicho.",
    },
    {
        "name": "Oficial • Reset + 3+1",
        "status": "OFICIAL — 20 Centenas",
        "base": "O Reset escolhe exatamente 5 bichos. O sorteio imediatamente anterior é usado para a regra de congelamento da dezena principal.",
        "history": "A lógica interna 3+1 ranqueia as quatro dezenas e as Centenas pelo histórico 1º–5º. Essa definição interna permanece fixa mesmo que você escolha apostar o bilhete em 1º ou 1º–5º.",
        "does": "Para cada bicho: normalmente usa 3 Centenas da dezena principal + 1 da segunda. Se a principal apareceu no sorteio anterior, ela descansa uma rodada e passa a usar 3 da segunda + 1 da terceira.",
        "output": "4 Centenas por bicho × 5 bichos = 20 Centenas.",
        "note": "A colocação do bilhete agora é livre; isso não muda silenciosamente a fórmula interna do 3+1.",
    },
    {
        "name": "Oficial • Reset combinações",
        "status": "OFICIAL — modalidades combinadas",
        "base": "O Reset fornece o núcleo de grupos da próxima rodada.",
        "history": "A força preditiva vem do Reset. Para Duque/Terno de Dezena, as dezenas dentro dos grupos ainda são ordenadas por frequência histórica.",
        "does": "Monta Dupla/Terno/Quadra/Quina de Grupo, Passe e combinações de Dezenas a partir dos bichos selecionados, sem introduzir um segundo seletor de animais.",
        "output": "Combinações prontas respeitando o tamanho exigido por cada modalidade.",
        "note": "Modalidades que possuem colocação fixa por regra própria continuam fixas; isso não é trava de método.",
    },
    {
        "name": "Experimental • Similaridade do Dia",
        "status": "EXPERIMENTAL / SOMBRA",
        "base": "Usa todas as extrações já ocorridas no dia corrente até a extração-base.",
        "history": "Compara esse prefixo com dias históricos anteriores que tenham os mesmos horários; nunca usa dias posteriores à base.",
        "does": "Score congelado: 45% mesmo bicho na mesma posição/horário, 30% mesmo bicho no mesmo horário fora da posição, 15% sobreposição do dia, 5% padrão de repetição e 5% mesmo dia da semana.",
        "output": "Localiza os dias mais parecidos e agrega, ponderadamente, os bichos do sorteio seguinte desses dias.",
        "note": "O percentual é índice de similaridade, não probabilidade de acerto. Permanece separado do método oficial.",
    },
    {
        "name": "Experimental • Similaridade combinações",
        "status": "EXPERIMENTAL — combinações",
        "base": "Usa os bichos produzidos pela Similaridade do Dia.",
        "history": "Mesma base histórica e mesmo corte temporal da Similaridade do Dia.",
        "does": "Depois de obter os bichos-sombra, apenas monta as combinações correspondentes à modalidade escolhida.",
        "output": "Duplas, Ternos, Quadras, Quinas, Passe ou combinações de Dezenas em modo experimental.",
        "note": "Não entra no desempenho oficial do Reset.",
    },
    {
        "name": "Especial • Seca do Dia 1º",
        "status": "ESPECIAL — modelo diário baseado em 1º prêmio",
        "base": "Para uma rodada-alvo, usa como dia-base o dia anterior ao alvo. Dentro desse dia considera somente os bichos que saíram em 1º prêmio.",
        "history": "Constrói relações dia → próximo dia disponível usando apenas 1º prêmios e apenas transições encerradas até o próprio dia-base.",
        "does": "Cada bicho-fonte do dia-base aponta seus alvos históricos mais fortes; o ranking final combina nº de indicações, fontes distintas, probabilidades e lifts. Na geração numérica, Centenas/Milhares também são ranqueadas somente pelo histórico de 1º prêmio até o dia-base.",
        "output": "Bichos e números para Centena ou Milhar. A colocação do bilhete agora pode ser 1º ou 1º–5º, mas o cálculo da Seca continua sendo de 1º prêmio.",
        "note": "O nome '1º' descreve a fonte estatística do método, não uma trava de colocação da aposta.",
    },
    {
        "name": "Manual",
        "status": "MANUAL — sem seleção GP-H",
        "base": "Não usa método para escolher números.",
        "history": "Nenhuma consulta histórica é necessária para a seleção.",
        "does": "Você escolhe modalidade, colocação, números e valor. A Central apenas valida, organiza, registra o Bilhete e depois audita o resultado.",
        "output": "Bilhete real com números escolhidos por você.",
        "note": "Continua participando do financeiro e da auditoria, mas não deve ser confundido com desempenho de método preditivo.",
    },
]


DEFAULT_HOURS = {
    "PPT": "09:00",
    "PTM": "11:00",
    "PT": "14:00",
    "PTV": "16:00",
    "PTN": "18:00",
    "FEDERAL": "20:00",
    "CORUJA": "21:00",
}


def sem_acento(txt: str) -> str:
    txt = unicodedata.normalize("NFD", txt or "")
    return "".join(c for c in txt if unicodedata.category(c) != "Mn").upper().strip()


BICHOS_NORMALIZADOS = {g: sem_acento(n) for g, n in BICHOS.items()}


def grupo_da_dezena(dezena: int) -> int:
    return (((int(dezena) - 1) % 100) // 4) + 1


def derivados_milhar(milhar: str):
    digits = re.sub(r"\D", "", str(milhar))
    if not digits:
        raise ValueError("Milhar vazia.")
    digits = digits[-4:].zfill(4)
    centena = digits[-3:]
    dezena = digits[-2:]
    grupo = grupo_da_dezena(int(dezena))
    bicho = BICHOS[grupo]
    return digits, centena, dezena, grupo, bicho


class TextExtractor(HTMLParser):
    """Extrai texto mantendo blocos em linhas para facilitar o parser."""
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data and data.strip():
            self.parts.append(html.unescape(data).strip())

    def lines(self):
        out = []
        for part in self.parts:
            for line in re.split(r"[\r\n]+", part):
                line = re.sub(r"\s+", " ", line).strip()
                if line:
                    out.append(line)
        return out


HEADING_RE = re.compile(
    r"\b(PPT|PTM|PTV|PTN|PT|FEDERAL|CORUJA|CORUJINHA)\b.*?\bdas?\s+(\d{1,2}:\d{2})",
    re.I,
)

PRIZE_RE = re.compile(
    r"^\s*([1-5])\s*[°ºoª]?\s*=?\s*(\d{1,4})\s*[–—-]\s*(\d{1,2})\s+(.+?)\s*$",
    re.I,
)


@dataclass
class PrizeRow:
    data: str
    dia_semana: str
    sorteio: str
    hora: str
    premio: int
    milhar: str
    centena: str
    dezena: str
    grupo: int
    bicho: str
    fonte: str
    grupo_publicado: int | None = None
    bicho_publicado: str | None = None


def parse_daily_html(raw_html: str, day: date, fonte: str) -> list[PrizeRow]:
    parser = TextExtractor()
    parser.feed(raw_html)

    current_sorteio = None
    current_hora = None
    rows: list[PrizeRow] = []

    for line in parser.lines():
        h = HEADING_RE.search(line)
        if h:
            current_sorteio = SORTEIO_ALIASES.get(h.group(1).upper(), h.group(1).upper())
            current_hora = h.group(2).zfill(5)
            continue

        m = PRIZE_RE.match(line)
        if not m or not current_sorteio or not current_hora:
            continue

        premio = int(m.group(1))
        milhar_raw = m.group(2)
        grupo_pub = int(m.group(3))
        bicho_pub = m.group(4).strip()

        milhar, centena, dezena, grupo_calc, bicho_calc = derivados_milhar(milhar_raw)

        rows.append(
            PrizeRow(
                data=day.isoformat(),
                dia_semana=day.strftime("%A"),
                sorteio=current_sorteio,
                hora=current_hora,
                premio=premio,
                milhar=milhar,
                centena=centena,
                dezena=dezena,
                grupo=grupo_calc,
                bicho=bicho_calc,
                fonte=fonte,
                grupo_publicado=grupo_pub,
                bicho_publicado=bicho_pub,
            )
        )
    return rows


def fetch_day(day: date, timeout=18) -> tuple[str, list[PrizeRow]]:
    url = BASE_URL.format(date=day.strftime("%d-%m-%Y"))
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GP-H-Central/0.1",
            "Accept-Language": "pt-BR,pt;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        raw = content.decode(charset, errors="replace")
    return url, parse_daily_html(raw, day, url)


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.init_schema()

    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def init_schema(self):
        with self.connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS resultados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT NOT NULL,
                    dia_semana TEXT,
                    sorteio TEXT NOT NULL,
                    hora TEXT NOT NULL,
                    premio INTEGER NOT NULL CHECK(premio BETWEEN 1 AND 5),
                    milhar TEXT NOT NULL,
                    centena TEXT NOT NULL,
                    dezena TEXT NOT NULL,
                    grupo INTEGER NOT NULL CHECK(grupo BETWEEN 1 AND 25),
                    bicho TEXT NOT NULL,
                    fonte TEXT,
                    grupo_publicado INTEGER,
                    bicho_publicado TEXT,
                    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(data, sorteio, hora, premio)
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_data ON resultados(data)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_sorteio_hora ON resultados(sorteio, hora)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_milhar ON resultados(milhar)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_centena ON resultados(centena)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_dezena ON resultados(dezena)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_grupo ON resultados(grupo)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_bicho ON resultados(bicho)")
            con.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    chave TEXT PRIMARY KEY,
                    valor TEXT
                )
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS jogos_congelados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    seletor TEXT NOT NULL DEFAULT 'Não registrado',
                    estrategia TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    escopo TEXT NOT NULL,
                    base_data TEXT,
                    base_sorteio TEXT,
                    base_hora TEXT,
                    alvo_modo TEXT NOT NULL,
                    alvo_data TEXT,
                    alvo_sorteio TEXT,
                    alvo_hora TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDENTE',
                    acertos INTEGER NOT NULL DEFAULT 0,
                    total_itens INTEGER NOT NULL DEFAULT 0,
                    auditado_em TEXT,
                    observacao TEXT
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS jogos_itens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    jogo_id INTEGER NOT NULL,
                    ordem INTEGER NOT NULL,
                    grupo INTEGER,
                    bicho TEXT,
                    numero TEXT NOT NULL,
                    dezena_base TEXT,
                    regra TEXT,
                    acertou INTEGER NOT NULL DEFAULT 0,
                    acerto_data TEXT,
                    acerto_sorteio TEXT,
                    acerto_hora TEXT,
                    acerto_premio INTEGER,
                    acerto_milhar TEXT,
                    FOREIGN KEY(jogo_id) REFERENCES jogos_congelados(id)
                        ON DELETE CASCADE
                )
            """)
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_jogos_status "
                "ON jogos_congelados(status)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_jogos_base_data "
                "ON jogos_congelados(base_data)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_jogos_itens_jogo "
                "ON jogos_itens(jogo_id)"
            )


            # Migração v0.16.0: preserva bancos criados nas versões anteriores.
            game_columns = {
                r["name"]
                for r in con.execute(
                    "PRAGMA table_info(jogos_congelados)"
                ).fetchall()
            }

            if "seletor" not in game_columns:
                con.execute(
                    "ALTER TABLE jogos_congelados "
                    "ADD COLUMN seletor TEXT "
                    "NOT NULL DEFAULT 'Não registrado'"
                )

            financial_columns = {
                "jogado": "INTEGER NOT NULL DEFAULT 0",
                "jogado_em": "TEXT",
                "valor_unitario": "REAL",
                "valor_total": "REAL",
                "multiplicador": "REAL",
                "retorno_min": "REAL",
                "retorno_max": "REAL",
                "retorno_real": "REAL",
                "resultado_liquido": "REAL",
            }

            for col, spec in financial_columns.items():
                if col not in game_columns:
                    con.execute(
                        f"ALTER TABLE jogos_congelados "
                        f"ADD COLUMN {col} {spec}"
                    )

            v20_columns = {
                "submodalidade": "TEXT",
                "divisor_posicoes": "INTEGER",
                "valor_posicao": "REAL",
                "cotacao_primaria": "REAL",
                "cotacao_secundaria": "REAL",
                "cotacao_combinada": "REAL",
                "acertos_financeiros": "INTEGER NOT NULL DEFAULT 0",
            }

            for col, spec in v20_columns.items():
                if col not in game_columns:
                    con.execute(
                        f"ALTER TABLE jogos_congelados "
                        f"ADD COLUMN {col} {spec}"
                    )

            v21_columns = {
                "origem_jogada": "TEXT",
                "editado_em": "TEXT",
            }

            for col, spec in v21_columns.items():
                if col not in game_columns:
                    con.execute(
                        f"ALTER TABLE jogos_congelados "
                        f"ADD COLUMN {col} {spec}"
                    )

            v22_columns = {
                "bilhete_id": "INTEGER",
            }

            for col, spec in v22_columns.items():
                if col not in game_columns:
                    con.execute(
                        f"ALTER TABLE jogos_congelados "
                        f"ADD COLUMN {col} {spec}"
                    )

            con.execute("""
                CREATE TABLE IF NOT EXISTS bilhetes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    alvo_data TEXT NOT NULL,
                    alvo_sorteio TEXT,
                    alvo_hora TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDENTE',
                    total_apostado REAL NOT NULL DEFAULT 0,
                    retorno_real REAL NOT NULL DEFAULT 0,
                    resultado_liquido REAL NOT NULL DEFAULT 0,
                    observacao TEXT
                )
            """)

            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_bilhetes_alvo "
                "ON bilhetes(alvo_data, alvo_sorteio, alvo_hora)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_jogos_bilhete "
                "ON jogos_congelados(bilhete_id)"
            )

            # v0.26.1: identidade estável dos registros para sincronização multi-PC.
            for table in ("bilhetes", "jogos_congelados"):
                cols = {
                    r["name"]
                    for r in con.execute(f"PRAGMA table_info({table})").fetchall()
                }
                if "sync_uid" not in cols:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN sync_uid TEXT")
                if "sync_updated_at" not in cols:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN sync_updated_at TEXT")

                # Registros antigos passam a ter ID estável sem alterar seu ID local.
                con.execute(
                    f"UPDATE {table} SET sync_uid=lower(hex(randomblob(16))) "
                    "WHERE sync_uid IS NULL OR TRIM(sync_uid)=''"
                )
                time_col = "criado_em"
                con.execute(
                    f"UPDATE {table} SET sync_updated_at=COALESCE(sync_updated_at, {time_col}, CURRENT_TIMESTAMP) "
                    "WHERE sync_updated_at IS NULL OR TRIM(sync_updated_at)=''"
                )

            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_bilhetes_sync_uid ON bilhetes(sync_uid)"
            )
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_jogos_sync_uid ON jogos_congelados(sync_uid)"
            )

            # Os triggers marcam qualquer alteração local. Durante importação remota,
            # sync_updated_at é enviado explicitamente e, portanto, não é sobrescrito.
            con.executescript("""
                CREATE TRIGGER IF NOT EXISTS trg_bilhetes_sync_insert
                AFTER INSERT ON bilhetes
                WHEN NEW.sync_uid IS NULL OR NEW.sync_updated_at IS NULL
                BEGIN
                    UPDATE bilhetes
                    SET sync_uid=COALESCE(NEW.sync_uid, lower(hex(randomblob(16)))),
                        sync_updated_at=COALESCE(NEW.sync_updated_at, strftime('%Y-%m-%dT%H:%M:%f','now'))
                    WHERE id=NEW.id;
                END;

                CREATE TRIGGER IF NOT EXISTS trg_bilhetes_sync_update
                AFTER UPDATE ON bilhetes
                WHEN NEW.sync_updated_at IS OLD.sync_updated_at
                BEGIN
                    UPDATE bilhetes
                    SET sync_updated_at=strftime('%Y-%m-%dT%H:%M:%f','now')
                    WHERE id=NEW.id;
                END;

                CREATE TRIGGER IF NOT EXISTS trg_jogos_sync_insert
                AFTER INSERT ON jogos_congelados
                WHEN NEW.sync_uid IS NULL OR NEW.sync_updated_at IS NULL
                BEGIN
                    UPDATE jogos_congelados
                    SET sync_uid=COALESCE(NEW.sync_uid, lower(hex(randomblob(16)))),
                        sync_updated_at=COALESCE(NEW.sync_updated_at, strftime('%Y-%m-%dT%H:%M:%f','now'))
                    WHERE id=NEW.id;
                END;

                CREATE TRIGGER IF NOT EXISTS trg_jogos_sync_update
                AFTER UPDATE ON jogos_congelados
                WHEN NEW.sync_updated_at IS OLD.sync_updated_at
                BEGIN
                    UPDATE jogos_congelados
                    SET sync_updated_at=strftime('%Y-%m-%dT%H:%M:%f','now')
                    WHERE id=NEW.id;
                END;
            """)

            for modality, quote in DEFAULT_QUOTES.items():
                con.execute(
                    "INSERT OR IGNORE INTO meta(chave, valor) VALUES(?, ?)",
                    (
                        "quote_" + sem_acento(modality).lower().replace(" ", "_"),
                        str(float(quote)),
                    ),
                )

            for component, quote in DEFAULT_MILHAR_CENTENA_QUOTES.items():
                con.execute(
                    "INSERT OR IGNORE INTO meta(chave, valor) VALUES(?, ?)",
                    (
                        f"quote_milhar_centena_{component}",
                        str(float(quote)),
                    ),
                )

            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_jogos_jogado "
                "ON jogos_congelados(jogado)"
            )

            # A Seca possui seletor interno conhecido e pode ser recuperada
            # com segurança nos registros antigos.
            con.execute("""
                UPDATE jogos_congelados
                SET seletor='Seca do Dia 1º'
                WHERE estrategia='Seca do Dia 1º'
                  AND (
                    seletor IS NULL
                    OR TRIM(seletor)=''
                    OR seletor='Não registrado'
                  )
            """)

            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_jogos_seletor "
                "ON jogos_congelados(seletor)"
            )


            # v0.27.0 — Central de Decisão / congelamento prospectivo.
            # Uma leitura é salva ANTES do resultado e nunca recalculada retroativamente.
            con.execute("""
                CREATE TABLE IF NOT EXISTS decision_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    base_data TEXT NOT NULL,
                    base_sorteio TEXT NOT NULL,
                    base_hora TEXT NOT NULL,
                    target_data TEXT NOT NULL,
                    target_sorteio TEXT NOT NULL,
                    target_hora TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDENTE',
                    confidence_score REAL NOT NULL DEFAULT 0,
                    confidence_label TEXT,
                    recommendation TEXT,
                    components_json TEXT NOT NULL DEFAULT '{}',
                    signals_json TEXT NOT NULL DEFAULT '{}',
                    result_groups_json TEXT,
                    audited_at TEXT,
                    note TEXT,
                    UNIQUE(base_data, base_sorteio, base_hora, target_data, target_sorteio, target_hora)
                )
            """)
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_decision_target "
                "ON decision_snapshots(target_data,target_sorteio,target_hora)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_decision_status "
                "ON decision_snapshots(status)"
            )

            # v0.30.0 — Laboratório Sombra.
            # Jogos/leitura são congelados antes do resultado e nunca aparecem
            # como "se tivesse jogado"; servem somente para recomendação futura.
            con.execute("""
                CREATE TABLE IF NOT EXISTS shadow_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    base_data TEXT NOT NULL,
                    base_sorteio TEXT NOT NULL,
                    base_hora TEXT NOT NULL,
                    target_data TEXT NOT NULL,
                    target_sorteio TEXT NOT NULL,
                    target_hora TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDENTE',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT,
                    audited_at TEXT,
                    trigger TEXT,
                    note TEXT,
                    UNIQUE(base_data,base_sorteio,base_hora,target_data,target_sorteio,target_hora)
                )
            """)
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_shadow_target "
                "ON shadow_snapshots(target_data,target_sorteio,target_hora)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_shadow_status "
                "ON shadow_snapshots(status)"
            )

    # ========================================================
    # CENTRAL DE DECISÃO v0.27.0
    # Congelamento prospectivo + índice de consistência dos sinais.
    # O índice NÃO é probabilidade de acerto.
    # ========================================================
    @staticmethod
    def _decision_clip(value, low=0.0, high=100.0):
        return max(float(low), min(float(high), float(value)))

    @staticmethod
    def _decision_signal_payload(result, kind):
        if not result:
            return {"available": False, "groups": [], "animals": [], "kind": kind}
        selected = result.get("selected") or []
        groups = [int(r["grupo"]) for r in selected if r.get("grupo")]
        payload = {
            "available": bool(groups),
            "groups": groups,
            "animals": [BICHOS.get(g, str(g)) for g in groups],
            "kind": kind,
        }
        if kind == "reset":
            payload["scores"] = [round(float(r.get("score_pct") or 0), 6) for r in selected]
            payload["training_transitions"] = int(result.get("training_transitions") or 0)
            payload["pair3_matches"] = int(result.get("pair3_matches") or 0)
            payload["context_mode"] = result.get("context_mode")
        elif kind == "pull":
            payload["source_counts"] = [int(r.get("source_count") or 0) for r in selected]
            payload["sum_prob"] = [round(float(r.get("sum_prob") or 0), 6) for r in selected]
        elif kind == "similarity":
            payload["weighted_shares"] = [round(float(r.get("weighted_share") or 0), 6) for r in selected]
            payload["candidate_count"] = int(result.get("candidate_count") or 0)
            payload["top_days"] = [
                {"date": d.get("date"), "score": round(float(d.get("score") or 0), 6)}
                for d in (result.get("top_days") or [])[:5]
            ]
            payload["positional"] = True
        return payload

    @staticmethod
    def _decision_weekday_label(day_iso):
        names = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
        try:
            return names[datetime.strptime(str(day_iso), "%Y-%m-%d").weekday()]
        except Exception:
            return "—"

    def _decision_audited_rows(self, window=None, target_hour=None, weekday=None):
        """Retorna snapshots auditados, aplicando filtros antes da janela."""
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM decision_snapshots WHERE status='AUDITADO' "
                "ORDER BY target_data DESC, target_hora DESC, id DESC"
            ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            if target_hour and str(d.get("target_hora") or "") != str(target_hour):
                continue
            if weekday and self._decision_weekday_label(d.get("target_data")) != str(weekday):
                continue
            out.append(d)
        if window not in (None, "all", "Todos"):
            try:
                out = out[:max(1, int(window))]
            except Exception:
                pass
        return out

    @staticmethod
    def _decision_performance_from_rows(rows):
        accum = {}
        for row in rows:
            try:
                signals = json.loads(row.get("signals_json") or "{}")
            except Exception:
                signals = {}
            for name, sig in signals.items():
                if not sig.get("available"):
                    continue
                a = accum.setdefault(name, {
                    "method": name, "rounds": 0, "coverage_hits": 0,
                    "rounds_2plus": 0, "rounds_3plus": 0,
                    "position_hits": 0, "position_rounds": 0,
                })
                hits = int(sig.get("coverage_hits") or 0)
                a["rounds"] += 1
                a["coverage_hits"] += hits
                a["rounds_2plus"] += int(hits >= 2)
                a["rounds_3plus"] += int(hits >= 3)
                if sig.get("position_hits") is not None:
                    a["position_hits"] += int(sig.get("position_hits") or 0)
                    a["position_rounds"] += 1
        out = []
        for a in accum.values():
            rounds = max(1, a["rounds"])
            a["avg_coverage"] = a["coverage_hits"] / rounds
            a["pct_2plus"] = a["rounds_2plus"] / rounds * 100.0
            a["pct_3plus"] = a["rounds_3plus"] / rounds * 100.0
            a["avg_position"] = (
                a["position_hits"] / a["position_rounds"]
                if a["position_rounds"] else None
            )
            out.append(a)
        out.sort(key=lambda r: (-r["avg_coverage"], -r["pct_2plus"], r["method"]))
        return out

    def decision_method_performance(self, window=30, target_hour=None, weekday=None):
        """Compara apenas previsões realmente congeladas antes do resultado."""
        rows = self._decision_audited_rows(window=window, target_hour=target_hour, weekday=weekday)
        return {
            "window": window,
            "target_hour": target_hour,
            "weekday": weekday,
            "audited_snapshots": len(rows),
            "rows": self._decision_performance_from_rows(rows),
        }

    def decision_performance_by_hour(self, window=120):
        rows = self._decision_audited_rows(window=window)
        buckets = {}
        for row in rows:
            buckets.setdefault(str(row.get("target_hora") or "—"), []).append(row)
        out=[]
        for hour, bucket in sorted(buckets.items()):
            perf={r["method"]:r for r in self._decision_performance_from_rows(bucket)}
            out.append({"label":hour, "rounds":len(bucket), "methods":perf})
        return {"window":window, "rows":out}

    def decision_performance_by_weekday(self, window=120):
        rows = self._decision_audited_rows(window=window)
        order=("Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo")
        buckets={name:[] for name in order}
        for row in rows:
            buckets.setdefault(self._decision_weekday_label(row.get("target_data")), []).append(row)
        out=[]
        for label in order:
            bucket=buckets.get(label) or []
            if not bucket:
                continue
            perf={r["method"]:r for r in self._decision_performance_from_rows(bucket)}
            out.append({"label":label, "rounds":len(bucket), "methods":perf})
        return {"window":window, "rows":out}

    @staticmethod
    def _decision_metrics_for_signal_list(values):
        n=len(values)
        if not n:
            return {"rounds":0,"avg_coverage":0.0,"pct_2plus":0.0,"pct_3plus":0.0}
        return {
            "rounds":n,
            "avg_coverage":sum(values)/n,
            "pct_2plus":sum(v>=2 for v in values)/n*100.0,
            "pct_3plus":sum(v>=3 for v in values)/n*100.0,
        }

    def decision_champion_challenger(self, window=60, min_rounds=12):
        """Compara desafiante e Reset nas MESMAS rodadas. Nunca promove automaticamente."""
        rows=self._decision_audited_rows(window=window)
        champion="Reset Cobertura"
        candidates=("Puxada Combinada","Similaridade")
        comparisons=[]
        for challenger in candidates:
            champ_hits=[]
            chal_hits=[]
            for row in rows:
                try:
                    signals=json.loads(row.get("signals_json") or "{}")
                except Exception:
                    continue
                cs=signals.get(champion) or {}
                ds=signals.get(challenger) or {}
                if not cs.get("available") or not ds.get("available"):
                    continue
                if cs.get("coverage_hits") is None or ds.get("coverage_hits") is None:
                    continue
                champ_hits.append(int(cs.get("coverage_hits") or 0))
                chal_hits.append(int(ds.get("coverage_hits") or 0))
            cm=self._decision_metrics_for_signal_list(champ_hits)
            dm=self._decision_metrics_for_signal_list(chal_hits)
            comparisons.append({
                "challenger":challenger, "paired_rounds":len(champ_hits),
                "champion":cm, "challenger_metrics":dm,
                "avg_diff":dm["avg_coverage"]-cm["avg_coverage"],
                "p2_diff":dm["pct_2plus"]-cm["pct_2plus"],
                "p3_diff":dm["pct_3plus"]-cm["pct_3plus"],
            })
        comparisons.sort(key=lambda x:(x["avg_diff"],x["p2_diff"],x["p3_diff"],x["paired_rounds"]), reverse=True)
        best=comparisons[0] if comparisons else None
        if not best or best["paired_rounds"] < int(min_rounds):
            status="AMOSTRA INSUFICIENTE"
            recommendation=f"Manter {champion} oficial; acumular pelo menos {int(min_rounds)} confrontos pareados."
        elif best["avg_diff"] >= 0.20 and best["p2_diff"] >= 0 and best["p3_diff"] >= -5:
            status="CANDIDATO FORTE"
            recommendation="Desafiante mostrou vantagem consistente. Manter em sombra e exigir confirmação antes de qualquer promoção manual."
        elif best["avg_diff"] >= 0.05 or best["p2_diff"] >= 5:
            status="DESAFIANTE EM OBSERVAÇÃO"
            recommendation="Há sinal de vantagem, mas ainda não é suficiente para trocar o método oficial."
        else:
            status="CAMPEÃO ESTÁVEL"
            recommendation=f"{champion} segue sem evidência suficiente para ser substituído."
        return {
            "window":window, "official_champion":champion, "best":best,
            "comparisons":comparisons, "status":status, "recommendation":recommendation,
            "min_rounds":int(min_rounds),
        }

    def decision_change_detection(self, recent_window=12, baseline_window=30):
        """Detector simples de mudança: compara bloco recente com bloco anterior."""
        rows=self._decision_audited_rows(window="Todos")
        methods=("Reset Cobertura","Puxada Combinada","Similaridade")
        out=[]
        for method in methods:
            values=[]
            for row in rows:
                try:
                    sig=(json.loads(row.get("signals_json") or "{}").get(method) or {})
                except Exception:
                    continue
                if sig.get("available") and sig.get("coverage_hits") is not None:
                    values.append(int(sig.get("coverage_hits") or 0))
            recent=values[:int(recent_window)]
            baseline=values[int(recent_window):int(recent_window)+int(baseline_window)]
            rm=self._decision_metrics_for_signal_list(recent)
            bm=self._decision_metrics_for_signal_list(baseline)
            avg_delta=rm["avg_coverage"]-bm["avg_coverage"] if baseline else 0.0
            p2_delta=rm["pct_2plus"]-bm["pct_2plus"] if baseline else 0.0
            if len(recent)<6 or len(baseline)<12:
                status="AMOSTRA INSUFICIENTE"
            elif avg_delta <= -0.50 or (avg_delta <= -0.30 and p2_delta <= -15):
                status="QUEDA FORTE"
            elif avg_delta <= -0.25 or p2_delta <= -12:
                status="ATENÇÃO"
            elif avg_delta >= 0.25 and p2_delta >= 10:
                status="MELHORA"
            else:
                status="ESTÁVEL"
            out.append({
                "method":method, "status":status,
                "recent_rounds":len(recent), "baseline_rounds":len(baseline),
                "recent_avg":rm["avg_coverage"], "baseline_avg":bm["avg_coverage"],
                "avg_delta":avg_delta, "recent_p2":rm["pct_2plus"],
                "baseline_p2":bm["pct_2plus"], "p2_delta":p2_delta,
            })
        priority={"QUEDA FORTE":0,"ATENÇÃO":1,"AMOSTRA INSUFICIENTE":2,"ESTÁVEL":3,"MELHORA":4}
        out.sort(key=lambda r:(priority.get(r["status"],9),r["method"]))
        return {"recent_window":recent_window,"baseline_window":baseline_window,"rows":out}

    @staticmethod
    def _decision_groups_from_item(game, item):
        if item.get("grupo") not in (None, ""):
            try:
                return [int(item["grupo"])]
            except Exception:
                pass
        kind=str(game.get("tipo") or "")
        tokens=[int(x) for x in re.findall(r"\d+", str(item.get("numero") or ""))]
        groups=[]
        if "Grupo" in kind or kind.startswith("Passe"):
            groups=[x for x in tokens if 1 <= x <= 25]
        else:
            for token in tokens:
                try:
                    groups.append(int(grupo_da_dezena(token % 100)))
                except Exception:
                    pass
        return groups

    def decision_concentration_from_generation(self, generation):
        generation=generation or {}
        rows=generation.get("rows") or []
        game={"tipo":generation.get("kind") or "Centena"}
        counter=Counter()
        for row in rows:
            for group in self._decision_groups_from_item(game,row):
                if 1 <= int(group) <= 25:
                    counter[int(group)] += 1
        total=sum(counter.values())
        if not total:
            return {"games":0,"items":len(rows),"group_mentions":0,"score":0.0,"label":"SEM LEITURA","top":[],"effective_groups":0.0,"top2_share":0.0}
        shares={g:c/total for g,c in counter.items()}
        hhi=sum(v*v for v in shares.values())
        effective=1.0/hhi if hhi else 0.0
        ordered=sorted(counter.items(), key=lambda kv:(-kv[1],kv[0]))
        top=[{"grupo":g,"bicho":BICHOS.get(g,str(g)),"count":c,"share":shares[g]*100.0} for g,c in ordered[:5]]
        top1=top[0]["share"] if top else 0.0
        top2=sum(r["share"] for r in top[:2])
        hhi_scaled=self._decision_clip((hhi-0.04)/(1.0-0.04)*100.0)
        score=round(self._decision_clip(0.70*top2 + 0.30*hhi_scaled),1)
        if top1 >= 45 or top2 >= 70 or score >= 65:
            label="ALTA"
        elif top1 >= 35 or top2 >= 55 or score >= 50:
            label="MODERADA"
        else:
            label="BAIXA"
        return {"games":1,"items":len(rows),"group_mentions":total,"score":score,"label":label,"top":top,"top1_share":top1,"top2_share":top2,"effective_groups":effective}

    def decision_bet_concentration(self, target_data=None, target_sorteio=None, target_hora=None):
        """Mede concentração dos jogos congelados para uma rodada-alvo."""
        if not target_data:
            snap=self.latest_decision_snapshot()
            if snap:
                target_data,target_sorteio,target_hora=(snap.get("target_data"),snap.get("target_sorteio"),snap.get("target_hora"))
        if not target_data:
            return {"games":0,"items":0,"group_mentions":0,"score":0.0,"label":"SEM JOGOS","top":[],"effective_groups":0.0}
        with self.connect() as con:
            games=con.execute(
                "SELECT * FROM jogos_congelados WHERE alvo_data=? AND COALESCE(alvo_sorteio,'')=COALESCE(?, '') AND COALESCE(alvo_hora,'')=COALESCE(?, '') ORDER BY id",
                (target_data,target_sorteio,target_hora),
            ).fetchall()
            counter=Counter()
            items_count=0
            for grow in games:
                game=dict(grow)
                items=con.execute("SELECT * FROM jogos_itens WHERE jogo_id=? ORDER BY ordem",(int(game["id"]),)).fetchall()
                for irow in items:
                    items_count += 1
                    for group in self._decision_groups_from_item(game,dict(irow)):
                        if 1 <= int(group) <= 25:
                            counter[int(group)] += 1
        total=sum(counter.values())
        if not total:
            return {"games":len(games),"items":items_count,"group_mentions":0,"score":0.0,"label":"SEM LEITURA","top":[],"effective_groups":0.0}
        shares={g:c/total for g,c in counter.items()}
        hhi=sum(v*v for v in shares.values())
        effective=1.0/hhi if hhi else 0.0
        ordered=sorted(counter.items(), key=lambda kv:(-kv[1],kv[0]))
        top=[]
        for g,c in ordered[:5]:
            top.append({"grupo":g,"bicho":BICHOS.get(g,str(g)),"count":c,"share":shares[g]*100.0})
        top1=top[0]["share"] if top else 0.0
        top2=sum(r["share"] for r in top[:2])
        # score combina dependência dos dois líderes com a concentração global (HHI).
        hhi_scaled=self._decision_clip((hhi-0.04)/(1.0-0.04)*100.0)
        score=round(self._decision_clip(0.70*top2 + 0.30*hhi_scaled),1)
        if top1 >= 45 or top2 >= 70 or score >= 65:
            label="ALTA"
        elif top1 >= 35 or top2 >= 55 or score >= 50:
            label="MODERADA"
        else:
            label="BAIXA"
        return {
            "games":len(games),"items":items_count,"group_mentions":total,
            "score":score,"label":label,"top":top,"top1_share":top1,
            "top2_share":top2,"effective_groups":effective,
            "target":{"data":target_data,"sorteio":target_sorteio,"hora":target_hora},
        }

    @staticmethod
    def _walk_forward_metric_summary(records):
        """Resume registros de um método sem misturar rodadas indisponíveis."""
        valid=[r for r in records if r.get("available")]
        n=len(valid)
        if not n:
            return {
                "rounds":0,"avg_coverage":0.0,"pct_1plus":0.0,"pct_2plus":0.0,
                "pct_3plus":0.0,"pct_4plus":0.0,"pct_5":0.0,"avg_position":None,
                "avg_random_expected":0.0,"uplift_vs_random":0.0,"errors":len(records),
            }
        hits=[int(r.get("coverage_hits") or 0) for r in valid]
        pos=[int(r.get("position_hits") or 0) for r in valid if r.get("position_hits") is not None]
        random_expected=[float(r.get("random_expected") or 0.0) for r in valid]
        avg=sum(hits)/n
        baseline=(sum(random_expected)/len(random_expected)) if random_expected else 0.0
        return {
            "rounds":n,
            "avg_coverage":avg,
            "pct_1plus":sum(v>=1 for v in hits)/n*100.0,
            "pct_2plus":sum(v>=2 for v in hits)/n*100.0,
            "pct_3plus":sum(v>=3 for v in hits)/n*100.0,
            "pct_4plus":sum(v>=4 for v in hits)/n*100.0,
            "pct_5":sum(v>=5 for v in hits)/n*100.0,
            "avg_position":(sum(pos)/len(pos)) if pos else None,
            "avg_random_expected":baseline,
            "uplift_vs_random":avg-baseline,
            "errors":len(records)-n,
        }

    def decision_walk_forward(self, window=120, methods=None, progress_callback=None, cancel_event=None):
        """
        Simulação histórica walk-forward sem look-ahead.

        Para cada extração-base selecionada, executa exatamente os métodos atuais
        usando somente informação anterior àquela base. O resultado imediatamente
        operacional seguinte é usado apenas DEPOIS para auditoria.

        window é a quantidade máxima de transições operacionais mais recentes.
        Nenhuma configuração é otimizada dentro deste método.
        """
        try:
            window=max(1,min(500,int(window)))
        except Exception:
            window=120
        method_order=("Reset Cobertura","Puxada Combinada","Similaridade")
        if methods:
            requested=[m for m in method_order if m in set(methods)]
            methods=tuple(requested or method_order)
        else:
            methods=method_order

        draws=self._draws_in_order()
        candidates=[]
        key_to_index={(d["data"],d["sorteio"],d["hora"]):i for i,d in enumerate(draws)}
        for i,base in enumerate(draws):
            if i < 35 or not self._is_operational_draw(base) or len(base.get("prizes") or []) < 5:
                continue
            # Walk-forward rigoroso: se a rodada operacional que ERA esperada
            # após a base não existe no histórico, pula o caso. Não usa uma
            # rodada posterior só porque hoje sabemos que ela existe.
            expected=self._reset_expected_target(base)
            target_index=key_to_index.get((expected["data"],expected["sorteio"],expected["hora"]))
            if target_index is None or target_index <= i:
                continue
            target=draws[target_index]
            if len(target.get("prizes") or []) < 5:
                continue
            candidates.append((i,base,target_index,target))
        candidates=candidates[-window:]
        total=len(candidates)
        details=[]
        cancelled=False

        for done,(base_index,base,target_index,target) in enumerate(candidates, start=1):
            if cancel_event is not None and cancel_event.is_set():
                cancelled=True
                break
            if progress_callback:
                try:
                    progress_callback(done-1,total,{
                        "data":base["data"],"sorteio":base["sorteio"],"hora":base["hora"],
                    })
                except Exception:
                    pass

            target_groups=[int(p["grupo"]) for p in target.get("prizes") or []]
            target_unique=set(target_groups)
            row={
                "base":{"data":base["data"],"sorteio":base["sorteio"],"hora":base["hora"]},
                "target":{"data":target["data"],"sorteio":target["sorteio"],"hora":target["hora"]},
                "target_groups":target_groups,
                "target_animals":[BICHOS.get(g,str(g)) for g in target_groups],
                "methods":{},
            }
            for method in methods:
                if cancel_event is not None and cancel_event.is_set():
                    cancelled=True
                    break
                try:
                    if method == "Reset Cobertura":
                        result=self.method_reset_coverage_v1(base["data"],base["sorteio"],base["hora"],top_n=5)
                        positional=None
                    elif method == "Puxada Combinada":
                        result=self.method_convergencia_g5(base["data"],base["sorteio"],base["hora"],top_n=5)
                        positional=None
                    else:
                        result=self.method_similarity_day(base["data"],base["sorteio"],base["hora"],top_days=12)
                        predicted_slots=[int(r["grupo"]) for r in (result.get("selected") or [])]
                        positional=sum(1 for a,b in zip(predicted_slots,target_groups) if int(a)==int(b))
                    predicted=[int(r["grupo"]) for r in (result.get("selected") or []) if r.get("grupo")]
                    pred_unique=set(predicted)
                    coverage=len(pred_unique & target_unique)
                    random_expected=(len(pred_unique)*len(target_unique)/25.0) if pred_unique else 0.0
                    row["methods"][method]={
                        "available":True,"groups":predicted,
                        "animals":[BICHOS.get(g,str(g)) for g in predicted],
                        "coverage_hits":coverage,"position_hits":positional,
                        "random_expected":random_expected,
                        "lookahead_safe":bool(result.get("lookahead_safe",True)),
                    }
                except Exception as exc:
                    row["methods"][method]={
                        "available":False,"groups":[],"animals":[],"coverage_hits":None,
                        "position_hits":None,"random_expected":0.0,"error":str(exc),
                    }
            details.append(row)
            if progress_callback:
                try:
                    progress_callback(done,total,{
                        "data":base["data"],"sorteio":base["sorteio"],"hora":base["hora"],
                    })
                except Exception:
                    pass
            if cancelled:
                break

        summary=[]
        for method in methods:
            records=[row["methods"].get(method,{"available":False}) for row in details]
            met=self._walk_forward_metric_summary(records)
            met["method"]=method
            summary.append(met)
        summary.sort(key=lambda r:(-r["avg_coverage"],-r["pct_2plus"],-r["pct_3plus"],r["method"]))

        paired=[]
        for row in details:
            if all((row["methods"].get(m) or {}).get("available") for m in methods):
                paired.append(row)
        paired_summary=[]
        for method in methods:
            vals=[int(row["methods"][method].get("coverage_hits") or 0) for row in paired]
            paired_summary.append({
                "method":method,
                "rounds":len(vals),
                "avg_coverage":(sum(vals)/len(vals)) if vals else 0.0,
                "pct_2plus":(sum(v>=2 for v in vals)/len(vals)*100.0) if vals else 0.0,
                "pct_3plus":(sum(v>=3 for v in vals)/len(vals)*100.0) if vals else 0.0,
            })
        paired_summary.sort(key=lambda r:(-r["avg_coverage"],-r["pct_2plus"],-r["pct_3plus"],r["method"]))
        best=paired_summary[0] if paired_summary else None

        # Robustez descritiva: compara a primeira e a segunda metade cronológica
        # do mesmo recorte. Não é teste de significância e não altera o método.
        split=max(1,len(details)//2) if details else 0
        robustness=[]
        for method in methods:
            first=[r["methods"].get(method,{"available":False}) for r in details[:split]]
            second=[r["methods"].get(method,{"available":False}) for r in details[split:]]
            fm=self._walk_forward_metric_summary(first)
            sm=self._walk_forward_metric_summary(second)
            robustness.append({
                "method":method,"first_rounds":fm["rounds"],"second_rounds":sm["rounds"],
                "first_avg":fm["avg_coverage"],"second_avg":sm["avg_coverage"],
                "delta":sm["avg_coverage"]-fm["avg_coverage"],
                "first_p2":fm["pct_2plus"],"second_p2":sm["pct_2plus"],
            })

        date_from=details[0]["target"]["data"] if details else None
        date_to=details[-1]["target"]["data"] if details else None
        return {
            "window":window,
            "requested_rounds":window,
            "eligible_rounds":total,
            "simulated_rounds":len(details),
            "cancelled":cancelled,
            "methods":list(methods),
            "summary":summary,
            "paired_rounds":len(paired),
            "paired_summary":paired_summary,
            "best_paired":best,
            "robustness":robustness,
            "details":details,
            "date_from":date_from,
            "date_to":date_to,
            "lookahead_safe":all(
                bool(sig.get("lookahead_safe",True))
                for row in details for sig in row.get("methods",{}).values() if sig.get("available")
            ),
            "config":{
                "Reset Cobertura":"last240 | pull | pair3 | probability",
                "Puxada Combinada":"G5 por estado ×1/×2/×3+; fallback Geral; 3 alvos por fonte",
                "Similaridade":"top 12 dias; pesos 45/30/15/5/5",
            },
        }

    def _decision_confidence(self, reset_result, pull_result, similarity_result):
        reset_groups = [int(r["grupo"]) for r in (reset_result or {}).get("selected", [])]
        pull_groups = [int(r["grupo"]) for r in (pull_result or {}).get("selected", [])]
        sim_groups = [int(r["grupo"]) for r in (similarity_result or {}).get("selected", [])]
        reset_set = set(reset_groups)

        overlaps = []
        overlap_detail = {}
        for name, groups in (("Puxada Combinada", pull_groups), ("Similaridade", sim_groups)):
            if groups:
                overlap = len(reset_set & set(groups))
                denom = max(1, min(5, len(set(groups))))
                score = overlap / denom * 100.0
                overlaps.append(score)
                overlap_detail[name] = {"overlap": overlap, "score": score}
        convergence = sum(overlaps) / len(overlaps) if overlaps else 35.0

        ranking = (reset_result or {}).get("ranking") or []
        selected = (reset_result or {}).get("selected") or []
        top_scores = [float(r.get("score_pct") or 0) for r in selected]
        mean_top = sum(top_scores) / len(top_scores) if top_scores else 0.0
        lift_component = self._decision_clip((mean_top - 18.0) / 18.0 * 100.0)
        gap = 0.0
        if len(ranking) >= 6:
            gap = float(ranking[4].get("score_pct") or 0) - float(ranking[5].get("score_pct") or 0)
        separation = self._decision_clip(gap / 4.0 * 100.0)
        reset_strength = 0.75 * lift_component + 0.25 * separation

        transitions = int((reset_result or {}).get("training_transitions") or 0)
        transition_score = self._decision_clip(transitions / 240.0 * 100.0)
        context_mode = (reset_result or {}).get("context_mode")
        if context_mode == "pair3":
            pair3 = int((reset_result or {}).get("pair3_matches") or 0)
            context_specific = self._decision_clip(pair3 / 20.0 * 100.0)
        else:
            pair3 = 0
            context_specific = 65.0
        context_support = 0.55 * transition_score + 0.45 * context_specific

        perf = self.decision_method_performance(window=30)
        reset_perf = next((r for r in perf["rows"] if r["method"] == "Reset Cobertura"), None)
        evidence_rounds = int(reset_perf["rounds"]) if reset_perf else 0
        if reset_perf:
            avg_hits = float(reset_perf["avg_coverage"])
            evidence = self._decision_clip((avg_hits - 0.5) / 2.5 * 100.0)
        else:
            evidence = 50.0

        raw = (
            0.35 * convergence
            + 0.25 * reset_strength
            + 0.20 * context_support
            + 0.20 * evidence
        )
        # Sem amostra prospectiva suficiente a Central não pode declarar confiança alta.
        cap = 68.0 if evidence_rounds < 3 else (74.0 if evidence_rounds < 10 else 100.0)
        score = min(raw, cap)
        score = round(self._decision_clip(score), 1)
        if score >= 75:
            label, recommendation = "ALTA", "Sinais fortes e consistentes"
        elif score >= 60:
            label, recommendation = "MODERADA", "Leitura normal; manter disciplina"
        elif score >= 45:
            label, recommendation = "BAIXA", "Cautela: sinais parcialmente divididos"
        else:
            label, recommendation = "MUITO BAIXA", "Sinais divididos; não elevar exposição"
        return {
            "score": score,
            "label": label,
            "recommendation": recommendation,
            "components": {
                "convergence": round(convergence, 1),
                "reset_strength": round(reset_strength, 1),
                "context_support": round(context_support, 1),
                "prospective_evidence": round(evidence, 1),
                "prospective_rounds": evidence_rounds,
                "overlap_detail": overlap_detail,
                "mean_reset_score": round(mean_top, 3),
                "reset_gap_5_6": round(gap, 3),
                "training_transitions": transitions,
                "pair3_matches": pair3,
                "confidence_cap": cap,
            },
        }

    def build_decision_reading(self, base_draw=None):
        base = base_draw or self.latest_operational_draw()
        if not base:
            raise ValueError("Não há extração operacional suficiente para a Central de Decisão.")
        reset = pull = sim = None
        errors = {}
        try:
            reset = self.method_reset_coverage_v1(base["data"], base["sorteio"], base["hora"], top_n=5)
        except Exception as exc:
            errors["Reset Cobertura"] = str(exc)
        try:
            pull = self.method_convergencia_g5(base["data"], base["sorteio"], base["hora"], top_n=5)
        except Exception as exc:
            errors["Puxada Combinada"] = str(exc)
        try:
            sim = self.method_similarity_day(base["data"], base["sorteio"], base["hora"], top_days=12)
        except Exception as exc:
            errors["Similaridade"] = str(exc)
        if not reset:
            raise ValueError(errors.get("Reset Cobertura") or "Reset Cobertura indisponível.")
        target = dict(reset.get("target") or self._reset_expected_target(base))
        confidence = self._decision_confidence(reset, pull, sim)
        signals = {
            "Reset Cobertura": self._decision_signal_payload(reset, "reset"),
            "Puxada Combinada": self._decision_signal_payload(pull, "pull"),
            "Similaridade": self._decision_signal_payload(sim, "similarity"),
        }
        return {
            "base": base,
            "target": target,
            "confidence": confidence,
            "signals": signals,
            "errors": errors,
        }

    def freeze_decision_snapshot(self, force=False):
        """Congela a primeira leitura da próxima rodada. Não sobrescreve previsão antiga."""
        reading = self.build_decision_reading()
        base = reading["base"]
        target = reading["target"]
        key = (
            base["data"], base["sorteio"], base["hora"],
            target["data"], target["sorteio"], target["hora"],
        )
        with self.connect() as con:
            existing = con.execute(
                "SELECT * FROM decision_snapshots WHERE base_data=? AND base_sorteio=? AND base_hora=? "
                "AND target_data=? AND target_sorteio=? AND target_hora=?",
                key,
            ).fetchone()
            if existing and not force:
                return self._decision_row_to_dict(existing), False
            conf = reading["confidence"]
            if existing:
                # force existe para testes/admin; mantém created_at original.
                con.execute(
                    "UPDATE decision_snapshots SET confidence_score=?, confidence_label=?, recommendation=?, "
                    "components_json=?, signals_json=?, note=? WHERE id=?",
                    (
                        conf["score"], conf["label"], conf["recommendation"],
                        json.dumps(conf["components"], ensure_ascii=False),
                        json.dumps(reading["signals"], ensure_ascii=False),
                        json.dumps(reading["errors"], ensure_ascii=False) if reading["errors"] else None,
                        int(existing["id"]),
                    ),
                )
                row = con.execute("SELECT * FROM decision_snapshots WHERE id=?", (int(existing["id"]),)).fetchone()
                return self._decision_row_to_dict(row), False
            cur = con.execute(
                "INSERT INTO decision_snapshots "
                "(base_data,base_sorteio,base_hora,target_data,target_sorteio,target_hora,confidence_score,confidence_label,recommendation,components_json,signals_json,note) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                key + (
                    conf["score"], conf["label"], conf["recommendation"],
                    json.dumps(conf["components"], ensure_ascii=False),
                    json.dumps(reading["signals"], ensure_ascii=False),
                    json.dumps(reading["errors"], ensure_ascii=False) if reading["errors"] else None,
                ),
            )
            row = con.execute("SELECT * FROM decision_snapshots WHERE id=?", (cur.lastrowid,)).fetchone()
        return self._decision_row_to_dict(row), True

    def _decision_row_to_dict(self, row):
        if row is None:
            return None
        d = dict(row)
        for field in ("components_json", "signals_json", "result_groups_json"):
            raw = d.get(field)
            key = field.replace("_json", "")
            try:
                d[key] = json.loads(raw) if raw else ({} if field != "result_groups_json" else [])
            except Exception:
                d[key] = {} if field != "result_groups_json" else []
        return d

    def latest_decision_snapshot(self):
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM decision_snapshots ORDER BY target_data DESC,target_hora DESC,id DESC LIMIT 1"
            ).fetchone()
        return self._decision_row_to_dict(row)

    def decision_snapshot_history(self, limit=100):
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM decision_snapshots ORDER BY target_data DESC,target_hora DESC,id DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [self._decision_row_to_dict(r) for r in rows]

    def audit_decision_snapshots(self):
        """Audita somente snapshots cujo alvo já existe na base."""
        changed = 0
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM decision_snapshots WHERE status='PENDENTE' ORDER BY id"
            ).fetchall()
            for row in rows:
                target = self.get_draw(row["target_data"], row["target_sorteio"], row["target_hora"])
                if not target or len(target.get("prizes") or []) < 5:
                    continue
                result_groups = [int(p["grupo"]) for p in target["prizes"]]
                result_set = set(result_groups)
                try:
                    signals = json.loads(row["signals_json"] or "{}")
                except Exception:
                    signals = {}
                for sig in signals.values():
                    groups = [int(g) for g in (sig.get("groups") or [])]
                    sig["coverage_hits"] = len(set(groups) & result_set)
                    if sig.get("positional") and len(groups) >= 5:
                        sig["position_hits"] = sum(
                            1 for i in range(5) if int(groups[i]) == int(result_groups[i])
                        )
                    else:
                        sig["position_hits"] = None
                con.execute(
                    "UPDATE decision_snapshots SET status='AUDITADO',signals_json=?,result_groups_json=?,audited_at=? WHERE id=?",
                    (
                        json.dumps(signals, ensure_ascii=False),
                        json.dumps(result_groups),
                        datetime.now().isoformat(timespec="seconds"),
                        int(row["id"]),
                    ),
                )
                changed += 1
        return changed

    # ========================================================
    # LABORATÓRIO SOMBRA v0.30.0
    # Congela jogos/sinais antes do resultado. O histórico sombra não é
    # exibido como arrependimento retrospectivo; alimenta apenas a recomendação.
    # ========================================================
    @staticmethod
    def _shadow_numbers(generation):
        return [
            str(r.get("numero") or "").strip()
            for r in (generation or {}).get("rows", [])
            if str(r.get("numero") or "").strip()
        ]

    @staticmethod
    def _shadow_group_list(method_result):
        out = []
        for row in (method_result or {}).get("selected", []):
            try:
                g = int(row.get("grupo"))
            except Exception:
                continue
            if 1 <= g <= 25 and g not in out:
                out.append(g)
        return out

    def _shadow_row_to_dict(self, row):
        if row is None:
            return None
        d = dict(row)
        for field in ("payload_json", "result_json"):
            raw = d.get(field)
            key = field.replace("_json", "")
            try:
                d[key] = json.loads(raw) if raw else {}
            except Exception:
                d[key] = {}
        return d

    def ensure_shadow_snapshot(self, target=None, base_draw=None, trigger="GERAR_JOGO"):
        """
        Cria UMA leitura sombra para a próxima rodada antes de o resultado existir.
        É idempotente por base+alvo. Nunca reconstrói uma rodada já conhecida.
        """
        target = dict(target or self.next_operational_target() or {})
        base_draw = dict(base_draw or self.latest_operational_draw() or {})
        if not target or not base_draw:
            return None, False
        if not base_draw.get("prizes") and all(base_draw.get(k) for k in ("data","sorteio","hora")):
            full_base = self.get_draw(base_draw["data"], base_draw["sorteio"], base_draw["hora"])
            if full_base:
                base_draw = full_base
        if not self.is_next_operational_target(target):
            return None, False
        # Proteção prospectiva: se o alvo já existe, não cria sombra retroativa.
        existing_target = self.get_draw(target.get("data"), target.get("sorteio"), target.get("hora"))
        if existing_target and len(existing_target.get("prizes") or []) >= 5:
            return None, False

        key = (
            base_draw.get("data"), base_draw.get("sorteio"), base_draw.get("hora"),
            target.get("data"), target.get("sorteio"), target.get("hora"),
        )
        if not all(key):
            return None, False
        with self.connect() as con:
            old = con.execute(
                "SELECT * FROM shadow_snapshots WHERE base_data=? AND base_sorteio=? AND base_hora=? "
                "AND target_data=? AND target_sorteio=? AND target_hora=?", key
            ).fetchone()
        if old is not None:
            return self._shadow_row_to_dict(old), False

        errors = {}
        payload = {
            "version": 1,
            "centena": {},
            "bichos": {},
            "seca_1p": {},
            "lookahead_safe": True,
        }

        reset = pull = sim = None
        try:
            reset = self.method_reset_coverage_v1(
                base_draw["data"], base_draw["sorteio"], base_draw["hora"], top_n=5
            )
        except Exception as exc:
            errors["Reset"] = str(exc)
        try:
            pull = self.method_convergencia_g5(
                base_draw["data"], base_draw["sorteio"], base_draw["hora"], top_n=5
            )
        except Exception as exc:
            errors["Puxada"] = str(exc)
        try:
            sim = self.method_similarity_day(
                base_draw["data"], base_draw["sorteio"], base_draw["hora"]
            )
        except Exception as exc:
            errors["Similaridade"] = str(exc)

        reset_groups = self._shadow_group_list(reset)
        pull_groups = self._shadow_group_list(pull)
        sim_groups = self._shadow_group_list(sim)

        if reset_groups:
            payload["bichos"]["Reset Cobertura"] = {
                "groups": reset_groups[:5], "objective": "1º–5º", "available": True
            }
            try:
                gen = self.generate_centenas_3plus1(reset_groups[:5], previous_draw=base_draw)
                _nums = self._shadow_numbers(gen)[:20]
                payload["centena"]["3+1"] = {
                    "numbers": _nums, "numbers_1": list(_nums), "groups": reset_groups[:5],
                    "objective": "1º/1º–5º", "available": True,
                    "note": "A fórmula interna 3+1 continua baseada em 1º–5º; a colocação muda apenas a auditoria do bilhete.",
                }
            except Exception as exc:
                errors["Centena 3+1"] = str(exc)
            try:
                gen = self.generate_historical_numbers(
                    groups=reset_groups[:5], kind="Centena", total=20, scope="1º–5º"
                )
                gen1 = self.generate_historical_numbers(
                    groups=reset_groups[:5], kind="Centena", total=20, scope="1º"
                )
                payload["centena"]["Reset + Histórica"] = {
                    "numbers": self._shadow_numbers(gen)[:20],
                    "numbers_1": self._shadow_numbers(gen1)[:20],
                    "groups": reset_groups[:5],
                    "objective": "1º/1º–5º", "available": True,
                }
            except Exception as exc:
                errors["Centena Reset + Histórica"] = str(exc)

        if pull_groups:
            payload["bichos"]["Puxada Combinada"] = {
                "groups": pull_groups[:5], "objective": "1º–5º", "available": True
            }
            try:
                gen = self.generate_historical_numbers(
                    groups=pull_groups[:5], kind="Centena", total=20, scope="1º–5º"
                )
                gen1 = self.generate_historical_numbers(
                    groups=pull_groups[:5], kind="Centena", total=20, scope="1º"
                )
                payload["centena"]["Puxada + Histórica"] = {
                    "numbers": self._shadow_numbers(gen)[:20],
                    "numbers_1": self._shadow_numbers(gen1)[:20],
                    "groups": pull_groups[:5],
                    "objective": "1º/1º–5º", "available": True,
                }
            except Exception as exc:
                errors["Centena Puxada + Histórica"] = str(exc)

        if sim_groups:
            payload["bichos"]["Similaridade"] = {
                "groups": sim_groups[:5], "objective": "1º–5º", "available": True
            }
            try:
                gen = self.generate_historical_numbers(
                    groups=sim_groups[:5], kind="Centena", total=20, scope="1º–5º"
                )
                gen1 = self.generate_historical_numbers(
                    groups=sim_groups[:5], kind="Centena", total=20, scope="1º"
                )
                payload["centena"]["Similaridade + Histórica"] = {
                    "numbers": self._shadow_numbers(gen)[:20],
                    "numbers_1": self._shadow_numbers(gen1)[:20],
                    "groups": sim_groups[:5],
                    "objective": "1º/1º–5º", "available": True,
                }
            except Exception as exc:
                errors["Centena Similaridade + Histórica"] = str(exc)

        # Seca: sempre avaliada SOMENTE contra o 1º prêmio.
        try:
            target_day = datetime.strptime(str(target["data"]), "%Y-%m-%d").date()
            dry_base = (target_day - timedelta(days=1)).isoformat()
            dry = self.method_dry_day_first_prize(base_date=dry_base, top_n=5)
            dry_groups = self._shadow_group_list(dry)
            if dry_groups:
                payload["seca_1p"]["Seca do Dia 1º"] = {
                    "groups": dry_groups[:5], "objective": "1º", "available": True,
                    "base_date": dry_base,
                }
        except Exception as exc:
            errors["Seca do Dia 1º"] = str(exc)

        payload["errors"] = errors
        with self.connect() as con:
            cur = con.execute(
                "INSERT OR IGNORE INTO shadow_snapshots "
                "(base_data,base_sorteio,base_hora,target_data,target_sorteio,target_hora,payload_json,trigger,note) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                key + (
                    json.dumps(payload, ensure_ascii=False),
                    str(trigger or "GERAR_JOGO"),
                    json.dumps(errors, ensure_ascii=False) if errors else None,
                ),
            )
            row = con.execute(
                "SELECT * FROM shadow_snapshots WHERE base_data=? AND base_sorteio=? AND base_hora=? "
                "AND target_data=? AND target_sorteio=? AND target_hora=?", key
            ).fetchone()
        return self._shadow_row_to_dict(row), bool(cur.rowcount)

    def audit_shadow_snapshots(self):
        """Audita silenciosamente leituras sombra cujo alvo já possui 1º–5º."""
        changed = 0
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM shadow_snapshots WHERE status='PENDENTE' ORDER BY id"
            ).fetchall()
            for row in rows:
                target = self.get_draw(row["target_data"], row["target_sorteio"], row["target_hora"])
                prizes = (target or {}).get("prizes") or []
                if len(prizes) < 5:
                    continue
                target_centenas = [str(p.get("centena") or "").zfill(3) for p in prizes]
                target_groups = [int(p["grupo"]) for p in prizes]
                result_set = set(target_groups)
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except Exception:
                    payload = {}

                for rec in (payload.get("centena") or {}).values():
                    nums = [str(x).zfill(3) for x in (rec.get("numbers") or [])]
                    nums1 = [str(x).zfill(3) for x in (rec.get("numbers_1") or rec.get("numbers") or [])]
                    matches = sorted(set(nums) & set(target_centenas))
                    first_match = bool(target_centenas and target_centenas[0] in set(nums1))
                    rec["audited"] = True
                    rec["hit_count"] = len(matches)
                    rec["win"] = bool(matches)
                    rec["matched_numbers"] = matches
                    # Para colocação 1º, usa o jogo que teria sido realmente gerado
                    # com ranking numérico de 1º prêmio (exceto 3+1, cuja fórmula interna é fixa).
                    rec["first_prize_hit"] = first_match
                    rec["matched_first_number"] = target_centenas[0] if first_match else None

                for rec in (payload.get("bichos") or {}).values():
                    groups = [int(g) for g in (rec.get("groups") or [])]
                    rec["audited"] = True
                    rec["coverage_hits"] = len(set(groups) & result_set)
                    rec["first_prize_hit"] = bool(target_groups and target_groups[0] in set(groups))

                for rec in (payload.get("seca_1p") or {}).values():
                    groups = [int(g) for g in (rec.get("groups") or [])]
                    rec["audited"] = True
                    rec["first_prize_hit"] = bool(target_groups and target_groups[0] in set(groups))
                    rec["coverage_hits"] = int(rec["first_prize_hit"])

                result = {
                    "centenas": target_centenas,
                    "groups": target_groups,
                    "first_group": target_groups[0] if target_groups else None,
                }
                con.execute(
                    "UPDATE shadow_snapshots SET status='AUDITADO',payload_json=?,result_json=?,audited_at=? WHERE id=?",
                    (
                        json.dumps(payload, ensure_ascii=False),
                        json.dumps(result, ensure_ascii=False),
                        datetime.now().isoformat(timespec="seconds"),
                        int(row["id"]),
                    ),
                )
                changed += 1
        return changed

    @staticmethod
    def _shadow_evidence_label(rounds, lead=0.0, recent_drop=False):
        rounds = int(rounds or 0)
        if rounds < 8:
            return "AMOSTRA INSUFICIENTE"
        if rounds >= 20 and lead >= 8.0 and not recent_drop:
            return "FORTE"
        if rounds >= 12 and lead >= 4.0 and not recent_drop:
            return "MODERADA"
        return "BAIXA"

    def shadow_recommendation(self, target=None, window=120, scope="1º–5º"):
        """
        Recomendação prospectiva por HORÁRIO baseada apenas em sombras auditadas.
        Não retorna mensagens retrospectivas por rodada.
        """
        target = dict(target or self.next_operational_target() or {})
        scope = "1º" if str(scope) == "1º" else "1º–5º"
        hour = str(target.get("hora") or "")
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM shadow_snapshots WHERE status='AUDITADO' AND target_hora=? "
                "ORDER BY target_data DESC,id DESC LIMIT ?",
                (hour, max(1, int(window))),
            ).fetchall()
        parsed = [self._shadow_row_to_dict(r) for r in rows]

        def centena_stats(name):
            vals=[]
            hits=[]
            for row in parsed:
                rec=((row.get("payload") or {}).get("centena") or {}).get(name)
                if not rec or not rec.get("audited"):
                    continue
                if scope == "1º":
                    vals.append(bool(rec.get("first_prize_hit")))
                    hits.append(1 if rec.get("first_prize_hit") else 0)
                else:
                    vals.append(bool(rec.get("win")))
                    hits.append(int(rec.get("hit_count") or 0))
            n=len(vals)
            rate=(sum(vals)/n*100.0) if n else 0.0
            recent=vals[:min(12,n)]
            recent_rate=(sum(recent)/len(recent)*100.0) if recent else rate
            return {"name":name,"rounds":n,"win_rate":rate,"recent_rate":recent_rate,
                    "avg_hits":(sum(hits)/n if n else 0.0)}

        centena_names=("3+1","Reset + Histórica","Puxada + Histórica","Similaridade + Histórica")
        cent = [centena_stats(n) for n in centena_names]
        cent = [r for r in cent if r["rounds"]]
        cent.sort(key=lambda r:(-r["win_rate"],-r["recent_rate"],-r["avg_hits"],r["name"]))
        cent_rec={"status":"SEM DADOS","best":None,"rows":cent}
        if cent:
            best=cent[0]
            second=cent[1] if len(cent)>1 else None
            lead=best["win_rate"]-(second["win_rate"] if second else 0.0)
            drop=best["recent_rate"]+12.0 < best["win_rate"]
            cent_rec={
                "status":self._shadow_evidence_label(best["rounds"],lead,drop),
                "best":best,"lead":lead,"rows":cent,
            }

        # Bichos: compara Reset, Puxada e Similaridade pela cobertura média Top 5.
        bstats=[]
        for name in ("Reset Cobertura","Puxada Combinada","Similaridade"):
            vals=[]
            for row in parsed:
                rec=((row.get("payload") or {}).get("bichos") or {}).get(name)
                if rec and rec.get("audited"):
                    if scope == "1º":
                        vals.append(1 if rec.get("first_prize_hit") else 0)
                    else:
                        vals.append(int(rec.get("coverage_hits") or 0))
            if vals:
                recent=vals[:min(12,len(vals))]
                bstats.append({
                    "name":name,"rounds":len(vals),"avg_coverage":sum(vals)/len(vals),
                    "recent_avg":sum(recent)/len(recent),
                })
        bstats.sort(key=lambda r:(-r["avg_coverage"],-r["recent_avg"],r["name"]))
        bicho_rec={"status":"SEM DADOS","best":None,"rows":bstats}
        if bstats:
            best=bstats[0]
            second=bstats[1] if len(bstats)>1 else None
            lead=(best["avg_coverage"]-(second["avg_coverage"] if second else 0.0))*20.0
            drop=best["recent_avg"]+0.45 < best["avg_coverage"]
            bicho_rec={
                "status":self._shadow_evidence_label(best["rounds"],lead,drop),
                "best":best,"lead":lead,"rows":bstats,
            }

        # Seca do 1º prêmio: objetivo específico e separado.
        dry_vals=[]
        for row in parsed:
            rec=((row.get("payload") or {}).get("seca_1p") or {}).get("Seca do Dia 1º")
            if rec and rec.get("audited"):
                dry_vals.append(bool(rec.get("first_prize_hit")))
        dry={"status":"SEM DADOS","rounds":0,"hit_rate":0.0}
        if dry_vals:
            n=len(dry_vals)
            rate=sum(dry_vals)/n*100.0
            recent=dry_vals[:min(12,n)]
            recent_rate=sum(recent)/len(recent)*100.0
            dry={
                "status":self._shadow_evidence_label(n, 5.0, recent_rate+12.0 < rate),
                "rounds":n,"hit_rate":rate,"recent_rate":recent_rate,
            }

        return {
            "target":target,"hour":hour,"scope":scope,"audited_rounds":len(parsed),
            "centena":cent_rec,"bichos":bicho_rec,"seca_1p":dry,
            "note":"Evidência prospectiva; não é probabilidade de acerto.",
        }

    def shadow_lab_status(self, target=None):
        """Resumo operacional do Laboratório Sombra sem expor arrependimento por rodada."""
        target = dict(target or self.next_operational_target() or {})
        hour = str(target.get("hora") or "")
        current = None
        audited = pending = 0
        last_audited = None
        with self.connect() as con:
            if hour:
                row = con.execute(
                    "SELECT COUNT(*) total, "
                    "SUM(CASE WHEN status='AUDITADO' THEN 1 ELSE 0 END) audited, "
                    "SUM(CASE WHEN status='PENDENTE' THEN 1 ELSE 0 END) pending, "
                    "MAX(CASE WHEN status='AUDITADO' THEN audited_at END) last_audited "
                    "FROM shadow_snapshots WHERE target_hora=?",
                    (hour,),
                ).fetchone()
                if row:
                    audited = int(row["audited"] or 0)
                    pending = int(row["pending"] or 0)
                    last_audited = row["last_audited"]
            if all(target.get(k) for k in ("data", "sorteio", "hora")):
                row = con.execute(
                    "SELECT * FROM shadow_snapshots WHERE target_data=? AND target_sorteio=? AND target_hora=? "
                    "ORDER BY id DESC LIMIT 1",
                    (target["data"], target["sorteio"], target["hora"]),
                ).fetchone()
                current = self._shadow_row_to_dict(row) if row else None
        return {
            "target": target,
            "hour": hour,
            "audited": audited,
            "pending": pending,
            "last_audited": last_audited,
            "current": current,
        }

    def decision_explain_group(self, snapshot, group):
        group = int(group)
        details = []
        for method, sig in (snapshot or {}).get("signals", {}).items():
            groups = [int(g) for g in (sig.get("groups") or [])]
            if group in groups:
                rank = groups.index(group) + 1
                extra = ""
                if sig.get("kind") == "reset":
                    scores = sig.get("scores") or []
                    if rank <= len(scores):
                        extra = f" • score {scores[rank-1]:.2f}%"
                elif sig.get("kind") == "pull":
                    counts = sig.get("source_counts") or []
                    if rank <= len(counts):
                        extra = f" • {counts[rank-1]} fonte(s)"
                elif sig.get("kind") == "similarity":
                    shares = sig.get("weighted_shares") or []
                    if rank <= len(shares):
                        extra = f" • voto ponderado {shares[rank-1]:.1f}%"
                details.append(f"{method}: posição {rank}{extra}")
            else:
                details.append(f"{method}: fora do Top 5")
        return details

    def upsert_rows(self, rows: list[PrizeRow]):
        sql = """
            INSERT INTO resultados
            (data, dia_semana, sorteio, hora, premio, milhar, centena, dezena,
             grupo, bicho, fonte, grupo_publicado, bicho_publicado, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(data, sorteio, hora, premio) DO UPDATE SET
                dia_semana=excluded.dia_semana,
                milhar=excluded.milhar,
                centena=excluded.centena,
                dezena=excluded.dezena,
                grupo=excluded.grupo,
                bicho=excluded.bicho,
                fonte=excluded.fonte,
                grupo_publicado=excluded.grupo_publicado,
                bicho_publicado=excluded.bicho_publicado,
                atualizado_em=CURRENT_TIMESTAMP
        """
        with self.connect() as con:
            con.executemany(
                sql,
                [
                    (
                        r.data, r.dia_semana, r.sorteio, r.hora, r.premio,
                        r.milhar, r.centena, r.dezena, r.grupo, r.bicho,
                        r.fonte, r.grupo_publicado, r.bicho_publicado
                    )
                    for r in rows
                ],
            )

    def has_date(self, day: date) -> bool:
        with self.connect() as con:
            return con.execute(
                "SELECT 1 FROM resultados WHERE data=? LIMIT 1", (day.isoformat(),)
            ).fetchone() is not None


    def game_count(self) -> int:
        with self.connect() as con:
            return con.execute(
                "SELECT COUNT(*) FROM jogos_congelados"
            ).fetchone()[0]

    @staticmethod
    def inspect_external_database(path):
        path = Path(path)
        info = {
            "path": str(path),
            "exists": path.is_file(),
            "resultados": 0,
            "jogos": 0,
            "latest_date": None,
            "error": None,
        }

        if not path.is_file():
            return info

        try:
            con = sqlite3.connect(path)
            con.row_factory = sqlite3.Row

            def table_exists(name):
                return con.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name=?",
                    (name,),
                ).fetchone() is not None

            if table_exists("resultados"):
                row = con.execute(
                    "SELECT COUNT(*) AS n, MAX(data) AS latest "
                    "FROM resultados"
                ).fetchone()
                info["resultados"] = int(row["n"] or 0)
                info["latest_date"] = row["latest"]

            if table_exists("jogos_congelados"):
                info["jogos"] = int(
                    con.execute(
                        "SELECT COUNT(*) FROM jogos_congelados"
                    ).fetchone()[0]
                )

            con.close()
        except Exception as exc:
            info["error"] = str(exc)

        return info

    def _existing_game_fingerprints(self):
        fingerprints = set()

        for game in self.list_frozen_games(limit=1000000):
            detail = self.frozen_game_details(game["id"])
            items = tuple(
                (
                    str(i.get("numero") or ""),
                    int(i.get("grupo") or 0),
                    str(i.get("regra") or ""),
                )
                for i in detail["items"]
            )

            fingerprints.add((
                str(game.get("criado_em") or ""),
                str(game.get("seletor") or "Não registrado"),
                str(game.get("estrategia") or ""),
                str(game.get("tipo") or ""),
                str(game.get("submodalidade") or ""),
                str(game.get("escopo") or ""),
                str(game.get("base_data") or ""),
                str(game.get("base_sorteio") or ""),
                str(game.get("base_hora") or ""),
                str(game.get("alvo_modo") or ""),
                str(game.get("alvo_data") or ""),
                str(game.get("alvo_sorteio") or ""),
                str(game.get("alvo_hora") or ""),
                items,
            ))

        return fingerprints

    def merge_external_database(self, path):
        """
        Mescla outra base sem substituir resultados atuais.

        v0.22:
        - resultados continuam conservadores (INSERT OR IGNORE);
        - jogos preservam financeiro e auditoria quando as colunas existem;
        - Bilhetes formais também são importados e remapeados;
        - registros antigos sem Bilhete continuam como legado.
        """
        path = Path(path).resolve()

        if not path.is_file():
            raise ValueError("Arquivo de banco não encontrado.")

        if path == Path(self.path).resolve():
            return {
                "resultados_adicionados": 0,
                "jogos_adicionados": 0,
                "bilhetes_adicionados": 0,
                "origem": str(path),
                "ignorado": True,
            }

        ext = sqlite3.connect(path)
        ext.row_factory = sqlite3.Row

        def ext_table(name):
            return ext.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name=?",
                (name,),
            ).fetchone() is not None

        added_results = 0
        added_games = 0
        added_tickets = 0

        try:
            # ------------------------------------------------
            # Resultados: somente preenche lacunas.
            # ------------------------------------------------
            if ext_table("resultados"):
                ext_columns = {
                    r["name"]
                    for r in ext.execute(
                        "PRAGMA table_info(resultados)"
                    ).fetchall()
                }

                required = {
                    "data","sorteio","hora","premio",
                    "milhar","centena","dezena","grupo","bicho",
                }

                if required.issubset(ext_columns):
                    select_cols = [
                        "data",
                        (
                            "dia_semana"
                            if "dia_semana" in ext_columns
                            else "NULL AS dia_semana"
                        ),
                        "sorteio","hora","premio","milhar","centena",
                        "dezena","grupo","bicho",
                        (
                            "fonte"
                            if "fonte" in ext_columns
                            else "NULL AS fonte"
                        ),
                        (
                            "grupo_publicado"
                            if "grupo_publicado" in ext_columns
                            else "NULL AS grupo_publicado"
                        ),
                        (
                            "bicho_publicado"
                            if "bicho_publicado" in ext_columns
                            else "NULL AS bicho_publicado"
                        ),
                    ]

                    source_rows = ext.execute(
                        "SELECT "
                        + ", ".join(select_cols)
                        + " FROM resultados "
                        "ORDER BY data, hora, sorteio, premio"
                    ).fetchall()

                    before = self.count()

                    with self.connect() as con:
                        con.executemany("""
                            INSERT OR IGNORE INTO resultados
                            (
                                data, dia_semana, sorteio, hora, premio,
                                milhar, centena, dezena, grupo, bicho,
                                fonte, grupo_publicado, bicho_publicado
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, [
                            (
                                r["data"],
                                r["dia_semana"],
                                r["sorteio"],
                                r["hora"],
                                r["premio"],
                                r["milhar"],
                                r["centena"],
                                r["dezena"],
                                r["grupo"],
                                r["bicho"],
                                r["fonte"],
                                r["grupo_publicado"],
                                r["bicho_publicado"],
                            )
                            for r in source_rows
                        ])

                    added_results = self.count() - before

            # ------------------------------------------------
            # Bilhetes: recria IDs e mantém mapa externo→local.
            # ------------------------------------------------
            ticket_map = {}

            if ext_table("bilhetes"):
                source_tickets = [
                    dict(r)
                    for r in ext.execute(
                        "SELECT * FROM bilhetes ORDER BY id"
                    ).fetchall()
                ]

                with self.connect() as con:
                    existing_rows = [
                        dict(r)
                        for r in con.execute(
                            "SELECT * FROM bilhetes"
                        ).fetchall()
                    ]

                def ticket_fp(t):
                    return (
                        str(t.get("criado_em") or ""),
                        str(t.get("alvo_data") or ""),
                        str(t.get("alvo_sorteio") or ""),
                        str(t.get("alvo_hora") or ""),
                        str(t.get("status") or ""),
                        round(float(t.get("total_apostado") or 0), 8),
                        round(float(t.get("retorno_real") or 0), 8),
                        round(float(t.get("resultado_liquido") or 0), 8),
                        str(t.get("observacao") or ""),
                    )

                existing_by_fp = {
                    ticket_fp(t): int(t["id"])
                    for t in existing_rows
                }

                for ticket in source_tickets:
                    fp = ticket_fp(ticket)

                    if fp in existing_by_fp:
                        ticket_map[int(ticket["id"])] = existing_by_fp[fp]
                        continue

                    with self.connect() as con:
                        cur = con.execute("""
                            INSERT INTO bilhetes
                            (
                                criado_em,
                                alvo_data,
                                alvo_sorteio,
                                alvo_hora,
                                status,
                                total_apostado,
                                retorno_real,
                                resultado_liquido,
                                observacao
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            ticket.get("criado_em")
                            or datetime.now().isoformat(timespec="seconds"),
                            ticket.get("alvo_data") or "",
                            ticket.get("alvo_sorteio"),
                            ticket.get("alvo_hora"),
                            ticket.get("status") or "PENDENTE",
                            float(ticket.get("total_apostado") or 0),
                            float(ticket.get("retorno_real") or 0),
                            float(ticket.get("resultado_liquido") or 0),
                            ticket.get("observacao") or "",
                        ))
                        new_ticket_id = int(cur.lastrowid)

                    ticket_map[int(ticket["id"])] = new_ticket_id
                    existing_by_fp[fp] = new_ticket_id
                    added_tickets += 1

            # ------------------------------------------------
            # Jogos congelados / reais.
            # ------------------------------------------------
            if ext_table("jogos_congelados"):
                game_columns = {
                    r["name"]
                    for r in ext.execute(
                        "PRAGMA table_info(jogos_congelados)"
                    ).fetchall()
                }

                item_columns = set()
                if ext_table("jogos_itens"):
                    item_columns = {
                        r["name"]
                        for r in ext.execute(
                            "PRAGMA table_info(jogos_itens)"
                        ).fetchall()
                    }

                existing = self._existing_game_fingerprints()

                source_games = ext.execute(
                    "SELECT * FROM jogos_congelados ORDER BY id"
                ).fetchall()

                for game_row in source_games:
                    game = dict(game_row)

                    source_items = []
                    if item_columns:
                        source_items = [
                            dict(r)
                            for r in ext.execute(
                                "SELECT * FROM jogos_itens "
                                "WHERE jogo_id=? ORDER BY ordem",
                                (game["id"],),
                            ).fetchall()
                        ]

                    selector = (
                        game.get("seletor")
                        if "seletor" in game_columns
                        else None
                    )

                    if not selector:
                        selector = (
                            "Seca do Dia 1º"
                            if game.get("estrategia") == "Seca do Dia 1º"
                            else "Não registrado"
                        )

                    items_fp = tuple(
                        (
                            str(i.get("numero") or ""),
                            int(i.get("grupo") or 0),
                            str(i.get("regra") or ""),
                        )
                        for i in source_items
                    )

                    fp = (
                        str(game.get("criado_em") or ""),
                        str(selector),
                        str(game.get("estrategia") or ""),
                        str(game.get("tipo") or ""),
                        str(game.get("submodalidade") or ""),
                        str(game.get("escopo") or ""),
                        str(game.get("base_data") or ""),
                        str(game.get("base_sorteio") or ""),
                        str(game.get("base_hora") or ""),
                        str(game.get("alvo_modo") or ""),
                        str(game.get("alvo_data") or ""),
                        str(game.get("alvo_sorteio") or ""),
                        str(game.get("alvo_hora") or ""),
                        items_fp,
                    )

                    if fp in existing:
                        continue

                    old_ticket_id = game.get("bilhete_id")
                    new_ticket_id = (
                        ticket_map.get(int(old_ticket_id))
                        if old_ticket_id
                        else None
                    )

                    with self.connect() as con:
                        cur = con.execute("""
                            INSERT INTO jogos_congelados
                            (
                                criado_em,
                                seletor,
                                estrategia,
                                tipo,
                                submodalidade,
                                escopo,
                                base_data,
                                base_sorteio,
                                base_hora,
                                alvo_modo,
                                alvo_data,
                                alvo_sorteio,
                                alvo_hora,
                                status,
                                acertos,
                                total_itens,
                                auditado_em,
                                observacao,
                                jogado,
                                jogado_em,
                                valor_unitario,
                                valor_total,
                                multiplicador,
                                retorno_min,
                                retorno_max,
                                retorno_real,
                                resultado_liquido,
                                divisor_posicoes,
                                valor_posicao,
                                cotacao_primaria,
                                cotacao_secundaria,
                                cotacao_combinada,
                                acertos_financeiros,
                                origem_jogada,
                                editado_em,
                                bilhete_id
                            )
                            VALUES (
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                            )
                        """, (
                            game.get("criado_em")
                            or datetime.now().isoformat(timespec="seconds"),
                            selector,
                            game.get("estrategia") or "Histórica simples",
                            game.get("tipo") or "Centena",
                            game.get("submodalidade"),
                            game.get("escopo") or "1º–5º",
                            game.get("base_data"),
                            game.get("base_sorteio"),
                            game.get("base_hora"),
                            game.get("alvo_modo") or "PROXIMA_EXTRACAO",
                            game.get("alvo_data"),
                            game.get("alvo_sorteio"),
                            game.get("alvo_hora"),
                            game.get("status") or "PENDENTE",
                            int(game.get("acertos") or 0),
                            int(
                                game.get("total_itens")
                                or len(source_items)
                            ),
                            game.get("auditado_em"),
                            game.get("observacao") or "",
                            int(game.get("jogado") or 0),
                            game.get("jogado_em"),
                            game.get("valor_unitario"),
                            game.get("valor_total"),
                            game.get("multiplicador"),
                            game.get("retorno_min"),
                            game.get("retorno_max"),
                            game.get("retorno_real"),
                            game.get("resultado_liquido"),
                            game.get("divisor_posicoes"),
                            game.get("valor_posicao"),
                            game.get("cotacao_primaria"),
                            game.get("cotacao_secundaria"),
                            game.get("cotacao_combinada"),
                            int(game.get("acertos_financeiros") or 0),
                            game.get("origem_jogada"),
                            game.get("editado_em"),
                            new_ticket_id,
                        ))

                        new_game_id = int(cur.lastrowid)

                        for item in source_items:
                            con.execute("""
                                INSERT INTO jogos_itens
                                (
                                    jogo_id,
                                    ordem,
                                    grupo,
                                    bicho,
                                    numero,
                                    dezena_base,
                                    regra,
                                    acertou,
                                    acerto_data,
                                    acerto_sorteio,
                                    acerto_hora,
                                    acerto_premio,
                                    acerto_milhar
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                new_game_id,
                                int(item.get("ordem") or 0),
                                item.get("grupo"),
                                item.get("bicho"),
                                str(item.get("numero") or ""),
                                item.get("dezena_base"),
                                item.get("regra"),
                                int(item.get("acertou") or 0),
                                item.get("acerto_data"),
                                item.get("acerto_sorteio"),
                                item.get("acerto_hora"),
                                item.get("acerto_premio"),
                                item.get("acerto_milhar"),
                            ))

                    existing.add(fp)
                    added_games += 1

            for mapped_id in set(ticket_map.values()):
                try:
                    self.refresh_ticket_totals(mapped_id)
                except Exception:
                    pass

        finally:
            ext.close()

        return {
            "resultados_adicionados": added_results,
            "jogos_adicionados": added_games,
            "bilhetes_adicionados": added_tickets,
            "origem": str(path),
            "ignorado": False,
        }

    # ------------------------------------------------------------------
    # Sincronização multi-PC por snapshots em pasta compartilhada (v0.26.1)
    # ------------------------------------------------------------------
    def _sync_table_columns(self, con, table):
        return [r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]

    @staticmethod
    def _sync_ticket_fingerprint(row):
        return (
            str(row.get("criado_em") or ""),
            str(row.get("alvo_data") or ""),
            str(row.get("alvo_sorteio") or ""),
            str(row.get("alvo_hora") or ""),
            round(float(row.get("total_apostado") or 0), 8),
            str(row.get("observacao") or ""),
        )

    @staticmethod
    def _sync_game_fingerprint(row, items=None):
        item_numbers = tuple(
            str(i.get("numero") or "")
            for i in (items or row.get("items") or [])
        )
        return (
            str(row.get("criado_em") or ""),
            str(row.get("seletor") or ""),
            str(row.get("estrategia") or ""),
            str(row.get("tipo") or ""),
            str(row.get("submodalidade") or ""),
            str(row.get("escopo") or ""),
            str(row.get("alvo_data") or ""),
            str(row.get("alvo_sorteio") or ""),
            str(row.get("alvo_hora") or ""),
            item_numbers,
        )

    def build_sync_snapshot(self, profile, visual_settings=None):
        """Exporta o estado sincronizável sem expor IDs locais de relações."""
        profile = profile or {}
        with self.connect() as con:
            results = [dict(r) for r in con.execute(
                "SELECT * FROM resultados ORDER BY data, hora, sorteio, premio"
            ).fetchall()]
            for r in results:
                r.pop("id", None)

            tickets = [dict(r) for r in con.execute(
                "SELECT * FROM bilhetes ORDER BY id"
            ).fetchall()]
            ticket_uid_by_id = {}
            for t in tickets:
                ticket_uid_by_id[int(t["id"])] = t.get("sync_uid")
                t.pop("id", None)

            games = [dict(r) for r in con.execute(
                "SELECT * FROM jogos_congelados ORDER BY id"
            ).fetchall()]
            exported_games = []
            for g in games:
                local_id = int(g["id"])
                ticket_id = g.get("bilhete_id")
                g["bilhete_sync_uid"] = (
                    ticket_uid_by_id.get(int(ticket_id)) if ticket_id else None
                )
                g.pop("id", None)
                g.pop("bilhete_id", None)
                items = [dict(r) for r in con.execute(
                    "SELECT * FROM jogos_itens WHERE jogo_id=? ORDER BY ordem, id",
                    (local_id,),
                ).fetchall()]
                for item in items:
                    item.pop("id", None)
                    item.pop("jogo_id", None)
                g["items"] = items
                exported_games.append(g)

            meta_rows = [
                dict(r)
                for r in con.execute(
                    "SELECT chave, valor FROM meta "
                    "WHERE chave LIKE 'quote_%' "
                    "OR chave IN ('bankroll_initial','bankroll_start_date') "
                    "ORDER BY chave"
                ).fetchall()
            ]

            decision_rows = [dict(r) for r in con.execute(
                "SELECT * FROM decision_snapshots ORDER BY id"
            ).fetchall()]
            for row in decision_rows:
                row.pop("id", None)

            shadow_rows = [dict(r) for r in con.execute(
                "SELECT * FROM shadow_snapshots ORDER BY id"
            ).fetchall()]
            for row in shadow_rows:
                row.pop("id", None)

        now = datetime.now().isoformat(timespec="seconds")
        snapshot = {
            "format_version": SYNC_FORMAT_VERSION,
            "app_version": APP_VERSION,
            "profile_code": normalize_profile_code(profile.get("profile_code")),
            "profile_name": profile.get("profile_name") or "Perfil GP-H",
            "generated_at": now,
            "device": {
                "device_id": profile.get("device_id"),
                "device_name": profile.get("device_name") or default_device_name(),
                "last_login_at": profile.get("last_login_at"),
            },
            "visual_settings": dict(visual_settings or {}),
            "meta": meta_rows,
            "resultados": results,
            "bilhetes": tickets,
            "jogos": exported_games,
            "decision_snapshots": decision_rows,
            "shadow_snapshots": shadow_rows,
        }
        content = {
            "visual_settings": snapshot["visual_settings"],
            "meta": meta_rows,
            "resultados": results,
            "bilhetes": tickets,
            "jogos": exported_games,
            "decision_snapshots": decision_rows,
            "shadow_snapshots": shadow_rows,
        }
        snapshot["content_hash"] = hashlib.sha256(
            json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return snapshot

    def _merge_sync_results(self, rows):
        added = updated = 0
        if not rows:
            return added, updated
        with self.connect() as con:
            for remote in rows:
                key = (
                    remote.get("data"), remote.get("sorteio"),
                    remote.get("hora"), remote.get("premio"),
                )
                if not all(v is not None for v in key):
                    continue
                local = con.execute(
                    "SELECT * FROM resultados WHERE data=? AND sorteio=? AND hora=? AND premio=?",
                    key,
                ).fetchone()
                remote_ts = _sync_timestamp(remote.get("atualizado_em"))
                if local is not None:
                    local_d = dict(local)
                    local_ts = _sync_timestamp(local_d.get("atualizado_em"))
                    if remote_ts <= local_ts:
                        continue
                    cols = [
                        c for c in remote.keys()
                        if c != "id" and c in local_d
                    ]
                    if not cols:
                        continue
                    sql = "UPDATE resultados SET " + ",".join(f"{c}=?" for c in cols) + \
                          " WHERE data=? AND sorteio=? AND hora=? AND premio=?"
                    con.execute(sql, [remote.get(c) for c in cols] + list(key))
                    updated += 1
                else:
                    cols = [
                        c for c in remote.keys()
                        if c != "id"
                    ]
                    placeholders = ",".join("?" for _ in cols)
                    try:
                        con.execute(
                            f"INSERT INTO resultados ({','.join(cols)}) VALUES ({placeholders})",
                            [remote.get(c) for c in cols],
                        )
                        added += 1
                    except sqlite3.IntegrityError:
                        pass
        return added, updated

    def _merge_sync_meta(self, rows):
        changed = 0
        allowed = {"bankroll_initial", "bankroll_start_date"}
        with self.connect() as con:
            for row in rows or []:
                key = str(row.get("chave") or "")
                if not (key.startswith("quote_") or key in allowed):
                    continue
                value = row.get("valor")
                current = con.execute(
                    "SELECT valor FROM meta WHERE chave=?", (key,)
                ).fetchone()
                if current is None or str(current[0]) != str(value):
                    con.execute(
                        "INSERT OR REPLACE INTO meta(chave, valor) VALUES(?, ?)",
                        (key, value),
                    )
                    changed += 1
        return changed

    def _sync_ticket_lookup_maps(self, con):
        by_uid = {}
        by_fp = {}
        for r in con.execute("SELECT * FROM bilhetes").fetchall():
            d = dict(r)
            if d.get("sync_uid"):
                by_uid[str(d["sync_uid"])] = d
            by_fp.setdefault(self._sync_ticket_fingerprint(d), d)
        return by_uid, by_fp

    def _sync_game_lookup_maps(self, con):
        by_uid = {}
        by_fp = {}
        games = [dict(r) for r in con.execute("SELECT * FROM jogos_congelados").fetchall()]
        for d in games:
            items = [dict(r) for r in con.execute(
                "SELECT * FROM jogos_itens WHERE jogo_id=? ORDER BY ordem, id",
                (int(d["id"]),),
            ).fetchall()]
            if d.get("sync_uid"):
                by_uid[str(d["sync_uid"])] = d
            by_fp.setdefault(self._sync_game_fingerprint(d, items), d)
        return by_uid, by_fp

    def _insert_or_update_sync_ticket(self, con, remote, by_uid, by_fp):
        uid = str(remote.get("sync_uid") or "").strip()
        if not uid:
            return None, False, False
        local = by_uid.get(uid)
        adopted = False
        if local is None:
            fp = self._sync_ticket_fingerprint(remote)
            local = by_fp.get(fp)
            if local is not None and local.get("sync_uid") != uid:
                # Mesma informação trazida de uma instalação anterior: adota o UID remoto.
                con.execute(
                    "UPDATE bilhetes SET sync_uid=? WHERE id=?",
                    (uid, int(local["id"])),
                )
                local = dict(local)
                local["sync_uid"] = uid
                adopted = True

        cols_available = set(self._sync_table_columns(con, "bilhetes"))
        payload = {
            k: v for k, v in remote.items()
            if k in cols_available and k != "id"
        }
        remote_ts = _sync_timestamp(remote.get("sync_updated_at"))

        if local is None:
            cols = list(payload.keys())
            if not cols:
                return None, False, False
            cur = con.execute(
                f"INSERT INTO bilhetes ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                [payload[c] for c in cols],
            )
            local_id = int(cur.lastrowid)
            newrow = dict(con.execute("SELECT * FROM bilhetes WHERE id=?", (local_id,)).fetchone())
            by_uid[uid] = newrow
            by_fp[self._sync_ticket_fingerprint(newrow)] = newrow
            return local_id, True, False

        local_ts = _sync_timestamp(local.get("sync_updated_at"))
        if remote_ts > local_ts:
            cols = [c for c in payload if c not in ("sync_uid",)]
            if cols:
                con.execute(
                    "UPDATE bilhetes SET " + ",".join(f"{c}=?" for c in cols) + " WHERE id=?",
                    [payload[c] for c in cols] + [int(local["id"])],
                )
            return int(local["id"]), False, True
        return int(local["id"]), False, adopted

    def _insert_or_update_sync_game(self, con, remote, ticket_id, by_uid, by_fp):
        uid = str(remote.get("sync_uid") or "").strip()
        if not uid:
            return None, False, False
        items = list(remote.get("items") or [])
        local = by_uid.get(uid)
        adopted = False
        if local is None:
            fp = self._sync_game_fingerprint(remote, items)
            local = by_fp.get(fp)
            if local is not None and local.get("sync_uid") != uid:
                con.execute(
                    "UPDATE jogos_congelados SET sync_uid=? WHERE id=?",
                    (uid, int(local["id"])),
                )
                local = dict(local)
                local["sync_uid"] = uid
                adopted = True

        cols_available = set(self._sync_table_columns(con, "jogos_congelados"))
        payload = {
            k: v for k, v in remote.items()
            if k in cols_available and k not in ("id", "bilhete_id")
        }
        payload["bilhete_id"] = ticket_id
        remote_ts = _sync_timestamp(remote.get("sync_updated_at"))

        def replace_items(game_id):
            con.execute("DELETE FROM jogos_itens WHERE jogo_id=?", (int(game_id),))
            item_cols_available = set(self._sync_table_columns(con, "jogos_itens"))
            for item in items:
                ip = {
                    k: v for k, v in item.items()
                    if k in item_cols_available and k not in ("id", "jogo_id")
                }
                ip["jogo_id"] = int(game_id)
                cols = list(ip.keys())
                if cols:
                    con.execute(
                        f"INSERT INTO jogos_itens ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                        [ip[c] for c in cols],
                    )

        if local is None:
            cols = list(payload.keys())
            cur = con.execute(
                f"INSERT INTO jogos_congelados ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                [payload[c] for c in cols],
            )
            local_id = int(cur.lastrowid)
            replace_items(local_id)
            newrow = dict(con.execute("SELECT * FROM jogos_congelados WHERE id=?", (local_id,)).fetchone())
            by_uid[uid] = newrow
            by_fp[self._sync_game_fingerprint(newrow, items)] = newrow
            return local_id, True, False

        local_ts = _sync_timestamp(local.get("sync_updated_at"))
        if remote_ts > local_ts:
            cols = [c for c in payload if c not in ("sync_uid",)]
            if cols:
                con.execute(
                    "UPDATE jogos_congelados SET " + ",".join(f"{c}=?" for c in cols) + " WHERE id=?",
                    [payload[c] for c in cols] + [int(local["id"])],
                )
            replace_items(int(local["id"]))
            return int(local["id"]), False, True
        elif ticket_id is not None and local.get("bilhete_id") != ticket_id:
            con.execute(
                "UPDATE jogos_congelados SET bilhete_id=? WHERE id=?",
                (ticket_id, int(local["id"])),
            )
            return int(local["id"]), False, True
        return int(local["id"]), False, adopted

    def _merge_sync_decision_snapshots(self, rows):
        added = updated = 0
        if not rows:
            return added, updated
        cols_allowed = {
            "created_at","base_data","base_sorteio","base_hora","target_data","target_sorteio","target_hora",
            "status","confidence_score","confidence_label","recommendation","components_json","signals_json",
            "result_groups_json","audited_at","note",
        }
        with self.connect() as con:
            for remote in rows:
                key = (
                    remote.get("base_data"), remote.get("base_sorteio"), remote.get("base_hora"),
                    remote.get("target_data"), remote.get("target_sorteio"), remote.get("target_hora"),
                )
                if not all(key):
                    continue
                local = con.execute(
                    "SELECT * FROM decision_snapshots WHERE base_data=? AND base_sorteio=? AND base_hora=? "
                    "AND target_data=? AND target_sorteio=? AND target_hora=?", key
                ).fetchone()
                if local is None:
                    data = {k: remote.get(k) for k in cols_allowed if k in remote}
                    keys = list(data)
                    con.execute(
                        f"INSERT INTO decision_snapshots ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                        [data[k] for k in keys],
                    )
                    added += 1
                    continue
                # A previsão mais antiga é a canônica; auditoria pode vir de qualquer PC.
                local_created = str(local["created_at"] or "9999")
                remote_created = str(remote.get("created_at") or "9999")
                changes = {}
                if remote_created < local_created:
                    for k in ("created_at","confidence_score","confidence_label","recommendation","components_json","signals_json","note"):
                        if k in remote:
                            changes[k] = remote.get(k)
                if str(remote.get("status") or "") == "AUDITADO" and str(local["status"] or "") != "AUDITADO":
                    for k in ("status","signals_json","result_groups_json","audited_at"):
                        changes[k] = remote.get(k)
                if changes:
                    sets = ",".join(f"{k}=?" for k in changes)
                    con.execute(f"UPDATE decision_snapshots SET {sets} WHERE id=?", list(changes.values()) + [int(local["id"])])
                    updated += 1
        return added, updated

    def _merge_sync_shadow_snapshots(self, rows):
        added = updated = 0
        if not rows:
            return added, updated
        cols_allowed = {
            "created_at","base_data","base_sorteio","base_hora","target_data","target_sorteio","target_hora",
            "status","payload_json","result_json","audited_at","trigger","note",
        }
        with self.connect() as con:
            for remote in rows:
                key = (
                    remote.get("base_data"), remote.get("base_sorteio"), remote.get("base_hora"),
                    remote.get("target_data"), remote.get("target_sorteio"), remote.get("target_hora"),
                )
                if not all(key):
                    continue
                local = con.execute(
                    "SELECT * FROM shadow_snapshots WHERE base_data=? AND base_sorteio=? AND base_hora=? "
                    "AND target_data=? AND target_sorteio=? AND target_hora=?", key
                ).fetchone()
                if local is None:
                    data={k:remote.get(k) for k in cols_allowed if k in remote}
                    keys=list(data)
                    con.execute(
                        f"INSERT INTO shadow_snapshots ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                        [data[k] for k in keys],
                    )
                    added += 1
                    continue
                # A leitura criada primeiro é canônica; uma auditoria pronta pode ser compartilhada.
                changes={}
                local_created=str(local["created_at"] or "9999")
                remote_created=str(remote.get("created_at") or "9999")
                if remote_created < local_created:
                    for k in ("created_at","payload_json","trigger","note"):
                        if k in remote:
                            changes[k]=remote.get(k)
                if str(remote.get("status") or "") == "AUDITADO" and str(local["status"] or "") != "AUDITADO":
                    for k in ("status","payload_json","result_json","audited_at"):
                        changes[k]=remote.get(k)
                if changes:
                    sets=",".join(f"{k}=?" for k in changes)
                    con.execute(
                        f"UPDATE shadow_snapshots SET {sets} WHERE id=?",
                        list(changes.values())+[int(local["id"])],
                    )
                    updated += 1
        return added, updated

    def merge_sync_snapshot(self, payload):
        """Mescla um snapshot remoto preservando IDs locais e relações."""
        if not isinstance(payload, dict):
            raise ValueError("Pacote de sincronização inválido.")
        if int(payload.get("format_version") or 0) != SYNC_FORMAT_VERSION:
            raise ValueError("Versão de pacote de sincronização incompatível.")

        r_add, r_upd = self._merge_sync_results(payload.get("resultados") or [])
        meta_changed = self._merge_sync_meta(payload.get("meta") or [])
        d_add, d_upd = self._merge_sync_decision_snapshots(payload.get("decision_snapshots") or [])
        sh_add, sh_upd = self._merge_sync_shadow_snapshots(payload.get("shadow_snapshots") or [])
        t_add = t_upd = g_add = g_upd = 0
        touched_tickets = set()

        with self.connect() as con:
            ticket_by_uid, ticket_by_fp = self._sync_ticket_lookup_maps(con)
            game_by_uid, game_by_fp = self._sync_game_lookup_maps(con)

            ticket_local_ids = {}
            for remote in payload.get("bilhetes") or []:
                local_id, added, updated = self._insert_or_update_sync_ticket(
                    con, remote, ticket_by_uid, ticket_by_fp
                )
                uid = str(remote.get("sync_uid") or "")
                if local_id is not None:
                    ticket_local_ids[uid] = local_id
                    touched_tickets.add(local_id)
                t_add += int(added)
                t_upd += int(updated)

            # Mapas podem ter mudado após inserções/adopções.
            ticket_by_uid, ticket_by_fp = self._sync_ticket_lookup_maps(con)
            for uid, row in ticket_by_uid.items():
                ticket_local_ids[uid] = int(row["id"])

            for remote in payload.get("jogos") or []:
                ticket_uid = str(remote.get("bilhete_sync_uid") or "").strip()
                ticket_id = ticket_local_ids.get(ticket_uid) if ticket_uid else None
                local_id, added, updated = self._insert_or_update_sync_game(
                    con, remote, ticket_id, game_by_uid, game_by_fp
                )
                if ticket_id is not None:
                    touched_tickets.add(ticket_id)
                g_add += int(added)
                g_upd += int(updated)

        # Totais de Bilhetes são derivados dos jogos e permanecem consistentes.
        for ticket_id in sorted(touched_tickets):
            try:
                self.refresh_ticket_totals(ticket_id)
            except Exception:
                pass

        return {
            "resultados_adicionados": r_add,
            "resultados_atualizados": r_upd,
            "bilhetes_adicionados": t_add,
            "bilhetes_atualizados": t_upd,
            "jogos_adicionados": g_add,
            "jogos_atualizados": g_upd,
            "configuracoes_atualizadas": meta_changed,
            "decisoes_adicionadas": d_add,
            "decisoes_atualizadas": d_upd,
            "sombras_adicionadas": sh_add,
            "sombras_atualizadas": sh_upd,
        }

    def sync_with_shared_folder(self, profile, visual_settings=None):
        """
        Sincroniza com snapshots independentes por dispositivo.
        Cada PC escreve somente o próprio arquivo; portanto não há SQLite compartilhado.
        """
        profile = dict(profile or {})
        code = normalize_profile_code(profile.get("profile_code"))
        if not valid_profile_code(code):
            raise ValueError("Perfil sem código GP-H válido.")
        if not profile.get("sync_enabled") or not profile.get("sync_folder"):
            raise ValueError("Configure uma pasta de sincronização primeiro.")

        root = account_sync_root(profile)
        if root is None:
            raise ValueError("Pasta de sincronização inválida.")
        devices_dir = root / "devices"
        devices_dir.mkdir(parents=True, exist_ok=True)

        # Teste de escrita antes de tocar na base.
        probe = root / ".write-test"
        try:
            probe.write_text("GP-H", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except Exception as exc:
            raise ValueError(f"A pasta não está disponível para gravação: {exc}") from exc

        own_device = str(profile.get("device_id") or "")
        packages = []
        ignored = []
        for path in devices_dir.glob("*.json"):
            if path.name.startswith("."):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if normalize_profile_code(data.get("profile_code")) != code:
                    ignored.append(path.name)
                    continue
                if int(data.get("format_version") or 0) != SYNC_FORMAT_VERSION:
                    ignored.append(path.name)
                    continue
                packages.append((data, path))
            except Exception:
                ignored.append(path.name)

        packages.sort(key=lambda pair: _sync_timestamp(pair[0].get("generated_at")))
        totals = Counter()
        remote_devices = []
        latest_visual = None
        latest_visual_at = datetime.min

        for data, path in packages:
            dev = data.get("device") or {}
            dev_id = str(dev.get("device_id") or "")
            if dev_id:
                remote_devices.append({
                    "device_id": dev_id,
                    "device_name": dev.get("device_name") or "Computador",
                    "generated_at": data.get("generated_at"),
                    "is_current": dev_id == own_device,
                })
            if dev_id == own_device:
                # O próprio snapshot antigo não precisa voltar para o mesmo banco.
                continue
            report = self.merge_sync_snapshot(data)
            totals.update(report)
            vis = data.get("visual_settings")
            vis_at = _sync_timestamp(data.get("generated_at"))
            if isinstance(vis, dict) and vis and vis_at > latest_visual_at:
                latest_visual = dict(vis)
                latest_visual_at = vis_at

        snapshot = self.build_sync_snapshot(profile, visual_settings=visual_settings)
        own_file = account_sync_device_file(profile)
        if own_file is None:
            raise ValueError("Não foi possível determinar o arquivo deste computador.")
        wrote_snapshot = True
        if own_file.is_file():
            try:
                previous_own = json.loads(own_file.read_text(encoding="utf-8"))
                if previous_own.get("content_hash") == snapshot.get("content_hash"):
                    wrote_snapshot = False
                    # Mantém a data do último pacote que realmente mudou; o perfil local
                    # registra separadamente a última tentativa de sincronização.
                    snapshot["generated_at"] = previous_own.get("generated_at") or snapshot["generated_at"]
            except Exception:
                pass
        if wrote_snapshot:
            _atomic_write_json(own_file, snapshot)

        # Um pequeno manifesto humano facilita diagnóstico sem ser fonte de verdade.
        manifest = {
            "format_version": SYNC_FORMAT_VERSION,
            "profile_code": code,
            "profile_name": profile.get("profile_name") or "Perfil GP-H",
            "last_sync_at": snapshot["generated_at"],
            "last_device": {
                "device_id": own_device,
                "device_name": profile.get("device_name") or default_device_name(),
            },
        }
        try:
            _atomic_write_json(root / "account_manifest.json", manifest)
        except Exception:
            pass

        # Releitura curta para contabilizar o próprio dispositivo quando é o primeiro sync.
        known = {d["device_id"]: d for d in remote_devices if d.get("device_id")}
        known[own_device] = {
            "device_id": own_device,
            "device_name": profile.get("device_name") or default_device_name(),
            "generated_at": snapshot["generated_at"],
            "is_current": True,
        }

        return {
            **dict(totals),
            "last_sync_at": datetime.now().isoformat(timespec="seconds"),
            "snapshot_changed": wrote_snapshot,
            "sync_root": str(root),
            "own_file": str(own_file),
            "device_count": len(known),
            "devices": sorted(
                known.values(),
                key=lambda d: (not d.get("is_current"), str(d.get("device_name") or "")),
            ),
            "ignored_files": ignored,
            "remote_visual_settings": latest_visual,
        }

    def sync_device_list(self, profile):
        root = account_sync_root(profile or {})
        if root is None:
            return []
        out = []
        for path in (root / "devices").glob("*.json") if (root / "devices").is_dir() else []:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if normalize_profile_code(data.get("profile_code")) != normalize_profile_code((profile or {}).get("profile_code")):
                    continue
                dev = data.get("device") or {}
                out.append({
                    "device_id": dev.get("device_id"),
                    "device_name": dev.get("device_name") or "Computador",
                    "generated_at": data.get("generated_at"),
                    "app_version": data.get("app_version"),
                    "is_current": dev.get("device_id") == (profile or {}).get("device_id"),
                })
            except Exception:
                continue
        out.sort(key=lambda d: (not d.get("is_current"), str(d.get("device_name") or "")))
        return out

    def auto_merge_previous_installations(self, paths):
        """
        Importação automática conservadora:
        - só é executada uma vez na base compartilhada;
        - bancos com mais resultados são processados primeiro;
        - nenhum registro atual é sobrescrito.
        """
        with self.connect() as con:
            done = con.execute(
                "SELECT valor FROM meta "
                "WHERE chave='auto_migracao_v017'"
            ).fetchone()

        if done:
            return {
                "executada": False,
                "fontes": 0,
                "resultados_adicionados": 0,
                "jogos_adicionados": 0,
                "mensagem": "Migração inicial já verificada.",
            }

        infos = []
        for path in paths:
            info = self.inspect_external_database(path)
            if (
                info["exists"]
                and not info["error"]
                and (info["resultados"] > 0 or info["jogos"] > 0)
            ):
                infos.append(info)

        infos.sort(
            key=lambda x: (
                -x["resultados"],
                -x["jogos"],
                str(x["path"]),
            )
        )

        total_results = 0
        total_games = 0
        used = 0

        for info in infos:
            report = self.merge_external_database(info["path"])
            total_results += report["resultados_adicionados"]
            total_games += report["jogos_adicionados"]
            used += 1

        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO meta(chave, valor) "
                "VALUES('auto_migracao_v017', ?)",
                (datetime.now().isoformat(timespec="seconds"),),
            )

        return {
            "executada": True,
            "fontes": used,
            "resultados_adicionados": total_results,
            "jogos_adicionados": total_games,
            "mensagem": (
                f"{used} base(s) anterior(es) verificada(s); "
                f"{total_results} resultado(s) e "
                f"{total_games} jogo(s) incorporado(s)."
            ),
        }

    def backup_to(self, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        source_con = sqlite3.connect(self.path)
        try:
            target_con = sqlite3.connect(destination)
            try:
                source_con.backup(target_con)
            finally:
                target_con.close()
        finally:
            source_con.close()

        return destination


    def count(self) -> int:
        with self.connect() as con:
            return con.execute("SELECT COUNT(*) FROM resultados").fetchone()[0]

    def minmax_date(self):
        with self.connect() as con:
            return con.execute("SELECT MIN(data), MAX(data) FROM resultados").fetchone()

    def distinct_draws(self):
        with self.connect() as con:
            return con.execute(
                "SELECT COUNT(*) FROM (SELECT DISTINCT data,sorteio,hora FROM resultados)"
            ).fetchone()[0]

    def search(
        self,
        tipo="Todos",
        valor="",
        date_from=None,
        date_to=None,
        sorteio="Todos",
        hora="Todos",
        premio="Todos",
    ):
        where = []
        args = []

        if date_from:
            where.append("data >= ?")
            args.append(date_from)
        if date_to:
            where.append("data <= ?")
            args.append(date_to)
        if sorteio != "Todos":
            where.append("sorteio = ?")
            args.append(sorteio)
        if hora != "Todos":
            where.append("hora = ?")
            args.append(hora)
        if premio != "Todos":
            where.append("premio = ?")
            args.append(int(premio))

        tipo = tipo.strip()
        valor_norm = sem_acento(valor)

        if tipo == "Bicho" and valor_norm:
            # bicho é buscado sem acento para aceitar "pavao"/"pavão".
            grupos = [g for g, n in BICHOS_NORMALIZADOS.items() if valor_norm in n]
            if grupos:
                q = ",".join("?" for _ in grupos)
                where.append(f"grupo IN ({q})")
                args.extend(grupos)
            else:
                where.append("1=0")
        elif tipo == "Grupo" and valor.strip():
            try:
                g = int(re.sub(r"\D", "", valor))
                where.append("grupo = ?")
                args.append(g)
            except ValueError:
                where.append("1=0")
        elif tipo == "Dezena" and valor.strip():
            v = re.sub(r"\D", "", valor)[-2:].zfill(2)
            where.append("dezena = ?")
            args.append(v)
        elif tipo == "Centena" and valor.strip():
            v = re.sub(r"\D", "", valor)[-3:].zfill(3)
            where.append("centena = ?")
            args.append(v)
        elif tipo == "Milhar" and valor.strip():
            v = re.sub(r"\D", "", valor)[-4:].zfill(4)
            where.append("milhar = ?")
            args.append(v)
        elif tipo == "Todos" and valor.strip():
            digits = re.sub(r"\D", "", valor)
            if digits:
                clauses = []
                local = []
                if len(digits) <= 2:
                    clauses += ["dezena = ?", "grupo = ?"]
                    local += [digits[-2:].zfill(2), int(digits)]
                if len(digits) <= 3:
                    clauses.append("centena = ?")
                    local.append(digits[-3:].zfill(3))
                clauses.append("milhar = ?")
                local.append(digits[-4:].zfill(4))
                where.append("(" + " OR ".join(clauses) + ")")
                args.extend(local)
            else:
                grupos = [g for g, n in BICHOS_NORMALIZADOS.items() if valor_norm in n]
                if grupos:
                    q = ",".join("?" for _ in grupos)
                    where.append(f"grupo IN ({q})")
                    args.extend(grupos)
                else:
                    where.append("1=0")

        sql = """
            SELECT data, sorteio, hora, premio, milhar, centena, dezena, grupo, bicho, fonte
            FROM resultados
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY data DESC, hora DESC, sorteio DESC, premio ASC"

        with self.connect() as con:
            return con.execute(sql, args).fetchall()


    def search_filter_options(
        self,
        date_from=None,
        date_to=None,
        selected_sort="Todos",
        selected_hour="Todos",
    ):
        """
        Opções dependentes do painel principal.

        - Sorteios disponíveis respeitam o período e, quando escolhido, a hora.
        - Horas disponíveis respeitam o período e, quando escolhido, o sorteio.
        """
        date_where = []
        date_args = []
        if date_from:
            date_where.append("data >= ?")
            date_args.append(date_from)
        if date_to:
            date_where.append("data <= ?")
            date_args.append(date_to)

        # Sorteios válidos no período e na hora selecionada.
        sort_where = list(date_where)
        sort_args = list(date_args)
        if selected_hour != "Todos":
            sort_where.append("hora = ?")
            sort_args.append(selected_hour)

        sort_sql = "SELECT DISTINCT sorteio FROM resultados"
        if sort_where:
            sort_sql += " WHERE " + " AND ".join(sort_where)
        sort_sql += " ORDER BY sorteio"

        # Horas válidas no período e no sorteio selecionado.
        hour_where = list(date_where)
        hour_args = list(date_args)
        if selected_sort != "Todos":
            hour_where.append("sorteio = ?")
            hour_args.append(selected_sort)

        hour_sql = "SELECT DISTINCT hora FROM resultados"
        if hour_where:
            hour_sql += " WHERE " + " AND ".join(hour_where)
        hour_sql += " ORDER BY hora"

        with self.connect() as con:
            sorts = [r[0] for r in con.execute(sort_sql, sort_args)]
            hours = [r[0] for r in con.execute(hour_sql, hour_args)]

        return sorts, hours

    def search_filter_combination_exists(
        self,
        date_from=None,
        date_to=None,
        sorteio="Todos",
        hora="Todos",
    ):
        where = []
        args = []

        if date_from:
            where.append("data >= ?")
            args.append(date_from)
        if date_to:
            where.append("data <= ?")
            args.append(date_to)
        if sorteio != "Todos":
            where.append("sorteio = ?")
            args.append(sorteio)
        if hora != "Todos":
            where.append("hora = ?")
            args.append(hora)

        sql = "SELECT 1 FROM resultados"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " LIMIT 1"

        with self.connect() as con:
            return con.execute(sql, args).fetchone() is not None

    def draw_combo_options(self, date_from=None, date_to=None):
        """Retorna somente pares reais (sorteio, hora) existentes na base."""
        where = []
        args = []

        if date_from:
            where.append("data >= ?")
            args.append(date_from)
        if date_to:
            where.append("data <= ?")
            args.append(date_to)

        sql = "SELECT DISTINCT sorteio, hora FROM resultados"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY hora, sorteio"

        with self.connect() as con:
            return [(r[0], r[1]) for r in con.execute(sql, args)]


    def filter_options(self):
        with self.connect() as con:
            sorteios = [r[0] for r in con.execute(
                "SELECT DISTINCT sorteio FROM resultados ORDER BY sorteio"
            )]
            horas = [r[0] for r in con.execute(
                "SELECT DISTINCT hora FROM resultados ORDER BY hora"
            )]
        return sorteios, horas


    def latest_date(self) -> date | None:
        with self.connect() as con:
            row = con.execute("SELECT MAX(data) FROM resultados").fetchone()
        if not row or not row[0]:
            return None
        return datetime.strptime(row[0], "%Y-%m-%d").date()

    def existing_prize_map(self, start_date: str | None = None, end_date: str | None = None):
        where = []
        args = []
        if start_date:
            where.append("data >= ?")
            args.append(start_date)
        if end_date:
            where.append("data <= ?")
            args.append(end_date)
        sql = """
            SELECT data, sorteio, hora, premio, milhar, centena, dezena, grupo, bicho
            FROM resultados
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self.connect() as con:
            rows = con.execute(sql, args).fetchall()
        return {
            (r["data"], r["sorteio"], r["hora"], r["premio"]): {
                "milhar": r["milhar"],
                "centena": r["centena"],
                "dezena": r["dezena"],
                "grupo": r["grupo"],
                "bicho": r["bicho"],
            }
            for r in rows
        }

    def compare_web_rows(self, rows: list[PrizeRow]):
        """
        Separa resultados encontrados na internet em:
        - novos: chave data/sorteio/hora/prêmio ainda não existente;
        - alterados: mesma chave, mas milhar/grupo/bicho diferente;
        - iguais: já armazenados exatamente.
        """
        if not rows:
            return [], [], 0
        start = min(r.data for r in rows)
        end = max(r.data for r in rows)
        current = self.existing_prize_map(start, end)
        novos = []
        alterados = []
        iguais = 0
        for r in rows:
            key = (r.data, r.sorteio, r.hora, r.premio)
            old = current.get(key)
            if old is None:
                novos.append(r)
                continue
            if (
                old["milhar"] != r.milhar
                or old["grupo"] != r.grupo
                or sem_acento(old["bicho"]) != sem_acento(r.bicho)
            ):
                alterados.append((r, old))
            else:
                iguais += 1
        return novos, alterados, iguais


    def stats_by_animal(self, date_from=None, date_to=None, sorteio="Todos", hora="Todos", premio="Todos"):
        where = []
        args = []

        if date_from:
            where.append("data >= ?")
            args.append(date_from)
        if date_to:
            where.append("data <= ?")
            args.append(date_to)
        if sorteio != "Todos":
            where.append("sorteio = ?")
            args.append(sorteio)
        if hora != "Todos":
            where.append("hora = ?")
            args.append(hora)
        if premio != "Todos":
            where.append("premio = ?")
            args.append(int(premio))

        clause = (" WHERE " + " AND ".join(where)) if where else ""

        with self.connect() as con:
            total_prizes = con.execute(
                "SELECT COUNT(*) FROM resultados" + clause, args
            ).fetchone()[0]

            total_draws = con.execute(
                "SELECT COUNT(*) FROM (SELECT DISTINCT data,sorteio,hora FROM resultados"
                + clause + ")",
                args
            ).fetchone()[0]

            rows = con.execute(
                """
                SELECT
                    grupo,
                    bicho,
                    COUNT(*) AS ocorrencias,
                    COUNT(DISTINCT data || '|' || sorteio || '|' || hora) AS extracoes_com_bicho,
                    SUM(CASE WHEN premio=1 THEN 1 ELSE 0 END) AS p1,
                    SUM(CASE WHEN premio=2 THEN 1 ELSE 0 END) AS p2,
                    SUM(CASE WHEN premio=3 THEN 1 ELSE 0 END) AS p3,
                    SUM(CASE WHEN premio=4 THEN 1 ELSE 0 END) AS p4,
                    SUM(CASE WHEN premio=5 THEN 1 ELSE 0 END) AS p5,
                    MAX(data || '|' || hora || '|' || sorteio || '|' || premio || '|' || milhar) AS ultima_chave
                FROM resultados
                """
                + clause +
                """
                GROUP BY grupo, bicho
                ORDER BY ocorrencias DESC, grupo ASC
                """,
                args,
            ).fetchall()

        out = []
        for r in rows:
            pct_prizes = (r["ocorrencias"] / total_prizes * 100) if total_prizes else 0.0
            pct_draws = (r["extracoes_com_bicho"] / total_draws * 100) if total_draws else 0.0
            last = None
            if r["ultima_chave"]:
                parts = r["ultima_chave"].split("|")
                if len(parts) >= 5:
                    last = {
                        "data": parts[0],
                        "hora": parts[1],
                        "sorteio": parts[2],
                        "premio": int(parts[3]),
                        "milhar": parts[4],
                    }
            out.append({
                "grupo": r["grupo"],
                "bicho": r["bicho"],
                "ocorrencias": r["ocorrencias"],
                "extracoes_com_bicho": r["extracoes_com_bicho"],
                "pct_premios": pct_prizes,
                "pct_extracoes": pct_draws,
                "p1": r["p1"], "p2": r["p2"], "p3": r["p3"], "p4": r["p4"], "p5": r["p5"],
                "ultima": last,
            })

        return {
            "total_prizes": total_prizes,
            "total_draws": total_draws,
            "rows": out,
        }

    def animal_hour_breakdown(self, grupo: int, date_from=None, date_to=None):
        where = ["grupo = ?"]
        args = [int(grupo)]
        if date_from:
            where.append("data >= ?")
            args.append(date_from)
        if date_to:
            where.append("data <= ?")
            args.append(date_to)

        clause = " WHERE " + " AND ".join(where)
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT sorteio, hora, COUNT(*) AS ocorrencias,
                       COUNT(DISTINCT data || '|' || sorteio || '|' || hora) AS extracoes
                FROM resultados
                """
                + clause +
                """
                GROUP BY sorteio, hora
                ORDER BY hora, sorteio
                """,
                args,
            ).fetchall()
        return [dict(r) for r in rows]

    def animal_recent_occurrences(self, grupo: int, limit=20, date_from=None, date_to=None):
        where = ["grupo = ?"]
        args = [int(grupo)]
        if date_from:
            where.append("data >= ?")
            args.append(date_from)
        if date_to:
            where.append("data <= ?")
            args.append(date_to)

        clause = " WHERE " + " AND ".join(where)
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT data,sorteio,hora,premio,milhar,centena,dezena,grupo,bicho
                FROM resultados
                """
                + clause +
                """
                ORDER BY data DESC, hora DESC, premio ASC
                LIMIT ?
                """,
                args + [int(limit)],
            ).fetchall()
        return [dict(r) for r in rows]



    def list_draws(self, date_from=None, date_to=None):
        """Lista extrações cadastradas em ordem cronológica."""
        draws = self._draws_in_order()
        out = []
        for d in draws:
            if date_from and d["data"] < date_from:
                continue
            if date_to and d["data"] > date_to:
                continue
            out.append(d)
        return out

    def get_draw(self, draw_date, sorteio, hora):
        for d in self._draws_in_order():
            if d["data"] == draw_date and d["sorteio"] == sorteio and d["hora"] == hora:
                return d
        return None

    def latest_draw(self):
        draws = self._draws_in_order()
        return draws[-1] if draws else None

    def draw_filter_options(self, draw_date=None):
        where = []
        args = []
        if draw_date:
            where.append("data = ?")
            args.append(draw_date)

        sort_sql = "SELECT DISTINCT sorteio FROM resultados"
        hour_sql = "SELECT DISTINCT hora FROM resultados"
        if where:
            clause = " WHERE " + " AND ".join(where)
            sort_sql += clause
            hour_sql += clause
        sort_sql += " ORDER BY sorteio"
        hour_sql += " ORDER BY hora"

        with self.connect() as con:
            sorts = [r[0] for r in con.execute(sort_sql, args)]
            hours = [r[0] for r in con.execute(hour_sql, args)]
        return sorts, hours

    def _draws_in_order(self):
        """
        Reconstrói as extrações em ordem cronológica a partir dos 5 prêmios.
        Cada item contém a chave da extração e a lista dos 5 prêmios.
        """
        with self.connect() as con:
            rows = con.execute("""
                SELECT data, sorteio, hora, premio, milhar, centena, dezena, grupo, bicho
                FROM resultados
                ORDER BY data ASC, hora ASC, sorteio ASC, premio ASC
            """).fetchall()

        draws = []
        current_key = None
        current = None

        for r in rows:
            key = (r["data"], r["sorteio"], r["hora"])
            if key != current_key:
                current_key = key
                current = {
                    "data": r["data"],
                    "sorteio": r["sorteio"],
                    "hora": r["hora"],
                    "prizes": [],
                }
                draws.append(current)
            current["prizes"].append({
                "premio": r["premio"],
                "milhar": r["milhar"],
                "centena": r["centena"],
                "dezena": r["dezena"],
                "grupo": r["grupo"],
                "bicho": r["bicho"],
            })
        return draws


    # ========================================================
    # GP-H RESET COBERTURA v1 — SELETOR OFICIAL
    # Configuração validada: last240 | pull | pair3 | probability
    # ========================================================
    def _is_operational_draw(self, draw):
        weekday = datetime.strptime(draw["data"], "%Y-%m-%d").weekday()
        name = draw["sorteio"]

        if weekday == 6:  # domingo
            return name in ("PT", "PTV")

        if weekday == 5:  # sábado
            return name in ("PPT", "PTM", "PT", "PTV", "CORUJA")

        return name in ("PPT", "PTM", "PT", "PTV", "PTN", "CORUJA")

    def latest_operational_draw(self):
        for draw in reversed(self._draws_in_order()):
            if self._is_operational_draw(draw):
                return draw
        return None

    def _reset_find_draw_index(self, draws, draw_date, sorteio, hora):
        for i, d in enumerate(draws):
            if (
                d["data"] == draw_date
                and d["sorteio"] == sorteio
                and d["hora"] == hora
            ):
                return i
        return None

    def _reset_next_operational_existing(self, draws, source_index):
        for i in range(source_index + 1, len(draws)):
            if self._is_operational_draw(draws[i]):
                return i, draws[i]
        return None, None

    def _reset_expected_target(self, source_draw):
        day = datetime.strptime(source_draw["data"], "%Y-%m-%d")
        weekday = day.weekday()
        source_sort = source_draw["sorteio"]

        weekday_sequence = [
            ("PPT", "09:00"),
            ("PTM", "11:00"),
            ("PT", "14:00"),
            ("PTV", "16:00"),
            ("PTN", "18:00"),
            ("CORUJA", "21:00"),
        ]
        saturday_sequence = [
            ("PPT", "09:00"),
            ("PTM", "11:00"),
            ("PT", "14:00"),
            ("PTV", "16:00"),
            ("CORUJA", "21:00"),
        ]
        sunday_sequence = [
            ("PT", "14:00"),
            ("PTV", "16:00"),
        ]

        if weekday == 5:
            sequence = saturday_sequence
        elif weekday == 6:
            sequence = sunday_sequence
        else:
            sequence = weekday_sequence

        pos = next(
            (i for i, item in enumerate(sequence) if item[0] == source_sort),
            None,
        )

        if pos is not None and pos + 1 < len(sequence):
            nxt_sort, nxt_hour = sequence[pos + 1]
            return {
                "data": source_draw["data"],
                "sorteio": nxt_sort,
                "hora": nxt_hour,
                "derived": True,
            }

        next_date = (day + timedelta(days=1)).strftime("%Y-%m-%d")

        if weekday == 5:
            return {
                "data": next_date,
                "sorteio": "PT",
                "hora": "14:00",
                "derived": True,
                "sunday_skip": True,
            }

        return {
            "data": next_date,
            "sorteio": "PPT",
            "hora": "09:00",
            "derived": True,
        }

    @staticmethod
    def _reset_presence(draw):
        out = [0.0] * 25
        for p in draw["prizes"]:
            group = int(p["grupo"])
            if 1 <= group <= 25:
                out[group - 1] = 1.0
        return out


    def next_operational_target(self):
        latest = self.latest_operational_draw()
        if not latest:
            return None

        target = dict(self._reset_expected_target(latest))
        target["base_data"] = latest["data"]
        target["base_sorteio"] = latest["sorteio"]
        target["base_hora"] = latest["hora"]
        return target

    def future_operational_targets(self, count=12):
        current = self.latest_operational_draw()
        if not current:
            return []

        targets = []
        source = current

        for _ in range(max(1, int(count))):
            target = dict(self._reset_expected_target(source))
            targets.append(target)
            source = {
                "data": target["data"],
                "sorteio": target["sorteio"],
                "hora": target["hora"],
                "prizes": [],
            }

        return targets

    def is_next_operational_target(self, target):
        nxt = self.next_operational_target()
        if not nxt or not target:
            return False
        return (
            nxt.get("data"),
            nxt.get("sorteio"),
            nxt.get("hora"),
        ) == (
            target.get("data"),
            target.get("sorteio"),
            target.get("hora"),
        )

    def pending_operational_games_for_target(self, target):
        if not target:
            return []

        pending = []
        for game in self.list_frozen_games(limit=1000000):
            if game["status"] != "PENDENTE":
                continue
            if game["alvo_modo"] != "PROXIMA_OPERACIONAL":
                continue

            base = self.get_draw(
                game["base_data"],
                game["base_sorteio"],
                game["base_hora"],
            )
            if not base:
                continue

            expected = self._reset_expected_target(base)
            if (
                expected["data"] == target["data"]
                and expected["sorteio"] == target["sorteio"]
                and expected["hora"] == target["hora"]
            ):
                pending.append(game)

        return pending

    def pending_game_count(self):
        with self.connect() as con:
            return int(
                con.execute("""
                    SELECT COUNT(*)
                    FROM jogos_congelados
                    WHERE status='PENDENTE'
                """).fetchone()[0]
            )

    def _operational_schedule_for_date(self, iso_date):
        weekday = datetime.strptime(iso_date, "%Y-%m-%d").weekday()

        if weekday == 6:
            return [("PT", "14:00"), ("PTV", "16:00")]
        if weekday == 5:
            return [
                ("PPT", "09:00"),
                ("PTM", "11:00"),
                ("PT", "14:00"),
                ("PTV", "16:00"),
                ("CORUJA", "21:00"),
            ]
        return [
            ("PPT", "09:00"),
            ("PTM", "11:00"),
            ("PT", "14:00"),
            ("PTV", "16:00"),
            ("PTN", "18:00"),
            ("CORUJA", "21:00"),
        ]

    def possible_operational_gaps(self, limit=500):
        latest = self.latest_operational_draw()
        if not latest:
            return []

        with self.connect() as con:
            first = con.execute(
                "SELECT MIN(data) FROM resultados"
            ).fetchone()[0]

            existing = {
                (r["data"], r["sorteio"], r["hora"])
                for r in con.execute("""
                    SELECT DISTINCT data, sorteio, hora
                    FROM resultados
                """).fetchall()
            }

        if not first:
            return []

        start = datetime.strptime(first, "%Y-%m-%d").date()
        end = datetime.strptime(latest["data"], "%Y-%m-%d").date()
        gaps = []
        current = start

        while current <= end:
            iso = current.isoformat()
            schedule = self._operational_schedule_for_date(iso)

            if iso == latest["data"]:
                last_index = next(
                    (
                        i for i, pair in enumerate(schedule)
                        if pair[0] == latest["sorteio"]
                        and pair[1] == latest["hora"]
                    ),
                    len(schedule) - 1,
                )
            else:
                last_index = len(schedule) - 1

            for idx, (sorteio, hora) in enumerate(schedule):
                if idx > last_index:
                    continue

                if (iso, sorteio, hora) not in existing:
                    gaps.append({
                        "data": iso,
                        "sorteio": sorteio,
                        "hora": hora,
                    })
                    if len(gaps) >= int(limit):
                        return gaps

            current += timedelta(days=1)

        return gaps

    def record_network_check(self, check_type, error_count):
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO meta(chave, valor) VALUES(?, ?)",
                ("last_network_check_type", str(check_type)),
            )
            con.execute(
                "INSERT OR REPLACE INTO meta(chave, valor) VALUES(?, ?)",
                (
                    "last_network_check_at",
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            con.execute(
                "INSERT OR REPLACE INTO meta(chave, valor) VALUES(?, ?)",
                ("last_network_error_count", str(int(error_count))),
            )

    def _meta_value(self, key, default=None):
        with self.connect() as con:
            row = con.execute(
                "SELECT valor FROM meta WHERE chave=?",
                (key,),
            ).fetchone()
        return row["valor"] if row else default

    def base_health(self):
        audit = self.audit()
        gaps = self.possible_operational_gaps()

        last_check = self._meta_value("last_network_check_at")
        last_check_type = self._meta_value("last_network_check_type")

        try:
            last_errors = int(
                self._meta_value("last_network_error_count", "0") or 0
            )
        except Exception:
            last_errors = 0

        structural_ok = (
            not audit["problems"]
            and not audit["incomplete"]
        )

        if not structural_ok:
            state = "ALERTA ESTRUTURAL"
        elif gaps:
            state = "OK ESTRUTURAL • REVISAR LACUNAS"
        else:
            state = "OK"

        return {
            "state": state,
            "audit": audit,
            "possible_gaps": gaps,
            "possible_gap_count": len(gaps),
            "pending_games": self.pending_game_count(),
            "last_network_check": last_check,
            "last_network_check_type": last_check_type,
            "last_network_errors": last_errors,
        }

    def auto_backup(self, reason="automatico", keep=5):
        backup_dir = Path(self.path).parent / "backups_automaticos"
        backup_dir.mkdir(parents=True, exist_ok=True)

        safe_reason = re.sub(
            r"[^A-Za-z0-9_-]+",
            "_",
            str(reason),
        ).strip("_") or "automatico"

        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        target = backup_dir / f"GP-H_auto_{safe_reason}_{stamp}.db"
        self.backup_to(target)

        backups = sorted(
            backup_dir.glob("GP-H_auto_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for old in backups[max(1, int(keep)):]:
            try:
                old.unlink()
            except Exception:
                pass

        return target


    def method_reset_coverage_v1(
        self,
        draw_date,
        sorteio,
        hora,
        top_n=5,
    ):
        """
        GP-H Reset Cobertura v1.

        Configuração oficial congelada:
          last240 | pull | pair3 | probability

        Fórmula portada do Reset Lab original.
        """
        top_n = max(1, min(10, int(top_n)))

        draws = self._draws_in_order()
        source_index = self._reset_find_draw_index(
            draws, draw_date, sorteio, hora
        )
        if source_index is None:
            raise ValueError("Extração-base não encontrada.")

        source_draw = draws[source_index]
        if len(source_draw["prizes"]) < 5:
            raise ValueError("A extração-base não possui 5 prêmios completos.")

        target_index, target_draw = self._reset_next_operational_existing(
            draws, source_index
        )

        if target_draw is None:
            target = self._reset_expected_target(source_draw)
            target_existing = False
        else:
            target = {
                "data": target_draw["data"],
                "sorteio": target_draw["sorteio"],
                "hora": target_draw["hora"],
                "derived": False,
            }
            target_existing = True

        # No Reset Lab, para prever o alvo após a base em source_index,
        # são conhecidas as transições j -> j+1 com j < source_index.
        train = list(range(max(0, source_index - 240), source_index))

        if len(train) < 35:
            raise ValueError(
                f"Base insuficiente para o Reset: {len(train)} transições; mínimo 35."
            )

        destination = [
            self._reset_presence(draws[j + 1])
            for j in train
        ]

        target_sort = target["sorteio"]

        sunday_skip = bool(
            datetime.strptime(source_draw["data"], "%Y-%m-%d").weekday() == 5
            and source_draw["sorteio"] == "CORUJA"
            and target_sort == "PT"
        )

        context_mode = "none" if sunday_skip else "pair3"

        context_weights = []
        pair3_matches = 0

        for j in train:
            weight = 1.0
            if context_mode == "pair3":
                if (
                    draws[j]["sorteio"] == source_draw["sorteio"]
                    and draws[j + 1]["sorteio"] == target_sort
                ):
                    weight = 3.0
                    pair3_matches += 1
            context_weights.append(weight)

        total_weight = sum(context_weights)

        # prior = (context @ destination + 5*0.18)/(sum(context)+5)
        prior = []
        for col in range(25):
            weighted_hits = sum(
                context_weights[row] * destination[row][col]
                for row in range(len(train))
            )
            prior.append(
                (weighted_hits + 5.0 * 0.18)
                / (total_weight + 5.0)
            )

        # Multiplicidade atual.
        current_counts = [0.0] * 25
        for p in source_draw["prizes"]:
            current_counts[int(p["grupo"]) - 1] += 1.0

        pull = [0.0] * 25
        pull_den = 0.0
        source_details = []

        source_presence_cache = [
            self._reset_presence(draws[j])
            for j in train
        ]

        for source_col, multiplicity in enumerate(current_counts):
            if multiplicity <= 0:
                continue

            eligible = [
                pos
                for pos in range(len(train))
                if source_presence_cache[pos][source_col] > 0
            ]

            eligible_weights = [
                context_weights[pos]
                for pos in eligible
            ]
            eligible_weight_sum = sum(eligible_weights)

            probability = []

            if eligible_weight_sum <= 0:
                probability = list(prior)
            else:
                for target_col in range(25):
                    weighted_hits = sum(
                        eligible_weights[k]
                        * destination[eligible[k]][target_col]
                        for k in range(len(eligible))
                    )
                    probability.append(
                        (weighted_hits + 7.0 * prior[target_col])
                        / (eligible_weight_sum + 7.0)
                    )

            for target_col in range(25):
                pull[target_col] += (
                    multiplicity * probability[target_col]
                )

            pull_den += multiplicity

            order_source = sorted(
                range(25),
                key=lambda idx: (-probability[idx], idx),
            )[:5]

            source_details.append({
                "grupo": source_col + 1,
                "bicho": BICHOS[source_col + 1],
                "multiplicity": int(multiplicity),
                "support": len(eligible),
                "weight_sum": eligible_weight_sum,
                "top5": [
                    {
                        "grupo": idx + 1,
                        "bicho": BICHOS[idx + 1],
                        "prob": probability[idx] * 100.0,
                    }
                    for idx in order_source
                ],
            })

        if pull_den > 0:
            pull = [value / pull_den for value in pull]
        else:
            pull = list(prior)

        order = sorted(
            range(25),
            key=lambda idx: (-pull[idx], idx),
        )

        ranking = [
            {
                "grupo": idx + 1,
                "bicho": BICHOS[idx + 1],
                "score": pull[idx],
                "score_pct": pull[idx] * 100.0,
                "prior": prior[idx],
                "prior_pct": prior[idx] * 100.0,
            }
            for idx in order
        ]

        return {
            "method": "GP-H Reset Cobertura v1",
            "official": True,
            "config": {
                "window": "last240",
                "family": "pull",
                "context": context_mode,
                "validated_context": "pair3",
                "ranking": "probability",
            },
            "base": source_draw,
            "target": target,
            "target_existing": target_existing,
            "training_transitions": len(train),
            "pair3_matches": pair3_matches,
            "context_mode": context_mode,
            "sunday_skip": sunday_skip,
            "source_details": source_details,
            "ranking": ranking,
            "selected": ranking[:top_n],
            "lookahead_safe": True,
        }


    def historical_pulls(
        self,
        base_group: int,
        state="Geral",
        date_from=None,
        date_to=None,
        source_sort="Todos",
        source_hour="Todos",
        before_draw_key=None,
    ):
        """
        Mede o que apareceu na extração imediatamente seguinte quando o bicho-base
        esteve presente na extração de origem.

        state:
          Geral = bicho presente 1 ou mais vezes
          ×1    = exatamente uma ocorrência na origem
          ×2    = exatamente duas ocorrências
          ×3+   = três ou mais ocorrências

        Métricas:
          suporte = número de extrações-base válidas
          acertos = número de extrações seguintes em que o alvo apareceu >=1 vez
          prob = acertos / suporte
          baseline = probabilidade do alvo na extração seguinte dentro do mesmo
                     contexto de origem, sem exigir o bicho-base
          lift = prob / baseline
        """
        base_group = int(base_group)
        draws = self._draws_in_order()

        cutoff_index = None
        if before_draw_key is not None:
            for idx, d in enumerate(draws):
                key = (d["data"], d["sorteio"], d["hora"])
                if key == tuple(before_draw_key):
                    cutoff_index = idx
                    break
            if cutoff_index is None:
                raise ValueError("Extração-base não encontrada para aplicar o corte temporal.")

        def source_context_ok(draw):
            if date_from and draw["data"] < date_from:
                return False
            if date_to and draw["data"] > date_to:
                return False
            if source_sort != "Todos" and draw["sorteio"] != source_sort:
                return False
            if source_hour != "Todos" and draw["hora"] != source_hour:
                return False
            return True

        def state_ok(count):
            if state == "Geral":
                return count >= 1
            if state == "×1":
                return count == 1
            if state == "×2":
                return count == 2
            if state == "×3+":
                return count >= 3
            return count >= 1

        # baseline no MESMO contexto de origem, mas sem exigir o bicho-base
        baseline_support = 0
        baseline_hits = {g: 0 for g in range(1, 26)}

        support = 0
        hit_draws = {g: 0 for g in range(1, 26)}
        total_occ = {g: 0 for g in range(1, 26)}
        pos_counts = {g: [0, 0, 0, 0, 0] for g in range(1, 26)}
        transitions = {}
        examples = {g: [] for g in range(1, 26)}

        max_i = len(draws) - 1
        if cutoff_index is not None:
            # Só usa transições cuja extração seguinte ocorreu ANTES ou,
            # no máximo, imediatamente antes da extração-base selecionada.
            # Assim, nenhuma informação posterior à base entra no cálculo.
            max_i = min(max_i, cutoff_index)

        for i in range(max_i):
            source = draws[i]
            target = draws[i + 1]

            if not source_context_ok(source):
                continue

            target_groups = [p["grupo"] for p in target["prizes"]]
            target_unique = set(target_groups)

            baseline_support += 1
            for g in target_unique:
                baseline_hits[g] += 1

            source_count = sum(1 for p in source["prizes"] if p["grupo"] == base_group)
            if not state_ok(source_count):
                continue

            support += 1
            trans_key = (
                source["sorteio"], source["hora"],
                target["sorteio"], target["hora"]
            )
            transitions[trans_key] = transitions.get(trans_key, 0) + 1

            for g in target_unique:
                hit_draws[g] += 1

            for p in target["prizes"]:
                g = p["grupo"]
                total_occ[g] += 1
                premio = int(p["premio"])
                if 1 <= premio <= 5:
                    pos_counts[g][premio - 1] += 1

            for g in target_unique:
                if len(examples[g]) < 40:
                    examples[g].append({
                        "source": source,
                        "target": target,
                        "source_count": source_count,
                    })

        ranking = []
        for g in range(1, 26):
            prob = (hit_draws[g] / support * 100.0) if support else 0.0
            base_prob = (
                baseline_hits[g] / baseline_support * 100.0
                if baseline_support else 0.0
            )
            lift = (prob / base_prob) if base_prob > 0 else 0.0

            ranking.append({
                "grupo": g,
                "bicho": BICHOS[g],
                "hit_draws": hit_draws[g],
                "prob": prob,
                "baseline_prob": base_prob,
                "lift": lift,
                "total_occ": total_occ[g],
                "p1": pos_counts[g][0],
                "p2": pos_counts[g][1],
                "p3": pos_counts[g][2],
                "p4": pos_counts[g][3],
                "p5": pos_counts[g][4],
                "examples": examples[g],
            })

        # Primeiro cobertura, depois lift, depois ocorrências; grupo só desempata.
        ranking.sort(
            key=lambda r: (-r["prob"], -r["lift"], -r["total_occ"], r["grupo"])
        )

        transition_rows = [
            {
                "source_sort": k[0],
                "source_hour": k[1],
                "target_sort": k[2],
                "target_hour": k[3],
                "count": v,
            }
            for k, v in transitions.items()
        ]
        transition_rows.sort(key=lambda r: (-r["count"], r["source_hour"], r["target_hour"]))

        return {
            "base_group": base_group,
            "base_bicho": BICHOS[base_group],
            "state": state,
            "support": support,
            "baseline_support": baseline_support,
            "ranking": ranking,
            "transitions": transition_rows,
        }


    def method_convergencia_g5(
        self,
        draw_date,
        sorteio,
        hora,
        top_n=5,
        min_state_support=5,
    ):
        """
        Primeiro método implementado no laboratório.

        Regras:
        1. Usa os 5 bichos da extração-base.
        2. Para cada bicho-base, respeita sua multiplicidade na própria extração:
           ×1, ×2 ou ×3+.
        3. Se o estado específico tiver suporte menor que min_state_support,
           recua para a tabela Geral daquele bicho.
        4. Cada bicho-base aponta seus 3 alvos mais fortes.
        5. Ranking final:
           - número de fontes distintas apontando o alvo;
           - soma das coberturas históricas;
           - média de lift;
           - grupo apenas como desempate final.
        6. Usa somente transições anteriores à extração-base selecionada
           (sem look-ahead).
        """
        top_n = max(1, min(25, int(top_n)))
        base = self.get_draw(draw_date, sorteio, hora)
        if not base:
            raise ValueError("Extração-base não encontrada.")

        counts = {}
        for p in base["prizes"]:
            g = p["grupo"]
            counts[g] = counts.get(g, 0) + 1

        cutoff = (draw_date, sorteio, hora)
        signals = {g: {
            "grupo": g,
            "bicho": BICHOS[g],
            "sources": [],
            "source_count": 0,
            "sum_prob": 0.0,
            "avg_lift": 0.0,
        } for g in range(1, 26)}

        source_details = []

        for source_group, multiplicity in sorted(counts.items()):
            if multiplicity == 1:
                desired_state = "×1"
            elif multiplicity == 2:
                desired_state = "×2"
            else:
                desired_state = "×3+"

            specific = self.historical_pulls(
                source_group,
                state=desired_state,
                before_draw_key=cutoff,
            )

            used = specific
            fallback = False
            if specific["support"] < int(min_state_support):
                used = self.historical_pulls(
                    source_group,
                    state="Geral",
                    before_draw_key=cutoff,
                )
                fallback = True

            top3 = used["ranking"][:3]
            source_details.append({
                "grupo": source_group,
                "bicho": BICHOS[source_group],
                "multiplicity": multiplicity,
                "desired_state": desired_state,
                "used_state": used["state"],
                "support": used["support"],
                "fallback": fallback,
                "top3": [
                    {
                        "grupo": r["grupo"],
                        "bicho": r["bicho"],
                        "prob": r["prob"],
                        "lift": r["lift"],
                        "hit_draws": r["hit_draws"],
                    }
                    for r in top3
                ],
            })

            for r in top3:
                t = signals[r["grupo"]]
                t["sources"].append({
                    "grupo": source_group,
                    "bicho": BICHOS[source_group],
                    "state": used["state"],
                    "prob": r["prob"],
                    "lift": r["lift"],
                    "support": used["support"],
                })
                t["source_count"] += 1
                t["sum_prob"] += r["prob"]

        ranking = []
        for g, rec in signals.items():
            if rec["source_count"]:
                rec["avg_lift"] = sum(s["lift"] for s in rec["sources"]) / rec["source_count"]
            ranking.append(rec)

        ranking.sort(
            key=lambda r: (
                -r["source_count"],
                -r["sum_prob"],
                -r["avg_lift"],
                r["grupo"],
            )
        )

        # Conta quantas transições históricas estavam disponíveis antes da base.
        all_draws = self._draws_in_order()
        base_idx = next(
            (i for i, d in enumerate(all_draws)
             if (d["data"], d["sorteio"], d["hora"]) == cutoff),
            None,
        )

        return {
            "method": "Convergência Histórica G5",
            "base": base,
            "base_counts": counts,
            "source_details": source_details,
            "ranking": ranking,
            "selected": ranking[:top_n],
            "top_n": top_n,
            "historical_draws_before": base_idx if base_idx is not None else 0,
            "lookahead_safe": True,
            "min_state_support": int(min_state_support),
        }


    def number_rankings_for_group(self, group: int, kind="Centena", scope="1º–5º", date_to=None):
        """
        Ranking histórico dos números válidos de um grupo.

        kind:
          Dezena, Centena ou Milhar

        scope:
          1º–5º = todos os cinco prêmios
          1º     = somente primeiro prêmio

        Ordenação:
          1) maior nº de ocorrências;
          2) ocorrência mais recente;
          3) menor valor numérico apenas para desempate final.

        Candidatos nunca observados também entram com frequência zero para que
        o gerador consiga completar uma quantidade solicitada sem inventar
        números fora do grupo.
        """
        group = int(group)
        if group < 1 or group > 25:
            raise ValueError("Grupo inválido.")

        if kind not in ("Dezena", "Centena", "Milhar"):
            raise ValueError("Tipo numérico inválido.")

        field = {
            "Dezena": "dezena",
            "Centena": "centena",
            "Milhar": "milhar",
        }[kind]

        width = {
            "Dezena": 2,
            "Centena": 3,
            "Milhar": 4,
        }[kind]

        where = ["grupo = ?"]
        args = [group]
        if scope == "1º":
            where.append("premio = 1")
        elif scope != "1º–5º":
            raise ValueError("Escopo inválido.")

        if date_to:
            where.append("data <= ?")
            args.append(str(date_to))

        sql = f"""
            SELECT {field} AS numero,
                   COUNT(*) AS ocorrencias,
                   MAX(data || '|' || hora || '|' || sorteio || '|' || premio) AS ultima
            FROM resultados
            WHERE {' AND '.join(where)}
            GROUP BY {field}
        """

        with self.connect() as con:
            observed_rows = con.execute(sql, args).fetchall()

        observed = {}
        for r in observed_rows:
            observed[r["numero"]] = {
                "ocorrencias": r["ocorrencias"],
                "ultima": r["ultima"],
            }

        # Gera todos os números matematicamente pertencentes ao grupo.
        if kind == "Dezena":
            candidates = []
            start = (group - 1) * 4 + 1
            for d in range(start, start + 4):
                candidates.append(f"{d % 100:02d}")
        elif kind == "Centena":
            candidates = [
                f"{n:03d}"
                for n in range(1000)
                if grupo_da_dezena(n % 100) == group
            ]
        else:
            candidates = [
                f"{n:04d}"
                for n in range(10000)
                if grupo_da_dezena(n % 100) == group
            ]

        ranking = []
        for num in candidates:
            info = observed.get(num, {"ocorrencias": 0, "ultima": ""})
            ultima = info["ultima"] or ""
            ranking.append({
                "numero": num.zfill(width),
                "ocorrencias": int(info["ocorrencias"]),
                "ultima": ultima,
            })

        ranking.sort(
            key=lambda r: (
                -r["ocorrencias"],
                r["ultima"] == "",
                # ISO data|hora permite ordem cronológica lexicográfica.
                "" if not r["ultima"] else "".join(chr(255 - ord(c)) for c in r["ultima"]),
                int(r["numero"]),
            )
        )

        # O truque acima para string descendente é pouco legível para auditoria.
        # Reordena de forma explícita e estável em duas passagens:
        ranking.sort(key=lambda r: int(r["numero"]))
        ranking.sort(key=lambda r: r["ultima"], reverse=True)
        ranking.sort(key=lambda r: r["ocorrencias"], reverse=True)

        return ranking

    def distribute_game_counts(self, total: int, groups: list[int], kind="Centena"):
        """
        Distribui a quantidade total de números de forma equilibrada entre os
        bichos selecionados. O restante vai para os primeiros do ranking.

        Dezena tem capacidade máxima 4 por grupo.
        Centena 40 por grupo.
        Milhar 400 por grupo.
        """
        total = int(total)
        if total < 1:
            raise ValueError("A quantidade precisa ser maior que zero.")
        if not groups:
            raise ValueError("Nenhum bicho selecionado.")

        capacity = {"Dezena": 4, "Centena": 40, "Milhar": 400}[kind]
        max_total = capacity * len(groups)
        total = min(total, max_total)

        n = len(groups)
        counts = {g: 0 for g in groups}

        # Round-robin preserva equilíbrio e respeita capacidade.
        assigned = 0
        while assigned < total:
            progressed = False
            for g in groups:
                if assigned >= total:
                    break
                if counts[g] < capacity:
                    counts[g] += 1
                    assigned += 1
                    progressed = True
            if not progressed:
                break

        return counts

    def generate_historical_numbers(
        self,
        groups: list[int],
        kind="Centena",
        total=20,
        scope="1º–5º",
    ):
        """
        Gera números historicamente mais fortes para os grupos selecionados.
        """
        groups = [int(g) for g in groups]
        # Remove duplicações preservando ordem.
        unique_groups = []
        for g in groups:
            if g not in unique_groups:
                unique_groups.append(g)
        groups = unique_groups

        counts = self.distribute_game_counts(total, groups, kind=kind)
        output = []

        for rank_group, g in enumerate(groups, start=1):
            ranking = self.number_rankings_for_group(g, kind=kind, scope=scope)
            take = counts[g]
            for pos, row in enumerate(ranking[:take], start=1):
                output.append({
                    "grupo": g,
                    "bicho": BICHOS[g],
                    "numero": row["numero"],
                    "ocorrencias": row["ocorrencias"],
                    "ultima": row["ultima"],
                    "rank_no_bicho": pos,
                    "rank_bicho": rank_group,
                })

        return {
            "kind": kind,
            "scope": scope,
            "groups": groups,
            "counts": counts,
            "requested_total": int(total),
            "generated_total": len(output),
            "rows": output,
        }


    def centena_rankings_for_dezena(self, group: int, dezena: str, scope="1º–5º"):
        """
        Ranking das 10 Centenas possíveis que terminam na dezena informada.
        Usa a mesma regra histórica do ranking geral:
        frequência -> recência -> menor número como desempate técnico final.
        """
        dezena = str(dezena).zfill(2)
        ranking = self.number_rankings_for_group(
            int(group), kind="Centena", scope=scope
        )
        return [r for r in ranking if r["numero"][-2:] == dezena]

    def generate_centenas_3plus1(
        self,
        groups: list[int],
        previous_draw=None,
    ):
        """
        Regra oficial de Centenas 3+1 do projeto GP-H.

        Escopo fixo: 1º–5º.

        Para cada um dos 5 bichos:
        - ordena as 4 dezenas pela frequência histórica 1º–5º;
        - normal: 3 Centenas na dezena principal + 1 na segunda;
        - se a dezena principal apareceu em qualquer prêmio do sorteio
          imediatamente anterior, ela fica congelada por uma rodada:
          3 Centenas na segunda + 1 na terceira;
        - dentro da dezena escolhida, usa as Centenas historicamente mais fortes.

        Empates de frequência entre dezenas são mantidos transparentes nos
        metadados e resolvidos apenas pelo desempate técnico já definido
        (recência e, por fim, menor número).
        """
        unique_groups = []
        for g in [int(x) for x in groups]:
            if g not in unique_groups:
                unique_groups.append(g)

        if len(unique_groups) != 5:
            raise ValueError(
                "A regra 3+1 usa exatamente 5 bichos para gerar 20 Centenas."
            )

        if previous_draw is None:
            previous_draw = self.latest_operational_draw()
        if previous_draw is None:
            raise ValueError(
                "Não há sorteio anterior na base para verificar o congelamento."
            )

        previous_dezenas = {
            str(p["dezena"]).zfill(2)
            for p in previous_draw.get("prizes", [])
        }

        rows = []
        animals = []

        for rank_group, g in enumerate(unique_groups, start=1):
            dez_rank = self.number_rankings_for_group(
                g, kind="Dezena", scope="1º–5º"
            )

            if len(dez_rank) < 3:
                raise ValueError(
                    f"Não foi possível montar o ranking de dezenas do grupo {g:02d}."
                )

            principal = dez_rank[0]
            segunda = dez_rank[1]
            terceira = dez_rank[2]

            principal_tied = (
                principal["ocorrencias"] == segunda["ocorrencias"]
            )

            frozen = principal["numero"] in previous_dezenas

            if frozen:
                main_dez = segunda["numero"]
                extra_dez = terceira["numero"]
                main_role = "3x 2ª dezena"
                extra_role = "1x 3ª dezena"
            else:
                main_dez = principal["numero"]
                extra_dez = segunda["numero"]
                main_role = "3x principal"
                extra_role = "1x 2ª dezena"

            main_centenas = self.centena_rankings_for_dezena(
                g, main_dez, scope="1º–5º"
            )
            extra_centenas = self.centena_rankings_for_dezena(
                g, extra_dez, scope="1º–5º"
            )

            if len(main_centenas) < 3 or len(extra_centenas) < 1:
                raise ValueError(
                    f"Centenas insuficientes para o grupo {g:02d}."
                )

            animal_meta = {
                "grupo": g,
                "bicho": BICHOS[g],
                "rank_bicho": rank_group,
                "principal": principal["numero"],
                "principal_ocorrencias": principal["ocorrencias"],
                "segunda": segunda["numero"],
                "segunda_ocorrencias": segunda["ocorrencias"],
                "terceira": terceira["numero"],
                "terceira_ocorrencias": terceira["ocorrencias"],
                "principal_tied": principal_tied,
                "frozen": frozen,
                "main_dezena": main_dez,
                "extra_dezena": extra_dez,
            }
            animals.append(animal_meta)

            for pos, c in enumerate(main_centenas[:3], start=1):
                rows.append({
                    "grupo": g,
                    "bicho": BICHOS[g],
                    "numero": c["numero"],
                    "dezena_base": main_dez,
                    "regra": main_role,
                    "ocorrencias": c["ocorrencias"],
                    "ultima": c["ultima"],
                    "rank_no_bicho": pos,
                    "rank_bicho": rank_group,
                    "frozen": frozen,
                    "principal": principal["numero"],
                    "segunda": segunda["numero"],
                    "terceira": terceira["numero"],
                    "principal_tied": principal_tied,
                })

            c = extra_centenas[0]
            rows.append({
                "grupo": g,
                "bicho": BICHOS[g],
                "numero": c["numero"],
                "dezena_base": extra_dez,
                "regra": extra_role,
                "ocorrencias": c["ocorrencias"],
                "ultima": c["ultima"],
                "rank_no_bicho": 4,
                "rank_bicho": rank_group,
                "frozen": frozen,
                "principal": principal["numero"],
                "segunda": segunda["numero"],
                "terceira": terceira["numero"],
                "principal_tied": principal_tied,
            })

        return {
            "kind": "Centena",
            "strategy": "Oficial 3+1",
            "scope": "1º–5º",
            "groups": unique_groups,
            "counts": {g: 4 for g in unique_groups},
            "requested_total": 20,
            "generated_total": len(rows),
            "rows": rows,
            "animals": animals,
            "previous_draw": previous_draw,
            "previous_dezenas": sorted(previous_dezenas),
        }



    def method_similarity_day(
        self,
        draw_date,
        sorteio,
        hora,
        top_days=12,
    ):
        """
        Sombra de Similaridade do Dia.

        Compara o prefixo do dia corrente até a extração-base com dias
        históricos anteriores que tenham os mesmos horários.

        Índice congelado:
        - 45% mesmo bicho na mesma posição e mesmo horário;
        - 30% mesmo bicho no mesmo horário, independentemente da posição;
        - 15% sobreposição geral do dia;
        - 5% padrão de repetição;
        - 5% mesmo dia da semana.

        O índice é similaridade, não probabilidade.

        Saída:
        - top históricos por similaridade;
        - 5 slots do sorteio seguinte, com repetição permitida;
        - agregação ponderada pelo índice de similaridade.
        """
        draws = self._draws_in_order()
        base_key = (draw_date, sorteio, hora)

        base_idx = next(
            (
                i for i, d in enumerate(draws)
                if (d["data"], d["sorteio"], d["hora"]) == base_key
            ),
            None,
        )
        if base_idx is None:
            raise ValueError("Extração-base não encontrada.")

        base_draw = draws[base_idx]
        base_date = base_draw["data"]

        # Prefixo do dia corrente, somente até a extração-base.
        current_day = [
            d for i, d in enumerate(draws[:base_idx + 1])
            if d["data"] == base_date
        ]
        if not current_day:
            raise ValueError("Não há extrações no dia-base.")

        current_hours = [(d["sorteio"], d["hora"]) for d in current_day]
        current_groups_by_hour = {
            (d["sorteio"], d["hora"]): [p["grupo"] for p in d["prizes"]]
            for d in current_day
        }

        def multiset_overlap(a, b):
            ca = {}
            cb = {}
            for x in a:
                ca[x] = ca.get(x, 0) + 1
            for x in b:
                cb[x] = cb.get(x, 0) + 1
            return sum(min(ca.get(k, 0), cb.get(k, 0)) for k in set(ca) | set(cb))

        def repetition_signature(groups):
            counts = {}
            for g in groups:
                counts[g] = counts.get(g, 0) + 1
            return tuple(sorted(counts.values(), reverse=True))

        # Agrupa draws anteriores por dia.
        days = {}
        for i, d in enumerate(draws[:base_idx]):
            days.setdefault(d["data"], []).append((i, d))

        current_flat = []
        for d in current_day:
            current_flat.extend([p["grupo"] for p in d["prizes"]])

        current_weekday = datetime.strptime(base_date, "%Y-%m-%d").weekday()

        candidates = []

        for hist_date, indexed_draws in sorted(days.items()):
            # Não usa o próprio dia e só considera datas anteriores.
            if hist_date >= base_date:
                continue

            hist_map = {
                (d["sorteio"], d["hora"]): (idx, d)
                for idx, d in indexed_draws
            }

            # Dia equivalente precisa ter todos os horários do prefixo atual.
            if any(h not in hist_map for h in current_hours):
                continue

            matched = [hist_map[h] for h in current_hours]
            matched.sort(key=lambda x: x[0])

            # O último draw equivalente precisa ter um próximo draw histórico
            # que ainda seja anterior à extração-base.
            last_idx = matched[-1][0]
            if last_idx + 1 >= base_idx:
                continue

            target = draws[last_idx + 1]
            target_key = (target["data"], target["sorteio"], target["hora"])
            if target_key == base_key:
                continue

            # 45%: mesma posição no mesmo horário.
            exact = 0
            total_slots = len(current_day) * 5

            # 30%: mesmo horário, posição livre.
            hour_overlap = 0

            hist_flat = []
            rep_parts = []

            for h in current_hours:
                current_groups = current_groups_by_hour[h]
                hist_draw = hist_map[h][1]
                hist_groups = [p["grupo"] for p in hist_draw["prizes"]]
                hist_flat.extend(hist_groups)

                exact += sum(
                    1 for a, b in zip(current_groups, hist_groups)
                    if a == b
                )
                hour_overlap += multiset_overlap(current_groups, hist_groups)

                rep_parts.append(
                    1.0
                    if repetition_signature(current_groups)
                    == repetition_signature(hist_groups)
                    else 0.0
                )

            exact_component = 45.0 * (exact / total_slots)
            hour_component = 30.0 * (hour_overlap / total_slots)

            # 15%: sobreposição geral do prefixo do dia.
            day_overlap = multiset_overlap(current_flat, hist_flat)
            day_component = 15.0 * (day_overlap / total_slots)

            # 5%: padrão de repetição.
            current_day_sig = repetition_signature(current_flat)
            hist_day_sig = repetition_signature(hist_flat)

            per_hour_rep = (
                sum(rep_parts) / len(rep_parts)
                if rep_parts else 0.0
            )
            overall_rep = 1.0 if current_day_sig == hist_day_sig else 0.0
            repetition_component = 5.0 * (
                0.70 * per_hour_rep + 0.30 * overall_rep
            )

            hist_weekday = datetime.strptime(hist_date, "%Y-%m-%d").weekday()
            weekday_component = 5.0 if hist_weekday == current_weekday else 0.0

            score = (
                exact_component
                + hour_component
                + day_component
                + repetition_component
                + weekday_component
            )

            candidates.append({
                "date": hist_date,
                "score": score,
                "exact_component": exact_component,
                "hour_component": hour_component,
                "day_component": day_component,
                "repetition_component": repetition_component,
                "weekday_component": weekday_component,
                "target": target,
            })

        candidates.sort(
            key=lambda r: (-r["score"], r["date"])
        )

        selected_days = candidates[:max(1, int(top_days))]

        # Votos ponderados por posição do sorteio seguinte.
        # Isso permite repetição natural entre os 5 slots.
        slot_scores = []
        slot_details = []

        for prize_pos in range(1, 6):
            score_by_group = {}
            contributors = {}

            for c in selected_days:
                target_prize = next(
                    (
                        p for p in c["target"]["prizes"]
                        if p["premio"] == prize_pos
                    ),
                    None,
                )
                if target_prize is None:
                    continue

                g = target_prize["grupo"]
                weight = max(c["score"], 0.0001)
                score_by_group[g] = score_by_group.get(g, 0.0) + weight
                contributors.setdefault(g, []).append({
                    "date": c["date"],
                    "score": c["score"],
                    "target_date": c["target"]["data"],
                    "target_sort": c["target"]["sorteio"],
                    "target_hour": c["target"]["hora"],
                    "target_group": g,
                    "target_bicho": BICHOS[g],
                })

            if not score_by_group:
                slot_scores.append(None)
                slot_details.append([])
                continue

            best_group = sorted(
                score_by_group,
                key=lambda g: (-score_by_group[g], g)
            )[0]

            total_weight = sum(score_by_group.values())
            weighted_share = (
                score_by_group[best_group] / total_weight * 100.0
                if total_weight else 0.0
            )

            slot_scores.append({
                "slot": prize_pos,
                "grupo": best_group,
                "bicho": BICHOS[best_group],
                "weighted_score": score_by_group[best_group],
                "weighted_share": weighted_share,
            })
            slot_details.append(contributors.get(best_group, []))

        selected = [s for s in slot_scores if s is not None]

        return {
            "method": "Sombra Similaridade do Dia",
            "base": base_draw,
            "current_day": current_day,
            "current_hours": current_hours,
            "candidate_count": len(candidates),
            "top_days": selected_days,
            "selected": selected,
            "slot_details": slot_details,
            "weights": {
                "same_position_hour": 45,
                "same_hour_any_position": 30,
                "day_overlap": 15,
                "repetition_pattern": 5,
                "same_weekday": 5,
            },
            "lookahead_safe": True,
        }



    def method_dry_day_first_prize(
        self,
        base_date,
        top_n=2,
        targets_per_source=3,
        min_support=3,
        count_repeats=True,
    ):
        """
        Seca do Dia — seletor diário baseado exclusivamente em 1º prêmio.

        Unidade histórica:
        - fonte: bichos que apareceram no 1º prêmio de um dia;
        - alvo: bichos que apareceram no 1º prêmio do próximo dia disponível.

        Ranking final:
        1) nº de indicações;
        2) nº de fontes distintas;
        3) soma das probabilidades históricas;
        4) soma dos lifts;
        5) grupo apenas como desempate técnico.

        Se count_repeats=True, um bicho que apareceu mais de uma vez no
        1º prêmio do dia-base reforça suas indicações.

        Sem look-ahead: só entram transições cujo dia-alvo já ocorreu
        até o próprio dia-base.
        """
        base_date = str(base_date)
        top_n = max(1, min(10, int(top_n)))
        targets_per_source = max(1, min(10, int(targets_per_source)))
        min_support = max(1, int(min_support))

        draws = self._draws_in_order()
        if not draws:
            raise ValueError("A base está vazia.")

        # 1º prêmios organizados por dia.
        day_firsts = {}
        for d in draws:
            if d["data"] > base_date:
                continue

            p1 = next(
                (p for p in d["prizes"] if p["premio"] == 1),
                None,
            )
            if p1 is None:
                continue

            day_firsts.setdefault(d["data"], []).append({
                "grupo": p1["grupo"],
                "bicho": p1["bicho"],
                "sorteio": d["sorteio"],
                "hora": d["hora"],
                "milhar": p1["milhar"],
            })

        if base_date not in day_firsts:
            raise ValueError(
                "Não há resultados de 1º prêmio cadastrados nesse dia-base."
            )

        dates = sorted(day_firsts)
        base_pos = dates.index(base_date)

        # Transições dia -> próximo dia disponível, sempre encerradas
        # antes ou no próprio dia-base.
        transitions = []
        for i in range(base_pos):
            source_date = dates[i]
            target_date = dates[i + 1]

            if target_date > base_date:
                continue

            transitions.append({
                "source_date": source_date,
                "target_date": target_date,
                "source_groups": [
                    x["grupo"] for x in day_firsts[source_date]
                ],
                "target_groups": [
                    x["grupo"] for x in day_firsts[target_date]
                ],
            })

        if not transitions:
            raise ValueError(
                "Ainda não existem transições diárias suficientes antes do dia-base."
            )

        baseline_support = len(transitions)
        baseline_hits = {g: 0 for g in range(1, 26)}

        for t in transitions:
            for g in set(t["target_groups"]):
                baseline_hits[g] += 1

        base_sources_raw = [
            x["grupo"] for x in day_firsts[base_date]
        ]

        if count_repeats:
            base_sources = list(base_sources_raw)
        else:
            base_sources = []
            for g in base_sources_raw:
                if g not in base_sources:
                    base_sources.append(g)

        # Tabela de relações para cada fonte presente no dia-base.
        relations = {}
        source_details = []

        for source_group in sorted(set(base_sources)):
            matching = [
                t for t in transitions
                if source_group in set(t["source_groups"])
            ]
            support = len(matching)
            ranking = []

            if support >= min_support:
                for target_group in range(1, 26):
                    hit_days = sum(
                        1 for t in matching
                        if target_group in set(t["target_groups"])
                    )

                    if hit_days == 0:
                        continue

                    prob = hit_days / support * 100.0
                    baseline_prob = (
                        baseline_hits[target_group]
                        / baseline_support
                        * 100.0
                        if baseline_support else 0.0
                    )
                    lift = (
                        prob / baseline_prob
                        if baseline_prob > 0 else 0.0
                    )

                    ranking.append({
                        "grupo": target_group,
                        "bicho": BICHOS[target_group],
                        "hit_days": hit_days,
                        "support": support,
                        "prob": prob,
                        "baseline_prob": baseline_prob,
                        "lift": lift,
                    })

                ranking.sort(
                    key=lambda r: (
                        -r["prob"],
                        -r["lift"],
                        -r["hit_days"],
                        r["grupo"],
                    )
                )
                ranking = ranking[:targets_per_source]

            relation = {
                "grupo": source_group,
                "bicho": BICHOS[source_group],
                "support": support,
                "ranking": ranking,
            }
            relations[source_group] = relation
            source_details.append(relation)

        # Convergência das fontes do dia-base.
        scores = {
            g: {
                "grupo": g,
                "bicho": BICHOS[g],
                "indications": 0,
                "distinct_sources": set(),
                "sum_prob": 0.0,
                "sum_lift": 0.0,
                "sources": [],
            }
            for g in range(1, 26)
        }

        for source_group in base_sources:
            relation = relations.get(source_group)
            if not relation or relation["support"] < min_support:
                continue

            for target in relation["ranking"]:
                rec = scores[target["grupo"]]
                rec["indications"] += 1
                rec["distinct_sources"].add(source_group)
                rec["sum_prob"] += target["prob"]
                rec["sum_lift"] += target["lift"]
                rec["sources"].append({
                    "grupo": source_group,
                    "bicho": BICHOS[source_group],
                    "support": relation["support"],
                    "prob": target["prob"],
                    "lift": target["lift"],
                })

        ranking = []
        for rec in scores.values():
            if rec["indications"] <= 0:
                continue

            rec["distinct_source_count"] = len(rec["distinct_sources"])
            rec["distinct_sources"] = sorted(rec["distinct_sources"])
            ranking.append(rec)

        ranking.sort(
            key=lambda r: (
                -r["indications"],
                -r["distinct_source_count"],
                -r["sum_prob"],
                -r["sum_lift"],
                r["grupo"],
            )
        )

        return {
            "method": "Seca do Dia — 1º prêmio",
            "base_date": base_date,
            "base_first_prizes": day_firsts[base_date],
            "base_sources_raw": base_sources_raw,
            "base_sources_used": base_sources,
            "count_repeats": bool(count_repeats),
            "targets_per_source": targets_per_source,
            "min_support": min_support,
            "transition_count": len(transitions),
            "baseline_support": baseline_support,
            "source_details": source_details,
            "ranking": ranking,
            "selected": ranking[:top_n],
            "top_n": top_n,
            "lookahead_safe": True,
        }

    def generate_dry_day_numbers(
        self,
        base_date,
        kind="Centena",
        total=2,
        top_animals=2,
        targets_per_source=3,
        min_support=3,
        count_repeats=True,
    ):
        """
        Gerador flexível da Seca do Dia.

        - Tipo: Centena ou Milhar.
        - Quantidade livre.
        - Bichos escolhidos pelo motor diário de 1º prêmio.
        - Números ranqueados somente pelo histórico de 1º prêmio.
        - Ranking numérico também é cortado no dia-base.
        """
        if kind not in ("Centena", "Milhar"):
            raise ValueError(
                "A Seca do Dia gera apenas Centena ou Milhar."
            )

        total = max(1, int(total))
        top_animals = max(1, min(10, int(top_animals)))

        method = self.method_dry_day_first_prize(
            base_date=base_date,
            top_n=top_animals,
            targets_per_source=targets_per_source,
            min_support=min_support,
            count_repeats=count_repeats,
        )

        groups = [
            r["grupo"] for r in method["selected"]
        ]
        if not groups:
            raise ValueError(
                "Nenhum bicho alcançou o suporte mínimo da Seca do Dia."
            )

        counts = self.distribute_game_counts(
            total=total,
            groups=groups,
            kind=kind,
        )

        rows = []

        for rank_group, g in enumerate(groups, start=1):
            number_ranking = self.number_rankings_for_group(
                g,
                kind=kind,
                scope="1º",
                date_to=base_date,
            )

            for pos, num in enumerate(
                number_ranking[:counts[g]],
                start=1,
            ):
                rows.append({
                    "grupo": g,
                    "bicho": BICHOS[g],
                    "numero": num["numero"],
                    "dezena_base": num["numero"][-2:],
                    "regra": "Seca 1º prêmio",
                    "ocorrencias": num["ocorrencias"],
                    "ultima": num["ultima"],
                    "rank_no_bicho": pos,
                    "rank_bicho": rank_group,
                })

        return {
            "kind": kind,
            "strategy": "Seca do Dia 1º",
            "scope": "1º",
            "base_date": str(base_date),
            "groups": groups,
            "counts": counts,
            "requested_total": total,
            "generated_total": len(rows),
            "rows": rows,
            "method": method,
        }



    def freeze_generated_game(self, generation, base_draw=None, observation=""):
        if not generation or not generation.get("rows"):
            raise ValueError("Não há jogo gerado para congelar.")

        selector = generation.get("selector", "Não registrado")
        strategy = generation.get("strategy", "Histórica simples")
        kind = generation.get("kind", "Centena")
        scope = generation.get("scope", "1º–5º")
        forced_target_mode = generation.get("target_mode")

        if strategy == "Seca do Dia 1º":
            selector = generation.get("selector") or "Seca do Dia 1º"
            base_data = generation.get("base_date")
            base_sort = None
            base_hour = None
            target_mode = forced_target_mode or "PROXIMO_DIA_1P"
            scope = "1º"
        else:
            if base_draw is None:
                base_draw = self.latest_operational_draw()
            if base_draw is None:
                raise ValueError("Não foi possível identificar a extração-base.")

            base_data = base_draw["data"]
            base_sort = base_draw["sorteio"]
            base_hour = base_draw["hora"]
            target_mode = forced_target_mode or "PROXIMA_OPERACIONAL"

        intended_target = generation.get("intended_target") or {}
        intended_data = intended_target.get("data")
        intended_sort = intended_target.get("sorteio")
        intended_hour = intended_target.get("hora")

        with self.connect() as con:
            cur = con.execute("""
                INSERT INTO jogos_congelados
                (
                    seletor, estrategia, tipo, submodalidade, escopo,
                    base_data, base_sorteio, base_hora,
                    alvo_modo, alvo_data, alvo_sorteio, alvo_hora,
                    total_itens, observacao, origem_jogada
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                selector,
                strategy,
                kind,
                generation.get("submodalidade"),
                scope,
                base_data,
                base_sort,
                base_hour,
                target_mode,
                intended_data,
                intended_sort,
                intended_hour,
                len(generation["rows"]),
                observation or "",
                generation.get("origem_jogada"),
            ))
            game_id = cur.lastrowid

            con.executemany("""
                INSERT INTO jogos_itens
                (jogo_id, ordem, grupo, bicho, numero, dezena_base, regra)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    game_id,
                    i,
                    row.get("grupo"),
                    row.get("bicho"),
                    str(row.get("numero", "")),
                    row.get("dezena_base"),
                    row.get("regra"),
                )
                for i, row in enumerate(generation["rows"], start=1)
            ])

        return game_id

    def list_frozen_games(self, limit=200):
        with self.connect() as con:
            rows = con.execute("""
                SELECT *
                FROM jogos_congelados
                ORDER BY id DESC
                LIMIT ?
            """, (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    def frozen_game_details(self, game_id):
        with self.connect() as con:
            game = con.execute(
                "SELECT * FROM jogos_congelados WHERE id=?",
                (int(game_id),),
            ).fetchone()
            if game is None:
                raise ValueError("Jogo congelado não encontrado.")

            items = con.execute("""
                SELECT *
                FROM jogos_itens
                WHERE jogo_id=?
                ORDER BY ordem
            """, (int(game_id),)).fetchall()

        return {"game": dict(game), "items": [dict(r) for r in items]}

    def _next_draw_after(self, base_data, base_sort, base_hour):
        draws = self._draws_in_order()
        for i, d in enumerate(draws):
            if (
                d["data"] == base_data
                and d["sorteio"] == base_sort
                and d["hora"] == base_hour
            ):
                return draws[i + 1] if i + 1 < len(draws) else None
        return None

    def _next_date_after(self, base_date):
        with self.connect() as con:
            row = con.execute("""
                SELECT MIN(data) AS data
                FROM resultados
                WHERE data > ?
            """, (str(base_date),)).fetchone()
        return row["data"] if row and row["data"] else None

    def _value_for_kind(self, prize, kind):
        base_kind = (
            INVERTED_MODALITIES[kind][0]
            if kind in INVERTED_MODALITIES
            else kind
        )

        if base_kind == "Grupo":
            return f"{int(prize['grupo']):02d}"
        if base_kind == "Dezena":
            return str(prize["dezena"]).zfill(2)
        if base_kind == "Centena":
            return str(prize["centena"]).zfill(3)
        if base_kind == "Milhar":
            return str(prize["milhar"]).zfill(4)
        return None

    def audit_frozen_game(self, game_id):
        detail = self.frozen_game_details(game_id)
        game = detail["game"]
        items = detail["items"]

        target_rows = []
        target_data = None
        target_sort = None
        target_hour = None

        if game["alvo_modo"] == "PROXIMO_DIA_1P":
            target_data = self._next_date_after(game["base_data"])
            if not target_data:
                return {
                    "game_id": int(game_id),
                    "audited": False,
                    "reason": "O próximo dia ainda não existe na base.",
                }

            with self.connect() as con:
                rows = con.execute("""
                    SELECT *
                    FROM resultados
                    WHERE data=? AND premio=1
                    ORDER BY hora, sorteio
                """, (target_data,)).fetchall()
            target_rows = [dict(r) for r in rows]

            if not target_rows:
                return {
                    "game_id": int(game_id),
                    "audited": False,
                    "reason": "O próximo dia ainda não possui 1º prêmio.",
                }

        else:
            draw = None

            if game["alvo_modo"] == "ALVO_ESPECIFICO":
                if (
                    game.get("alvo_data")
                    and game.get("alvo_sorteio")
                    and game.get("alvo_hora")
                ):
                    draw = self.get_draw(
                        game["alvo_data"],
                        game["alvo_sorteio"],
                        game["alvo_hora"],
                    )

            elif game["alvo_modo"] == "PROXIMA_OPERACIONAL":
                if (
                    game.get("alvo_data")
                    and game.get("alvo_sorteio")
                    and game.get("alvo_hora")
                ):
                    draw = self.get_draw(
                        game["alvo_data"],
                        game["alvo_sorteio"],
                        game["alvo_hora"],
                    )
                else:
                    draws = self._draws_in_order()
                    source_index = self._reset_find_draw_index(
                        draws,
                        game["base_data"],
                        game["base_sorteio"],
                        game["base_hora"],
                    )
                    if source_index is not None:
                        _, draw = self._reset_next_operational_existing(
                            draws,
                            source_index,
                        )

            else:
                draw = self._next_draw_after(
                    game["base_data"],
                    game["base_sorteio"],
                    game["base_hora"],
                )

            if draw is None:
                return {
                    "game_id": int(game_id),
                    "audited": False,
                    "reason": (
                        "O resultado do alvo congelado ainda não existe na base."
                        if game["alvo_modo"] == "ALVO_ESPECIFICO"
                        else (
                            "A próxima rodada operacional ainda não existe na base."
                            if game["alvo_modo"] == "PROXIMA_OPERACIONAL"
                            else "A próxima extração ainda não existe na base."
                        )
                    ),
                }

            target_data = draw["data"]
            target_sort = draw["sorteio"]
            target_hour = draw["hora"]

            prizes = list(draw["prizes"])
            if (
                game["escopo"] == "1º"
                and game["tipo"] not in FIXED_PLACEMENT_MODALITIES
            ):
                prizes = [
                    p for p in prizes
                    if int(p["premio"]) == 1
                ]

            target_rows = [
                {
                    "data": target_data,
                    "sorteio": target_sort,
                    "hora": target_hour,
                    **p,
                }
                for p in prizes
            ]

        winning_items = 0
        item_updates = []

        for item in items:
            events = self._game_item_events(
                game,
                item,
                target_rows,
            )

            if events:
                winning_items += 1
                first = next(
                    (e for e in events if e.get("row")),
                    events[0],
                )
                row = first.get("row") or {}
                item_updates.append((
                    1,
                    row.get("data"),
                    row.get("sorteio"),
                    row.get("hora"),
                    first.get("premio"),
                    first.get("milhar"),
                    item["id"],
                ))
            else:
                item_updates.append((
                    0,
                    None,
                    None,
                    None,
                    None,
                    None,
                    item["id"],
                ))

        with self.connect() as con:
            con.executemany("""
                UPDATE jogos_itens
                SET
                    acertou=?,
                    acerto_data=?,
                    acerto_sorteio=?,
                    acerto_hora=?,
                    acerto_premio=?,
                    acerto_milhar=?
                WHERE id=?
            """, item_updates)

            con.execute("""
                UPDATE jogos_congelados
                SET
                    status='AUDITADO',
                    acertos=?,
                    alvo_data=?,
                    alvo_sorteio=?,
                    alvo_hora=?,
                    auditado_em=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                winning_items,
                target_data,
                target_sort,
                target_hour,
                int(game_id),
            ))

        settlement = self.settle_game_financial(game_id)

        if game.get("bilhete_id"):
            self.refresh_ticket_totals(
                int(game["bilhete_id"])
            )

        return {
            "game_id": int(game_id),
            "audited": True,
            "hits": winning_items,
            "total": len(items),
            "financial_hits": (
                settlement.get("acertos_financeiros", 0)
                if settlement
                else 0
            ),
            "target_data": target_data,
            "target_sort": target_sort,
            "target_hour": target_hour,
        }

    def _payout_key(self, kind, scope):
        safe_kind = sem_acento(str(kind)).lower().replace(" ", "_")
        safe_scope = (
            str(scope)
            .replace("º", "")
            .replace("–", "-")
            .replace(" ", "")
        )
        return f"payout_{safe_kind}_{safe_scope}"

    def _quote_key(self, modality):
        return (
            "quote_"
            + sem_acento(str(modality)).lower().replace(" ", "_")
        )

    def get_quote(self, modality):
        default = DEFAULT_QUOTES.get(str(modality), 0.0)
        raw = self._meta_value(
            self._quote_key(modality),
            str(default),
        )
        try:
            return float(raw or 0)
        except Exception:
            return float(default)

    def set_quote(self, modality, value):
        value = float(value)
        if value < 0:
            raise ValueError("A cotação não pode ser negativa.")
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO meta(chave, valor) VALUES(?, ?)",
                (self._quote_key(modality), str(value)),
            )

    def get_milhar_centena_quotes(self):
        result = {}
        for component, default in DEFAULT_MILHAR_CENTENA_QUOTES.items():
            raw = self._meta_value(
                f"quote_milhar_centena_{component}",
                str(default),
            )
            try:
                result[component] = float(raw or 0)
            except Exception:
                result[component] = float(default)
        return result

    def set_milhar_centena_quotes(self, centena, milhar, ambos):
        values = {
            "centena": float(centena),
            "milhar": float(milhar),
            "ambos": float(ambos),
        }
        if any(v < 0 for v in values.values()):
            raise ValueError("As cotações não podem ser negativas.")
        with self.connect() as con:
            for component, value in values.items():
                con.execute(
                    "INSERT OR REPLACE INTO meta(chave, valor) VALUES(?, ?)",
                    (
                        f"quote_milhar_centena_{component}",
                        str(value),
                    ),
                )

    def quote_catalog(self):
        return {
            "simples": {
                modality: self.get_quote(modality)
                for modality in DEFAULT_QUOTES
            },
            "milhar_centena": self.get_milhar_centena_quotes(),
        }

    def get_payout_multiplier(self, kind, scope):
        raw = self._meta_value(self._payout_key(kind, scope), "0")
        try:
            return float(raw or 0)
        except Exception:
            return 0.0

    def set_payout_multiplier(self, kind, scope, value):
        value = float(value)
        if value < 0:
            raise ValueError("O multiplicador não pode ser negativo.")
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO meta(chave, valor) VALUES(?, ?)",
                (self._payout_key(kind, scope), str(value)),
            )

    def payout_table(self):
        kinds = ("Grupo", "Dezena", "Centena", "Milhar")
        scopes = ("1º", "1º–5º")
        return {
            (kind, scope): self.get_payout_multiplier(kind, scope)
            for kind in kinds
            for scope in scopes
        }

    def game_planned_target(self, game):
        if game.get("alvo_data"):
            return {
                "data": game.get("alvo_data"),
                "sorteio": game.get("alvo_sorteio"),
                "hora": game.get("alvo_hora"),
                "whole_day": (
                    game.get("alvo_modo") == "PROXIMO_DIA_1P"
                    and not game.get("alvo_sorteio")
                ),
            }

        if game.get("alvo_modo") == "PROXIMO_DIA_1P":
            base = game.get("base_data")
            if not base:
                return None
            next_date = (
                datetime.strptime(base, "%Y-%m-%d").date()
                + timedelta(days=1)
            ).isoformat()
            return {
                "data": next_date,
                "sorteio": None,
                "hora": None,
                "whole_day": True,
            }

        if (
            game.get("base_data")
            and game.get("base_sorteio")
            and game.get("base_hora")
        ):
            base = self.get_draw(
                game["base_data"],
                game["base_sorteio"],
                game["base_hora"],
            )
            if base:
                target = self._reset_expected_target(base)
                return {
                    "data": target["data"],
                    "sorteio": target["sorteio"],
                    "hora": target["hora"],
                    "whole_day": False,
                }

        return None

    def _target_rows_from_game(self, game):
        target = self.game_planned_target(game)
        if not target:
            return []

        if target["whole_day"]:
            with self.connect() as con:
                rows = con.execute("""
                    SELECT *
                    FROM resultados
                    WHERE data=? AND premio=1
                    ORDER BY hora, sorteio
                """, (target["data"],)).fetchall()
            return [dict(r) for r in rows]

        if not target["sorteio"] or not target["hora"]:
            return []

        draw = self.get_draw(
            target["data"],
            target["sorteio"],
            target["hora"],
        )
        if not draw:
            return []

        prizes = list(draw["prizes"])
        if game.get("escopo") == "1º":
            prizes = [p for p in prizes if int(p["premio"]) == 1]

        return [
            {
                "data": target["data"],
                "sorteio": target["sorteio"],
                "hora": target["hora"],
                **p,
            }
            for p in prizes
        ]

    def _financial_snapshot(
        self,
        kind,
        scope,
        item_count,
        value_per_item,
        submodalidade=None,
    ):
        stake = float(value_per_item)
        if stake < 0:
            raise ValueError("O valor por palpite não pode ser negativo.")

        count = max(0, int(item_count))
        total = stake * count

        fixed = kind in FIXED_PLACEMENT_MODALITIES

        if fixed:
            divisor = 1
            max_events = count
        else:
            divisor = 5 if scope == "1º–5º" else 1
            max_events = 5 if scope == "1º–5º" else 1

        value_position = stake / divisor if divisor else stake

        special = (
            kind == "Milhar"
            and submodalidade == "Milhar/Centena"
        )

        if special:
            quotes = self.get_milhar_centena_quotes()
            primary = quotes["milhar"]
            secondary = quotes["centena"]
            combined = quotes["ambos"]

            min_return = (
                value_position * secondary
                if stake > 0 and secondary > 0
                else None
            )
            max_return = (
                max_events * value_position * combined
                if stake > 0 and combined > 0
                else None
            )

        else:
            quote = self.get_quote(kind)
            primary = quote if quote > 0 else None
            secondary = None
            combined = None

            one_hit = (
                value_position * quote
                if stake > 0 and quote > 0
                else None
            )

            min_return = one_hit

            if fixed:
                max_return = (
                    count * stake * quote
                    if stake > 0 and quote > 0
                    else None
                )
            else:
                max_return = (
                    max_events * one_hit
                    if one_hit is not None
                    else None
                )

        return {
            "valor_unitario": stake,
            "valor_total": total,
            "divisor_posicoes": divisor,
            "valor_posicao": value_position,
            "cotacao_primaria": primary,
            "cotacao_secundaria": secondary,
            "cotacao_combinada": combined,
            "multiplicador": primary,
            "retorno_min": min_return,
            "retorno_max": max_return,
            "fixed_placement": fixed,
            "submodalidade": submodalidade,
            "max_eventos": max_events,
            "single_position": (not fixed and max_events == 1),
        }

    def _financial_bounds_for_rows(
        self,
        kind,
        scope,
        rows,
        value_per_item,
        submodalidade=None,
    ):
        snap = self._financial_snapshot(
            kind,
            scope,
            len(rows),
            value_per_item,
            submodalidade=submodalidade,
        )

        if kind not in INVERTED_MODALITIES:
            return snap

        quote = self.get_quote(kind)
        value_position = float(snap["valor_posicao"] or 0)
        hit_values = []

        for row in rows:
            number = str(row.get("numero", ""))
            count = self._unique_permutation_count(number)
            if count <= 0:
                continue
            hit_values.append(
                value_position * quote / count
            )

        if hit_values:
            snap["retorno_min"] = min(hit_values)
            max_events = 5 if scope == "1º–5º" else 1
            snap["retorno_max"] = max(hit_values) * max_events
        else:
            snap["retorno_min"] = None
            snap["retorno_max"] = None

        return snap

    def register_play(self, generation, value_per_item, base_draw=None):
        if not generation or not generation.get("rows"):
            raise ValueError("Não há jogo gerado.")

        strategy = generation.get("strategy", "")
        intended_target = generation.get("intended_target")
        target_mode = generation.get("target_mode")

        if intended_target is None:
            if strategy == "Seca do Dia 1º":
                base_date = generation.get("base_date")
                if base_date:
                    intended_target = {
                        "data": (
                            datetime.strptime(base_date, "%Y-%m-%d").date()
                            + timedelta(days=1)
                        ).isoformat(),
                        "sorteio": None,
                        "hora": None,
                    }
            else:
                intended_target = self.next_operational_target()

        generation = dict(generation)
        generation["intended_target"] = intended_target
        if target_mode:
            generation["target_mode"] = target_mode

        game_id = self.freeze_generated_game(
            generation,
            base_draw=base_draw,
        )

        submodalidade = generation.get("submodalidade")
        snap = self._financial_bounds_for_rows(
            generation.get("kind", "Centena"),
            generation.get("scope", "1º–5º"),
            generation["rows"],
            value_per_item,
            submodalidade=submodalidade,
        )

        with self.connect() as con:
            con.execute("""
                UPDATE jogos_congelados
                SET
                    jogado=1,
                    jogado_em=CURRENT_TIMESTAMP,
                    submodalidade=?,
                    valor_unitario=?,
                    valor_total=?,
                    divisor_posicoes=?,
                    valor_posicao=?,
                    multiplicador=?,
                    cotacao_primaria=?,
                    cotacao_secundaria=?,
                    cotacao_combinada=?,
                    retorno_min=?,
                    retorno_max=?,
                    origem_jogada=COALESCE(origem_jogada, ?)
                WHERE id=?
            """, (
                submodalidade,
                snap["valor_unitario"],
                snap["valor_total"],
                snap["divisor_posicoes"],
                snap["valor_posicao"],
                snap["multiplicador"],
                snap["cotacao_primaria"],
                snap["cotacao_secundaria"],
                snap["cotacao_combinada"],
                snap["retorno_min"],
                snap["retorno_max"],
                generation.get("origem_jogada", "Gerada"),
                int(game_id),
            ))

        return game_id

    def mark_frozen_as_played(
        self,
        game_id,
        value_per_item,
        submodalidade=None,
    ):
        detail = self.frozen_game_details(game_id)
        game = detail["game"]

        if game["status"] != "PENDENTE":
            raise ValueError(
                "Só é possível informar o valor como jogada real "
                "enquanto o resultado ainda está pendente."
            )

        check = self.audit_frozen_game(game_id)
        if check.get("audited"):
            raise ValueError(
                "O resultado desse jogo já estava disponível. "
                "O valor não pode ser registrado retroativamente como jogada real."
            )

        if game["tipo"] != "Milhar":
            submodalidade = game.get("submodalidade")
        elif not submodalidade:
            submodalidade = game.get("submodalidade") or "Milhar"

        snap = self._financial_bounds_for_rows(
            game["tipo"],
            game["escopo"],
            detail["items"],
            value_per_item,
            submodalidade=submodalidade,
        )

        target = self.game_planned_target(game)

        with self.connect() as con:
            con.execute("""
                UPDATE jogos_congelados
                SET
                    jogado=1,
                    jogado_em=CURRENT_TIMESTAMP,
                    submodalidade=?,
                    valor_unitario=?,
                    valor_total=?,
                    divisor_posicoes=?,
                    valor_posicao=?,
                    multiplicador=?,
                    cotacao_primaria=?,
                    cotacao_secundaria=?,
                    cotacao_combinada=?,
                    retorno_min=?,
                    retorno_max=?,
                    alvo_data=COALESCE(alvo_data, ?),
                    alvo_sorteio=COALESCE(alvo_sorteio, ?),
                    alvo_hora=COALESCE(alvo_hora, ?),
                    origem_jogada=COALESCE(origem_jogada, 'Congelamento antigo')
                WHERE id=?
            """, (
                submodalidade,
                snap["valor_unitario"],
                snap["valor_total"],
                snap["divisor_posicoes"],
                snap["valor_posicao"],
                snap["multiplicador"],
                snap["cotacao_primaria"],
                snap["cotacao_secundaria"],
                snap["cotacao_combinada"],
                snap["retorno_min"],
                snap["retorno_max"],
                target.get("data") if target else None,
                target.get("sorteio") if target else None,
                target.get("hora") if target else None,
                int(game_id),
            ))

        return self.frozen_game_details(game_id)["game"]

    def refresh_game_financial_snapshot(self, game_id):
        detail = self.frozen_game_details(game_id)
        game = detail["game"]

        if not game.get("jogado"):
            return game

        stake = float(game.get("valor_unitario") or 0)
        snap = self._financial_bounds_for_rows(
            game["tipo"],
            game["escopo"],
            detail["items"],
            stake,
            submodalidade=game.get("submodalidade"),
        )

        with self.connect() as con:
            con.execute("""
                UPDATE jogos_congelados
                SET
                    divisor_posicoes=?,
                    valor_posicao=?,
                    multiplicador=?,
                    cotacao_primaria=?,
                    cotacao_secundaria=?,
                    cotacao_combinada=?,
                    retorno_min=?,
                    retorno_max=?
                WHERE id=?
            """, (
                snap["divisor_posicoes"],
                snap["valor_posicao"],
                snap["multiplicador"],
                snap["cotacao_primaria"],
                snap["cotacao_secundaria"],
                snap["cotacao_combinada"],
                snap["retorno_min"],
                snap["retorno_max"],
                int(game_id),
            ))

        if game["status"] == "AUDITADO":
            self.settle_game_financial(game_id)

        return self.frozen_game_details(game_id)["game"]

    def _parse_group_combo(self, number):
        groups = []
        for part in re.split(r"[-,/+ ]+", str(number)):
            part = part.strip()
            if not part:
                continue
            try:
                g = int(part)
            except Exception:
                continue
            if 1 <= g <= 25 and g not in groups:
                groups.append(g)
        return groups

    def _game_item_events(self, game, item, target_rows):
        kind = game["tipo"]
        number = str(item["numero"])
        sub = game.get("submodalidade")
        events = []

        if kind in GROUP_COMBO_SIZES:
            wanted = set(self._parse_group_combo(number))
            present = {int(r["grupo"]) for r in target_rows}
            expected = GROUP_COMBO_SIZES[kind]
            if len(wanted) == expected and wanted.issubset(present):
                events.append({
                    "category": kind,
                    "premio": None,
                    "milhar": None,
                    "row": None,
                    "number": number,
                })
            return events

        if kind in DEZENA_COMBO_SIZES:
            wanted = {
                p.zfill(2)
                for p in re.split(r"[-,/+ ]+", number)
                if p.strip()
            }
            present = {
                str(r["dezena"]).zfill(2)
                for r in target_rows
            }
            expected = DEZENA_COMBO_SIZES[kind]
            if len(wanted) == expected and wanted.issubset(present):
                events.append({
                    "category": kind,
                    "premio": None,
                    "milhar": None,
                    "row": None,
                    "number": number,
                })
            return events

        if kind in PASSE_MODALITIES:
            groups = self._parse_group_combo(number)
            if len(groups) != 2:
                return events

            first_row = next(
                (
                    r for r in target_rows
                    if int(r.get("premio") or 0) == 1
                ),
                None,
            )
            tail_groups = {
                int(r["grupo"])
                for r in target_rows
                if 2 <= int(r.get("premio") or 0) <= 5
            }

            if first_row:
                first_group = int(first_row["grupo"])
                a, b = groups

                if kind == "Passe vai":
                    won = (
                        first_group == a
                        and b in tail_groups
                    )
                else:
                    won = (
                        (first_group == a and b in tail_groups)
                        or (first_group == b and a in tail_groups)
                    )

                if won:
                    events.append({
                        "category": kind,
                        "premio": 1,
                        "milhar": first_row.get("milhar"),
                        "row": first_row,
                        "number": number,
                    })
            return events

        if kind in INVERTED_MODALITIES:
            base_kind, _digits = INVERTED_MODALITIES[kind]
            wanted_sorted = sorted(number)
            for row in target_rows:
                target_value = self._value_for_kind(
                    row,
                    base_kind,
                )
                if (
                    target_value is not None
                    and sorted(str(target_value)) == wanted_sorted
                ):
                    events.append({
                        "category": kind,
                        "premio": row.get("premio"),
                        "milhar": row.get("milhar"),
                        "row": row,
                        "number": number,
                    })
            return events

        if kind == "Milhar" and sub == "Milhar/Centena":
            wanted_milhar = number.zfill(4)
            wanted_centena = wanted_milhar[-3:]

            for row in target_rows:
                if str(row["milhar"]).zfill(4) == wanted_milhar:
                    events.append({
                        "category": "Milhar + Centena",
                        "premio": row.get("premio"),
                        "milhar": row.get("milhar"),
                        "row": row,
                        "number": number,
                    })
                elif str(row["centena"]).zfill(3) == wanted_centena:
                    events.append({
                        "category": "Centena",
                        "premio": row.get("premio"),
                        "milhar": row.get("milhar"),
                        "row": row,
                        "number": number,
                    })
            return events

        for row in target_rows:
            target_value = self._value_for_kind(row, kind)
            if target_value == number:
                events.append({
                    "category": kind,
                    "premio": row.get("premio"),
                    "milhar": row.get("milhar"),
                    "row": row,
                    "number": number,
                })

        return events

    def _event_payout(self, game, event):
        if not game.get("jogado"):
            return 0.0

        stake = float(game.get("valor_unitario") or 0)
        divisor = int(game.get("divisor_posicoes") or 1)
        value_position = game.get("valor_posicao")
        if value_position is None:
            value_position = stake / divisor
        value_position = float(value_position or 0)

        kind = game["tipo"]
        category = event.get("category")

        if kind in FIXED_PLACEMENT_MODALITIES:
            quote = float(
                game.get("cotacao_primaria")
                or self.get_quote(kind)
            )
            return stake * quote

        if kind in INVERTED_MODALITIES:
            quote = float(
                game.get("cotacao_primaria")
                or self.get_quote(kind)
            )
            count = self._unique_permutation_count(
                event.get("number", "")
            )
            if count <= 0:
                return 0.0
            return value_position * quote / count

        if kind == "Milhar" and game.get("submodalidade") == "Milhar/Centena":
            if category == "Milhar + Centena":
                quote = float(
                    game.get("cotacao_combinada")
                    or self.get_milhar_centena_quotes()["ambos"]
                )
            else:
                quote = float(
                    game.get("cotacao_secundaria")
                    or self.get_milhar_centena_quotes()["centena"]
                )
            return value_position * quote

        quote = float(
            game.get("cotacao_primaria")
            or self.get_quote(kind)
        )
        return value_position * quote

    def settle_game_financial(self, game_id):
        detail = self.frozen_game_details(game_id)
        game = detail["game"]

        if not game.get("jogado"):
            return None

        target_rows = self._target_rows_from_game(game)
        if not target_rows:
            return None

        gross = 0.0
        event_count = 0

        for item in detail["items"]:
            events = self._game_item_events(
                game,
                item,
                target_rows,
            )
            for event in events:
                gross += self._event_payout(game, event)
                event_count += 1

        total = float(game.get("valor_total") or 0)
        net = gross - total

        with self.connect() as con:
            con.execute("""
                UPDATE jogos_congelados
                SET
                    retorno_real=?,
                    resultado_liquido=?,
                    acertos_financeiros=?
                WHERE id=?
            """, (
                gross,
                net,
                event_count,
                int(game_id),
            ))

        return {
            "retorno_real": gross,
            "resultado_liquido": net,
            "acertos_financeiros": event_count,
        }

    def play_game_analysis(self, game_id):
        detail = self.frozen_game_details(game_id)
        game = detail["game"]
        items = detail["items"]
        target_rows = self._target_rows_from_game(game)

        analyzed = []

        for item in items:
            number = str(item["numero"])
            events = (
                self._game_item_events(game, item, target_rows)
                if game["status"] == "AUDITADO"
                else []
            )

            hit = bool(events)
            proximity = ""
            where_parts = []
            item_return = 0.0

            for event in events:
                category = event.get("category")
                premio = event.get("premio")
                milhar = event.get("milhar")

                label = ""
                if premio:
                    label += f"{premio}º"
                if milhar:
                    label += (f" {milhar}" if label else str(milhar))
                if category:
                    label += (f" • {category}" if label else category)

                payout = self._event_payout(game, event)
                item_return += payout
                if payout > 0:
                    label += (
                        f" • R$ {payout:.2f}".replace(".", ",")
                    )

                where_parts.append(label)

            if not hit and game["status"] == "AUDITADO":
                kind = game["tipo"]
                group = int(item.get("grupo") or 0)

                if kind == "Milhar":
                    centena = number[-3:]
                    if any(
                        str(r["centena"]).zfill(3) == centena
                        for r in target_rows
                    ):
                        proximity = f"Mesma Centena {centena}"
                    else:
                        dezena = number[-2:]
                        if any(
                            str(r["dezena"]).zfill(2) == dezena
                            for r in target_rows
                        ):
                            proximity = f"Mesma Dezena {dezena}"
                        elif group and any(
                            int(r["grupo"]) == group
                            for r in target_rows
                        ):
                            proximity = f"Mesmo Grupo {group:02d}"

                elif kind == "Centena":
                    dezena = number[-2:]
                    if any(
                        str(r["dezena"]).zfill(2) == dezena
                        for r in target_rows
                    ):
                        proximity = f"Mesma Dezena {dezena}"
                    elif group and any(
                        int(r["grupo"]) == group
                        for r in target_rows
                    ):
                        proximity = f"Mesmo Grupo {group:02d}"

                elif kind == "Dezena":
                    if group and any(
                        int(r["grupo"]) == group
                        for r in target_rows
                    ):
                        proximity = f"Mesmo Grupo {group:02d}"

            analyzed.append({
                **item,
                "hit": hit,
                "events": events,
                "where": " | ".join(where_parts),
                "proximity": proximity,
                "item_return": item_return,
            })

        return {
            "game": game,
            "items": analyzed,
            "target": self.game_planned_target(game),
            "result_rows": target_rows,
        }


    def _unique_permutation_count(self, number):
        text = str(number)
        return len(set(permutations(text)))

    def generate_group_combinations(
        self,
        groups,
        kind,
        total=5,
    ):
        size = GROUP_COMBO_SIZES.get(kind)
        if not size:
            raise ValueError("Modalidade de grupo combinada inválida.")

        unique = []
        for g in groups:
            g = int(g)
            if g not in unique:
                unique.append(g)

        if len(unique) < size:
            raise ValueError(
                f"{kind} precisa de pelo menos {size} grupos distintos."
            )

        combos = list(combinations(unique, size))
        rows = []

        for combo in combos[:max(1, int(total))]:
            rows.append({
                "grupo": None,
                "bicho": " + ".join(BICHOS[g] for g in combo),
                "numero": "-".join(f"{g:02d}" for g in combo),
                "dezena_base": "—",
                "regra": kind,
            })

        return {
            "kind": kind,
            "strategy": "Combinação",
            "scope": "1º–5º",
            "groups": unique,
            "rows": rows,
        }

    def generate_passe_combinations(
        self,
        groups,
        kind,
        total=5,
    ):
        if kind not in PASSE_MODALITIES:
            raise ValueError("Modalidade Passe inválida.")

        unique = []
        for g in groups:
            g = int(g)
            if g not in unique:
                unique.append(g)

        if len(unique) < 2:
            raise ValueError("Passe precisa de dois grupos distintos.")

        if kind == "Passe vai":
            pairs = [
                (a, b)
                for a in unique
                for b in unique
                if a != b
            ]
        else:
            pairs = list(combinations(unique, 2))

        rows = []
        for a, b in pairs[:max(1, int(total))]:
            rows.append({
                "grupo": None,
                "bicho": f"{BICHOS[a]} → {BICHOS[b]}" if kind == "Passe vai"
                    else f"{BICHOS[a]} ↔ {BICHOS[b]}",
                "numero": f"{a:02d}-{b:02d}",
                "dezena_base": "—",
                "regra": kind,
            })

        return {
            "kind": kind,
            "strategy": "Passe",
            "scope": "1º–5º",
            "groups": unique,
            "rows": rows,
        }

    def generate_dezena_combinations(
        self,
        groups,
        kind,
        total=5,
    ):
        size = DEZENA_COMBO_SIZES.get(kind)
        if not size:
            raise ValueError("Modalidade de dezenas combinadas inválida.")

        candidates = []
        seen = set()

        for g in groups:
            ranking = self.number_rankings_for_group(
                int(g),
                kind="Dezena",
                scope="1º–5º",
            )
            for row in ranking[:4]:
                number = str(row["numero"]).zfill(2)
                if number in seen:
                    continue
                seen.add(number)
                candidates.append({
                    "numero": number,
                    "grupo": int(g),
                    "bicho": BICHOS[int(g)],
                    "ocorrencias": int(row.get("ocorrencias") or 0),
                    "ultima": row.get("ultima") or "",
                })

        candidates.sort(
            key=lambda r: (
                -r["ocorrencias"],
                r["ultima"],
                r["numero"],
            )
        )

        combos = list(combinations(candidates, size))
        rows = []

        for combo in combos[:max(1, int(total))]:
            nums = [r["numero"] for r in combo]
            rows.append({
                "grupo": None,
                "bicho": " + ".join(nums),
                "numero": "-".join(nums),
                "dezena_base": "—",
                "regra": kind,
            })

        return {
            "kind": kind,
            "strategy": "Dezenas históricas",
            "scope": "1º–5º",
            "groups": [int(g) for g in groups],
            "rows": rows,
        }

    def generate_inverted_numbers(
        self,
        groups,
        kind,
        total=10,
        scope="1º–5º",
    ):
        base_kind, _digits = INVERTED_MODALITIES[kind]
        generation = self.generate_historical_numbers(
            groups=groups,
            kind=base_kind,
            total=total,
            scope=scope,
        )
        generation["kind"] = kind
        generation["scope"] = scope
        generation["strategy"] = "Histórica invertida"

        for row in generation["rows"]:
            row["regra"] = (
                f"{kind} • {self._unique_permutation_count(row['numero'])} inversões"
            )

        return generation

    def manual_generation(
        self,
        kind,
        numbers_text,
        scope="1º–5º",
        submodalidade=None,
    ):
        raw = str(numbers_text or "").strip()
        if not raw:
            raise ValueError("Informe pelo menos um palpite.")

        combo_kinds = (
            set(GROUP_COMBO_SIZES)
            | set(DEZENA_COMBO_SIZES)
            | set(PASSE_MODALITIES)
        )

        if kind in combo_kinds:
            tokens = [
                t.strip()
                for t in re.split(r"[,;\n]+", raw)
                if t.strip()
            ]
        else:
            tokens = [
                t.strip()
                for t in re.split(r"[,;\s]+", raw)
                if t.strip()
            ]

        rows = []
        seen = set()

        for token in tokens:
            if kind in GROUP_COMBO_SIZES:
                expected = GROUP_COMBO_SIZES[kind]
                groups = self._parse_group_combo(token)
                if len(groups) != expected:
                    raise ValueError(
                        f"{kind} inválida: {token}. "
                        f"Informe {expected} grupos."
                    )
                normalized_groups = sorted(groups)
                normalized = "-".join(
                    f"{g:02d}" for g in normalized_groups
                )
                groups = normalized_groups
                if normalized in seen:
                    continue
                seen.add(normalized)
                rows.append({
                    "grupo": None,
                    "bicho": " + ".join(BICHOS[g] for g in groups),
                    "numero": normalized,
                    "dezena_base": "—",
                    "regra": "Manual",
                })
                continue

            if kind in PASSE_MODALITIES:
                groups = self._parse_group_combo(token)
                if len(groups) != 2:
                    raise ValueError(
                        f"{kind} inválido: {token}. Informe dois grupos."
                    )
                if kind == "Passe vai e vem":
                    groups = sorted(groups)
                normalized = "-".join(
                    f"{g:02d}" for g in groups
                )
                if normalized in seen:
                    continue
                seen.add(normalized)
                rows.append({
                    "grupo": None,
                    "bicho": (
                        f"{BICHOS[groups[0]]} → {BICHOS[groups[1]]}"
                        if kind == "Passe vai"
                        else f"{BICHOS[groups[0]]} ↔ {BICHOS[groups[1]]}"
                    ),
                    "numero": normalized,
                    "dezena_base": "—",
                    "regra": "Manual",
                })
                continue

            if kind in DEZENA_COMBO_SIZES:
                expected = DEZENA_COMBO_SIZES[kind]
                parts = [
                    p for p in re.split(r"[-/+\s]+", token.strip())
                    if p
                ]
                if len(parts) != expected:
                    raise ValueError(
                        f"{kind} inválido: {token}. "
                        f"Informe {expected} dezenas."
                    )
                nums = []
                for part in parts:
                    digits = re.sub(r"\D", "", part)
                    if not digits or int(digits) > 99:
                        raise ValueError(f"Dezena inválida: {part}")
                    nums.append(digits.zfill(2))
                if len(set(nums)) != expected:
                    raise ValueError(
                        f"{kind} exige dezenas distintas: {token}"
                    )
                normalized = "-".join(nums)
                if normalized in seen:
                    continue
                seen.add(normalized)
                rows.append({
                    "grupo": None,
                    "bicho": " + ".join(nums),
                    "numero": normalized,
                    "dezena_base": "—",
                    "regra": "Manual",
                })
                continue

            digits = re.sub(r"\D", "", token)
            if not digits:
                continue

            base_kind = (
                INVERTED_MODALITIES[kind][0]
                if kind in INVERTED_MODALITIES
                else kind
            )

            if base_kind == "Grupo":
                value = int(digits)
                if not 1 <= value <= 25:
                    raise ValueError(f"Grupo inválido: {token}")
                number = f"{value:02d}"
                group = value

            elif base_kind == "Dezena":
                if len(digits) > 2 or int(digits) > 99:
                    raise ValueError(f"Dezena inválida: {token}")
                number = digits.zfill(2)
                dez = int(number)
                group = 25 if dez == 0 else ((dez - 1) // 4) + 1

            elif base_kind == "Centena":
                if len(digits) > 3:
                    raise ValueError(f"Centena inválida: {token}")
                number = digits.zfill(3)
                dez = int(number[-2:])
                group = 25 if dez == 0 else ((dez - 1) // 4) + 1

            elif base_kind == "Milhar":
                if len(digits) > 4:
                    raise ValueError(f"Milhar inválida: {token}")
                number = digits.zfill(4)
                dez = int(number[-2:])
                group = 25 if dez == 0 else ((dez - 1) // 4) + 1

            else:
                raise ValueError(
                    f"Entrada manual ainda não suporta {kind}."
                )

            if number in seen:
                continue
            seen.add(number)

            rule = "Manual"
            if kind in INVERTED_MODALITIES:
                rule += (
                    f" • {self._unique_permutation_count(number)} inversões"
                )

            rows.append({
                "grupo": group,
                "bicho": BICHOS[group],
                "numero": number,
                "dezena_base": number[-2:] if base_kind != "Grupo" else "—",
                "regra": rule,
            })

        if not rows:
            raise ValueError("Nenhum palpite válido foi informado.")

        forced_scope = (
            "1º–5º"
            if kind in FIXED_PLACEMENT_MODALITIES
            else scope
        )

        return {
            "kind": kind,
            "strategy": "Manual",
            "scope": forced_scope,
            "selector": "Manual",
            "submodalidade": (
                submodalidade
                if kind == "Milhar"
                else None
            ),
            "rows": rows,
        }

    def target_has_result(self, target):
        if not target:
            return False

        if target.get("whole_day"):
            with self.connect() as con:
                return con.execute(
                    "SELECT 1 FROM resultados "
                    "WHERE data=? AND premio=1 LIMIT 1",
                    (target["data"],),
                ).fetchone() is not None

        if not target.get("sorteio") or not target.get("hora"):
            return False

        return self.get_draw(
            target["data"],
            target["sorteio"],
            target["hora"],
        ) is not None

    def register_ticket(self, entries, base_draw=None):
        if not entries:
            raise ValueError("O bilhete está vazio.")

        targets = []

        for entry in entries:
            generation = entry.get("generation")
            if not generation or not generation.get("rows"):
                raise ValueError("Há uma entrada do bilhete sem palpites.")

            target = (
                generation.get("intended_target")
                or self.next_operational_target()
            )
            if not target:
                raise ValueError(
                    "Não foi possível identificar o alvo do bilhete."
                )

            targets.append((
                target.get("data"),
                target.get("sorteio"),
                target.get("hora"),
            ))

        if len(set(targets)) != 1:
            raise ValueError(
                "O bilhete contém jogos para rodadas diferentes. "
                "Registre uma rodada por vez."
            )

        target_data, target_sort, target_hour = targets[0]

        with self.connect() as con:
            cur = con.execute("""
                INSERT INTO bilhetes
                (alvo_data, alvo_sorteio, alvo_hora, status)
                VALUES (?, ?, ?, 'PENDENTE')
            """, (
                target_data,
                target_sort,
                target_hour,
            ))
            ticket_id = int(cur.lastrowid)

        created = []

        try:
            for entry in entries:
                generation = copy.deepcopy(entry["generation"])
                generation["origem_jogada"] = entry.get(
                    "origem_jogada",
                    "Gerada",
                )

                game_id = self.register_play(
                    generation,
                    float(entry["stake_per_item"]),
                    base_draw=base_draw,
                )

                with self.connect() as con:
                    con.execute("""
                        UPDATE jogos_congelados
                        SET
                            origem_jogada=?,
                            bilhete_id=?
                        WHERE id=?
                    """, (
                        entry.get("origem_jogada", "Gerada"),
                        ticket_id,
                        int(game_id),
                    ))

                created.append(game_id)

            self.refresh_ticket_totals(ticket_id)

        except Exception:
            with self.connect() as con:
                if created:
                    con.executemany(
                        "DELETE FROM jogos_congelados WHERE id=?",
                        [(int(gid),) for gid in created],
                    )
                con.execute(
                    "DELETE FROM bilhetes WHERE id=?",
                    (ticket_id,),
                )
            raise

        return {
            "ticket_id": ticket_id,
            "game_ids": created,
        }

    def delete_ticket(self, ticket_id):
        """Exclui um bilhete registrado e todos os jogos/itens ligados a ele."""
        ticket_id = int(ticket_id)
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM bilhetes WHERE id=?",
                (ticket_id,),
            ).fetchone()
            if row is None:
                return {
                    "deleted": False,
                    "ticket_id": ticket_id,
                    "games_deleted": 0,
                }

            game_ids = [
                int(r["id"])
                for r in con.execute(
                    "SELECT id FROM jogos_congelados WHERE bilhete_id=? ORDER BY id",
                    (ticket_id,),
                ).fetchall()
            ]

            if game_ids:
                con.executemany(
                    "DELETE FROM jogos_itens WHERE jogo_id=?",
                    [(gid,) for gid in game_ids],
                )
                con.execute(
                    "DELETE FROM jogos_congelados WHERE bilhete_id=?",
                    (ticket_id,),
                )

            con.execute(
                "DELETE FROM bilhetes WHERE id=?",
                (ticket_id,),
            )

        return {
            "deleted": True,
            "ticket_id": ticket_id,
            "games_deleted": len(game_ids),
            "ticket": dict(row),
        }

    def play_round_summaries(self, limit=200):
        groups = {}

        for game in self.list_frozen_games(limit=5000):
            target = self.game_planned_target(game)
            if not target:
                key = (
                    game.get("alvo_data") or game.get("base_data") or "",
                    game.get("alvo_sorteio") or "?",
                    game.get("alvo_hora") or "",
                )
            else:
                key = (
                    target.get("data") or "",
                    target.get("sorteio") or "DIA",
                    target.get("hora") or "",
                )

            bucket = groups.setdefault(key, {
                "key": key,
                "data": key[0],
                "sorteio": key[1],
                "hora": key[2],
                "games": 0,
                "real_games": 0,
                "frozen_games": 0,
                "ticket_ids": set(),
                "legacy_real_games": 0,
                "legacy_games": 0,
                "modalidades": set(),
                "apostado": 0.0,
                "retorno": 0.0,
                "liquido_fechado": 0.0,
                "pendente": 0.0,
                "pending_count": 0,
                "audited_count": 0,
            })

            bucket["games"] += 1

            if game.get("bilhete_id"):
                bucket["ticket_ids"].add(int(game["bilhete_id"]))
            else:
                bucket["legacy_games"] += 1

            label = game["tipo"]
            if game.get("submodalidade"):
                label += f"/{game['submodalidade']}"
            bucket["modalidades"].add(label)

            if game.get("jogado"):
                bucket["real_games"] += 1
                if not game.get("bilhete_id"):
                    bucket["legacy_real_games"] += 1

                stake = float(game.get("valor_total") or 0)
                bucket["apostado"] += stake

                if game["status"] == "AUDITADO":
                    bucket["audited_count"] += 1
                    ret = float(game.get("retorno_real") or 0)
                    bucket["retorno"] += ret
                    bucket["liquido_fechado"] += ret - stake
                else:
                    bucket["pending_count"] += 1
                    bucket["pendente"] += stake
            else:
                bucket["frozen_games"] += 1
                if game["status"] == "PENDENTE":
                    bucket["pending_count"] += 1
                else:
                    bucket["audited_count"] += 1

        rows = []

        for bucket in groups.values():
            bucket["modalidades_text"] = ", ".join(
                sorted(bucket["modalidades"])
            )
            bucket["ticket_count"] = (
                len(bucket["ticket_ids"])
                + (1 if bucket["legacy_games"] else 0)
            )
            bucket["status"] = (
                "Aguardando"
                if bucket["pending_count"]
                else "Finalizado"
            )
            bucket["ticket_ids"] = sorted(bucket["ticket_ids"])
            rows.append(bucket)

        rows.sort(
            key=lambda r: (
                r["data"],
                r["hora"],
                r["sorteio"],
            ),
            reverse=True,
        )
        return rows[:int(limit)]

    def refresh_ticket_totals(self, ticket_id):
        with self.connect() as con:
            games = [
                dict(r)
                for r in con.execute("""
                    SELECT *
                    FROM jogos_congelados
                    WHERE bilhete_id=?
                    ORDER BY id
                """, (int(ticket_id),)).fetchall()
            ]

            if not games:
                con.execute(
                    "DELETE FROM bilhetes WHERE id=?",
                    (int(ticket_id),),
                )
                return None

            total = sum(
                float(g.get("valor_total") or 0)
                for g in games
                if g.get("jogado")
            )

            retorno = sum(
                float(g.get("retorno_real") or 0)
                for g in games
                if g.get("jogado")
                and g["status"] == "AUDITADO"
            )

            closed_stake = sum(
                float(g.get("valor_total") or 0)
                for g in games
                if g.get("jogado")
                and g["status"] == "AUDITADO"
            )

            pending = any(
                g["status"] == "PENDENTE"
                for g in games
            )

            status = "PENDENTE" if pending else "AUDITADO"
            net = retorno - closed_stake

            con.execute("""
                UPDATE bilhetes
                SET
                    status=?,
                    total_apostado=?,
                    retorno_real=?,
                    resultado_liquido=?
                WHERE id=?
            """, (
                status,
                total,
                retorno,
                net,
                int(ticket_id),
            ))

        return self.ticket_details(ticket_id)

    def ticket_details(self, ticket_id):
        with self.connect() as con:
            ticket = con.execute(
                "SELECT * FROM bilhetes WHERE id=?",
                (int(ticket_id),),
            ).fetchone()

            if ticket is None:
                raise ValueError("Bilhete não encontrado.")

            games = con.execute("""
                SELECT *
                FROM jogos_congelados
                WHERE bilhete_id=?
                ORDER BY id
            """, (int(ticket_id),)).fetchall()

        return {
            "ticket": dict(ticket),
            "games": [dict(g) for g in games],
        }

    def tickets_for_round(self, round_key):
        data, sorteio, hora = round_key

        with self.connect() as con:
            rows = con.execute("""
                SELECT *
                FROM bilhetes
                WHERE alvo_data=?
                  AND COALESCE(alvo_sorteio, '')=?
                  AND COALESCE(alvo_hora, '')=?
                ORDER BY id DESC
            """, (
                data,
                "" if sorteio == "DIA" else sorteio,
                hora or "",
            )).fetchall()

        out = []

        for row in rows:
            ticket = dict(row)
            detail = self.ticket_details(ticket["id"])
            ticket["games"] = detail["games"]
            ticket["modalidades"] = ", ".join(
                sorted({
                    (
                        g["tipo"]
                        + (
                            f"/{g['submodalidade']}"
                            if g.get("submodalidade")
                            else ""
                        )
                    )
                    for g in detail["games"]
                })
            )
            out.append(ticket)

        # Jogos reais anteriores à v0.22 sem bilhete formal.
        legacy = [
            g
            for g in self.games_for_round(round_key)
            if not g.get("bilhete_id")
        ]

        if legacy:
            out.append({
                "id": None,
                "legacy": True,
                "alvo_data": data,
                "alvo_sorteio": (
                    None if sorteio == "DIA" else sorteio
                ),
                "alvo_hora": hora,
                "status": (
                    "PENDENTE"
                    if any(g["status"] == "PENDENTE" for g in legacy)
                    else "AUDITADO"
                ),
                "total_apostado": sum(
                    float(g.get("valor_total") or 0)
                    for g in legacy
                    if g.get("jogado")
                ),
                "retorno_real": sum(
                    float(g.get("retorno_real") or 0)
                    for g in legacy
                    if g.get("jogado")
                ),
                "resultado_liquido": sum(
                    float(g.get("resultado_liquido") or 0)
                    for g in legacy
                    if g["status"] == "AUDITADO"
                ),
                "modalidades": ", ".join(
                    sorted({
                        g["tipo"]
                        + (
                            f"/{g['submodalidade']}"
                            if g.get("submodalidade")
                            else ""
                        )
                        for g in legacy
                    })
                ),
                "games": legacy,
            })

        return out

    def games_for_ticket(self, ticket_id, round_key=None):
        if ticket_id is None:
            if round_key is None:
                return []
            return [
                g
                for g in self.games_for_round(round_key)
                if not g.get("bilhete_id")
            ]

        return self.ticket_details(ticket_id)["games"]

    def copy_ticket_text(self, ticket_id, round_key=None):
        if ticket_id is None:
            games = self.games_for_ticket(
                None,
                round_key=round_key,
            )
            if not games:
                raise ValueError("Bilhete legado vazio.")
            target = self.game_planned_target(games[0])
            title = "BILHETE LEGADO"
        else:
            detail = self.ticket_details(ticket_id)
            games = detail["games"]
            t = detail["ticket"]
            target = {
                "data": t["alvo_data"],
                "sorteio": t["alvo_sorteio"],
                "hora": t["alvo_hora"],
                "whole_day": not bool(t["alvo_sorteio"]),
            }
            title = f"BILHETE #{ticket_id}"

        date_txt = datetime.strptime(
            target["data"],
            "%Y-%m-%d",
        ).strftime("%d/%m/%Y")

        if target.get("whole_day"):
            header = f"{date_txt} • DIA • 1º prêmio"
        else:
            header = (
                f"{date_txt} • "
                f"{target.get('sorteio') or '—'} "
                f"{target.get('hora') or ''}"
            ).strip()

        lines = [
            title,
            header,
            "",
        ]

        grand_total = 0.0

        for game in games:
            detail = self.frozen_game_details(game["id"])
            modality = game["tipo"]
            if game.get("submodalidade"):
                modality += f" / {game['submodalidade']}"

            stake = float(game.get("valor_unitario") or 0)
            subtotal = float(game.get("valor_total") or 0)
            grand_total += subtotal

            lines.append(
                f"{modality.upper()} • {game['escopo']} "
                f"• {self._format_money_plain(stake)} por palpite"
            )

            nums = [
                str(item["numero"])
                for item in detail["items"]
            ]

            for i in range(0, len(nums), 4):
                lines.append("  " + "   ".join(nums[i:i+4]))

            lines.append(
                f"Subtotal: {self._format_money_plain(subtotal)}"
            )
            lines.append("")

        lines.append(
            f"TOTAL DO BILHETE: {self._format_money_plain(grand_total)}"
        )
        return "\n".join(lines)

    @staticmethod
    def _format_money_plain(value):
        value = float(value or 0)
        text = f"{value:,.2f}"
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {text}"

    def games_for_round(self, round_key):
        data, sorteio, hora = round_key
        matched = []

        for game in self.list_frozen_games(limit=5000):
            target = self.game_planned_target(game)
            if target:
                key = (
                    target.get("data") or "",
                    target.get("sorteio") or "DIA",
                    target.get("hora") or "",
                )
            else:
                key = (
                    game.get("alvo_data") or game.get("base_data") or "",
                    game.get("alvo_sorteio") or "?",
                    game.get("alvo_hora") or "",
                )
            if key == (data, sorteio, hora):
                matched.append(game)

        return matched

    def financial_summary(self, period="today"):
        today = datetime.now().date()

        if period == "today":
            start = today
            end = today
        elif period == "week":
            start = today - timedelta(days=today.weekday())
            end = today
        elif period == "month":
            start = today.replace(day=1)
            end = today
        else:
            raise ValueError("Período inválido.")

        summary = {
            "period": period,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "games": 0,
            "rounds": set(),
            "apostado": 0.0,
            "retorno": 0.0,
            "apostado_fechado": 0.0,
            "liquido_fechado": 0.0,
            "em_aberto": 0.0,
            "positivas": 0,
        }

        round_closed = {}

        for game in self.list_frozen_games(limit=10000):
            if not game.get("jogado"):
                continue

            target = self.game_planned_target(game)
            if not target or not target.get("data"):
                continue

            try:
                d = datetime.strptime(
                    target["data"], "%Y-%m-%d"
                ).date()
            except Exception:
                continue

            if not (start <= d <= end):
                continue

            summary["games"] += 1
            key = (
                target.get("data"),
                target.get("sorteio") or "DIA",
                target.get("hora") or "",
            )
            summary["rounds"].add(key)

            stake = float(game.get("valor_total") or 0)
            summary["apostado"] += stake

            if game["status"] == "AUDITADO":
                ret = float(game.get("retorno_real") or 0)
                summary["retorno"] += ret
                summary["apostado_fechado"] += stake
                summary["liquido_fechado"] += ret - stake

                rb = round_closed.setdefault(
                    key, {"stake": 0.0, "return": 0.0}
                )
                rb["stake"] += stake
                rb["return"] += ret
            else:
                summary["em_aberto"] += stake

        summary["positivas"] = sum(
            1
            for r in round_closed.values()
            if r["return"] > r["stake"]
        )
        summary["round_count"] = len(summary["rounds"])
        summary["roi"] = (
            summary["liquido_fechado"]
            / summary["apostado_fechado"]
            * 100.0
            if summary["apostado_fechado"] > 0
            else None
        )
        summary["rounds"] = list(summary["rounds"])
        return summary

    def financial_by_kind(self, period="month"):
        base = {}
        today = datetime.now().date()

        if period == "today":
            start = today
        elif period == "week":
            start = today - timedelta(days=today.weekday())
        else:
            start = today.replace(day=1)

        for game in self.list_frozen_games(limit=10000):
            if not game.get("jogado"):
                continue

            target = self.game_planned_target(game)
            if not target or not target.get("data"):
                continue

            try:
                d = datetime.strptime(
                    target["data"], "%Y-%m-%d"
                ).date()
            except Exception:
                continue

            if not (start <= d <= today):
                continue

            label = game["tipo"]
            if game.get("submodalidade"):
                label += f" / {game['submodalidade']}"

            row = base.setdefault(label, {
                "modalidade": label,
                "jogos": 0,
                "apostado": 0.0,
                "retorno": 0.0,
                "fechados": 0,
                "liquido": 0.0,
            })

            stake = float(game.get("valor_total") or 0)
            row["jogos"] += 1
            row["apostado"] += stake

            if game["status"] == "AUDITADO":
                ret = float(game.get("retorno_real") or 0)
                row["fechados"] += 1
                row["retorno"] += ret
                row["liquido"] += ret - stake

        rows = list(base.values())
        rows.sort(
            key=lambda r: (-r["apostado"], r["modalidade"])
        )
        return rows

    def financial_history(
        self,
        date_from=None,
        date_to=None,
        modality=None,
        method=None,
        status=None,
        limit=2000,
    ):
        rows = []

        for game in self.list_frozen_games(limit=10000):
            if not game.get("jogado"):
                continue

            target = self.game_planned_target(game)
            if not target or not target.get("data"):
                continue

            d = target["data"]

            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue

            label = game["tipo"]
            if game.get("submodalidade"):
                label += f" / {game['submodalidade']}"

            method_label = (
                f"{game.get('seletor') or '—'} | "
                f"{game.get('estrategia') or '—'}"
            )

            if modality and modality != "Todos" and label != modality:
                continue
            if method and method != "Todos" and method_label != method:
                continue

            visual_status = (
                "Aguardando"
                if game["status"] == "PENDENTE"
                else (
                    "Positivo"
                    if float(game.get("resultado_liquido") or 0) > 0
                    else (
                        "Empate"
                        if abs(float(game.get("resultado_liquido") or 0)) < 1e-12
                        else "Negativo"
                    )
                )
            )

            if status and status != "Todos" and visual_status != status:
                continue

            rows.append({
                "id": game["id"],
                "bilhete_id": game.get("bilhete_id"),
                "data": d,
                "sorteio": target.get("sorteio") or "DIA",
                "hora": target.get("hora") or "",
                "modalidade": label,
                "metodo": method_label,
                "qtd": int(game.get("total_itens") or 0),
                "apostado": float(game.get("valor_total") or 0),
                "retorno": (
                    float(game.get("retorno_real") or 0)
                    if game["status"] == "AUDITADO"
                    else None
                ),
                "liquido": (
                    float(game.get("resultado_liquido") or 0)
                    if game["status"] == "AUDITADO"
                    else None
                ),
                "status": visual_status,
            })

        rows.sort(
            key=lambda r: (
                r["data"],
                r["hora"],
                r["id"],
            ),
            reverse=True,
        )

        return rows[:int(limit)]

    def financial_filter_options(self):
        modalities = set()
        methods = set()

        for game in self.list_frozen_games(limit=10000):
            if not game.get("jogado"):
                continue

            modality = game["tipo"]
            if game.get("submodalidade"):
                modality += f" / {game['submodalidade']}"
            modalities.add(modality)

            methods.add(
                f"{game.get('seletor') or '—'} | "
                f"{game.get('estrategia') or '—'}"
            )

        return {
            "modalidades": ["Todos"] + sorted(modalities),
            "metodos": ["Todos"] + sorted(methods),
            "status": [
                "Todos",
                "Aguardando",
                "Positivo",
                "Negativo",
                "Empate",
            ],
        }

    def method_financial_performance(
        self,
        date_from=None,
        date_to=None,
    ):
        groups = {}

        for game in self.list_frozen_games(limit=10000):
            if not game.get("jogado"):
                continue

            target = self.game_planned_target(game)
            if not target or not target.get("data"):
                continue

            d = target["data"]
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue

            selector = game.get("seletor") or "Não registrado"
            strategy = game.get("estrategia") or "—"
            key = (selector, strategy)

            rec = groups.setdefault(key, {
                "seletor": selector,
                "estrategia": strategy,
                "jogos": 0,
                "fechados": 0,
                "vencedores": 0,
                "itens": 0,
                "acertos": 0,
                "apostado": 0.0,
                "retorno": 0.0,
                "liquido": 0.0,
            })

            rec["jogos"] += 1
            rec["itens"] += int(game.get("total_itens") or 0)
            rec["apostado"] += float(game.get("valor_total") or 0)

            if game["status"] == "AUDITADO":
                rec["fechados"] += 1
                rec["acertos"] += int(game.get("acertos") or 0)
                ret = float(game.get("retorno_real") or 0)
                stake = float(game.get("valor_total") or 0)
                rec["retorno"] += ret
                rec["liquido"] += ret - stake
                if ret > stake:
                    rec["vencedores"] += 1

        rows = list(groups.values())

        for rec in rows:
            rec["roi"] = (
                rec["liquido"] / rec["apostado"] * 100.0
                if rec["apostado"] > 0
                else None
            )
            rec["taxa_jogo_positivo"] = (
                rec["vencedores"] / rec["fechados"] * 100.0
                if rec["fechados"] > 0
                else None
            )
            rec["acertos_por_item"] = (
                rec["acertos"] / rec["itens"] * 100.0
                if rec["itens"] > 0
                else None
            )

        rows.sort(
            key=lambda r: (
                -r["fechados"],
                -(r["roi"] if r["roi"] is not None else -999999),
                r["seletor"],
                r["estrategia"],
            )
        )
        return rows

    def set_bankroll(self, initial_value, start_date=None):
        value = float(initial_value)
        if value < 0:
            raise ValueError("A banca inicial não pode ser negativa.")

        if start_date is None:
            start_date = datetime.now().strftime("%Y-%m-%d")

        datetime.strptime(start_date, "%Y-%m-%d")

        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO meta(chave, valor) VALUES(?, ?)",
                ("bankroll_initial", str(value)),
            )
            con.execute(
                "INSERT OR REPLACE INTO meta(chave, valor) VALUES(?, ?)",
                ("bankroll_start_date", str(start_date)),
            )

    def bankroll_status(self):
        raw = self._meta_value("bankroll_initial")
        start_date = self._meta_value("bankroll_start_date")

        if raw is None or start_date is None:
            return {
                "configured": False,
                "initial": 0.0,
                "start_date": None,
                "apostado": 0.0,
                "retorno": 0.0,
                "em_aberto": 0.0,
                "saldo": 0.0,
                "lucro_liquido": 0.0,
            }

        initial = float(raw or 0)
        apostado = 0.0
        retorno = 0.0
        em_aberto = 0.0

        for game in self.list_frozen_games(limit=10000):
            if not game.get("jogado"):
                continue

            target = self.game_planned_target(game)
            if not target or not target.get("data"):
                continue
            if target["data"] < start_date:
                continue

            stake = float(game.get("valor_total") or 0)
            apostado += stake

            if game["status"] == "AUDITADO":
                retorno += float(game.get("retorno_real") or 0)
            else:
                em_aberto += stake

        saldo = initial - apostado + retorno

        return {
            "configured": True,
            "initial": initial,
            "start_date": start_date,
            "apostado": apostado,
            "retorno": retorno,
            "em_aberto": em_aberto,
            "saldo": saldo,
            "lucro_liquido": saldo - initial,
        }

    def daily_closing_report(self, date_iso):
        datetime.strptime(date_iso, "%Y-%m-%d")

        history = self.financial_history(
            date_from=date_iso,
            date_to=date_iso,
            limit=10000,
        )

        total_stake = sum(r["apostado"] for r in history)
        total_return = sum(
            r["retorno"] or 0
            for r in history
            if r["retorno"] is not None
        )
        open_stake = sum(
            r["apostado"]
            for r in history
            if r["status"] == "Aguardando"
        )
        closed_stake = total_stake - open_stake
        closed_net = total_return - closed_stake

        by_round = {}
        by_modality = {}
        by_method = {}

        for row in history:
            round_key = (
                row["sorteio"],
                row["hora"],
            )
            rr = by_round.setdefault(
                round_key,
                {"stake":0.0,"return":0.0,"open":0.0},
            )
            rr["stake"] += row["apostado"]
            if row["retorno"] is None:
                rr["open"] += row["apostado"]
            else:
                rr["return"] += row["retorno"]

            mm = by_modality.setdefault(
                row["modalidade"],
                {"stake":0.0,"return":0.0,"open":0.0},
            )
            mm["stake"] += row["apostado"]
            if row["retorno"] is None:
                mm["open"] += row["apostado"]
            else:
                mm["return"] += row["retorno"]

            meth = by_method.setdefault(
                row["metodo"],
                {"stake":0.0,"return":0.0,"open":0.0},
            )
            meth["stake"] += row["apostado"]
            if row["retorno"] is None:
                meth["open"] += row["apostado"]
            else:
                meth["return"] += row["retorno"]

        date_br = datetime.strptime(
            date_iso,
            "%Y-%m-%d",
        ).strftime("%d/%m/%Y")

        lines = [
            f"FECHAMENTO DO DIA — {date_br}",
            "",
            f"Apostado: {self._format_money_plain(total_stake)}",
            f"Retorno: {self._format_money_plain(total_return)}",
            f"Saldo fechado: {self._format_money_plain(closed_net)}",
            f"Em aberto: {self._format_money_plain(open_stake)}",
            "",
            "RODADAS",
        ]

        for (sorteio, hora), data in sorted(by_round.items(), key=lambda x: x[0][1]):
            closed = data["stake"] - data["open"]
            net = data["return"] - closed
            lines.append(
                f"- {sorteio} {hora}: "
                f"apostado {self._format_money_plain(data['stake'])} • "
                f"retorno {self._format_money_plain(data['return'])} • "
                f"saldo fechado {self._format_money_plain(net)}"
                + (
                    f" • aberto {self._format_money_plain(data['open'])}"
                    if data["open"] else ""
                )
            )

        lines.append("")
        lines.append("MODALIDADES")

        for modality, data in sorted(by_modality.items()):
            closed = data["stake"] - data["open"]
            net = data["return"] - closed
            lines.append(
                f"- {modality}: "
                f"{self._format_money_plain(net)}"
            )

        lines.append("")
        lines.append("MÉTODOS")

        for method, data in sorted(by_method.items()):
            closed = data["stake"] - data["open"]
            net = data["return"] - closed
            lines.append(
                f"- {method}: "
                f"{self._format_money_plain(net)}"
            )

        return {
            "date": date_iso,
            "history": history,
            "apostado": total_stake,
            "retorno": total_return,
            "saldo_fechado": closed_net,
            "em_aberto": open_stake,
            "text": "\n".join(lines),
        }

    def update_pending_play(
        self,
        game_id,
        kind,
        scope,
        numbers_text,
        value_per_item,
        target,
        submodalidade=None,
    ):
        detail = self.frozen_game_details(game_id)
        game = detail["game"]

        if game["status"] != "PENDENTE":
            raise ValueError(
                "Jogada já auditada não pode ser alterada."
            )

        current_check = self.audit_frozen_game(game_id)
        if current_check.get("audited"):
            raise ValueError(
                "O resultado já estava disponível; a jogada foi bloqueada."
            )

        if self.target_has_result(target):
            raise ValueError(
                "O alvo escolhido já possui resultado. "
                "Não é permitido editar retroativamente."
            )

        generation = self.manual_generation(
            kind,
            numbers_text,
            scope=scope,
            submodalidade=submodalidade,
        )
        rows = generation["rows"]

        stake = float(value_per_item)
        if stake <= 0:
            raise ValueError(
                "O valor por palpite deve ser maior que zero."
            )

        snap = self._financial_bounds_for_rows(
            kind,
            generation["scope"],
            rows,
            stake,
            submodalidade=generation.get("submodalidade"),
        )

        old_numbers = [
            str(i["numero"])
            for i in detail["items"]
        ]
        new_numbers = [
            str(r["numero"])
            for r in rows
        ]

        changed_definition = (
            kind != game["tipo"]
            or generation["scope"] != game["escopo"]
            or (
                generation.get("submodalidade") or ""
            ) != (
                game.get("submodalidade") or ""
            )
            or old_numbers != new_numbers
            or target.get("data") != game.get("alvo_data")
            or target.get("sorteio") != game.get("alvo_sorteio")
            or target.get("hora") != game.get("alvo_hora")
        )

        with self.connect() as con:
            if changed_definition:
                selector = "Manual/Editado"
                strategy = "Manual/Editado"
            else:
                selector = (
                    game.get("seletor")
                    or "Não registrado"
                )
                strategy = (
                    game.get("estrategia")
                    or "Manual"
                )

            con.execute("""
                UPDATE jogos_congelados
                SET
                    seletor=?,
                    estrategia=?,
                    tipo=?,
                    submodalidade=?,
                    escopo=?,
                    alvo_modo='ALVO_ESPECIFICO',
                    alvo_data=?,
                    alvo_sorteio=?,
                    alvo_hora=?,
                    total_itens=?,
                    valor_unitario=?,
                    valor_total=?,
                    divisor_posicoes=?,
                    valor_posicao=?,
                    multiplicador=?,
                    cotacao_primaria=?,
                    cotacao_secundaria=?,
                    cotacao_combinada=?,
                    retorno_min=?,
                    retorno_max=?,
                    retorno_real=NULL,
                    resultado_liquido=NULL,
                    acertos=0,
                    acertos_financeiros=0,
                    auditado_em=NULL,
                    status='PENDENTE',
                    editado_em=CURRENT_TIMESTAMP,
                    origem_jogada='Editada'
                WHERE id=?
            """, (
                selector,
                strategy,
                kind,
                generation.get("submodalidade"),
                generation["scope"],
                target.get("data"),
                target.get("sorteio"),
                target.get("hora"),
                len(rows),
                snap["valor_unitario"],
                snap["valor_total"],
                snap["divisor_posicoes"],
                snap["valor_posicao"],
                snap["multiplicador"],
                snap["cotacao_primaria"],
                snap["cotacao_secundaria"],
                snap["cotacao_combinada"],
                snap["retorno_min"],
                snap["retorno_max"],
                int(game_id),
            ))

            con.execute(
                "DELETE FROM jogos_itens WHERE jogo_id=?",
                (int(game_id),),
            )

            con.executemany("""
                INSERT INTO jogos_itens
                (
                    jogo_id, ordem, grupo, bicho,
                    numero, dezena_base, regra
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    int(game_id),
                    i,
                    row.get("grupo"),
                    row.get("bicho"),
                    str(row.get("numero", "")),
                    row.get("dezena_base"),
                    row.get("regra"),
                )
                for i, row in enumerate(rows, start=1)
            ])

        if game.get("bilhete_id"):
            self.refresh_ticket_totals(
                int(game["bilhete_id"])
            )

        return self.frozen_game_details(game_id)

    def frozen_performance_filter_options(self):
        with self.connect() as con:
            selectors = [
                r[0] for r in con.execute("""
                    SELECT DISTINCT seletor
                    FROM jogos_congelados
                    WHERE seletor IS NOT NULL AND TRIM(seletor) <> ''
                    ORDER BY seletor
                """).fetchall()
            ]
            strategies = [
                r[0] for r in con.execute("""
                    SELECT DISTINCT estrategia
                    FROM jogos_congelados
                    ORDER BY estrategia
                """).fetchall()
            ]
            kinds = [
                r[0] for r in con.execute("""
                    SELECT DISTINCT tipo
                    FROM jogos_congelados
                    ORDER BY tipo
                """).fetchall()
            ]
            scopes = [
                r[0] for r in con.execute("""
                    SELECT DISTINCT escopo
                    FROM jogos_congelados
                    ORDER BY escopo
                """).fetchall()
            ]

        return {
            "selectors": selectors,
            "strategies": strategies,
            "kinds": kinds,
            "scopes": scopes,
        }

    def frozen_performance(
        self,
        selector="Todos",
        strategy="Todos",
        kind="Todos",
        scope="Todos",
    ):
        """
        Resume apenas jogos realmente congelados.

        Métricas:
        - jogo vencedor: jogo auditado com >=1 item exato acertado;
        - taxa de jogos: vencedores / jogos auditados;
        - taxa por item: itens exatos acertados / itens auditados;
        - média: acertos exatos / jogo auditado.

        A tabela é agrupada por Seletor + Estratégia + Tipo + Escopo.
        """
        where = []
        args = []

        if selector != "Todos":
            where.append("seletor = ?")
            args.append(selector)
        if strategy != "Todos":
            where.append("estrategia = ?")
            args.append(strategy)
        if kind != "Todos":
            where.append("tipo = ?")
            args.append(kind)
        if scope != "Todos":
            where.append("escopo = ?")
            args.append(scope)

        where_sql = ""
        if where:
            where_sql = " WHERE " + " AND ".join(where)

        with self.connect() as con:
            rows = con.execute(f"""
                SELECT
                    seletor,
                    estrategia,
                    tipo,
                    escopo,
                    COUNT(*) AS jogos_total,
                    SUM(CASE WHEN status='AUDITADO' THEN 1 ELSE 0 END)
                        AS jogos_auditados,
                    SUM(CASE WHEN status='PENDENTE' THEN 1 ELSE 0 END)
                        AS jogos_pendentes,
                    SUM(
                        CASE
                            WHEN status='AUDITADO' AND acertos > 0 THEN 1
                            ELSE 0
                        END
                    ) AS jogos_vencedores,
                    SUM(
                        CASE WHEN status='AUDITADO' THEN total_itens ELSE 0 END
                    ) AS itens_auditados,
                    SUM(
                        CASE WHEN status='AUDITADO' THEN acertos ELSE 0 END
                    ) AS acertos
                FROM jogos_congelados
                {where_sql}
                GROUP BY seletor, estrategia, tipo, escopo
            """, args).fetchall()

        result_rows = []

        for r in rows:
            audited = int(r["jogos_auditados"] or 0)
            pending = int(r["jogos_pendentes"] or 0)
            winners = int(r["jogos_vencedores"] or 0)
            items = int(r["itens_auditados"] or 0)
            hits = int(r["acertos"] or 0)

            game_rate = winners / audited * 100.0 if audited else 0.0
            item_rate = hits / items * 100.0 if items else 0.0
            avg_hits = hits / audited if audited else 0.0
            avg_items = items / audited if audited else 0.0

            result_rows.append({
                "seletor": r["seletor"] or "Não registrado",
                "estrategia": r["estrategia"],
                "tipo": r["tipo"],
                "escopo": r["escopo"],
                "jogos_total": int(r["jogos_total"] or 0),
                "jogos_auditados": audited,
                "jogos_pendentes": pending,
                "jogos_vencedores": winners,
                "itens_auditados": items,
                "acertos": hits,
                "taxa_jogos": game_rate,
                "taxa_itens": item_rate,
                "media_acertos": avg_hits,
                "media_itens": avg_items,
            })

        # Prioriza amostra auditada, não a taxa. Evita fazer um método com
        # 1 jogo aparecer automaticamente como "melhor" que um método testado.
        result_rows.sort(
            key=lambda r: (
                -r["jogos_auditados"],
                -r["itens_auditados"],
                -r["taxa_itens"],
                r["seletor"],
                r["estrategia"],
                r["tipo"],
            )
        )

        summary = {
            "jogos_total": sum(r["jogos_total"] for r in result_rows),
            "jogos_auditados": sum(r["jogos_auditados"] for r in result_rows),
            "jogos_pendentes": sum(r["jogos_pendentes"] for r in result_rows),
            "jogos_vencedores": sum(r["jogos_vencedores"] for r in result_rows),
            "itens_auditados": sum(r["itens_auditados"] for r in result_rows),
            "acertos": sum(r["acertos"] for r in result_rows),
        }

        summary["taxa_jogos"] = (
            summary["jogos_vencedores"]
            / summary["jogos_auditados"]
            * 100.0
            if summary["jogos_auditados"] else 0.0
        )
        summary["taxa_itens"] = (
            summary["acertos"]
            / summary["itens_auditados"]
            * 100.0
            if summary["itens_auditados"] else 0.0
        )
        summary["media_acertos"] = (
            summary["acertos"]
            / summary["jogos_auditados"]
            if summary["jogos_auditados"] else 0.0
        )

        return {
            "summary": summary,
            "rows": result_rows,
        }


    def audit_frozen_games(self):
        with self.connect() as con:
            ids = [
                r["id"]
                for r in con.execute("""
                    SELECT id
                    FROM jogos_congelados
                    WHERE status='PENDENTE'
                    ORDER BY id
                """).fetchall()
            ]

        audited = []
        pending = []

        for game_id in ids:
            result = self.audit_frozen_game(game_id)
            if result["audited"]:
                audited.append(result)
            else:
                pending.append(result)

        # Auditorias prospectivas auxiliares são silenciosas.
        try:
            shadow_changed = self.audit_shadow_snapshots()
        except Exception:
            shadow_changed = 0
        try:
            decision_changed = self.audit_decision_snapshots()
        except Exception:
            decision_changed = 0

        # v0.35.0 — o Laboratório deixa de depender de uma aposta oficial.
        # Sempre que chega/é auditado um resultado, congela silenciosamente a
        # leitura da próxima rodada operacional, ainda sem conhecer o resultado-alvo.
        try:
            _shadow_row, shadow_created = self.ensure_shadow_snapshot(
                trigger="POS_RESULTADO"
            )
        except Exception:
            shadow_created = False

        return {
            "audited": audited,
            "pending": pending,
            "audited_count": len(audited),
            "pending_count": len(pending),
            "shadow_audited_count": shadow_changed,
            "shadow_created_count": 1 if shadow_created else 0,
            "decision_audited_count": decision_changed,
        }


    def audit(self):
        problems = []
        with self.connect() as con:
            total = con.execute("SELECT COUNT(*) FROM resultados").fetchone()[0]
            min_d, max_d = con.execute("SELECT MIN(data), MAX(data) FROM resultados").fetchone()
            draws = con.execute("""
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT data,sorteio,hora FROM resultados
                )
            """).fetchone()[0]

            dup = con.execute("""
                SELECT COUNT(*) FROM (
                    SELECT data,sorteio,hora,premio,COUNT(*) c
                    FROM resultados
                    GROUP BY data,sorteio,hora,premio
                    HAVING c > 1
                )
            """).fetchone()[0]
            if dup:
                problems.append(f"{dup} chave(s) duplicada(s).")

            invalid = con.execute("""
                SELECT id, milhar, centena, dezena, grupo, bicho
                FROM resultados
                WHERE LENGTH(milhar)<>4 OR LENGTH(centena)<>3 OR LENGTH(dezena)<>2
                   OR grupo<1 OR grupo>25
            """).fetchall()
            if invalid:
                problems.append(f"{len(invalid)} registro(s) com formato inválido.")

            mismatch = 0
            rows = con.execute("SELECT milhar, grupo, bicho FROM resultados").fetchall()
            for r in rows:
                try:
                    _, _, _, g, b = derivados_milhar(r["milhar"])
                    if g != r["grupo"] or sem_acento(b) != sem_acento(r["bicho"]):
                        mismatch += 1
                except Exception:
                    mismatch += 1
            if mismatch:
                problems.append(f"{mismatch} registro(s) com grupo/bicho incompatível com a dezena.")

            pub_mismatch = con.execute("""
                SELECT COUNT(*) FROM resultados
                WHERE grupo_publicado IS NOT NULL AND grupo_publicado <> grupo
            """).fetchone()[0]
            if pub_mismatch:
                problems.append(
                    f"{pub_mismatch} divergência(s) entre o grupo publicado e o grupo calculado."
                )

            incomplete = con.execute("""
                SELECT data,sorteio,hora,COUNT(*) c
                FROM resultados
                GROUP BY data,sorteio,hora
                HAVING c <> 5
                ORDER BY data,hora
            """).fetchall()

        return {
            "total": total,
            "draws": draws,
            "min_date": min_d,
            "max_date": max_d,
            "problems": problems,
            "incomplete": [tuple(r) for r in incomplete],
        }


def parse_br_date(txt: str) -> str | None:
    txt = (txt or "").strip()
    if not txt:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Data inválida: {txt}. Use DD/MM/AAAA.")






PT_MONTHS = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]
PT_WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _db_home_summary(self):
    with self.connect() as con:
        prizes = con.execute("SELECT COUNT(*) FROM resultados").fetchone()[0]
        draws = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT DISTINCT data, sorteio, hora FROM resultados
            )
        """).fetchone()[0]
        days = con.execute("SELECT COUNT(DISTINCT data) FROM resultados").fetchone()[0]

    return {
        "prizes": prizes,
        "draws": draws,
        "days": days,
        "latest": self.latest_draw(),
    }


def _db_delay_leaders(self):
    """Retorna bicho, centena e dezena mais atrasados por extrações completas.

    Uma extração é identificada por (data, sorteio, hora). Qualquer aparição nos
    cinco prêmios zera o atraso daquele valor naquela extração. Centenas e dezenas
    nunca observadas não entram no ranking; empates são preservados.
    """
    empty = {"bicho": None, "centena": None, "dezena": None, "total_extracoes": 0}
    with self.connect() as con:
        rows = con.execute("""
            SELECT data, sorteio, hora, premio, milhar, centena, dezena, grupo, bicho
            FROM resultados
            ORDER BY data ASC, hora ASC, sorteio ASC, premio ASC
        """).fetchall()
    if not rows:
        return empty

    draw_keys = []
    draw_index = {}
    for r in rows:
        key = (r["data"], r["sorteio"], r["hora"])
        if key not in draw_index:
            draw_index[key] = len(draw_keys)
            draw_keys.append(key)
    newest_idx = len(draw_keys) - 1

    last_seen = {"bicho": {}, "centena": {}, "dezena": {}}
    last_row = {"bicho": {}, "centena": {}, "dezena": {}}
    for r in rows:
        idx = draw_index[(r["data"], r["sorteio"], r["hora"])]
        values = {
            "bicho": int(r["grupo"]),
            "centena": str(r["centena"]).zfill(3),
            "dezena": str(r["dezena"]).zfill(2),
        }
        for field, value in values.items():
            if idx >= last_seen[field].get(value, -1):
                last_seen[field][value] = idx
                last_row[field][value] = dict(r)

    result = {"total_extracoes": len(draw_keys)}
    for field in ("bicho", "centena", "dezena"):
        if not last_seen[field]:
            result[field] = None
            continue
        delays = {value: newest_idx - idx for value, idx in last_seen[field].items()}
        max_delay = max(delays.values())
        tied = sorted(
            [value for value, delay in delays.items() if delay == max_delay],
            key=lambda v: int(v) if str(v).isdigit() else str(v),
        )
        first = tied[0]
        result[field] = {
            "value": first,
            "delay": int(max_delay),
            "ties": tied,
            "tie_count": len(tied),
            "last": last_row[field][first],
        }
    return result


def _db_home_animal_cards(self):
    out = []
    with self.connect() as con:
        for g in range(1, 26):
            last = con.execute("""
                SELECT data, sorteio, hora, premio, milhar, centena, dezena
                FROM resultados
                WHERE grupo=?
                ORDER BY data DESC, hora DESC, premio ASC
                LIMIT 1
            """, (g,)).fetchone()

            occ = con.execute(
                "SELECT COUNT(*) FROM resultados WHERE grupo=?", (g,)
            ).fetchone()[0]

            p1 = con.execute(
                "SELECT COUNT(*) FROM resultados WHERE grupo=? AND premio=1", (g,)
            ).fetchone()[0]

            out.append({
                "grupo": g,
                "bicho": BICHOS[g],
                "dezenas": [f"{((g - 1) * 4 + i) % 100:02d}" for i in range(1, 5)],
                "ocorrencias": occ,
                "p1": p1,
                "ultima": dict(last) if last else None,
            })
    return out


Database.home_summary = _db_home_summary
Database.home_animal_cards = _db_home_animal_cards
Database.delay_leaders = _db_delay_leaders


class DatePickerDialog(tk.Toplevel):
    """Calendário simples feito apenas com Tkinter (sem dependências externas)."""
    def __init__(self, master, target_var: tk.StringVar, initial_date=None, title="Selecionar data"):
        super().__init__(master)
        self.target_var = target_var
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        if initial_date is None:
            initial_date = date.today()

        self.current_year = initial_date.year
        self.current_month = initial_date.month
        self.selected_date = initial_date

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        nav = ttk.Frame(outer)
        nav.pack(fill="x")

        ttk.Button(nav, text="◀", width=3, command=self.prev_month).pack(side="left")
        self.month_label = ttk.Label(
            nav, text="", font=("Segoe UI Semibold", 11), anchor="center"
        )
        self.month_label.pack(side="left", expand=True, fill="x", padx=8)
        ttk.Button(nav, text="▶", width=3, command=self.next_month).pack(side="right")

        self.days_frame = ttk.Frame(outer)
        self.days_frame.pack(fill="both", expand=True, pady=(10, 6))

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(4, 0))
        ttk.Button(footer, text="Hoje", command=self.select_today).pack(side="left")
        ttk.Button(footer, text="Limpar", command=self.clear_date).pack(side="left", padx=(6, 0))
        ttk.Button(footer, text="Cancelar", command=self.destroy).pack(side="right")

        self.render_calendar()

    def render_calendar(self):
        for child in self.days_frame.winfo_children():
            child.destroy()

        self.month_label.configure(
            text=f"{PT_MONTHS[self.current_month]} {self.current_year}"
        )

        for c, wd in enumerate(PT_WEEKDAYS):
            ttk.Label(
                self.days_frame,
                text=wd,
                width=5,
                anchor="center",
                font=("Segoe UI Semibold", 9)
            ).grid(row=0, column=c, padx=1, pady=1)

        cal = calendar.Calendar(firstweekday=0)  # segunda-feira
        month_days = cal.monthdayscalendar(self.current_year, self.current_month)

        for r, week in enumerate(month_days, start=1):
            for c, day_num in enumerate(week):
                if day_num == 0:
                    ttk.Label(self.days_frame, text="", width=5).grid(
                        row=r, column=c, padx=1, pady=1
                    )
                    continue

                d = date(self.current_year, self.current_month, day_num)
                text = f"{day_num:02d}"

                btn = ttk.Button(
                    self.days_frame,
                    text=text,
                    width=4,
                    command=lambda chosen=d: self.choose(chosen)
                )
                btn.grid(row=r, column=c, padx=1, pady=1)

    def prev_month(self):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self.render_calendar()

    def next_month(self):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self.render_calendar()

    def choose(self, chosen: date):
        self.target_var.set(chosen.strftime("%d/%m/%Y"))
        self.destroy()

    def select_today(self):
        self.choose(date.today())

    def clear_date(self):
        self.target_var.set("")
        self.destroy()


class CalendarField(ttk.Frame):
    """Campo de data somente leitura + botão de calendário."""
    def __init__(self, master, textvariable: tk.StringVar, width=12, on_change=None):
        super().__init__(master)
        self.var = textvariable
        self.on_change = on_change

        self.entry = ttk.Entry(
            self, textvariable=self.var, width=width, state="readonly"
        )
        self.entry.pack(side="left")

        self.button = ttk.Button(
            self, text="📅", width=3, command=self.open_picker
        )
        self.button.pack(side="left", padx=(3, 0))

        self.var.trace_add("write", self._changed)

    def _changed(self, *_):
        if self.on_change:
            self.on_change()

    def open_picker(self):
        initial = None
        txt = self.var.get().strip()
        if txt:
            try:
                initial = datetime.strptime(txt, "%d/%m/%Y").date()
            except ValueError:
                initial = None
        DatePickerDialog(self, self.var, initial_date=initial)





class AnimalQuickDetailsDialog(tk.Toplevel):
    def __init__(self, master, db: Database, grupo: int):
        super().__init__(master)
        self.db = db
        self.grupo = grupo

        self.title(f"{BICHOS[grupo]} — Grupo {grupo:02d}")
        self.geometry("720x520")
        self.minsize(620, 430)
        self.resizable(True, True)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        dezenas = [f"{((grupo - 1) * 4 + i) % 100:02d}" for i in range(1, 5)]

        ttk.Label(
            outer,
            text=f"{BICHO_ICONS.get(grupo, '')}  {BICHOS[grupo]} — Grupo {grupo:02d}",
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text="Dezenas: " + " • ".join(dezenas),
        ).pack(anchor="w", pady=(3, 10))

        stats = self.db.stats_by_animal()
        row = next((r for r in stats["rows"] if r["grupo"] == grupo), None)

        info = ttk.Frame(outer, style="Card.TFrame", padding=12)
        info.pack(fill="x", pady=(0, 10))

        if row:
            ttk.Label(
                info,
                text=f"Ocorrências: {row['ocorrencias']}   •   Em 1º prêmio: {row['p1']}",
                style="Card.TLabel",
                font=("Segoe UI Semibold", 10),
            ).pack(anchor="w")
            ttk.Label(
                info,
                text=(
                    f"1º: {row['p1']}   •   2º: {row['p2']}   •   3º: {row['p3']}   •   "
                    f"4º: {row['p4']}   •   5º: {row['p5']}"
                ),
                style="Card.TLabel",
            ).pack(anchor="w", pady=(4, 0))

        ttk.Label(
            outer,
            text="15 ocorrências mais recentes",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w", pady=(4, 6))

        frame = ttk.Frame(outer)
        frame.pack(fill="both", expand=True)

        cols = ("data","sorteio","hora","premio","milhar","centena","dezena")
        tree = ttk.Treeview(frame, columns=cols, show="headings")

        for c, label, width in [
            ("data","Data",95),("sorteio","Sorteio",90),("hora","Hora",70),
            ("premio","Prêmio",65),("milhar","Milhar",75),
            ("centena","Centena",75),("dezena","Dezena",65),
        ]:
            tree.heading(c, text=label)
            tree.column(c, width=width, anchor="center")

        y = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=y.set)
        tree.grid(row=0,column=0,sticky="nsew")
        y.grid(row=0,column=1,sticky="ns")
        frame.rowconfigure(0,weight=1)
        frame.columnconfigure(0,weight=1)

        for r in self.db.animal_recent_occurrences(grupo, limit=15):
            d = datetime.strptime(r["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            tree.insert("", "end", values=(
                d, r["sorteio"], r["hora"], f'{r["premio"]}º',
                r["milhar"], r["centena"], r["dezena"]
            ))

        footer = ttk.Frame(outer, padding=(0, 10, 0, 0))
        footer.pack(fill="x")

        ttk.Button(
            footer,
            text="Detalhes completos",
            command=lambda: AnimalDetailsDialog(self, self.db, grupo),
        ).pack(side="left")

        ttk.Button(footer, text="Fechar", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Minimizar", command=self.iconify).pack(side="right", padx=(0, 8))


class GameGeneratorDialog(tk.Toplevel):
    """
    Gerador simples de Grupo / Dezena / Centena / Milhar.
    Usa o histórico local para ordenar números.
    """
    def __init__(self, master, db: Database):
        super().__init__(master)
        self.db = db
        self.title("Gerador de jogos — GP-H")
        self.geometry("1120x760")
        self.minsize(920, 620)
        self.resizable(True, True)

        self.var_source = tk.StringVar(value="Método — último resultado")
        self.var_num_animals = tk.StringVar(value="5")
        self.var_kind = tk.StringVar(value="Centena")
        self.var_scope = tk.StringVar(value="1º–5º")
        self.var_total = tk.StringVar(value="20")

        self.manual_groups = []
        self.current_groups = []
        self.current_generation = None

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Gerador de jogos",
            font=("Segoe UI Semibold", 19),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text=(
                "Escolha de onde vêm os bichos, o tipo de número e quantos jogos quer. "
                "O programa distribui a quantidade entre os bichos e usa a força histórica "
                "do escopo selecionado."
            ),
            wraplength=1010,
        ).pack(anchor="w", pady=(4, 14))

        # ----------------------------------------------------
        # PASSO 1 — BICHOS
        # ----------------------------------------------------
        step1 = ttk.Frame(outer, style="Card.TFrame", padding=14)
        step1.pack(fill="x", pady=(0, 10))

        ttk.Label(
            step1,
            text="1. Escolha os bichos",
            style="Card.TLabel",
            font=("Segoe UI Semibold", 12),
        ).grid(row=0, column=0, columnspan=5, sticky="w")

        ttk.Label(
            step1, text="Origem", style="Card.TLabel"
        ).grid(row=1, column=0, sticky="w", pady=(8,0), padx=(0,8))

        cb_source = ttk.Combobox(
            step1,
            textvariable=self.var_source,
            values=["Método — último resultado", "Escolher manualmente"],
            width=27,
            state="readonly",
        )
        cb_source.grid(row=2, column=0, sticky="w", padx=(0,12))
        cb_source.bind("<<ComboboxSelected>>", self.on_source_changed)

        ttk.Label(
            step1, text="Quantidade de bichos", style="Card.TLabel"
        ).grid(row=1, column=1, sticky="w", pady=(8,0), padx=(0,8))

        self.cb_animals = ttk.Combobox(
            step1,
            textvariable=self.var_num_animals,
            values=["1","2","3","4","5","6","7","8","9","10"],
            width=10,
            state="readonly",
        )
        self.cb_animals.grid(row=2, column=1, sticky="w", padx=(0,12))

        self.manual_btn = ttk.Button(
            step1,
            text="Selecionar bichos",
            command=self.choose_manual_groups,
            state="disabled",
        )
        self.manual_btn.grid(row=2, column=2, sticky="w")

        self.animals_label = ttk.Label(
            step1,
            text="Os bichos serão calculados pelo método ao gerar.",
            style="Card.TLabel",
            wraplength=560,
        )
        self.animals_label.grid(row=3, column=0, columnspan=5, sticky="w", pady=(9,0))

        # ----------------------------------------------------
        # PASSO 2 — TIPO E ESCOPO
        # ----------------------------------------------------
        step2 = ttk.Frame(outer, style="Card.TFrame", padding=14)
        step2.pack(fill="x", pady=(0, 10))

        ttk.Label(
            step2,
            text="2. Escolha o jogo",
            style="Card.TLabel",
            font=("Segoe UI Semibold", 12),
        ).grid(row=0, column=0, columnspan=6, sticky="w")

        ttk.Label(step2, text="Tipo", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8,0), padx=(0,8)
        )
        cb_kind = ttk.Combobox(
            step2,
            textvariable=self.var_kind,
            values=["Grupo","Dezena","Centena","Milhar"],
            width=12,
            state="readonly",
        )
        cb_kind.grid(row=2, column=0, sticky="w", padx=(0,12))
        cb_kind.bind("<<ComboboxSelected>>", self.on_kind_changed)

        ttk.Label(step2, text="Histórico usado", style="Card.TLabel").grid(
            row=1, column=1, sticky="w", pady=(8,0), padx=(0,8)
        )
        self.cb_scope = ttk.Combobox(
            step2,
            textvariable=self.var_scope,
            values=["1º–5º","1º"],
            width=12,
            state="readonly",
        )
        self.cb_scope.grid(row=2, column=1, sticky="w", padx=(0,12))

        ttk.Label(step2, text="Quantidade", style="Card.TLabel").grid(
            row=1, column=2, sticky="w", pady=(8,0), padx=(0,8)
        )
        self.cb_total = ttk.Combobox(
            step2,
            textvariable=self.var_total,
            values=["5","10","15","20","25","30","40","50"],
            width=10,
            state="readonly",
        )
        self.cb_total.grid(row=2, column=2, sticky="w", padx=(0,12))

        ttk.Button(
            step2,
            text="3. GERAR",
            style="Accent.TButton",
            command=self.generate,
        ).grid(row=2, column=3, sticky="w", padx=(12,0))

        self.rule_label = ttk.Label(
            step2,
            text="Centena: números exatos mais frequentes no 1º–5º.",
            style="Card.TLabel",
            wraplength=520,
        )
        self.rule_label.grid(row=3, column=0, columnspan=5, sticky="w", pady=(9,0))

        # ----------------------------------------------------
        # RESULTADO
        # ----------------------------------------------------
        result_head = ttk.Frame(outer)
        result_head.pack(fill="x", pady=(4,5))

        ttk.Label(
            result_head,
            text="Jogos gerados",
            font=("Segoe UI Semibold", 15),
        ).pack(side="left")

        self.summary_label = ttk.Label(
            result_head, text="Clique em GERAR."
        )
        self.summary_label.pack(side="left", padx=(12,0))

        result_frame = ttk.Frame(outer)
        result_frame.pack(fill="both", expand=True)

        cols = ("jogo","bicho","grupo","numero","freq","ultima")
        self.tree = ttk.Treeview(
            result_frame, columns=cols, show="headings", selectmode="browse"
        )

        for c, label, width, anchor in [
            ("jogo","#",50,"center"),
            ("bicho","Bicho",150,"w"),
            ("grupo","Grupo",70,"center"),
            ("numero","Número",120,"center"),
            ("freq","Ocorrências históricas",150,"center"),
            ("ultima","Última ocorrência",230,"w"),
        ]:
            self.tree.heading(c, text=label)
            self.tree.column(c, width=width, anchor=anchor)

        y = ttk.Scrollbar(result_frame, orient="vertical", command=self.tree.yview)
        x = ttk.Scrollbar(result_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)

        footer = ttk.Frame(outer, padding=(0,10,0,0))
        footer.pack(fill="x")

        ttk.Button(
            footer, text="Copiar números", command=self.copy_numbers
        ).pack(side="left")

        ttk.Button(
            footer, text="Fechar", command=self.destroy
        ).pack(side="right")

        ttk.Button(
            footer, text="Minimizar", command=self.iconify
        ).pack(side="right", padx=(0,8))

    def on_source_changed(self, _event=None):
        manual = self.var_source.get() == "Escolher manualmente"
        self.manual_btn.configure(state="normal" if manual else "disabled")
        self.cb_animals.configure(state="disabled" if manual else "readonly")

        if manual:
            if self.manual_groups:
                self.update_animals_label(self.manual_groups)
            else:
                self.animals_label.configure(text="Clique em Selecionar bichos.")
        else:
            self.animals_label.configure(
                text="Os bichos serão calculados pelo método usando o último resultado cadastrado."
            )

    def on_kind_changed(self, _event=None):
        kind = self.var_kind.get()
        if kind == "Grupo":
            self.cb_scope.configure(state="disabled")
            self.cb_total.configure(state="disabled")
            self.rule_label.configure(
                text="Grupo: mostra diretamente os bichos selecionados."
            )
        else:
            self.cb_scope.configure(state="readonly")
            self.cb_total.configure(state="readonly")

            if kind == "Dezena":
                self.rule_label.configure(
                    text="Dezena: ordena as 4 dezenas do grupo pela frequência histórica."
                )
            elif kind == "Centena":
                self.rule_label.configure(
                    text="Centena: ordena as 40 centenas possíveis do grupo pela frequência histórica."
                )
            else:
                self.rule_label.configure(
                    text="Milhar: ordena as 400 milhares possíveis do grupo pela frequência histórica."
                )

    def choose_manual_groups(self):
        ManualGroupSelectorDialog(self, self.manual_groups, self.on_manual_groups_selected)

    def on_manual_groups_selected(self, groups):
        self.manual_groups = groups
        self.update_animals_label(groups)

    def update_animals_label(self, groups):
        if not groups:
            self.animals_label.configure(text="Nenhum bicho selecionado.")
            return
        txt = " • ".join(f"{BICHOS[g]} ({g:02d})" for g in groups)
        self.animals_label.configure(text=txt)

    def resolve_groups(self):
        if self.var_source.get() == "Escolher manualmente":
            if not self.manual_groups:
                raise ValueError("Selecione pelo menos um bicho.")
            return list(self.manual_groups)

        latest = self.db.latest_draw()
        if not latest:
            raise ValueError("A base não possui resultado para usar no método.")

        n = int(self.var_num_animals.get())
        result = self.db.method_convergencia_g5(
            latest["data"],
            latest["sorteio"],
            latest["hora"],
            top_n=n,
            min_state_support=5,
        )
        groups = [r["grupo"] for r in result["selected"]]
        self.update_animals_label(groups)
        return groups

    def format_last(self, raw):
        if not raw:
            return "Nunca apareceu"
        parts = raw.split("|")
        if len(parts) >= 4:
            d = datetime.strptime(parts[0], "%Y-%m-%d").strftime("%d/%m/%Y")
            return f"{d} {parts[1]} • {parts[2]} • {parts[3]}º"
        return raw

    def generate(self):
        try:
            groups = self.resolve_groups()
            self.current_groups = groups
            kind = self.var_kind.get()

            for item in self.tree.get_children():
                self.tree.delete(item)

            if kind == "Grupo":
                self.current_generation = {
                    "kind": "Grupo",
                    "groups": groups,
                    "rows": [
                        {
                            "grupo": g,
                            "bicho": BICHOS[g],
                            "numero": f"{g:02d}",
                            "ocorrencias": "",
                            "ultima": "",
                        }
                        for g in groups
                    ],
                }
            else:
                self.current_generation = self.db.generate_historical_numbers(
                    groups=groups,
                    kind=kind,
                    total=int(self.var_total.get()),
                    scope=self.var_scope.get(),
                )

            rows = self.current_generation["rows"]

            for i, r in enumerate(rows, start=1):
                self.tree.insert(
                    "", "end",
                    values=(
                        i,
                        r["bicho"],
                        f'{r["grupo"]:02d}',
                        r["numero"],
                        r.get("ocorrencias", ""),
                        self.format_last(r.get("ultima", "")) if kind != "Grupo" else "—",
                    )
                )

            if kind == "Grupo":
                self.summary_label.configure(
                    text=f"{len(rows)} grupo(s) selecionado(s)."
                )
            else:
                counts = self.current_generation["counts"]
                dist = " | ".join(
                    f"{BICHOS[g]}: {counts[g]}"
                    for g in groups
                )
                self.summary_label.configure(
                    text=f"{len(rows)} {kind.lower()}(s) • {dist}"
                )

        except Exception as e:
            messagebox.showerror("Gerador", str(e), parent=self)

    def copy_numbers(self):
        if not self.current_generation or not self.current_generation.get("rows"):
            messagebox.showinfo("Gerador", "Gere os jogos primeiro.", parent=self)
            return

        numbers = [r["numero"] for r in self.current_generation["rows"]]
        text = ", ".join(numbers)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        messagebox.showinfo("Gerador", "Números copiados.", parent=self)


class ManualGroupSelectorDialog(tk.Toplevel):
    def __init__(self, master, selected_groups, callback):
        super().__init__(master)
        self.callback = callback
        self.title("Selecionar bichos")
        self.geometry("620x500")
        self.resizable(True, True)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Escolha os bichos",
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text="Você pode selecionar quantos quiser.",
        ).pack(anchor="w", pady=(3,10))

        list_frame = ttk.Frame(outer)
        list_frame.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(
            list_frame,
            selectmode=tk.MULTIPLE,
            font=("Segoe UI", 11),
            exportselection=False,
        )
        y = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=y.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        y.pack(side="right", fill="y")

        for g in range(1,26):
            self.listbox.insert("end", f"{g:02d} - {BICHOS[g]}")

        for g in selected_groups:
            self.listbox.selection_set(g - 1)

        footer = ttk.Frame(outer, padding=(0,10,0,0))
        footer.pack(fill="x")

        ttk.Button(
            footer, text="Cancelar", command=self.destroy
        ).pack(side="right")

        ttk.Button(
            footer, text="Usar selecionados",
            style="Accent.TButton",
            command=self.confirm,
        ).pack(side="right", padx=(0,8))

    def confirm(self):
        groups = [i + 1 for i in self.listbox.curselection()]
        if not groups:
            messagebox.showinfo(
                "Selecionar bichos",
                "Selecione pelo menos um bicho.",
                parent=self,
            )
            return
        self.callback(groups)
        self.destroy()


class MethodsLabDialog(tk.Toplevel):
    """
    Tela simples para usar o método atual sem exigir que o usuário entenda
    suporte, lift, fallback ou outras métricas antes de gerar os bichos.
    """
    def __init__(self, master, db: Database):
        super().__init__(master)
        self.db = db
        self.title("Métodos — GP-H")
        self.geometry("1080x720")
        self.minsize(900, 600)
        self.resizable(True, True)

        self.var_date = tk.StringVar()
        self.var_sort = tk.StringVar(value="Todos")
        self.var_hour = tk.StringVar(value="Todos")
        self.var_topn = tk.StringVar(value="5")
        self.var_min_support = tk.StringVar(value="5")
        self.var_choose_old = tk.BooleanVar(value=False)
        self.var_advanced = tk.BooleanVar(value=False)

        self.current_result = None
        self.current_draw = None

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)

        # Título e explicação em português simples.
        ttk.Label(
            outer,
            text="Método de Puxada Combinada",
            font=("Segoe UI Semibold", 19),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text=(
                "Como usar: 1) escolha o resultado-base; 2) escolha quantos bichos quer; "
                "3) clique em GERAR BICHOS. O programa olha as puxadas históricas dos "
                "bichos do resultado-base e junta os sinais que mais se repetem."
            ),
            wraplength=980,
        ).pack(anchor="w", pady=(4, 14))

        # ----------------------------------------------------
        # PASSO 1
        # ----------------------------------------------------
        step1 = ttk.Frame(outer, style="Card.TFrame", padding=14)
        step1.pack(fill="x", pady=(0, 10))

        ttk.Label(
            step1,
            text="1. Resultado-base",
            style="Card.TLabel",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")

        self.base_label = ttk.Label(
            step1,
            text="Carregando último resultado…",
            style="Card.TLabel",
            wraplength=930,
            padding=(0, 7, 0, 7),
        )
        self.base_label.pack(anchor="w", fill="x")

        base_actions = ttk.Frame(step1, style="Card.TFrame")
        base_actions.pack(fill="x")

        ttk.Button(
            base_actions,
            text="Usar último resultado",
            command=self.load_latest,
        ).pack(side="left")

        ttk.Checkbutton(
            base_actions,
            text="Escolher outro resultado",
            variable=self.var_choose_old,
            command=self.toggle_base_selector,
        ).pack(side="left", padx=(12, 0))

        self.base_selector = ttk.Frame(step1, style="Card.TFrame")

        ttk.Label(
            self.base_selector, text="Data", style="Card.TLabel"
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        CalendarField(
            self.base_selector,
            self.var_date,
            width=11,
            on_change=self.on_date_changed,
        ).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(3, 0))

        ttk.Label(
            self.base_selector, text="Sorteio", style="Card.TLabel"
        ).grid(row=0, column=1, sticky="w", padx=(0, 10))
        self.cb_sort = ttk.Combobox(
            self.base_selector,
            textvariable=self.var_sort,
            values=["Todos"],
            width=12,
            state="readonly",
        )
        self.cb_sort.grid(row=1, column=1, sticky="w", padx=(0, 10), pady=(3, 0))
        self.cb_sort.bind("<<ComboboxSelected>>", self.on_sort_changed)

        ttk.Label(
            self.base_selector, text="Hora", style="Card.TLabel"
        ).grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.cb_hour = ttk.Combobox(
            self.base_selector,
            textvariable=self.var_hour,
            values=["Todos"],
            width=10,
            state="readonly",
        )
        self.cb_hour.grid(row=1, column=2, sticky="w", padx=(0, 10), pady=(3, 0))
        self.cb_hour.bind("<<ComboboxSelected>>", self.on_hour_changed)

        ttk.Button(
            self.base_selector,
            text="Usar este resultado",
            command=self.use_selected_draw,
        ).grid(row=1, column=3, padx=(8, 0), pady=(3, 0))

        # ----------------------------------------------------
        # PASSO 2 + 3
        # ----------------------------------------------------
        step23 = ttk.Frame(outer, style="Card.TFrame", padding=14)
        step23.pack(fill="x", pady=(0, 10))

        left_controls = ttk.Frame(step23, style="Card.TFrame")
        left_controls.pack(side="left")

        ttk.Label(
            left_controls,
            text="2. Quantos bichos você quer?",
            style="Card.TLabel",
            font=("Segoe UI Semibold", 11),
        ).grid(row=0, column=0, sticky="w")

        ttk.Combobox(
            left_controls,
            textvariable=self.var_topn,
            values=["1","2","3","4","5","6","7","8","9","10"],
            width=7,
            state="readonly",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        ttk.Button(
            step23,
            text="3. GERAR BICHOS",
            style="Accent.TButton",
            command=self.calculate,
        ).pack(side="left", padx=(24, 0), pady=(12, 0))

        ttk.Checkbutton(
            step23,
            text="Opções técnicas",
            variable=self.var_advanced,
            command=self.toggle_advanced,
        ).pack(side="right", pady=(12, 0))

        self.advanced_frame = ttk.Frame(outer, style="Card.TFrame", padding=12)

        ttk.Label(
            self.advanced_frame,
            text="Suporte mínimo para usar ×1 / ×2 / ×3+:",
            style="Card.TLabel",
        ).pack(side="left")

        ttk.Combobox(
            self.advanced_frame,
            textvariable=self.var_min_support,
            values=["3","5","8","10"],
            width=7,
            state="readonly",
        ).pack(side="left", padx=(8, 12))

        ttk.Label(
            self.advanced_frame,
            text=(
                "Padrão: 5. Se houver pouca amostra no estado específico, "
                "o programa usa a puxada Geral."
            ),
            style="Card.TLabel",
        ).pack(side="left")

        # ----------------------------------------------------
        # RESULTADO PRINCIPAL
        # ----------------------------------------------------
        result_head = ttk.Frame(outer)
        result_head.pack(fill="x", pady=(4, 5))

        ttk.Label(
            result_head,
            text="Bichos indicados",
            font=("Segoe UI Semibold", 15),
        ).pack(side="left")

        self.result_note = ttk.Label(
            result_head,
            text="Clique em GERAR BICHOS.",
        )
        self.result_note.pack(side="left", padx=(12, 0))

        result_frame = ttk.Frame(outer)
        result_frame.pack(fill="both", expand=True)

        cols = ("rank", "bicho", "grupo", "fontes")
        self.tree = ttk.Treeview(
            result_frame,
            columns=cols,
            show="headings",
            selectmode="browse",
            height=10,
        )
        for c, label, width, anchor in [
            ("rank", "#", 55, "center"),
            ("bicho", "Bicho", 220, "w"),
            ("grupo", "Grupo", 90, "center"),
            ("fontes", "Quantos bichos-base apontaram", 250, "center"),
        ]:
            self.tree.heading(c, text=label)
            self.tree.column(c, width=width, anchor=anchor)

        y = ttk.Scrollbar(result_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=y.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)

        footer = ttk.Frame(outer, padding=(0, 10, 0, 0))
        footer.pack(fill="x")

        ttk.Button(
            footer,
            text="Ver detalhes técnicos",
            command=self.open_technical_details,
        ).pack(side="left")

        ttk.Label(
            footer,
            text="Os detalhes técnicos ficam separados para não atrapalhar o uso normal.",
        ).pack(side="left", padx=(10, 0))

        ttk.Button(footer, text="Fechar", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Minimizar", command=self.iconify).pack(side="right", padx=(0, 8))

        self.load_latest()

    # --------------------------------------------------------
    # Seleção da base
    # --------------------------------------------------------
    def _date_iso(self):
        txt = self.var_date.get().strip()
        if not txt:
            return None
        return parse_br_date(txt)

    def toggle_base_selector(self):
        if self.var_choose_old.get():
            self.base_selector.pack(fill="x", pady=(10, 0))
            self.refresh_draw_options()
        else:
            self.base_selector.pack_forget()

    def toggle_advanced(self):
        if self.var_advanced.get():
            self.advanced_frame.pack(fill="x", pady=(0, 10))
        else:
            self.advanced_frame.pack_forget()

    def refresh_draw_options(self):
        d = self._date_iso()
        sorts, hours = self.db.draw_filter_options(d)
        self.cb_sort["values"] = ["Todos"] + sorts
        self.cb_hour["values"] = ["Todos"] + hours

        if self.var_sort.get() not in self.cb_sort["values"]:
            self.var_sort.set("Todos")
        if self.var_hour.get() not in self.cb_hour["values"]:
            self.var_hour.set("Todos")

    def on_date_changed(self):
        self.var_sort.set("Todos")
        self.var_hour.set("Todos")
        self.refresh_draw_options()

    def on_sort_changed(self, _event=None):
        d = self._date_iso()
        if not d:
            return

        sort = self.var_sort.get()
        if sort == "Todos":
            self.refresh_draw_options()
            return

        rows = self.db.search(date_from=d, date_to=d, sorteio=sort)
        hours = sorted({r["hora"] for r in rows})
        self.cb_hour["values"] = ["Todos"] + hours

        if len(hours) == 1:
            self.var_hour.set(hours[0])
        elif self.var_hour.get() not in self.cb_hour["values"]:
            self.var_hour.set("Todos")

    def on_hour_changed(self, _event=None):
        d = self._date_iso()
        hour = self.var_hour.get()
        if not d or hour == "Todos":
            return

        rows = self.db.search(date_from=d, date_to=d, hora=hour)
        sorts = sorted({r["sorteio"] for r in rows})
        self.cb_sort["values"] = ["Todos"] + sorts

        if len(sorts) == 1:
            self.var_sort.set(sorts[0])
        elif self.var_sort.get() not in self.cb_sort["values"]:
            self.var_sort.set("Todos")

    def load_latest(self):
        latest = self.db.latest_draw()
        if not latest:
            messagebox.showinfo("Métodos", "A base ainda não possui extrações.", parent=self)
            return

        self.current_draw = latest

        d = datetime.strptime(latest["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
        self.var_date.set(d)
        self.refresh_draw_options()
        self.var_sort.set(latest["sorteio"])
        self.on_sort_changed()
        self.var_hour.set(latest["hora"])

        self.show_base(latest)

    def use_selected_draw(self):
        try:
            d = self._date_iso()
            if not d:
                raise ValueError("Escolha uma data.")

            sort = self.var_sort.get()
            hour = self.var_hour.get()

            if sort == "Todos":
                raise ValueError("Escolha o sorteio.")
            if hour == "Todos":
                raise ValueError("Escolha a hora.")

            draw = self.db.get_draw(d, sort, hour)
            if not draw:
                raise ValueError("Não encontrei esse resultado na base.")

            self.current_draw = draw
            self.show_base(draw)
            self.var_choose_old.set(False)
            self.toggle_base_selector()

        except Exception as e:
            messagebox.showerror("Métodos", str(e), parent=self)

    def show_base(self, draw):
        d = datetime.strptime(draw["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
        result = " • ".join(
            f"{p['premio']}º {p['bicho']} ({p['grupo']:02d})"
            for p in draw["prizes"]
        )
        self.base_label.configure(
            text=f"{d} • {draw['sorteio']} {draw['hora']} → {result}"
        )

    # --------------------------------------------------------
    # Cálculo simplificado
    # --------------------------------------------------------
    def calculate(self):
        try:
            if not self.current_draw:
                raise ValueError("Escolha um resultado-base primeiro.")

            draw = self.current_draw
            result = self.db.method_convergencia_g5(
                draw["data"],
                draw["sorteio"],
                draw["hora"],
                top_n=int(self.var_topn.get()),
                min_state_support=int(self.var_min_support.get()),
            )
            self.current_result = result

            for item in self.tree.get_children():
                self.tree.delete(item)

            for rank, r in enumerate(result["selected"], start=1):
                self.tree.insert(
                    "",
                    "end",
                    iid=str(r["grupo"]),
                    values=(
                        rank,
                        r["bicho"],
                        f'{r["grupo"]:02d}',
                        r["source_count"],
                    ),
                )

            selected_txt = " • ".join(
                f"{r['bicho']} ({r['grupo']:02d})"
                for r in result["selected"]
            )
            self.result_note.configure(text=selected_txt)

        except Exception as e:
            messagebox.showerror("Métodos", str(e), parent=self)

    def open_technical_details(self):
        if not self.current_result:
            messagebox.showinfo(
                "Métodos",
                "Primeiro clique em GERAR BICHOS.",
                parent=self,
            )
            return
        MethodsTechnicalDialog(self, self.current_result)






class ResetCoverageTechnicalDialog(tk.Toplevel):
    def __init__(self, master, result):
        super().__init__(master)
        self.result = result

        self.title("Detalhes técnicos — GP-H Reset Cobertura v1")
        self.geometry("1080x660")
        self.minsize(900, 540)
        self.resizable(True, True)

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="GP-H Reset Cobertura v1 — OFICIAL",
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")

        cfg = result["config"]
        target = result["target"]

        context_text = (
            "pair3"
            if result["context_mode"] == "pair3"
            else "neutro — passagem de domingo sem forçar pair3"
        )

        ttk.Label(
            outer,
            text=(
                f"Configuração: {cfg['window']} • {cfg['family']} • "
                f"{cfg['validated_context']} • {cfg['ranking']}  |  "
                f"Contexto desta rodada: {context_text}  |  "
                f"Treino: {result['training_transitions']} transições  |  "
                f"Alvo: {target['data']} • {target['sorteio']} {target['hora']}"
            ),
            wraplength=1030,
        ).pack(anchor="w", pady=(3, 8))

        ttk.Label(
            outer,
            text=(
                "Score = estimativa suavizada de presença do grupo em qualquer "
                "um dos cinco prêmios seguintes (G5). Repetições na base entram "
                "pela multiplicidade real."
            ),
            wraplength=1030,
        ).pack(anchor="w", pady=(0, 8))

        base_box = ttk.Frame(outer, style="Card.TFrame", padding=8)
        base_box.pack(fill="x", pady=(0, 8))

        ttk.Label(
            base_box,
            text="Base: " + " • ".join(
                f"{p['bicho']}({p['grupo']:02d})"
                for p in result["base"]["prizes"]
            ),
            style="Card.TLabel",
        ).pack(anchor="w")

        ttk.Label(
            base_box,
            text=(
                f"pair3 com peso 3: {result['pair3_matches']} amostra(s)."
                if result["context_mode"] == "pair3"
                else "pair3 desligado nesta passagem operacional."
            ),
            style="Card.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        table = ttk.Frame(outer)
        table.pack(fill="both", expand=True)

        cols = ("rank","grupo","bicho","score","prior")
        tree = ttk.Treeview(table, columns=cols, show="headings")

        labels = {
            "rank":"#","grupo":"G","bicho":"Bicho",
            "score":"Score Reset","prior":"Prior",
        }
        widths = {
            "rank":42,"grupo":50,"bicho":140,
            "score":120,"prior":120,
        }

        for c in cols:
            tree.heading(c, text=labels[c])
            tree.column(
                c, width=widths[c],
                anchor="w" if c == "bicho" else "center",
            )

        y = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=y.set)
        tree.grid(row=0,column=0,sticky="nsew")
        y.grid(row=0,column=1,sticky="ns")
        table.rowconfigure(0,weight=1)
        table.columnconfigure(0,weight=1)

        selected_groups = {r["grupo"] for r in result["selected"]}

        for rank, r in enumerate(result["ranking"], start=1):
            tree.insert(
                "", "end",
                tags=("selected",) if r["grupo"] in selected_groups else (),
                values=(
                    rank,
                    f'{r["grupo"]:02d}',
                    r["bicho"],
                    f'{r["score_pct"]:.3f}%',
                    f'{r["prior_pct"]:.3f}%',
                ),
            )

        tree.tag_configure(
            "selected",
            font=("Segoe UI Semibold", 8),
        )

        footer = ttk.Frame(outer, padding=(0, 8, 0, 0))
        footer.pack(fill="x")

        ttk.Label(
            footer,
            text=(
                "Fórmula: last240 • pull • pair3 • probability. "
                "Prior suavizado com 5×0,18; pull suavizado com peso 7; "
                "pair3 pesa 3 no mesmo par origem→alvo."
            ),
            wraplength=850,
        ).pack(side="left")

        ttk.Button(
            footer, text="Fechar", command=self.destroy
        ).pack(side="right")




class EditPlayDialog(tk.Toplevel):
    def __init__(self, master, db: Database, game_id, on_saved=None):
        super().__init__(master)
        self.db = db
        self.game_id = int(game_id)
        self.on_saved = on_saved

        detail = db.frozen_game_details(self.game_id)
        self.game = detail["game"]
        self.items = detail["items"]

        self.title(f"Editar jogada #{self.game_id}")
        self.geometry("720x610")
        self.minsize(650, 560)
        self.resizable(True, True)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text=f"Editar jogada #{self.game_id}",
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text=(
                "Permitido somente antes do resultado. "
                "Se números, modalidade ou alvo mudarem, o registro passa a "
                "ser classificado como Manual/Editado para não atribuir o "
                "resultado ao método original."
            ),
            wraplength=670,
        ).pack(anchor="w", pady=(3,10))

        form = ttk.Frame(
            outer,
            style="Card.TFrame",
            padding=10,
        )
        form.pack(fill="x")

        self.kind = tk.StringVar(value=self.game["tipo"])
        self.scope = tk.StringVar(value=self.game["escopo"])
        self.sub = tk.StringVar(
            value=self.game.get("submodalidade") or "Milhar"
        )
        self.value = tk.StringVar(
            value=str(self.game.get("valor_unitario") or "0,20").replace(".", ",")
        )

        target = db.game_planned_target(self.game) or {}
        target_date = target.get("data") or datetime.now().strftime("%Y-%m-%d")
        try:
            target_date_br = datetime.strptime(
                target_date, "%Y-%m-%d"
            ).strftime("%d/%m/%Y")
        except Exception:
            target_date_br = target_date

        self.target_date = tk.StringVar(value=target_date_br)
        self.target_sort = tk.StringVar(
            value=target.get("sorteio") or "PT"
        )
        self.target_hour = tk.StringVar(
            value=target.get("hora") or "14:00"
        )

        fields = [
            (
                "Tipo",
                self.kind,
                [
                    "Grupo",
                    "Dupla de Grupo",
                    "Terno de Grupo",
                    "Quadra de Grupo",
                    "Quina de Grupo",
                    "Passe vai",
                    "Passe vai e vem",
                    "Dezena",
                    "Duque de Dezena",
                    "Terno de Dezena",
                    "Dezena Invertida",
                    "Centena",
                    "Centena Invertida",
                    "Milhar",
                    "Milhar Invertida",
                ],
            ),
            ("Colocação", self.scope, ["1º","1º–5º"]),
            ("Milhar", self.sub, ["Milhar","Milhar/Centena"]),
        ]

        for col, (label, var, values) in enumerate(fields):
            ttk.Label(
                form,
                text=label,
                style="Card.TLabel",
            ).grid(row=0,column=col,sticky="w",padx=(0,8))

            cb = ttk.Combobox(
                form,
                textvariable=var,
                values=values,
                width=16,
                state="readonly",
            )
            cb.grid(row=1,column=col,sticky="w",padx=(0,8),pady=(2,7))

        ttk.Label(
            form,
            text="Data alvo",
            style="Card.TLabel",
        ).grid(row=2,column=0,sticky="w",padx=(0,8))

        ttk.Entry(
            form,
            textvariable=self.target_date,
            width=16,
        ).grid(row=3,column=0,sticky="w",padx=(0,8),pady=(2,7))

        ttk.Label(
            form,
            text="Sorteio",
            style="Card.TLabel",
        ).grid(row=2,column=1,sticky="w",padx=(0,8))

        ttk.Combobox(
            form,
            textvariable=self.target_sort,
            values=["PPT","PTM","PT","PTV","PTN","CORUJA"],
            width=16,
            state="readonly",
        ).grid(row=3,column=1,sticky="w",padx=(0,8),pady=(2,7))

        ttk.Label(
            form,
            text="Hora",
            style="Card.TLabel",
        ).grid(row=2,column=2,sticky="w",padx=(0,8))

        ttk.Combobox(
            form,
            textvariable=self.target_hour,
            values=["09:00","11:00","14:00","16:00","18:00","21:00"],
            width=16,
            state="readonly",
        ).grid(row=3,column=2,sticky="w",padx=(0,8),pady=(2,7))

        ttk.Label(
            form,
            text="Valor por palpite",
            style="Card.TLabel",
        ).grid(row=4,column=0,sticky="w",padx=(0,8))

        ttk.Entry(
            form,
            textvariable=self.value,
            width=16,
        ).grid(row=5,column=0,sticky="w",padx=(0,8),pady=(2,0))

        ttk.Label(
            outer,
            text="Palpites",
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", pady=(10,4))

        self.numbers = tk.Text(
            outer,
            height=8,
            wrap="word",
        )
        self.numbers.pack(fill="both", expand=True)
        self.numbers.insert(
            "1.0",
            ", ".join(str(i["numero"]) for i in self.items),
        )

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(10,0))

        ttk.Button(
            footer,
            text="Cancelar",
            command=self.destroy,
        ).pack(side="right")

        ttk.Button(
            footer,
            text="Salvar edição",
            style="Accent.TButton",
            command=self.save,
        ).pack(side="right", padx=(0,6))

    def save(self):
        try:
            date_iso = datetime.strptime(
                self.target_date.get().strip(),
                "%d/%m/%Y",
            ).strftime("%Y-%m-%d")

            raw = self.value.get().strip()
            value = float(
                raw.replace(".", "").replace(",", ".")
                if "," in raw
                else raw
            )

            kind = self.kind.get()
            scope = (
                "1º–5º"
                if kind in FIXED_PLACEMENT_MODALITIES
                else self.scope.get()
            )

            target = {
                "data": date_iso,
                "sorteio": self.target_sort.get(),
                "hora": self.target_hour.get(),
                "whole_day": False,
            }

            self.db.update_pending_play(
                self.game_id,
                kind,
                scope,
                self.numbers.get("1.0", "end").strip(),
                value,
                target,
                submodalidade=(
                    self.sub.get()
                    if kind == "Milhar"
                    else None
                ),
            )

            if self.on_saved:
                self.on_saved()

            messagebox.showinfo(
                "Editar jogada",
                "Jogada atualizada antes do resultado.",
                parent=self,
            )
            self.destroy()

        except Exception as exc:
            messagebox.showerror(
                "Editar jogada",
                str(exc),
                parent=self,
            )


class PayoutConfigDialog(tk.Toplevel):
    def __init__(self, master, db: Database, on_saved=None):
        super().__init__(master)
        self.db = db
        self.on_saved = on_saved

        self.title("Cotações / Tabela de prêmios")
        self.geometry("860x650")
        self.minsize(780, 590)
        self.resizable(True, True)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Cotações da banca",
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text=(
                "Valores por R$ 1,00. Em 1º–5º a cotação é a mesma, "
                "mas o valor do palpite é dividido por 5 posições. "
                "Terno de Grupo é colocação fixa e não divide por 5."
            ),
            wraplength=810,
        ).pack(anchor="w", pady=(4,10))

        current = db.quote_catalog()
        self.vars = {}

        simple = ttk.Frame(
            outer,
            style="Card.TFrame",
            padding=10,
        )
        simple.pack(fill="x")

        modalities = list(DEFAULT_QUOTES.keys())
        split = (len(modalities) + 1) // 2

        for side, subset in enumerate(
            [modalities[:split], modalities[split:]]
        ):
            base_col = side * 3

            ttk.Label(
                simple,
                text="Modalidade",
                style="Card.TLabel",
                font=("Segoe UI Semibold", 9),
            ).grid(
                row=0,column=base_col,sticky="w",padx=(0,8),pady=(0,5)
            )

            ttk.Label(
                simple,
                text="Cotação",
                style="Card.TLabel",
                font=("Segoe UI Semibold", 9),
            ).grid(
                row=0,column=base_col+1,sticky="w",padx=(0,18),pady=(0,5)
            )

            for row, modality in enumerate(subset, start=1):
                ttk.Label(
                    simple,
                    text=modality,
                    style="Card.TLabel",
                ).grid(
                    row=row,column=base_col,sticky="w",padx=(0,8),pady=3
                )

                var = tk.StringVar(
                    value=f"{current['simples'][modality]:g}"
                )
                self.vars[modality] = var

                ttk.Entry(
                    simple,
                    textvariable=var,
                    width=12,
                ).grid(
                    row=row,column=base_col+1,sticky="w",padx=(0,18),pady=3
                )

        special = ttk.Frame(
            outer,
            style="Card.TFrame",
            padding=10,
        )
        special.pack(fill="x", pady=(8,0))

        ttk.Label(
            special,
            text="Milhar/Centena",
            style="Card.TLabel",
            font=("Segoe UI Semibold", 11),
        ).grid(row=0,column=0,columnspan=6,sticky="w",pady=(0,5))

        self.mc_vars = {}
        for col, (component, label) in enumerate([
            ("centena","Só Centena"),
            ("milhar","Só Milhar"),
            ("ambos","Milhar + Centena no mesmo resultado"),
        ]):
            ttk.Label(
                special,
                text=label,
                style="Card.TLabel",
            ).grid(row=1,column=col*2,sticky="w",padx=(0,6))

            var = tk.StringVar(
                value=f"{current['milhar_centena'][component]:g}"
            )
            self.mc_vars[component] = var

            ttk.Entry(
                special,
                textvariable=var,
                width=12,
            ).grid(row=1,column=col*2+1,sticky="w",padx=(0,16))

        ttk.Label(
            outer,
            text=(
                "Exemplo: Centena R$ 0,20 no 1º–5º → "
                "R$ 0,20 ÷ 5 = R$ 0,04 por posição → "
                "R$ 0,04 × 600 = R$ 24,00 por acerto naquela posição."
            ),
            wraplength=810,
        ).pack(anchor="w", pady=(10,0))

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(14,0))

        ttk.Button(
            footer,
            text="Cancelar",
            command=self.destroy,
        ).pack(side="right")

        ttk.Button(
            footer,
            text="Salvar cotações",
            style="Accent.TButton",
            command=self.save,
        ).pack(side="right", padx=(0,7))

    def save(self):
        try:
            for modality, var in self.vars.items():
                raw = var.get().strip().replace(",", ".")
                value = float(raw) if raw else 0.0
                self.db.set_quote(modality, value)

            self.db.set_milhar_centena_quotes(
                self.mc_vars["centena"].get().strip().replace(",", ".") or 0,
                self.mc_vars["milhar"].get().strip().replace(",", ".") or 0,
                self.mc_vars["ambos"].get().strip().replace(",", ".") or 0,
            )

            if self.on_saved:
                self.on_saved()

            messagebox.showinfo(
                "Cotações",
                "Cotações salvas.",
                parent=self,
            )
            self.destroy()

        except Exception as exc:
            messagebox.showerror(
                "Cotações",
                str(exc),
                parent=self,
            )

class FrozenGameDetailsDialog(tk.Toplevel):
    def __init__(self, master, db: Database, game_id: int):
        super().__init__(master)
        self.db = db
        self.game_id = int(game_id)

        detail = db.frozen_game_details(self.game_id)
        game = detail["game"]
        items = detail["items"]

        self.title(f"Jogo congelado #{self.game_id}")
        self.geometry("980x620")
        self.minsize(820, 520)
        self.resizable(True, True)

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text=f"Jogo #{self.game_id} • {game['estrategia']}",
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")

        base = "—"
        if game["base_data"]:
            base = datetime.strptime(game["base_data"], "%Y-%m-%d").strftime("%d/%m/%Y")

        target = "aguardando"
        if game["alvo_data"]:
            target = datetime.strptime(game["alvo_data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            if game["alvo_sorteio"]:
                target += f" • {game['alvo_sorteio']} {game['alvo_hora']}"
            else:
                target += " • dia inteiro 1º"

        ttk.Label(
            outer,
            text=(
                f"Seletor: {game.get('seletor') or 'Não registrado'} • "
                f"Tipo: {game['tipo']} • Escopo: {game['escopo']} • "
                f"Base: {base} • Alvo: {target} • Status: {game['status']} • "
                f"Acertos: {game['acertos']}/{game['total_itens']} • "
                + (
                    f"Apostado: R$ {float(game.get('valor_total') or 0):.2f}"
                    if game.get("jogado")
                    else "Valor não informado"
                )
            ),
            wraplength=930,
        ).pack(anchor="w", pady=(3, 8))

        table = ttk.Frame(outer)
        table.pack(fill="both", expand=True)

        cols = ("ordem","bicho","grupo","numero","regra","hit","onde")
        tree = ttk.Treeview(table, columns=cols, show="headings")

        labels = {
            "ordem":"#","bicho":"Bicho","grupo":"G","numero":"Número",
            "regra":"Regra","hit":"Acerto","onde":"Onde acertou",
        }
        widths = {
            "ordem":40,"bicho":110,"grupo":45,"numero":90,
            "regra":150,"hit":60,"onde":330,
        }

        for c in cols:
            tree.heading(c, text=labels[c])
            tree.column(
                c,
                width=widths[c],
                anchor="w" if c in ("bicho","regra","onde") else "center",
            )

        y = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        x = ttk.Scrollbar(table, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tree.grid(row=0,column=0,sticky="nsew")
        y.grid(row=0,column=1,sticky="ns")
        x.grid(row=1,column=0,sticky="ew")
        table.rowconfigure(0,weight=1)
        table.columnconfigure(0,weight=1)

        for item in items:
            where = "—"
            if item["acertou"]:
                d = datetime.strptime(
                    item["acerto_data"], "%Y-%m-%d"
                ).strftime("%d/%m/%Y")
                where = d
                if item["acerto_sorteio"]:
                    where += f" • {item['acerto_sorteio']} {item['acerto_hora']}"
                if item["acerto_premio"]:
                    where += f" • {item['acerto_premio']}º"
                if item["acerto_milhar"]:
                    where += f" • {item['acerto_milhar']}"

            tree.insert(
                "", "end",
                values=(
                    item["ordem"],
                    item["bicho"] or "—",
                    f"{item['grupo']:02d}" if item["grupo"] else "—",
                    item["numero"],
                    item["regra"] or "—",
                    (
                        "SIM" if item["acertou"]
                        else ("NÃO" if game["status"] == "AUDITADO" else "—")
                    ),
                    where,
                ),
            )

        footer = ttk.Frame(outer, padding=(0,8,0,0))
        footer.pack(fill="x")

        ttk.Button(
            footer, text="Auditar este jogo", command=self.audit_this
        ).pack(side="left")

        ttk.Button(
            footer, text="Fechar", command=self.destroy
        ).pack(side="right")

    def audit_this(self):
        result = self.db.audit_frozen_game(self.game_id)

        if result["audited"]:
            messagebox.showinfo(
                "Auditoria",
                f"Jogo auditado: {result['hits']}/{result['total']} acerto(s).",
                parent=self,
            )
            self.destroy()
        else:
            messagebox.showinfo("Auditoria", result["reason"], parent=self)


class DryDayTechnicalDialog(tk.Toplevel):
    def __init__(self, master, result):
        super().__init__(master)
        self.result = result

        self.title(
            "Detalhes técnicos — Seca do Dia 1º"
        )
        self.geometry("1080x650")
        self.minsize(880, 540)
        self.resizable(True, True)

        outer = ttk.Frame(
            self, padding=12
        )
        outer.pack(
            fill="both", expand=True
        )

        ttk.Label(
            outer,
            text="Seca do Dia — 1º prêmio",
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")

        d = datetime.strptime(
            result["base_date"],
            "%Y-%m-%d",
        ).strftime("%d/%m/%Y")

        ttk.Label(
            outer,
            text=(
                f"Dia-base: {d} • "
                f"{len(result['base_first_prizes'])} "
                f"1º prêmio(s) • "
                f"{result['transition_count']} "
                f"transição(ões) históricas • "
                f"alvos/fonte: {result['targets_per_source']} • "
                f"suporte mínimo: {result['min_support']}."
            ),
            wraplength=1000,
        ).pack(
            anchor="w", pady=(3, 7)
        )

        ttk.Label(
            outer,
            text=(
                "1º prêmios usados: "
                + " • ".join(
                    f"{x['hora']} "
                    f"{x['bicho']}({x['grupo']:02d})"
                    for x in result["base_first_prizes"]
                )
            ),
            wraplength=1000,
        ).pack(
            anchor="w", pady=(0, 8)
        )

        table = ttk.Frame(outer)
        table.pack(
            fill="both", expand=True
        )

        cols = (
            "rank","grupo","bicho",
            "indic","fontes","prob",
            "lift","origens",
        )
        tree = ttk.Treeview(
            table,
            columns=cols,
            show="headings",
        )

        labels = {
            "rank":"#",
            "grupo":"G",
            "bicho":"Bicho",
            "indic":"Indicações",
            "fontes":"Fontes",
            "prob":"Σ Prob.",
            "lift":"Σ Lift",
            "origens":"Quem apontou",
        }
        widths = {
            "rank":38,
            "grupo":42,
            "bicho":100,
            "indic":70,
            "fontes":60,
            "prob":75,
            "lift":65,
            "origens":500,
        }

        for c in cols:
            tree.heading(
                c, text=labels[c]
            )
            tree.column(
                c,
                width=widths[c],
                anchor=(
                    "w"
                    if c in ("bicho","origens")
                    else "center"
                ),
            )

        y = ttk.Scrollbar(
            table,
            orient="vertical",
            command=tree.yview,
        )
        x = ttk.Scrollbar(
            table,
            orient="horizontal",
            command=tree.xview,
        )
        tree.configure(
            yscrollcommand=y.set,
            xscrollcommand=x.set,
        )
        tree.grid(
            row=0,column=0,sticky="nsew"
        )
        y.grid(
            row=0,column=1,sticky="ns"
        )
        x.grid(
            row=1,column=0,sticky="ew"
        )
        table.rowconfigure(
            0, weight=1
        )
        table.columnconfigure(
            0, weight=1
        )

        selected_groups = {
            r["grupo"]
            for r in result["selected"]
        }

        for rank, r in enumerate(
            result["ranking"], start=1
        ):
            origins = " | ".join(
                f"{s['bicho']} "
                f"{s['prob']:.1f}%/"
                f"{s['lift']:.2f}x"
                for s in r["sources"]
            )

            tree.insert(
                "",
                "end",
                tags=(
                    ("selected",)
                    if r["grupo"] in selected_groups
                    else ()
                ),
                values=(
                    rank,
                    f'{r["grupo"]:02d}',
                    r["bicho"],
                    r["indications"],
                    r["distinct_source_count"],
                    f'{r["sum_prob"]:.1f}',
                    f'{r["sum_lift"]:.2f}',
                    origins,
                ),
            )

        tree.tag_configure(
            "selected",
            font=("Segoe UI Semibold", 8),
        )

        footer = ttk.Frame(
            outer, padding=(0,8,0,0)
        )
        footer.pack(fill="x")

        ttk.Label(
            footer,
            text=(
                "Indicações = quantas vezes as fontes do dia-base "
                "apontaram o alvo. Com 'Contar repetições', "
                "um bicho repetido no 1º prêmio reforça o sinal."
            ),
            wraplength=820,
        ).pack(side="left")

        ttk.Button(
            footer,
            text="Fechar",
            command=self.destroy,
        ).pack(side="right")


class SimilarityTechnicalDialog(tk.Toplevel):
    def __init__(self, master, result):
        super().__init__(master)
        self.result = result
        self.title("Detalhes técnicos — Sombra Similaridade")
        self.geometry("1040x620")
        self.minsize(860, 520)
        self.resizable(True, True)

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Sombra Similaridade do Dia",
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text=(
                "Índice de similaridade: 45% mesma posição/hora + "
                "30% mesmo horário + 15% sobreposição do dia + "
                "5% repetição + 5% mesmo dia da semana. "
                "O índice não é probabilidade."
            ),
            wraplength=980,
        ).pack(anchor="w", pady=(3, 8))

        summary = ttk.Frame(outer, style="Card.TFrame", padding=8)
        summary.pack(fill="x", pady=(0, 8))

        ttk.Label(
            summary,
            text=(
                f"Prefixo analisado: {len(result['current_day'])} extração(ões) • "
                f"Dias comparáveis: {result['candidate_count']} • "
                f"Top usados: {len(result['top_days'])}"
            ),
            style="Card.TLabel",
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text="Dias históricos mais semelhantes",
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", pady=(0, 4))

        table = ttk.Frame(outer)
        table.pack(fill="both", expand=True)

        cols = (
            "rank","date","score","pos","hour","day","rep","week",
            "target"
        )
        tree = ttk.Treeview(table, columns=cols, show="headings")

        labels = {
            "rank":"#","date":"Dia","score":"Índice","pos":"Pos./hora",
            "hour":"Mesmo horário","day":"Dia","rep":"Repetição",
            "week":"Semana","target":"Próximo sorteio"
        }
        widths = {
            "rank":38,"date":85,"score":65,"pos":80,"hour":90,
            "day":55,"rep":70,"week":55,"target":260
        }

        for c in cols:
            tree.heading(c, text=labels[c])
            tree.column(
                c, width=widths[c],
                anchor="w" if c == "target" else "center"
            )

        y = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        x = ttk.Scrollbar(table, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tree.grid(row=0,column=0,sticky="nsew")
        y.grid(row=0,column=1,sticky="ns")
        x.grid(row=1,column=0,sticky="ew")
        table.rowconfigure(0,weight=1)
        table.columnconfigure(0,weight=1)

        for rank, r in enumerate(result["top_days"], start=1):
            d = datetime.strptime(r["date"], "%Y-%m-%d").strftime("%d/%m/%Y")
            target = r["target"]
            td = datetime.strptime(
                target["data"], "%Y-%m-%d"
            ).strftime("%d/%m/%Y")

            tree.insert(
                "", "end",
                values=(
                    rank,
                    d,
                    f'{r["score"]:.2f}',
                    f'{r["exact_component"]:.2f}',
                    f'{r["hour_component"]:.2f}',
                    f'{r["day_component"]:.2f}',
                    f'{r["repetition_component"]:.2f}',
                    f'{r["weekday_component"]:.2f}',
                    f"{td} • {target['sorteio']} {target['hora']} • "
                    + " / ".join(
                        f"{p['bicho']}({p['grupo']:02d})"
                        for p in target["prizes"]
                    ),
                ),
            )

        footer = ttk.Frame(outer, padding=(0, 8, 0, 0))
        footer.pack(fill="x")

        ttk.Label(
            footer,
            text=(
                "Os 5 bichos finais são votados separadamente por posição "
                "do sorteio seguinte. Por isso um mesmo bicho pode aparecer "
                "em mais de um slot."
            ),
            wraplength=760,
        ).pack(side="left")

        ttk.Button(
            footer, text="Fechar", command=self.destroy
        ).pack(side="right")


class MethodsTechnicalDialog(tk.Toplevel):
    """Detalhes completos ficam separados da tela simples."""
    def __init__(self, master, result):
        super().__init__(master)
        self.result = result
        self.title("Detalhes técnicos — Método de Puxada Combinada")
        self.geometry("1280x720")
        self.minsize(1000, 580)
        self.resizable(True, True)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Detalhes técnicos",
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text=(
                "Aqui aparecem as métricas que ficaram escondidas na tela principal: "
                "fontes, soma da cobertura, lift, estado usado e suporte."
            ),
            wraplength=1120,
        ).pack(anchor="w", pady=(3, 10))

        # Ranking completo
        rank_frame = ttk.Frame(outer)
        rank_frame.pack(fill="both", expand=True)

        cols = ("rank","grupo","bicho","fontes","somaprob","lift","origens")
        self.tree = ttk.Treeview(
            rank_frame, columns=cols, show="headings", selectmode="browse"
        )

        labels = {
            "rank":"#",
            "grupo":"Grupo",
            "bicho":"Bicho",
            "fontes":"Fontes",
            "somaprob":"Soma cobertura",
            "lift":"Lift médio",
            "origens":"Quem apontou",
        }
        widths = {
            "rank":42,"grupo":58,"bicho":110,"fontes":70,
            "somaprob":110,"lift":90,"origens":650,
        }

        for c in cols:
            self.tree.heading(c, text=labels[c])
            self.tree.column(
                c,
                width=widths[c],
                anchor="w" if c in ("bicho","origens") else "center",
            )

        y = ttk.Scrollbar(rank_frame, orient="vertical", command=self.tree.yview)
        x = ttk.Scrollbar(rank_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        rank_frame.rowconfigure(0, weight=1)
        rank_frame.columnconfigure(0, weight=1)

        selected_groups = {r["grupo"] for r in result["selected"]}

        for rank, r in enumerate(result["ranking"], start=1):
            origins = " | ".join(
                f"{s['bicho']}[{s['state']}] {s['prob']:.1f}%/{s['lift']:.2f}x"
                for s in r["sources"]
            ) if r["sources"] else "—"

            tags = ("selected",) if r["grupo"] in selected_groups else ()

            self.tree.insert(
                "",
                "end",
                iid=str(r["grupo"]),
                tags=tags,
                values=(
                    rank,
                    f'{r["grupo"]:02d}',
                    r["bicho"],
                    r["source_count"],
                    f'{r["sum_prob"]:.2f}%',
                    f'{r["avg_lift"]:.2f}x',
                    origins,
                ),
            )

        self.tree.tag_configure("selected", font=("Segoe UI Semibold", 9))
        self.tree.bind("<Double-1>", self.open_selected_detail)

        footer = ttk.Frame(outer, padding=(0, 10, 0, 0))
        footer.pack(fill="x")

        ttk.Button(
            footer,
            text="Detalhes do bicho selecionado",
            command=self.open_selected_detail,
        ).pack(side="left")

        ttk.Button(
            footer, text="Fechar", command=self.destroy
        ).pack(side="right")
        ttk.Button(
            footer, text="Minimizar", command=self.iconify
        ).pack(side="right", padx=(0, 8))

    def open_selected_detail(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(
                "Detalhes técnicos",
                "Selecione um bicho no ranking.",
                parent=self,
            )
            return

        group = int(sel[0])
        row = next(
            (r for r in self.result["ranking"] if r["grupo"] == group),
            None,
        )
        if row:
            MethodTargetDetailsDialog(self, self.result, row)


class MethodTargetDetailsDialog(tk.Toplevel):
    def __init__(self, master, result, target_row):
        super().__init__(master)
        self.title(f"Detalhes do bicho — {target_row['bicho']}")
        self.geometry("920x520")
        self.minsize(760, 430)
        self.resizable(True, True)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text=f"{target_row['bicho']} — Grupo {target_row['grupo']:02d}",
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text=(
                f"Foi apontado por {target_row['source_count']} bicho(s) da base. "
                f"Soma da cobertura: {target_row['sum_prob']:.2f}% • "
                f"Lift médio: {target_row['avg_lift']:.2f}x"
            ),
            wraplength=850,
        ).pack(anchor="w", pady=(4,10))

        cols = ("base","estado","suporte","cobertura","lift")
        tree = ttk.Treeview(outer, columns=cols, show="headings")

        for c, lab, w in [
            ("base","Quem puxou",190),
            ("estado","Estado usado",120),
            ("suporte","Amostra",90),
            ("cobertura","Cobertura",110),
            ("lift","Lift",90),
        ]:
            tree.heading(c, text=lab)
            tree.column(c, width=w, anchor="w" if c == "base" else "center")

        tree.pack(fill="both", expand=True)

        for s in target_row["sources"]:
            tree.insert("", "end", values=(
                f"{s['bicho']} ({s['grupo']:02d})",
                s["state"],
                s["support"],
                f"{s['prob']:.2f}%",
                f"{s['lift']:.2f}x",
            ))

        footer = ttk.Frame(outer, padding=(0,10,0,0))
        footer.pack(fill="x")

        ttk.Label(
            footer,
            text=(
                "Se o estado ×1/×2/×3+ tinha pouca amostra, "
                "o programa usou a puxada Geral daquele bicho."
            ),
            wraplength=650,
        ).pack(side="left")

        ttk.Button(footer, text="Fechar", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Minimizar", command=self.iconify).pack(side="right", padx=(0,8))


class HistoricalPullsDialog(tk.Toplevel):
    def __init__(self, master, db: Database):
        super().__init__(master)
        self.db = db
        self.title("Puxadas históricas — GP-H")
        self.geometry("1280x780")
        self.minsize(1060, 650)

        animal_values = [f"{g:02d} - {BICHOS[g]}" for g in range(1, 26)]
        sorteios, horas = self.db.filter_options()

        self.var_animal = tk.StringVar(value=animal_values[0])
        self.var_state = tk.StringVar(value="Geral")
        self.var_from = tk.StringVar()
        self.var_to = tk.StringVar()
        self.var_sort = tk.StringVar(value="Todos")
        self.var_hour = tk.StringVar(value="Todos")
        self.current = None

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Puxadas históricas",
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text=(
                "Pergunta respondida: quando o bicho-base apareceu nesta condição, "
                "quais bichos apareceram na extração imediatamente seguinte?"
            ),
        ).pack(anchor="w", pady=(3, 2))

        ttk.Label(
            outer,
            text=(
                "Probabilidade = frequência histórica observada. Lift compara essa frequência "
                "com a taxa natural do alvo no mesmo contexto; não é garantia de próximo resultado."
            ),
        ).pack(anchor="w", pady=(0, 10))

        filt = ttk.Frame(outer, style="Card.TFrame", padding=12)
        filt.pack(fill="x")

        widgets = [
            ("Bicho-base", ttk.Combobox(
                filt, textvariable=self.var_animal, values=animal_values,
                width=20, state="readonly"
            )),
            ("Estado", ttk.Combobox(
                filt, textvariable=self.var_state,
                values=["Geral", "×1", "×2", "×3+"],
                width=9, state="readonly"
            )),
            ("De", CalendarField(filt, self.var_from, width=11)),
            ("Até", CalendarField(filt, self.var_to, width=11)),
            ("Origem", ttk.Combobox(
                filt, textvariable=self.var_sort,
                values=["Todos"] + sorteios, width=11, state="readonly"
            )),
            ("Hora origem", ttk.Combobox(
                filt, textvariable=self.var_hour,
                values=["Todos"] + horas, width=10, state="readonly"
            )),
        ]

        for col, (label, widget) in enumerate(widgets):
            ttk.Label(filt, text=label, style="Card.TLabel").grid(
                row=0, column=col, sticky="w", padx=(0, 10)
            )
            widget.grid(row=1, column=col, sticky="w", padx=(0, 10), pady=(4, 0))

        ttk.Button(
            filt, text="Calcular puxadas", style="Accent.TButton", command=self.refresh
        ).grid(row=1, column=6, padx=(6, 0), pady=(4, 0))

        self.summary = ttk.Label(outer, text="", padding=(0, 10))
        self.summary.pack(anchor="w")

        # Ranking
        rank_frame = ttk.Frame(outer)
        rank_frame.pack(fill="both", expand=True)

        cols = (
            "rank","grupo","bicho","hits","prob","baseline","lift","ocorr",
            "p1","p2","p3","p4","p5"
        )
        self.tree = ttk.Treeview(rank_frame, columns=cols, show="headings", selectmode="browse")

        labels = {
            "rank":"#","grupo":"Grupo","bicho":"Bicho","hits":"Próx. c/ bicho",
            "prob":"Cobertura","baseline":"Base natural","lift":"Lift",
            "ocorr":"Ocorrências","p1":"1º","p2":"2º","p3":"3º","p4":"4º","p5":"5º"
        }
        widths = {
            "rank":42,"grupo":58,"bicho":110,"hits":105,"prob":85,"baseline":90,
            "lift":65,"ocorr":90,"p1":45,"p2":45,"p3":45,"p4":45,"p5":45
        }

        for c in cols:
            self.tree.heading(c, text=labels[c])
            self.tree.column(c, width=widths[c], anchor="center" if c != "bicho" else "w")

        y = ttk.Scrollbar(rank_frame, orient="vertical", command=self.tree.yview)
        x = ttk.Scrollbar(rank_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        rank_frame.rowconfigure(0, weight=1)
        rank_frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self.open_selected_examples)

        bottom = ttk.Frame(outer, padding=(0, 10, 0, 0))
        bottom.pack(fill="x")

        self.transition_label = ttk.Label(
            bottom,
            text="Transições usadas: —",
            wraplength=900,
        )
        self.transition_label.pack(side="left", fill="x", expand=True)

        ttk.Button(
            bottom, text="Fechar", command=self.destroy
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            bottom, text="Minimizar", command=self.iconify
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            bottom, text="Ver exemplos do selecionado", command=self.open_selected_examples
        ).pack(side="right", padx=(10, 0))

        self.refresh()

    def selected_group(self):
        value = self.var_animal.get().strip()
        m = re.match(r"(\d{1,2})", value)
        if not m:
            raise ValueError("Selecione um bicho-base.")
        return int(m.group(1))

    def refresh(self):
        try:
            d1 = parse_br_date(self.var_from.get())
            d2 = parse_br_date(self.var_to.get())
            if d1 and d2 and d1 > d2:
                raise ValueError("A data inicial não pode ser maior que a final.")

            result = self.db.historical_pulls(
                base_group=self.selected_group(),
                state=self.var_state.get(),
                date_from=d1,
                date_to=d2,
                source_sort=self.var_sort.get(),
                source_hour=self.var_hour.get(),
            )
            self.current = result

            for item in self.tree.get_children():
                self.tree.delete(item)

            for rank, r in enumerate(result["ranking"], start=1):
                self.tree.insert("", "end", iid=str(r["grupo"]), values=(
                    rank,
                    f'{r["grupo"]:02d}',
                    r["bicho"],
                    r["hit_draws"],
                    f'{r["prob"]:.2f}%',
                    f'{r["baseline_prob"]:.2f}%',
                    f'{r["lift"]:.2f}x',
                    r["total_occ"],
                    r["p1"], r["p2"], r["p3"], r["p4"], r["p5"],
                ))

            self.summary.configure(
                text=(
                    f"Base: {result['base_bicho']} ({result['base_group']:02d}) • "
                    f"Estado {result['state']} • "
                    f"Suporte: {result['support']} extração(ões) com a condição • "
                    f"Baseline: {result['baseline_support']} transição(ões) no mesmo contexto."
                )
            )

            trans = result["transitions"][:5]
            if trans:
                txt = " | ".join(
                    f"{t['source_sort']} {t['source_hour']} → "
                    f"{t['target_sort']} {t['target_hour']}: {t['count']}"
                    for t in trans
                )
                self.transition_label.configure(text="Transições usadas: " + txt)
            else:
                self.transition_label.configure(text="Transições usadas: nenhuma com a condição selecionada.")

        except Exception as e:
            messagebox.showerror("Puxadas históricas", str(e), parent=self)

    def open_selected_examples(self, _event=None):
        if not self.current:
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Puxadas", "Selecione um bicho-alvo primeiro.", parent=self)
            return

        target_group = int(sel[0])
        target = next(
            (r for r in self.current["ranking"] if r["grupo"] == target_group),
            None
        )
        if not target:
            return

        PullExamplesDialog(
            self,
            base_group=self.current["base_group"],
            state=self.current["state"],
            target_row=target,
        )


class PullExamplesDialog(tk.Toplevel):
    def __init__(self, master, base_group: int, state: str, target_row):
        super().__init__(master)
        self.title(
            f"Exemplos — {BICHOS[base_group]} → {target_row['bicho']}"
        )
        self.geometry("1180x620")
        self.minsize(930, 500)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text=f"{BICHOS[base_group]} ({base_group:02d}) [{state}] → {target_row['bicho']} ({target_row['grupo']:02d})",
            font=("Segoe UI Semibold", 15),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text=(
                f"Exibindo até {len(target_row['examples'])} exemplos em que o alvo apareceu "
                "na extração imediatamente seguinte."
            ),
        ).pack(anchor="w", pady=(3, 10))

        cols = (
            "data1","origem","base","data2","destino","resultado_destino"
        )
        tree = ttk.Treeview(outer, columns=cols, show="headings")

        labels = {
            "data1":"Data origem",
            "origem":"Origem",
            "base":"Base na origem",
            "data2":"Data seguinte",
            "destino":"Extração seguinte",
            "resultado_destino":"5 bichos da extração seguinte",
        }
        widths = {
            "data1":100,"origem":145,"base":110,"data2":105,"destino":150,"resultado_destino":430
        }

        for c in cols:
            tree.heading(c, text=labels[c])
            tree.column(c, width=widths[c], anchor="center" if c != "resultado_destino" else "w")

        y = ttk.Scrollbar(outer, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=y.set)
        tree.pack(side="left", fill="both", expand=True)
        y.pack(side="right", fill="y")

        for ex in target_row["examples"]:
            s = ex["source"]
            t = ex["target"]
            d1 = datetime.strptime(s["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            d2 = datetime.strptime(t["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            result_txt = " • ".join(
                f"{p['premio']}º {p['bicho']} ({p['grupo']:02d})"
                for p in t["prizes"]
            )
            tree.insert("", "end", values=(
                d1,
                f"{s['sorteio']} {s['hora']}",
                f"{ex['source_count']}x {BICHOS[base_group]}",
                d2,
                f"{t['sorteio']} {t['hora']}",
                result_txt,
            ))

class StatisticsDialog(tk.Toplevel):
    def __init__(self, master, db: Database):
        super().__init__(master)
        self.db = db
        self.title("Estatísticas históricas — GP-H")
        self.geometry("1280x760")
        self.minsize(1040, 620)

        self.var_from = tk.StringVar()
        self.var_to = tk.StringVar()
        self.var_sort = tk.StringVar(value="Todos")
        self.var_hour = tk.StringVar(value="Todos")
        self.var_prize = tk.StringVar(value="Todos")
        self.current_stats = None

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Estatísticas históricas dos 25 bichos",
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text=(
                "Frequência observada no histórico. Estes números descrevem o passado e "
                "não significam que um bicho esteja 'devendo' ou vá sair no próximo sorteio."
            ),
        ).pack(anchor="w", pady=(3, 10))

        filt = ttk.Frame(outer, style="Card.TFrame", padding=12)
        filt.pack(fill="x")

        sorteios, horas = self.db.filter_options()

        for col, (label, widget) in enumerate([
            ("De", CalendarField(filt, self.var_from, width=11)),
            ("Até", CalendarField(filt, self.var_to, width=11)),
            ("Sorteio", ttk.Combobox(filt, textvariable=self.var_sort, values=["Todos"]+sorteios, width=12, state="readonly")),
            ("Hora", ttk.Combobox(filt, textvariable=self.var_hour, values=["Todos"]+horas, width=10, state="readonly")),
            ("Prêmio", ttk.Combobox(filt, textvariable=self.var_prize, values=["Todos","1","2","3","4","5"], width=8, state="readonly")),
        ]):
            ttk.Label(filt, text=label, style="Card.TLabel").grid(row=0, column=col, sticky="w", padx=(0,10))
            widget.grid(row=1, column=col, sticky="w", padx=(0,10), pady=(4,0))

        ttk.Button(
            filt, text="Atualizar estatísticas", style="Accent.TButton", command=self.refresh
        ).grid(row=1, column=5, sticky="w", pady=(4,0))

        ttk.Button(
            filt, text="Limpar filtros", command=self.clear_filters
        ).grid(row=1, column=6, sticky="w", padx=(8,0), pady=(4,0))

        self.summary = ttk.Label(outer, text="", padding=(0,10))
        self.summary.pack(anchor="w")

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        cols = ("rank","grupo","bicho","ocorrencias","pctpremios","draws","pctdraws","p1","p2","p3","p4","p5","ultima")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        labels = {
            "rank":"#","grupo":"Grupo","bicho":"Bicho","ocorrencias":"Ocorrências",
            "pctpremios":"% prêmios","draws":"Extrações c/ bicho","pctdraws":"% extrações",
            "p1":"1º","p2":"2º","p3":"3º","p4":"4º","p5":"5º","ultima":"Última ocorrência"
        }
        widths = {
            "rank":42,"grupo":58,"bicho":110,"ocorrencias":88,"pctpremios":80,
            "draws":105,"pctdraws":88,"p1":45,"p2":45,"p3":45,"p4":45,"p5":45,"ultima":180
        }
        for c in cols:
            self.tree.heading(c, text=labels[c])
            self.tree.column(c, width=widths[c], anchor="center" if c != "bicho" else "w")

        y = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        x = ttk.Scrollbar(left, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.tree.grid(row=0,column=0,sticky="nsew")
        y.grid(row=0,column=1,sticky="ns")
        x.grid(row=1,column=0,sticky="ew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self.open_selected_details)

        bottom = ttk.Frame(outer, padding=(0,10,0,0))
        bottom.pack(fill="x")
        ttk.Label(
            bottom,
            text="Dica: dê dois cliques em um bicho para ver horários e ocorrências recentes."
        ).pack(side="left")
        ttk.Button(bottom, text="Fechar", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="Minimizar", command=self.iconify).pack(side="right", padx=(0,8))
        ttk.Button(bottom, text="Detalhes do selecionado", command=self.open_selected_details).pack(side="right", padx=(0,8))

        self.refresh()

    def clear_filters(self):
        self.var_from.set("")
        self.var_to.set("")
        self.var_sort.set("Todos")
        self.var_hour.set("Todos")
        self.var_prize.set("Todos")
        self.refresh()

    def refresh(self):
        try:
            d1 = parse_br_date(self.var_from.get())
            d2 = parse_br_date(self.var_to.get())
            if d1 and d2 and d1 > d2:
                raise ValueError("A data inicial não pode ser maior que a final.")

            stats = self.db.stats_by_animal(
                date_from=d1,
                date_to=d2,
                sorteio=self.var_sort.get(),
                hora=self.var_hour.get(),
                premio=self.var_prize.get(),
            )
            self.current_stats = stats

            for item in self.tree.get_children():
                self.tree.delete(item)

            for rank, r in enumerate(stats["rows"], start=1):
                last_txt = "—"
                if r["ultima"]:
                    d = datetime.strptime(r["ultima"]["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
                    last_txt = (
                        f"{d} {r['ultima']['hora']} • {r['ultima']['premio']}º • "
                        f"{r['ultima']['milhar']}"
                    )
                self.tree.insert("", "end", iid=str(r["grupo"]), values=(
                    rank, f'{r["grupo"]:02d}', r["bicho"], r["ocorrencias"],
                    f'{r["pct_premios"]:.2f}%', r["extracoes_com_bicho"],
                    f'{r["pct_extracoes"]:.2f}%',
                    r["p1"], r["p2"], r["p3"], r["p4"], r["p5"], last_txt
                ))

            self.summary.configure(
                text=(
                    f"Escopo: {stats['total_prizes']:,} prêmio(s) • "
                    f"{stats['total_draws']:,} extração(ões) • "
                    f"{len(stats['rows'])} bicho(s) encontrado(s)."
                ).replace(",", ".")
            )
        except Exception as e:
            messagebox.showerror("Estatísticas", str(e), parent=self)

    def open_selected_details(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Estatísticas", "Selecione um bicho primeiro.", parent=self)
            return
        grupo = int(sel[0])
        d1 = parse_br_date(self.var_from.get())
        d2 = parse_br_date(self.var_to.get())
        AnimalDetailsDialog(self, self.db, grupo, d1, d2)


class AnimalDetailsDialog(tk.Toplevel):
    def __init__(self, master, db: Database, grupo: int, date_from=None, date_to=None):
        super().__init__(master)
        self.db = db
        self.grupo = grupo
        self.title(f"Detalhes — {BICHOS[grupo]} ({grupo:02d})")
        self.geometry("900x650")
        self.minsize(760, 540)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text=f"{BICHOS[grupo]} — Grupo {grupo:02d}",
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")

        # Horários
        ttk.Label(outer, text="Distribuição por sorteio/horário", padding=(0,10,0,4)).pack(anchor="w")
        hour_frame = ttk.Frame(outer)
        hour_frame.pack(fill="x")

        hcols = ("sorteio","hora","ocorrencias","extracoes")
        htree = ttk.Treeview(hour_frame, columns=hcols, show="headings", height=8)
        for c, lab, w in [
            ("sorteio","Sorteio",120),("hora","Hora",90),
            ("ocorrencias","Ocorrências",120),("extracoes","Extrações com o bicho",150)
        ]:
            htree.heading(c,text=lab)
            htree.column(c,width=w,anchor="center")
        htree.pack(fill="x")

        for r in self.db.animal_hour_breakdown(grupo, date_from, date_to):
            htree.insert("", "end", values=(r["sorteio"], r["hora"], r["ocorrencias"], r["extracoes"]))

        # Recent occurrences
        ttk.Label(outer, text="20 ocorrências mais recentes", padding=(0,12,0,4)).pack(anchor="w")
        recent_frame = ttk.Frame(outer)
        recent_frame.pack(fill="both", expand=True)

        cols = ("data","sorteio","hora","premio","milhar","centena","dezena")
        tree = ttk.Treeview(recent_frame, columns=cols, show="headings")
        for c, lab, w in [
            ("data","Data",100),("sorteio","Sorteio",95),("hora","Hora",80),
            ("premio","Prêmio",70),("milhar","Milhar",90),("centena","Centena",90),("dezena","Dezena",80)
        ]:
            tree.heading(c,text=lab)
            tree.column(c,width=w,anchor="center")

        y = ttk.Scrollbar(recent_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=y.set)
        tree.grid(row=0,column=0,sticky="nsew")
        y.grid(row=0,column=1,sticky="ns")
        recent_frame.rowconfigure(0,weight=1)
        recent_frame.columnconfigure(0,weight=1)

        for r in self.db.animal_recent_occurrences(grupo, 20, date_from, date_to):
            d = datetime.strptime(r["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            tree.insert("", "end", values=(
                d,r["sorteio"],r["hora"],f'{r["premio"]}º',
                r["milhar"],r["centena"],r["dezena"]
            ))

class UpdatePreviewDialog(tk.Toplevel):
    def __init__(self, master, db: Database, novos, alterados, iguais, on_apply):
        super().__init__(master)
        self.db = db
        self.novos = novos
        self.alterados = alterados
        self.iguais = iguais
        self.on_apply = on_apply

        self.title("Atualizações encontradas na internet")
        self.geometry("1120x650")
        self.minsize(900, 520)
        self.transient(master)
        self.grab_set()

        top = ttk.Frame(self, padding=16)
        top.pack(fill="x")

        draw_keys = {
            (r.data, r.sorteio, r.hora)
            for r in novos
        } | {
            (r.data, r.sorteio, r.hora)
            for r, _ in alterados
        }

        ttk.Label(
            top,
            text="Resultados encontrados",
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")

        ttk.Label(
            top,
            text=(
                f"{len(draw_keys)} extração(ões) com novidade • "
                f"{len(novos)} prêmio(s) novo(s) • "
                f"{len(alterados)} alteração(ões) • "
                f"{iguais} prêmio(s) já estavam corretos."
            ),
        ).pack(anchor="w", pady=(5, 0))

        ttk.Label(
            top,
            text=(
                "Revise abaixo. Nada será gravado até você clicar em "
                "\"Adicionar encontrados\"."
            ),
        ).pack(anchor="w", pady=(2, 0))

        table_frame = ttk.Frame(self, padding=(16, 0, 16, 0))
        table_frame.pack(fill="both", expand=True)

        cols = ("status","data","sorteio","hora","premio","milhar","centena","dezena","grupo","bicho")
        tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        labels = {
            "status":"Status","data":"Data","sorteio":"Sorteio","hora":"Hora",
            "premio":"Prêmio","milhar":"Milhar","centena":"Centena",
            "dezena":"Dezena","grupo":"Grupo","bicho":"Bicho"
        }
        widths = {
            "status":90,"data":95,"sorteio":90,"hora":70,"premio":65,
            "milhar":80,"centena":75,"dezena":70,"grupo":65,"bicho":120
        }
        for c in cols:
            tree.heading(c, text=labels[c])
            tree.column(c, width=widths[c], anchor="center" if c != "bicho" else "w")

        y = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        x = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        combined = [("NOVO", r, None) for r in novos] + [
            ("ALTERADO", r, old) for r, old in alterados
        ]
        combined.sort(key=lambda item: (item[1].data, item[1].hora, item[1].sorteio, item[1].premio))

        for status, r, old in combined:
            d = datetime.strptime(r.data, "%Y-%m-%d").strftime("%d/%m/%Y")
            tree.insert("", "end", values=(
                status, d, r.sorteio, r.hora, f"{r.premio}º",
                r.milhar, r.centena, r.dezena, f"{r.grupo:02d}", r.bicho
            ))
            if status == "ALTERADO" and old:
                tree.insert("", "end", values=(
                    "ANTERIOR", d, r.sorteio, r.hora, f"{r.premio}º",
                    old["milhar"], old["milhar"][-3:], old["milhar"][-2:],
                    f'{old["grupo"]:02d}', old["bicho"]
                ))

        bottom = ttk.Frame(self, padding=16)
        bottom.pack(fill="x")

        ttk.Button(bottom, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(
            bottom,
            text="Adicionar encontrados",
            style="Accent.TButton",
            command=self.apply,
        ).pack(side="right", padx=(0, 10))

    def apply(self):
        rows = list(self.novos) + [r for r, _ in self.alterados]
        if not rows:
            messagebox.showinfo("Atualizações", "Não há nada novo para adicionar.", parent=self)
            self.destroy()
            return

        draws = len({(r.data, r.sorteio, r.hora) for r in rows})
        if not messagebox.askyesno(
            "Confirmar atualização",
            f"Adicionar/atualizar {len(rows)} prêmio(s) de {draws} extração(ões)?",
            parent=self,
        ):
            return

        try:
            if hasattr(self.master, "create_auto_backup"):
                self.master.create_auto_backup("antes_atualizacao")
        except Exception as exc:
            messagebox.showerror(
                "Atualização",
                (
                    "Não consegui criar o backup automático.\n\n"
                    f"{exc}\n\n"
                    "Nenhum resultado foi alterado."
                ),
                parent=self,
            )
            return

        self.db.upsert_rows(rows)
        audit = self.db.audit()

        if audit["problems"]:
            messagebox.showwarning(
                "Atualização salva com alertas",
                "Os resultados foram salvos, mas a revisão encontrou alertas.\n"
                "Abra \"Revisar base\" para conferir.",
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Atualização concluída",
                f"{len(rows)} prêmio(s) foram adicionados/atualizados.\n\n"
                "A revisão automática da base terminou sem inconsistências estruturais.",
                parent=self,
            )

        self.on_apply()
        self.destroy()

class ManualDialog(tk.Toplevel):
    def __init__(self, master, db: Database, on_saved):
        super().__init__(master)
        self.db = db
        self.on_saved = on_saved
        self.title("Adicionar resultado manual")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self.var_date = tk.StringVar(value=date.today().strftime("%d/%m/%Y"))
        self.var_sort = tk.StringVar(value="PT")
        self.var_hour = tk.StringVar(value="14:00")
        self.vars_milhar = [tk.StringVar() for _ in range(5)]

        frm = ttk.Frame(self, padding=16)
        frm.grid(sticky="nsew")

        ttk.Label(frm, text="Data").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.var_date, width=14).grid(row=1, column=0, padx=(0, 10))

        ttk.Label(frm, text="Sorteio").grid(row=0, column=1, sticky="w")
        cb = ttk.Combobox(
            frm, textvariable=self.var_sort,
            values=["PPT","PTM","PT","PTV","PTN","FEDERAL","CORUJA"],
            width=12, state="readonly"
        )
        cb.grid(row=1, column=1, padx=(0, 10))
        cb.bind("<<ComboboxSelected>>", self.update_hour)

        ttk.Label(frm, text="Hora").grid(row=0, column=2, sticky="w")
        ttk.Entry(frm, textvariable=self.var_hour, width=10).grid(row=1, column=2)

        ttk.Separator(frm).grid(row=2, column=0, columnspan=3, sticky="ew", pady=12)

        for i, var in enumerate(self.vars_milhar, start=1):
            ttk.Label(frm, text=f"{i}º prêmio").grid(row=2+i, column=0, sticky="w", pady=3)
            ttk.Entry(frm, textvariable=var, width=12).grid(row=2+i, column=1, sticky="w", pady=3)

        btns = ttk.Frame(frm)
        btns.grid(row=9, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="Salvar e revisar", command=self.save).pack(side="right")

        self.bind("<Return>", lambda e: self.save())
        self.bind("<Escape>", lambda e: self.destroy())

    def update_hour(self, _=None):
        self.var_hour.set(DEFAULT_HOURS.get(self.var_sort.get(), ""))

    def save(self):
        try:
            d = datetime.strptime(self.var_date.get().strip(), "%d/%m/%Y").date()
            sort = self.var_sort.get()
            hour = self.var_hour.get().strip()
            if not re.fullmatch(r"\d{2}:\d{2}", hour):
                raise ValueError("Hora inválida. Use HH:MM.")

            rows = []
            for i, var in enumerate(self.vars_milhar, start=1):
                value = var.get().strip()
                if not value:
                    raise ValueError(f"Informe a milhar do {i}º prêmio.")
                milhar, centena, dezena, grupo, bicho = derivados_milhar(value)
                rows.append(PrizeRow(
                    data=d.isoformat(),
                    dia_semana=d.strftime("%A"),
                    sorteio=sort,
                    hora=hour,
                    premio=i,
                    milhar=milhar,
                    centena=centena,
                    dezena=dezena,
                    grupo=grupo,
                    bicho=bicho,
                    fonte="CADASTRO MANUAL",
                    grupo_publicado=grupo,
                    bicho_publicado=bicho,
                ))
            self.db.upsert_rows(rows)
            self.on_saved()
            self.destroy()
            messagebox.showinfo("GP-H", "Resultado salvo e base revisada.")
        except Exception as e:
            messagebox.showerror("Não foi possível salvar", str(e), parent=self)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.account_profile = load_account_profile()
        self.db = Database(DB_PATH)

        self.startup_migration_report = {
            "executada": False,
            "fontes": 0,
            "resultados_adicionados": 0,
            "jogos_adicionados": 0,
            "mensagem": "",
        }

        # Só a base compartilhada oficial procura versões antigas.
        # Testes ou bancos explicitamente apontados não são contaminados.
        try:
            if Path(DB_PATH).resolve() == Path(DATA_DIR / "gph_historico.db").resolve():
                self.startup_migration_report = (
                    self.db.auto_merge_previous_installations(
                        discover_previous_database_paths()
                    )
                )
        except Exception as exc:
            self.startup_migration_report = {
                "executada": False,
                "fontes": 0,
                "resultados_adicionados": 0,
                "jogos_adicionados": 0,
                "mensagem": f"Migração automática não concluída: {exc}",
            }

        self.sync_queue = queue.Queue()
        self.sync_running = False
        self.update_running = False
        self.account_sync_running = False
        self.last_rows = []
        self.program_update_settings = load_program_update_settings()
        # A versão realmente em execução é a fonte de verdade após atualização/rollback.
        if self.program_update_settings.get("last_installed_version") != APP_VERSION:
            self.program_update_settings["last_installed_version"] = APP_VERSION
            self.program_update_settings["pending_version"] = None
            self.program_update_settings = save_program_update_settings(self.program_update_settings)
        self.program_update_check_running = False
        self.program_update_download_running = False
        self.available_program_update = None
        self.program_update_status_var = None
        self.program_update_available_var = None
        self.program_update_install_btn = None

        self.visual_settings = load_visual_settings()
        self.theme_name = self.visual_settings.get("theme", "Noturno Azul")
        if self.theme_name not in THEME_PALETTES:
            self.theme_name = "Noturno Azul"
        self.colors = dict(THEME_PALETTES[self.theme_name])
        self.animal_pack_name = self.visual_settings.get("animal_pack", "Natural")
        if self.animal_pack_name not in ANIMAL_PACKS:
            self.animal_pack_name = "Natural"

        # v0.31.0: quem ainda estava no pacote padrão antigo recebe uma única
        # migração visual para o novo Natural. Escolhas explícitas por
        # Semi-realista/Minimalista são preservadas e o usuário pode voltar
        # ao Cartoon Elegante a qualquer momento em Aparência.
        if (
            self.animal_pack_name == "Cartoon Elegante"
            and not self.visual_settings.get("natural_pack_migrated_v031")
        ):
            self.animal_pack_name = "Natural"
            self.visual_settings["animal_pack"] = "Natural"
            self.visual_settings["natural_pack_migrated_v031"] = True
            save_visual_settings(self.visual_settings)

        # Primeira execução: materializa as preferências padrão na pasta persistente.
        if not VISUAL_SETTINGS_PATH.is_file():
            self.visual_settings = {
                "theme": self.theme_name,
                "animal_pack": self.animal_pack_name,
            }
            save_visual_settings(self.visual_settings)

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1280x760")
        self.minsize(1050, 650)
        self.configure(bg=self.colors["bg"])

        # v0.32.2: mantém a abertura maximizada introduzida na v0.32.1.
        # A chamada é adiada até o primeiro ciclo do Tk para que funcione
        # também no executável Windows após a janela ser materializada.
        self.after(0, self._maximize_main_window)

        self._load_visual_assets()
        if self.app_icon is not None:
            try:
                self.iconphoto(True, self.app_icon)
            except tk.TclError:
                pass
        # Já deixa a identidade pronta para o futuro executável do Windows.
        try:
            ico = LOGO_ASSET_DIR / "gph_icon.ico"
            if os.name == "nt" and ico.is_file():
                self.iconbitmap(default=str(ico))
        except tk.TclError:
            pass

        self._build_style()
        self._build_ui()
        if not self._ensure_profile_login():
            self._startup_cancelled = True
            try:
                self.destroy()
            except Exception:
                pass
            return
        self._startup_cancelled = False

        # Preparação para executável: fechamento seguro e log de exceções de callbacks Tk.
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self.report_callback_exception = self._report_callback_exception

        # Atalhos de uso diário.
        self.bind_all(
            "<Control-j>",
            lambda _e: self.show_play_page(),
        )
        self.bind_all(
            "<Control-g>",
            lambda _e: self.show_generator_page(),
        )
        self.bind_all(
            "<Control-r>",
            lambda _e: self.show_results(),
        )
        self.bind_all(
            "<F5>",
            lambda _e: self.start_update_search(),
        )

        self.after(150, self.poll_queue)

        if (self.account_profile or {}).get("sync_enabled") and (self.account_profile or {}).get("sync_auto", True):
            self.after(1200, lambda: self.account_sync_now(silent=True))
        self.after(60000, self._account_sync_periodic)

        # v0.27.0: audita leituras anteriores e congela a próxima rodada
        # automaticamente quando já existe histórico suficiente.
        self.after(1700, self._auto_decision_cycle)

        # Verificação do PROGRAMA é independente da atualização de resultados (F5).
        # Se ainda não houver servidor configurado, não faz rede nem mostra aviso.
        if self.program_update_settings.get("auto_check") and self.program_update_settings.get("manifest_url"):
            self.after(4200, lambda: self.program_update_check(manual=False))

        if self.db.count() == 0:
            self.after(700, self.first_run_prompt)

    def _account_status_text(self):
        profile = getattr(self, "account_profile", None) or {}
        name = profile.get("profile_name")
        if not name:
            return "Perfil: não vinculado"
        if profile.get("sync_enabled") and profile.get("sync_folder"):
            status = profile.get("sync_status")
            if status == "ok":
                sync = "Sync: OK"
            elif status == "error":
                sync = "Sync: erro"
            elif status == "running":
                sync = "Sync: ..."
            else:
                sync = "Sync: configurado"
            return f"Perfil: {name} • {sync}"
        return f"Perfil: {name} • Sync: local"

    def _refresh_account_status(self):
        label = getattr(self, "account_status", None)
        if label is not None:
            try:
                label.configure(text=self._account_status_text())
            except tk.TclError:
                pass

    def _ensure_profile_login(self):
        profile = self.account_profile
        if profile and profile.get("remember_login", True):
            profile["last_login_at"] = datetime.now().isoformat(timespec="seconds")
            self.account_profile = save_account_profile(profile)
            self._refresh_account_status()
            return True
        return self._show_profile_dialog(required=True)

    def _show_profile_dialog(self, required=False):
        current = self.account_profile or {}
        win = tk.Toplevel(self)
        win.title("Perfil GP-H")
        win.resizable(False, False)
        win.transient(self)
        win.configure(bg=self.colors["bg"])
        try:
            win.grab_set()
        except tk.TclError:
            pass

        outer = ttk.Frame(self._make_scrollable_page_body(win, "profile_dialog"), padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Entrar na Central", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "O perfil identifica seus computadores. Não há senha. "
                "Para usar o mesmo perfil em outro PC, informe o mesmo nome e código."
            ),
            style="Sub.TLabel", wraplength=520, justify="left",
        ).pack(anchor="w", pady=(2, 14))

        form = ttk.Frame(outer, style="Card.TFrame", padding=12)
        form.pack(fill="x")
        name_var = tk.StringVar(value=current.get("profile_name", ""))
        code_var = tk.StringVar(value=current.get("profile_code", ""))
        remember_var = tk.BooleanVar(value=current.get("remember_login", True))

        ttk.Label(form, text="Seu nome", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        name_entry = ttk.Entry(form, textvariable=name_var, width=38)
        name_entry.grid(row=1, column=0, sticky="ew", pady=(2, 9))
        ttk.Label(
            form, text="Código da conta", style="Card.TLabel"
        ).grid(row=2, column=0, sticky="w")
        code_entry = ttk.Entry(form, textvariable=code_var, width=38)
        code_entry.grid(row=3, column=0, sticky="ew", pady=(2, 4))
        ttk.Label(
            form,
            text="No primeiro PC, use CRIAR NOVO PERFIL. Nos outros, cole o código e use ENTRAR COM CÓDIGO.",
            style="CardMuted.TLabel", wraplength=480, justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(0, 8))
        ttk.Checkbutton(
            form, text="Manter conectado neste computador", variable=remember_var
        ).grid(row=5, column=0, sticky="w")
        form.grid_columnconfigure(0, weight=1)

        ttk.Label(
            outer,
            text=(
                "Depois de entrar, abra Base / Configurações → Conta / Perfil e escolha uma pasta "
                "sincronizada pelo OneDrive, Google Drive ou Dropbox para compartilhar os dados entre PCs."
            ),
            style="Sub.TLabel", wraplength=520, justify="left",
        ).pack(anchor="w", pady=(10, 10))

        result = {"ok": False}

        def finish(profile, created=False):
            self.account_profile = save_account_profile(profile)
            result["ok"] = True
            self._refresh_account_status()
            if created:
                try:
                    self.clipboard_clear()
                    self.clipboard_append(profile["profile_code"])
                    self.update()
                except tk.TclError:
                    pass
            win.destroy()
            if created:
                messagebox.showinfo(
                    "Perfil criado",
                    f"Perfil: {profile['profile_name']}\nCódigo: {profile['profile_code']}\n\n"
                    "O código já foi copiado. Guarde-o para vincular os outros PCs.",
                    parent=self,
                )

        def create_new():
            try:
                profile = build_account_profile(
                    name_var.get(), remember_login=remember_var.get(), existing=None
                )
                finish(profile, created=True)
            except Exception as exc:
                messagebox.showerror("Perfil", str(exc), parent=win)

        def link_existing():
            try:
                profile = build_account_profile(
                    name_var.get(), code=code_var.get(),
                    remember_login=remember_var.get(), existing=current,
                )
                finish(profile, created=False)
            except Exception as exc:
                messagebox.showerror("Perfil", str(exc), parent=win)

        actions = ttk.Frame(outer)
        actions.pack(fill="x")
        ttk.Button(
            actions, text="CRIAR NOVO PERFIL", style="Accent.TButton", command=create_new
        ).pack(side="left")
        ttk.Button(
            actions, text="ENTRAR COM CÓDIGO", command=link_existing
        ).pack(side="left", padx=(7, 0))

        def close_dialog():
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", close_dialog)
        name_entry.focus_set()
        self.update_idletasks()
        try:
            x = self.winfo_rootx() + max(20, (self.winfo_width() - 570) // 2)
            y = self.winfo_rooty() + max(20, (self.winfo_height() - 440) // 2)
            win.geometry(f"570x440+{x}+{y}")
        except tk.TclError:
            win.geometry("570x440")
        self.wait_window(win)
        return result["ok"]

    def account_copy_code(self):
        profile = self.account_profile or {}
        code = profile.get("profile_code")
        if not code:
            return
        self.clipboard_clear()
        self.clipboard_append(code)
        self.update()
        self.status.configure(text="Código do perfil copiado.")

    def account_edit_name(self):
        profile = self.account_profile or {}
        if not profile:
            return
        value = simpledialog.askstring(
            "Nome do perfil", "Nome:", initialvalue=profile.get("profile_name", ""), parent=self
        )
        if value is None:
            return
        try:
            updated = build_account_profile(
                value, code=profile.get("profile_code"),
                remember_login=profile.get("remember_login", True), existing=profile,
            )
            self.account_profile = save_account_profile(updated)
            self._refresh_account_status()
            if getattr(self, "_page", None) == "base":
                self.show_base_config()
        except Exception as exc:
            messagebox.showerror("Perfil", str(exc), parent=self)

    def account_rename_device(self):
        profile = self.account_profile or {}
        if not profile:
            return
        value = simpledialog.askstring(
            "Nome deste computador",
            "Como você quer identificar este PC?",
            initialvalue=profile.get("device_name", default_device_name()), parent=self,
        )
        if value is None:
            return
        value = re.sub(r"\s+", " ", value.strip())
        if not value:
            messagebox.showwarning("Conta", "Informe um nome para este computador.", parent=self)
            return
        profile["device_name"] = value[:60]
        self.account_profile = save_account_profile(profile)
        if getattr(self, "_page", None) == "base":
            self.show_base_config()

    def account_set_remember(self, value):
        profile = self.account_profile or {}
        if not profile:
            return
        profile["remember_login"] = bool(value)
        self.account_profile = save_account_profile(profile)

    def account_relink(self):
        if not messagebox.askyesno(
            "Vincular outro perfil",
            "Isso altera somente a identidade deste computador. O banco local não será apagado.\n\nContinuar?",
            parent=self,
        ):
            return
        old_code = normalize_profile_code((self.account_profile or {}).get("profile_code"))
        self._show_profile_dialog(required=False)
        new_code = normalize_profile_code((self.account_profile or {}).get("profile_code"))
        if new_code and new_code != old_code:
            profile = dict(self.account_profile or {})
            profile["sync_folder"] = None
            profile["sync_enabled"] = False
            profile["sync_status"] = "not_configured"
            profile["last_sync_at"] = None
            profile["sync_last_error"] = None
            self.account_profile = save_account_profile(profile)
            self._refresh_account_status()
        if getattr(self, "_page", None) == "base":
            self.show_base_config()

    def _account_sync_folder_default(self):
        for key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
            value = os.environ.get(key)
            if value and Path(value).is_dir():
                return str(Path(value))
        home = Path.home()
        for name in ("OneDrive", "Google Drive", "Dropbox"):
            candidate = home / name
            if candidate.is_dir():
                return str(candidate)
        return str(home)

    def account_configure_sync(self):
        profile = self.account_profile or {}
        if not profile:
            return
        current = profile.get("sync_folder") or self._account_sync_folder_default()
        path = filedialog.askdirectory(
            title="Escolha uma pasta sincronizada entre seus PCs",
            initialdir=current if Path(current).exists() else str(Path.home()),
            parent=self,
        )
        if not path:
            return
        chosen = Path(path).expanduser().resolve()
        try:
            chosen.mkdir(parents=True, exist_ok=True)
            probe = chosen / ".gph-sync-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except Exception as exc:
            messagebox.showerror(
                "Sincronização",
                f"Não consigo gravar nessa pasta.\n\n{exc}",
                parent=self,
            )
            return
        profile["sync_folder"] = str(chosen)
        profile["sync_enabled"] = True
        profile["sync_auto"] = True
        profile["sync_status"] = "configured"
        profile["sync_last_error"] = None
        self.account_profile = save_account_profile(profile)
        self._refresh_account_status()
        if getattr(self, "_page", None) == "base":
            self.show_base_config()
        self.account_sync_now(silent=False)

    def account_set_sync_enabled(self, value):
        profile = self.account_profile or {}
        if not profile:
            return
        if value and not profile.get("sync_folder"):
            self.account_configure_sync()
            return
        profile["sync_enabled"] = bool(value)
        profile["sync_status"] = "configured" if value else "disabled"
        self.account_profile = save_account_profile(profile)
        self._refresh_account_status()

    def account_set_sync_auto(self, value):
        profile = self.account_profile or {}
        if not profile:
            return
        profile["sync_auto"] = bool(value)
        self.account_profile = save_account_profile(profile)

    def account_open_sync_folder(self):
        profile = self.account_profile or {}
        root = account_sync_root(profile)
        if root is None:
            messagebox.showinfo(
                "Sincronização",
                "Configure uma pasta de sincronização primeiro.",
                parent=self,
            )
            return
        self._open_folder(root, "Pasta de sincronização")

    def account_show_devices(self):
        profile = self.account_profile or {}
        if not profile.get("sync_folder"):
            messagebox.showinfo(
                "Dispositivos",
                "A sincronização ainda não está configurada neste PC.",
                parent=self,
            )
            return
        devices = self.db.sync_device_list(profile)
        if not devices:
            messagebox.showinfo(
                "Dispositivos",
                "Ainda não há snapshots de dispositivos nessa conta.\nUse 'Sincronizar agora' primeiro.",
                parent=self,
            )
            return
        lines = []
        for d in devices:
            when = d.get("generated_at") or "—"
            try:
                when = datetime.fromisoformat(str(when)).strftime("%d/%m/%Y %H:%M")
            except Exception:
                pass
            marker = " (este PC)" if d.get("is_current") else ""
            lines.append(
                f"• {d.get('device_name') or 'Computador'}{marker}\n"
                f"  Último pacote: {when} • app {d.get('app_version') or '—'}"
            )
        messagebox.showinfo(
            "Dispositivos vinculados",
            "\n\n".join(lines),
            parent=self,
        )

    def account_sync_now(self, silent=False):
        profile = self.account_profile or {}
        if self.account_sync_running:
            if not silent:
                self.status.configure(text="Sincronização entre PCs já está em andamento.")
            return
        if not profile.get("sync_enabled") or not profile.get("sync_folder"):
            if silent:
                return
            if messagebox.askyesno(
                "Sincronização entre PCs",
                "Ainda não há pasta compartilhada configurada.\n\nDeseja escolher uma pasta do OneDrive, Google Drive ou Dropbox agora?",
                parent=self,
            ):
                self.account_configure_sync()
            return
        if self.sync_running or self.update_running:
            if not silent:
                messagebox.showinfo(
                    "Sincronização",
                    "Aguarde a atualização da base terminar antes de sincronizar entre PCs.",
                    parent=self,
                )
            return

        if not silent:
            try:
                self.create_auto_backup("antes_sync_multi_pc")
            except Exception:
                pass

        self.account_sync_running = True
        # Sincronização automática deve ser visualmente silenciosa.
        # Antes da v0.27.1, mudar o status para "running" a cada minuto
        # e reconstruir a tela ao terminar causava a piscada percebida pelo usuário.
        if not silent:
            profile["sync_status"] = "running"
            profile["sync_last_error"] = None
            self.account_profile = save_account_profile(profile)
            self._refresh_account_status()
            self.status.configure(text="Sincronizando dados entre PCs...")

        snapshot_profile = dict(self.account_profile)
        snapshot_visual = dict(self.visual_settings)

        def worker():
            try:
                report = self.db.sync_with_shared_folder(
                    snapshot_profile,
                    visual_settings=snapshot_visual,
                )
                self.sync_queue.put(("account_sync_done", report, bool(silent)))
            except Exception as exc:
                self.sync_queue.put(("account_sync_error", str(exc), bool(silent)))

        threading.Thread(target=worker, daemon=True).start()

    def _account_sync_periodic(self):
        try:
            profile = self.account_profile or {}
            if profile.get("sync_enabled") and profile.get("sync_auto", True):
                self.account_sync_now(silent=True)
        finally:
            try:
                self.after(60000, self._account_sync_periodic)
            except tk.TclError:
                pass

    def _account_sync_report_text(self, report):
        parts = []
        pairs = [
            ("Resultados novos", "resultados_adicionados"),
            ("Resultados atualizados", "resultados_atualizados"),
            ("Bilhetes novos", "bilhetes_adicionados"),
            ("Bilhetes atualizados", "bilhetes_atualizados"),
            ("Jogos novos", "jogos_adicionados"),
            ("Jogos atualizados", "jogos_atualizados"),
        ]
        for label, key in pairs:
            value = int(report.get(key) or 0)
            if value:
                parts.append(f"{label}: {value}")
        if not parts:
            parts.append("Nenhuma diferença de dados encontrada.")
        parts.append(f"Dispositivos na conta: {int(report.get('device_count') or 1)}")
        return "\n".join(parts)

    def _report_callback_exception(self, exc_type, exc_value, exc_tb):
        """Captura erros de botões/callbacks que o mainloop do Tk não propaga."""
        try:
            if exc_value is None:
                exc_value = RuntimeError(str(exc_type))
            exc_value.__traceback__ = exc_tb
        except Exception:
            pass
        log_path = write_crash_log(exc_value)
        msg = "O GP-H encontrou um erro durante esta ação."
        if log_path:
            msg += f"\n\nRelatório salvo em:\n{log_path}"
        try:
            messagebox.showerror("GP-H - erro", msg, parent=self)
        except Exception:
            pass

    def _has_unsaved_draft(self):
        if getattr(self, "play_ticket_draft", None):
            return True
        if (
            getattr(self, "_page", None) == "play"
            and getattr(self, "play_view", None) == "manual_builder"
            and getattr(self, "manual_builder_rows", None)
        ):
            return True
        return False

    def _draft_description(self):
        parts = []
        ticket = getattr(self, "play_ticket_draft", None) or []
        if ticket:
            parts.append(f"bilhete em montagem com {len(ticket)} modalidade(s)")
        if (
            getattr(self, "_page", None) == "play"
            and getattr(self, "play_view", None) == "manual_builder"
            and getattr(self, "manual_builder_rows", None)
        ):
            parts.append(f"Jogo Manual com {len(self.manual_builder_rows)} palpite(s) ainda não salvo(s)")
        return " e ".join(parts) if parts else "rascunho não salvo"

    def _on_close_request(self):
        if self._has_unsaved_draft():
            if not messagebox.askyesno(
                "Fechar a Central?",
                "Existe " + self._draft_description() + ".\n\n"
                "Se fechar agora, esse rascunho será perdido. Deseja fechar mesmo assim?",
                parent=self,
            ):
                return
        try:
            self.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------
    # Atualizações do PROGRAMA (não confundir com atualização de resultados)
    # ------------------------------------------------------------
    def _program_update_channel_label(self):
        key = (self.program_update_settings or {}).get("channel", "stable")
        return "Teste" if key == "test" else "Estável"

    def program_update_set_channel(self, label):
        key = PROGRAM_UPDATE_CHANNELS.get(str(label), "stable")
        self.program_update_settings["channel"] = key
        self.program_update_settings = save_program_update_settings(self.program_update_settings)
        self.available_program_update = None
        self._refresh_program_update_widgets()

    def program_update_set_auto_check(self, value):
        self.program_update_settings["auto_check"] = bool(value)
        self.program_update_settings = save_program_update_settings(self.program_update_settings)

    def _program_update_status_text(self):
        s = self.program_update_settings or {}
        if self.program_update_check_running:
            return "Consultando o servidor de atualizações..."
        if s.get("last_error"):
            return f"Última verificação: erro • {s.get('last_error')}"
        when = s.get("last_check_at")
        if when:
            try:
                when = datetime.fromisoformat(str(when)).strftime("%d/%m/%Y %H:%M")
            except Exception:
                pass
            return f"Última verificação: {when}"
        if not s.get("manifest_url"):
            return "Servidor ainda não configurado • mecanismo local pronto para testes"
        try:
            from urllib.parse import urlparse
            host = urlparse(str(s.get("manifest_url") or "")).hostname
            if host:
                return f"Servidor: {host} • ainda não verificado nesta instalação."
        except Exception:
            pass
        return "Servidor configurado • ainda não verificado nesta instalação."

    def _refresh_program_update_widgets(self):
        try:
            if self.program_update_status_var is not None:
                self.program_update_status_var.set(self._program_update_status_text())
            if self.program_update_available_var is not None:
                rel = self.available_program_update
                if rel and _is_newer_version(rel.get("version")):
                    notes = str(rel.get("notes") or "").strip().replace("\n", " ")
                    if len(notes) > 180:
                        notes = notes[:177] + "..."
                    txt = f"Nova versão disponível: v{rel['version']}"
                    if notes:
                        txt += f" • {notes}"
                else:
                    txt = f"Versão instalada: v{APP_VERSION} • Canal: {self._program_update_channel_label()}"
                self.program_update_available_var.set(txt)
            btn = self.program_update_install_btn
            if btn is not None:
                rel = self.available_program_update
                if rel and _is_newer_version(rel.get("version")) and not self.program_update_download_running:
                    btn.state(["!disabled"])
                else:
                    btn.state(["disabled"])
        except tk.TclError:
            pass

    def program_update_configure_server(self):
        current = str((self.program_update_settings or {}).get("manifest_url") or "")
        value = simpledialog.askstring(
            "Servidor de atualização",
            "Cole o endereço HTTPS do arquivo update_manifest.json.\n\n"
            "Essa configuração é feita uma vez e fica salva neste computador.",
            initialvalue=current, parent=self,
        )
        if value is None:
            return
        value = value.strip()
        try:
            if value:
                _validate_update_manifest_url(value)
            self.program_update_settings["manifest_url"] = value
            self.program_update_settings["server_name"] = "Servidor configurado" if value else "Não configurado"
            self.program_update_settings["last_error"] = None
            self.program_update_settings = save_program_update_settings(self.program_update_settings)
            self.available_program_update = None
            self._refresh_program_update_widgets()
            if value:
                self.program_update_check(manual=True)
        except Exception as exc:
            messagebox.showerror("Servidor de atualização", str(exc), parent=self)

    def program_update_check(self, manual=True):
        if self.program_update_check_running:
            if manual:
                self.status.configure(text="Já estou verificando atualizações do programa...")
            return
        url = str((self.program_update_settings or {}).get("manifest_url") or "").strip()
        if not url:
            if manual:
                messagebox.showinfo(
                    "Atualizações do programa",
                    "O mecanismo de atualização já está instalado nesta versão, mas o endereço oficial de publicação ainda não foi configurado.\n\n"
                    "Enquanto terminamos o sistema, você pode usar 'Instalar pacote local...' para testar o atualizador sem mexer nos seus dados.",
                    parent=self,
                )
            return
        self.program_update_check_running = True
        self.program_update_settings["last_error"] = None
        self._refresh_program_update_widgets()
        channel = self.program_update_settings.get("channel", "stable")

        def worker():
            try:
                manifest = _fetch_json_url(url)
                release = _release_from_manifest(manifest, channel=channel, manifest_url=url)
                result = (True, release, None)
            except Exception as exc:
                result = (False, None, str(exc))
            self.sync_queue.put(("program_update_check_done", result, manual))

        threading.Thread(target=worker, daemon=True).start()

    def _program_update_check_done(self, result, manual):
        ok, release, error = result
        self.program_update_check_running = False
        self.program_update_settings["last_check_at"] = datetime.now().isoformat(timespec="seconds")
        self.program_update_settings["last_error"] = error
        if ok:
            self.available_program_update = release if _is_newer_version(release.get("version")) else None
            self.program_update_settings["last_available_version"] = release.get("version")
        self.program_update_settings = save_program_update_settings(self.program_update_settings)
        self._refresh_program_update_widgets()
        if not ok:
            if manual:
                messagebox.showerror("Atualizações do programa", f"Não foi possível verificar.\n\n{error}", parent=self)
            return
        if self.available_program_update:
            self.status.configure(text=f"Atualização v{release['version']} disponível.")
            if manual:
                messagebox.showinfo(
                    "Nova versão disponível",
                    f"Versão instalada: v{APP_VERSION}\nNova versão: v{release['version']}\n\n"
                    f"{str(release.get('notes') or 'Abra Configurações para baixar e instalar.')}",
                    parent=self,
                )
        elif manual:
            messagebox.showinfo(
                "Atualizações do programa",
                f"Você já está na versão mais recente do canal {self._program_update_channel_label()}: v{APP_VERSION}.",
                parent=self,
            )

    def _program_update_install_dir(self):
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return ROOT

    def _program_update_updater_command(self):
        install_dir = self._program_update_install_dir()
        if getattr(sys, "frozen", False):
            updater = install_dir / PROGRAM_UPDATE_UPDATER_EXE
            if not updater.is_file():
                raise FileNotFoundError(
                    f"{PROGRAM_UPDATE_UPDATER_EXE} não foi encontrado ao lado da Central."
                )
            return [str(updater)]
        script = ROOT / "gph_updater.py"
        if not script.is_file():
            raise FileNotFoundError("gph_updater.py não encontrado para o teste local.")
        return [sys.executable, str(script)]

    def _program_update_latest_backup(self):
        try:
            items = sorted(PROGRAM_UPDATE_BACKUP_DIR.glob("GP-H_backup_programa_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
            return items[0] if items else None
        except Exception:
            return None

    def program_update_install_available(self):
        rel = self.available_program_update
        if not rel or not _is_newer_version(rel.get("version")):
            messagebox.showinfo("Atualizações", "Nenhuma atualização nova está pronta para instalar.", parent=self)
            return
        if self.program_update_download_running:
            return
        if self._has_unsaved_draft():
            messagebox.showwarning(
                "Salve o jogo antes de atualizar",
                "Existe " + self._draft_description() + ". Salve ou descarte o rascunho antes de instalar uma atualização.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Baixar e instalar atualização?",
            f"Atualizar de v{APP_VERSION} para v{rel['version']}?\n\n"
            "A Central será fechada durante a instalação. Histórico, Bilhetes e Financeiro ficam na pasta de dados e não são substituídos.",
            parent=self,
        ):
            return
        self.program_update_download_running = True
        self._refresh_program_update_widgets()
        self.status.configure(text=f"Baixando atualização v{rel['version']}...")
        dest = PROGRAM_UPDATE_DOWNLOAD_DIR / f"GP-H_update_v{rel['version']}.zip"

        def worker():
            try:
                used_url = _download_update_file(
                    [rel.get("url")] + list(rel.get("mirrors") or []), dest, timeout=60
                )
                actual = _sha256_file(dest)
                if actual != rel["sha256"]:
                    raise ValueError("O arquivo baixado falhou na verificação SHA-256 e não será instalado.")
                meta = _read_local_update_package(dest)
                if str(meta.get("version")) != str(rel.get("version")):
                    raise ValueError("A versão interna do pacote não corresponde ao manifesto.")
                result = (True, dest, actual, None)
            except Exception as exc:
                try:
                    dest.unlink(missing_ok=True)
                except Exception:
                    pass
                result = (False, None, None, str(exc))
            self.sync_queue.put(("program_update_download_done", result, rel))

        threading.Thread(target=worker, daemon=True).start()

    def _program_update_download_done(self, result, rel):
        self.program_update_download_running = False
        ok, package, sha, error = result
        self._refresh_program_update_widgets()
        if not ok:
            messagebox.showerror("Atualização", f"Não foi possível preparar a instalação.\n\n{error}", parent=self)
            return
        self._launch_program_updater_install(package, sha, rel.get("version"))

    def program_update_install_local_package(self):
        if self._has_unsaved_draft():
            messagebox.showwarning("Atualização", "Salve ou descarte o rascunho atual antes de atualizar.", parent=self)
            return
        path = filedialog.askopenfilename(
            title="Selecionar pacote de atualização GP-H",
            filetypes=[("Pacote GP-H", "*.zip"), ("Todos os arquivos", "*.*")],
            parent=self,
        )
        if not path:
            return
        try:
            meta = _read_local_update_package(path)
            version = str(meta.get("version") or "")
            sha = _sha256_file(path)
            if not _is_newer_version(version):
                if not messagebox.askyesno(
                    "Pacote local",
                    f"O pacote é v{version} e a Central instalada é v{APP_VERSION}.\n\nInstalar mesmo assim?",
                    parent=self,
                ):
                    return
            else:
                if not messagebox.askyesno(
                    "Pacote local",
                    f"Instalar a atualização local v{version}?\n\nA Central será fechada e a versão atual será salva para rollback.",
                    parent=self,
                ):
                    return
            self._launch_program_updater_install(Path(path), sha, version)
        except Exception as exc:
            messagebox.showerror("Pacote local", f"Pacote inválido.\n\n{exc}", parent=self)

    def _launch_program_updater_install(self, package, sha, version):
        try:
            cmd = self._program_update_updater_command()
            install_dir = self._program_update_install_dir()
            main_exe = Path(sys.executable).name if getattr(sys, "frozen", False) else PROGRAM_UPDATE_MAIN_EXE
            cmd += [
                "--install",
                "--package", str(Path(package).resolve()),
                "--install-dir", str(install_dir),
                "--backup-dir", str(PROGRAM_UPDATE_BACKUP_DIR),
                "--expected-sha256", str(sha),
                "--current-version", APP_VERSION,
                "--pid", str(os.getpid()),
                "--main-exe", main_exe,
                "--log", str(PROGRAM_UPDATE_LOG_PATH),
            ]
            subprocess.Popen(cmd, cwd=str(install_dir), close_fds=(os.name != "nt"))
            self.program_update_settings["pending_version"] = str(version)
            self.program_update_settings = save_program_update_settings(self.program_update_settings)
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Atualizador", f"Não foi possível iniciar o atualizador.\n\n{exc}", parent=self)

    def program_update_rollback(self):
        backup = self._program_update_latest_backup()
        if not backup:
            messagebox.showinfo("Restaurar versão anterior", "Ainda não existe backup de uma atualização do programa.", parent=self)
            return
        if self._has_unsaved_draft():
            messagebox.showwarning("Restaurar versão", "Salve ou descarte o rascunho atual antes de restaurar.", parent=self)
            return
        if not messagebox.askyesno(
            "Restaurar versão anterior?",
            f"Será restaurado:\n{backup.name}\n\nA Central será fechada. Seus dados não serão alterados.",
            parent=self,
        ):
            return
        try:
            cmd = self._program_update_updater_command()
            install_dir = self._program_update_install_dir()
            main_exe = Path(sys.executable).name if getattr(sys, "frozen", False) else PROGRAM_UPDATE_MAIN_EXE
            cmd += [
                "--rollback", "--backup", str(backup),
                "--install-dir", str(install_dir),
                "--pid", str(os.getpid()),
                "--main-exe", main_exe,
                "--log", str(PROGRAM_UPDATE_LOG_PATH),
            ]
            subprocess.Popen(cmd, cwd=str(install_dir), close_fds=(os.name != "nt"))
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Restaurar versão", str(exc), parent=self)

    def program_update_open_folder(self):
        self._open_folder(PROGRAM_UPDATE_DIR, "Atualizações do programa")

    def _latest_auto_backup(self):
        try:
            files = sorted(
                AUTO_BACKUP_DIR.glob("GP-H_auto_*.db"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            return files[0] if files else None
        except Exception:
            return None

    def _open_folder(self, path, title="Pasta"):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", str(path)])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showinfo(title, f"A pasta está em:\n{path}\n\n{exc}", parent=self)

    def base_open_log_folder(self):
        self._open_folder(LOG_DIR, "Pasta de logs")

    def base_copy_diagnostics(self):
        latest = self._latest_auto_backup()
        latest_txt = str(latest) if latest else "Nenhum backup automático encontrado"
        text = (
            f"{APP_NAME} v{APP_VERSION}\n"
            f"Banco: {DB_PATH}\n"
            f"Dados: {DATA_DIR}\n"
            f"Logs: {LOG_DIR}\n"
            f"Último backup automático: {latest_txt}\n"
            f"Tema: {self.theme_name}\n"
            f"Bichos: {self.animal_pack_name}\n"
            f"Perfil: {(self.account_profile or {}).get('profile_name', '—')}\n"
            f"Código: {(self.account_profile or {}).get('profile_code', '—')}\n"
            f"Este PC: {(self.account_profile or {}).get('device_name', '—')}\n"
            f"Sync ativo: {bool((self.account_profile or {}).get('sync_enabled'))}\n"
            f"Pasta sync: {(self.account_profile or {}).get('sync_folder', '—')}\n"
            f"Última sync: {(self.account_profile or {}).get('last_sync_at', '—')}\n"
            f"Canal de atualização: {self._program_update_channel_label()}\n"
            f"Manifesto de atualização: {(self.program_update_settings or {}).get('manifest_url') or 'ainda não configurado'}\n"
            f"Python: {sys.version.split()[0]}\n"
            f"Executável: {sys.executable}"
        )
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.status.configure(text="Diagnóstico copiado para a área de transferência.")

    def _show_about(self):
        latest = self._latest_auto_backup()
        latest_txt = "Nenhum ainda"
        if latest:
            try:
                latest_txt = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            except Exception:
                latest_txt = latest.name
        text = (
            f"{APP_NAME}\nVersão {APP_VERSION}\n\n"
            "Central local para histórico, estudos, geração, bilhetes e acompanhamento financeiro do GP-H.\n\n"
            f"Banco ativo:\n{DB_PATH}\n\n"
            f"Pasta de dados:\n{DATA_DIR}\n\n"
            f"Último backup automático: {latest_txt}\n"
            f"Tema: {self.theme_name}\n"
            f"Pacote de bichos: {self.animal_pack_name}\n"
            f"Perfil: {(self.account_profile or {}).get('profile_name', '—')}\n"
            f"Código: {(self.account_profile or {}).get('profile_code', '—')}\n"
            f"Este PC: {(self.account_profile or {}).get('device_name', '—')}\n"
            f"Sincronização: {'ativa' if (self.account_profile or {}).get('sync_enabled') else 'somente local'}\n"
            f"Última sincronização: {(self.account_profile or {}).get('last_sync_at') or 'nunca'}\n\n"
            "Atualizações recentes:\n"
            "• v0.35.1 — Busca/atualização de resultados passa a reler somente os últimos 7 dias, em vez de 30.\n"
            "• v0.36.0 — Decisão incorpora o Laboratório Sombra e o rolamento inteligente vira padrão global de interface.\n"
            "• v0.35.3 — Recomendação da Rodada explica desempenho do horário, convergência atual e Seca do 1º.\n"
            "• v0.35.0 — Laboratório Sombra visível, coleta prospectiva automática após novos resultados e painel separado para Puxadas/Seca 1º.\n"
            "• v0.34.1 — versão de teste da primeira publicação real pelo GitHub; métodos e fórmulas permanecem inalterados.\n"
            "• v0.34.0 — cliente de atualização pronto para servidor HTTPS estático, URLs relativas, espelhos e configuração do servidor.\n"
            "• v0.32.0 — fundação do atualizador do programa: canais Estável/Teste, download verificado, backup e rollback.\n"
            "• v0.33.0 — Home reorganizada: 25 bichos com grupo/dezenas, último resultado vertical, atrasos ampliados e indicadores diários no Financeiro.\n• v0.31.0 — polimento de Jogar/Bilhetes, recomendação única, seleção visual consistente e pacote Natural dos 25 bichos.\n"
            "• v0.30.0 — Laboratório Sombra, Recomendação da Rodada, Puxadas de Bicho e Seca exclusiva do 1º prêmio.\n"
            "• v0.29.0 — Simulador Walk-Forward histórico sem look-ahead, comparação pareada e exportação CSV.\n"
            "• v0.28.0 — Central de Decisão Etapa 2: horário/dia, Campeão × Desafiante, tendência e concentração dos jogos.\n"
            "• v0.27.1 — sincronização automática silenciosa, sem reset visual, perda de scroll ou palpites em montagem.\n"
            "• v0.27.0 — Central de Decisão, confiança transparente e congelamento prospectivo das previsões.\n"
            "• v0.26.1 — sincronização real entre PCs por pasta compartilhada, preservando banco local em cada computador.\n"
            "• v0.25.9 — polimento de usabilidade: rolagem inteligente, ações responsivas e textos longos sem esconder botões.\n"
            "• v0.25.8 — máximo de 4 palpites por coluna, ajuste automático de fonte e botão Copiar palpites.\n"
            "• v0.25.7 — rolagem completa na tela Jogar e grade de palpites sem corte.\n"
            "• v0.25.6 — preparação para EXE, diagnóstico, logs e fechamento seguro.\n"
            "• v0.25.5 — colocação destravada, exportação de Estatísticas e guia dos métodos.\n"
            "• v0.25.4 — revisão da biblioteca visual de bichos."
        )
        messagebox.showinfo("Sobre a Central", text, parent=self)

    def _maximize_main_window(self):
        """Inicia a janela principal maximizada sem depender de resolução fixa."""
        try:
            # Windows/Tk: forma nativa e mais confiável.
            self.state("zoomed")
            return
        except tk.TclError:
            pass
        try:
            # Fallback usado por alguns gerenciadores de janela.
            self.attributes("-zoomed", True)
        except (tk.TclError, TypeError):
            pass

    def _load_visual_assets(self):
        """Carrega identidade visual, ícones e os pacotes de bichos."""
        self.animal_pack_images = {}
        self.animal_images_tiny = {}
        self.animal_images_small = {}
        self.animal_images_medium = {}
        self.animal_images_large = {}
        self.nav_icon_images = {}
        self.nav_icon_active_images = {}
        self.logo_sidebar = None
        self.app_icon = None

        animal_slugs = {
            1:"avestruz",2:"aguia",3:"burro",4:"borboleta",5:"cachorro",
            6:"cabra",7:"carneiro",8:"camelo",9:"cobra",10:"coelho",
            11:"cavalo",12:"elefante",13:"galo",14:"gato",15:"jacare",
            16:"leao",17:"macaco",18:"porco",19:"pavao",20:"peru",
            21:"touro",22:"tigre",23:"urso",24:"veado",25:"vaca",
        }

        # Todos os pacotes são carregados uma única vez. Isso permite mostrar
        # prévias e trocar de conjunto imediatamente sem acessar a internet.
        for pack_name, folder_name in ANIMAL_PACKS.items():
            pack = {"large": {}, "medium": {}, "small": {}, "tiny": {}}
            folder = ANIMAL_PACK_DIR / folder_name
            for grupo, slug in animal_slugs.items():
                path = folder / f"{grupo:02d}_{slug}.png"
                # Compatibilidade com instalações antigas: o pacote principal
                # pode recorrer à antiga pasta assets/bichos se algum asset faltar.
                if not path.is_file() and pack_name == "Cartoon Elegante":
                    path = ANIMAL_ASSET_DIR / f"{grupo:02d}_{slug}.png"
                if path.is_file():
                    try:
                        src = tk.PhotoImage(file=str(path))
                        pack["large"][grupo] = src.subsample(2, 2)
                        pack["medium"][grupo] = src.subsample(3, 3)
                        pack["small"][grupo] = src.subsample(4, 4)
                        pack["tiny"][grupo] = src.subsample(8, 8)
                    except tk.TclError:
                        pass
            self.animal_pack_images[pack_name] = pack

        self._activate_animal_pack(self.animal_pack_name)

        for key in ("home","ticket","results","search","statistics","pulls","methods","generator","database","animals"):
            normal = ICON_ASSET_DIR / f"{key}.png"
            active = ICON_ASSET_DIR / f"{key}_active.png"
            try:
                if normal.is_file():
                    self.nav_icon_images[key] = tk.PhotoImage(file=str(normal))
                if active.is_file():
                    self.nav_icon_active_images[key] = tk.PhotoImage(file=str(active))
            except tk.TclError:
                pass

        try:
            logo = LOGO_ASSET_DIR / "gph_logo_sidebar.png"
            if logo.is_file():
                self.logo_sidebar = tk.PhotoImage(file=str(logo))
            icon = LOGO_ASSET_DIR / "gph_icon.png"
            if icon.is_file():
                src = tk.PhotoImage(file=str(icon))
                self.app_icon = src.subsample(4, 4)
        except tk.TclError:
            self.logo_sidebar = None
            self.app_icon = None

    def _activate_animal_pack(self, pack_name):
        pack = self.animal_pack_images.get(pack_name) or self.animal_pack_images.get("Cartoon Elegante", {})
        self.animal_images_large = pack.get("large", {})
        self.animal_images_medium = pack.get("medium", {})
        self.animal_images_small = pack.get("small", {})
        self.animal_images_tiny = pack.get("tiny", {})

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        c = self.colors
        bg, card, card2 = c["bg"], c["card"], c["card2"]
        text, muted, border = c["text"], c["muted"], c["border"]
        accent, accent_hover = c["accent"], c["accent_hover"]

        style.configure("TFrame", background=bg)
        style.configure("Card.TFrame", background=card)
        style.configure("Toolbar.TFrame", background=card2)
        style.configure("TLabel", background=bg, foreground=text, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=bg, foreground=text, font=("Segoe UI Semibold", 17))
        style.configure("Sub.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=card, foreground=text, font=("Segoe UI", 9))
        style.configure("CardMuted.TLabel", background=card, foreground=muted, font=("Segoe UI", 8))
        style.configure("Section.TLabel", background=card, foreground=text, font=("Segoe UI Semibold", 11))
        style.configure("Kpi.TLabel", background=card, foreground=text, font=("Segoe UI Semibold", 15))
        style.configure("KpiCaption.TLabel", background=card, foreground=muted, font=("Segoe UI", 8))
        style.configure("Success.TLabel", background=card, foreground=c["success"], font=("Segoe UI Semibold", 10))
        style.configure("Danger.TLabel", background=card, foreground=c["danger"], font=("Segoe UI Semibold", 10))

        style.configure(
            "TButton", font=("Segoe UI Semibold", 9), padding=(10, 6),
            background=card2, foreground=text, bordercolor=border,
            focusthickness=1, focuscolor=accent, relief="flat",
        )
        style.map(
            "TButton",
            background=[("active", c["hover"]), ("pressed", c["band"])],
            foreground=[("disabled", muted), ("!disabled", text)],
        )
        style.configure(
            "Accent.TButton", font=("Segoe UI Semibold", 9), padding=(12, 7),
            background=accent, foreground="#FFFFFF", bordercolor=accent, relief="flat",
        )
        style.map(
            "Accent.TButton",
            background=[("active", accent_hover), ("pressed", accent), ("!disabled", accent)],
            foreground=[("!disabled", "#FFFFFF")],
        )
        style.configure("Quiet.TButton", font=("Segoe UI", 9), padding=(9, 5), background=card2, foreground=muted, bordercolor=border)
        style.map("Quiet.TButton", background=[("active", c["hover"])])

        # Abas internas: a seleção acompanha a paleta ativa em toda a Central.
        style.configure(
            "Subnav.TButton", font=("Segoe UI Semibold", 9), padding=(11, 6),
            background=card2, foreground=text, bordercolor=border, relief="flat",
        )
        style.map(
            "Subnav.TButton",
            background=[("active", c["hover"]), ("pressed", c["band"])],
            foreground=[("!disabled", text)],
        )
        style.configure(
            "SubnavActive.TButton", font=("Segoe UI Semibold", 9), padding=(11, 6),
            background=c["selection"], foreground=text, bordercolor=accent, relief="flat",
        )
        style.map(
            "SubnavActive.TButton",
            background=[("active", c["selection"]), ("pressed", c["selection"]), ("!disabled", c["selection"])],
            foreground=[("!disabled", text)],
        )
        style.configure(
            "Recommendation.TLabel", background=card, foreground=text,
            font=("Segoe UI Semibold", 11),
        )

        style.configure(
            "Treeview", font=("Segoe UI", 8), rowheight=25,
            background=c["tree"], fieldbackground=c["tree"], foreground=text,
            bordercolor=border, lightcolor=border, darkcolor=border,
        )
        style.map("Treeview", background=[("selected", c["selection"])], foreground=[("selected", text)])
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 8), background=card2, foreground=text, relief="flat")
        style.map("Treeview.Heading", background=[("active", c["hover"])])

        style.configure("TEntry", padding=5, fieldbackground=c["entry"], foreground=text, insertcolor=text, bordercolor=border)
        style.configure("TCombobox", padding=4, fieldbackground=c["entry"], background=card2, foreground=text, arrowcolor=muted, bordercolor=border)
        style.map("TCombobox", fieldbackground=[("readonly", c["entry"])], foreground=[("readonly", text)], selectbackground=[("readonly", c["selection"])])
        style.configure("TSpinbox", padding=4, fieldbackground=c["entry"], foreground=text, arrowcolor=muted, bordercolor=border)
        style.configure("TCheckbutton", font=("Segoe UI", 8), background=bg, foreground=text)
        style.configure("TScrollbar", background=card2, troughcolor=bg, bordercolor=bg, arrowcolor=muted, darkcolor=card2, lightcolor=card2)
        style.map("TScrollbar", background=[("active", c["hover"]), ("pressed", accent)])

    def _set_theme(self, theme_name):
        if theme_name not in THEME_PALETTES:
            return
        previous_page = getattr(self, "_page", None)
        self.theme_name = theme_name
        self.colors = dict(THEME_PALETTES[theme_name])
        self.visual_settings["theme"] = theme_name
        save_visual_settings(self.visual_settings)
        self.configure(bg=self.colors["bg"])
        # Recria apenas a camada visual. Banco, jogos e métodos permanecem intactos.
        for child in self.winfo_children():
            child.destroy()
        self._build_style()
        self._build_ui()
        # A troca de aparência acontece em Configurações; não jogar o usuário de volta à Home.
        if previous_page == "base":
            self.show_base_config()
        self.status.configure(text=f"Tema aplicado: {theme_name}.")

    def _theme_changed(self, _event=None):
        value = self.theme_var.get().strip()
        if value and value != self.theme_name:
            self._set_theme(value)

    def _set_animal_pack(self, pack_name):
        if pack_name not in ANIMAL_PACKS:
            return
        previous_page = getattr(self, "_page", None)
        self.animal_pack_name = pack_name
        self.visual_settings["animal_pack"] = pack_name
        save_visual_settings(self.visual_settings)
        self._activate_animal_pack(pack_name)

        # Recria apenas widgets visuais para que Home, resultados e tooltips
        # passem a usar o novo pacote imediatamente.
        for child in self.winfo_children():
            child.destroy()
        self._build_style()
        self._build_ui()
        if previous_page == "base":
            self.show_base_config()
        elif previous_page == "home_animals":
            self.show_home_animals()
        elif previous_page == "home":
            self.show_home()
        self.status.configure(text=f"Pacote dos bichos aplicado: {pack_name}.")

    def _show_animal_pack_preview(self, pack_name):
        """Abre uma prévia grande 5x5 do pacote sem alterar a seleção atual."""
        if pack_name not in ANIMAL_PACKS:
            return
        pop = tk.Toplevel(self)
        pop.title(f"Prévia — {pack_name}")
        pop.geometry("820x700")
        pop.minsize(720, 620)
        try:
            self.update_idletasks()
            px = self.winfo_rootx() + max(0, (self.winfo_width() - 820) // 2)
            py = self.winfo_rooty() + max(0, (self.winfo_height() - 700) // 2)
            pop.geometry(f"820x700+{px}+{py}")
        except tk.TclError:
            pass
        pop.transient(self)
        pop.configure(bg=self.colors["bg"])

        outer = ttk.Frame(self._make_scrollable_page_body(pop, "animal_pack_preview"), padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=pack_name, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Os 25 bichos do pacote, no tamanho em que ficam fáceis de comparar.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        grid = tk.Frame(outer, bg=self.colors["bg"])
        grid.pack(fill="both", expand=True)
        pack = self.animal_pack_images.get(pack_name, {}).get("medium", {})
        animal_names = {
            1:"AVESTRUZ",2:"ÁGUIA",3:"BURRO",4:"BORBOLETA",5:"CACHORRO",
            6:"CABRA",7:"CARNEIRO",8:"CAMELO",9:"COBRA",10:"COELHO",
            11:"CAVALO",12:"ELEFANTE",13:"GALO",14:"GATO",15:"JACARÉ",
            16:"LEÃO",17:"MACACO",18:"PORCO",19:"PAVÃO",20:"PERU",
            21:"TOURO",22:"TIGRE",23:"URSO",24:"VEADO",25:"VACA",
        }
        for col in range(5):
            grid.grid_columnconfigure(col, weight=1, uniform="packpreview")
        for row in range(5):
            grid.grid_rowconfigure(row, weight=1, uniform="packpreview")

        for grupo in range(1, 26):
            card = tk.Frame(
                grid, bg=self.colors["card2"],
                highlightbackground=self.colors["border"], highlightthickness=1, bd=0,
            )
            card.grid(row=(grupo-1)//5, column=(grupo-1)%5, sticky="nsew", padx=4, pady=4)
            img = pack.get(grupo)
            if img is not None:
                tk.Label(card, image=img, bg=self.colors["card2"], bd=0).pack(pady=(5, 1))
            tk.Label(
                card, text=f"{grupo:02d} · {animal_names[grupo]}",
                bg=self.colors["card2"], fg=self.colors["text"],
                font=("Segoe UI Semibold", 8),
            ).pack(pady=(0, 5))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Fechar", command=pop.destroy, style="Quiet.TButton").pack(side="right")
        if pack_name != self.animal_pack_name:
            ttk.Button(
                actions, text="USAR ESTE PACOTE",
                command=lambda: (pop.destroy(), self._set_animal_pack(pack_name)),
                style="Accent.TButton",
            ).pack(side="right", padx=(0, 8))

    def _build_ui(self):
        self._page = None
        self._hover_popup = None
        self._hover_after_id = None
        self._install_smart_scroll_policy()

        shell = ttk.Frame(self)
        shell.pack(fill="both", expand=True)

        # Menu lateral fixo
        self.sidebar = tk.Frame(shell, bg=self.colors["sidebar"], width=190)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Área principal
        right = ttk.Frame(shell)
        right.pack(side="left", fill="both", expand=True)

        self.content = ttk.Frame(right, padding=(14, 11))
        self.content.pack(fill="both", expand=True)

        status_bar = ttk.Frame(right, padding=(18, 4, 18, 8))
        status_bar.pack(fill="x")
        self.status = ttk.Label(status_bar, text="Pronto.", style="Sub.TLabel")
        self.status.pack(side="left")
        self.account_status = ttk.Label(
            status_bar, text=self._account_status_text(), style="Sub.TLabel"
        )
        self.account_status.pack(side="right")

        if self.logo_sidebar is not None:
            tk.Label(
                self.sidebar, image=self.logo_sidebar, bg=self.colors["sidebar"], bd=0
            ).pack(anchor="w", padx=9, pady=(17, 2))
        else:
            tk.Label(
                self.sidebar, text="GP-H", bg=self.colors["sidebar"], fg=self.colors["text"],
                font=("Segoe UI Semibold", 19), anchor="w",
            ).pack(fill="x", padx=18, pady=(18, 0))

        tk.Label(
            self.sidebar,
            text=f"v{APP_VERSION}  •  CENTRAL HISTÓRICA",
            bg=self.colors["sidebar"],
            fg=self.colors["muted"],
            font=("Segoe UI Semibold", 7),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 15))

        self.nav_buttons = {}
        self.nav_button_icon_keys = {}

        # Uso diário primeiro; estudos ficam em um segundo bloco.
        for label, command, icon_key in [
            ("Início", self.show_home, "home"),
            ("Jogar", self.show_play_page, "ticket"),
            ("Decisão", self.show_decision_page, "methods"),
            ("Resultados", self.show_results, "results"),
        ]:
            self._add_nav_button(label, command, icon_key=icon_key)

        tk.Frame(self.sidebar, bg=self.colors["divider"], height=1).pack(
            fill="x", padx=14, pady=12
        )

        for label, command, icon_key in [
            ("Pesquisa", self.show_search, "search"),
            ("Estatísticas", self.show_statistics_page, "statistics"),
            ("Puxadas", self.show_pulls_page, "pulls"),
            ("Métodos", self.show_methods_page, "methods"),
            ("Gerador", self.show_generator_page, "generator"),
        ]:
            self._add_nav_button(label, command, secondary=True, icon_key=icon_key)

        tk.Frame(self.sidebar, bg=self.colors["divider"], height=1).pack(
            fill="x", padx=14, pady=12
        )

        self._add_nav_button(
            "Base / Configurações", self.show_base_config, secondary=True, icon_key="database"
        )

        tk.Label(
            self.sidebar,
            text="Operação • Estudos • Histórico",
            bg=self.colors["sidebar"],
            fg=self.colors["muted"],
            font=("Segoe UI", 8),
        ).pack(side="bottom", pady=14)

        self._update_results_nav_badge()
        self.show_home()

    def _add_nav_button(self, label, command, secondary=False, icon_key=None):
        img = self.nav_icon_images.get(icon_key) if icon_key else None
        btn = tk.Button(
            self.sidebar,
            text=label,
            image=img if img else "",
            compound="left",
            command=command,
            bg=self.colors["sidebar"],
            fg=self.colors["muted"] if secondary else self.colors["text"],
            activebackground=self.colors["hover"],
            activeforeground=self.colors["text"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["sidebar"],
            highlightcolor=self.colors["accent"],
            anchor="w",
            padx=16,
            pady=7,
            font=("Segoe UI", 9 if secondary else 10),
            cursor="hand2",
        )
        btn.pack(fill="x", padx=7, pady=1)
        self.nav_buttons[label] = btn
        self.nav_button_icon_keys[label] = icon_key

    def _update_results_nav_badge(self):
        if not hasattr(self, "nav_buttons"):
            return

        btn = self.nav_buttons.get("Resultados")
        if not btn:
            return

        pending = self.db.pending_game_count()
        btn.configure(
            text=(
                f"Resultados  • {pending}"
                if pending
                else "Resultados"
            )
        )

    def _set_active_nav(self, label):
        for name, btn in self.nav_buttons.items():
            active = name == label
            btn.configure(
                bg=self.colors["selection"] if active else self.colors["sidebar"],
                fg=self.colors["text"] if active else (
                    self.colors["text"] if name in ("Início", "Jogar", "Decisão", "Resultados") else self.colors["muted"]
                ),
                highlightbackground=self.colors["accent"] if active else self.colors["sidebar"],
                highlightcolor=self.colors["accent"],
            )
            key = self.nav_button_icon_keys.get(name)
            if key:
                img = (self.nav_icon_active_images if active else self.nav_icon_images).get(key)
                if img is not None:
                    btn.configure(image=img)

    def _clear_content(self):
        self._hide_animal_hover()
        for child in self.content.winfo_children():
            child.destroy()

    def _page_title(self, title, subtitle=""):
        ttk.Label(
            self.content,
            text=title,
            style="Title.TLabel",
        ).pack(anchor="w")
        if subtitle:
            ttk.Label(
                self.content,
                text=subtitle,
                style="Sub.TLabel",
                wraplength=1040,
            ).pack(anchor="w", pady=(3, 14))

    def _make_scrollable_page_body(self, parent, key):
        """Área vertical rolável: roda funciona sob qualquer filho e a barra só aparece quando necessária."""
        host = ttk.Frame(parent)
        host.pack(fill="both", expand=True)
        canvas = tk.Canvas(
            host, highlightthickness=0, borderwidth=0, bg=self.colors["bg"]
        )
        bar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

        body = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas._gph_smart_scroll = True
        if not hasattr(self, "_smart_scroll_canvases"):
            self._smart_scroll_canvases = {}
        self._smart_scroll_canvases[key] = canvas

        def update_bar():
            try:
                bbox = canvas.bbox("all")
                content_h = (bbox[3] - bbox[1]) if bbox else 0
                need = content_h > max(1, canvas.winfo_height()) + 2
                managed = bool(bar.winfo_manager())
                if need and not managed:
                    bar.pack(side="right", fill="y")
                elif not need and managed:
                    bar.pack_forget()
            except tk.TclError:
                pass

        def update_region(_event=None):
            try:
                bbox = canvas.bbox("all")
                if bbox:
                    canvas.configure(scrollregion=bbox)
                update_bar()
            except tk.TclError:
                pass

        def resize_body(event):
            try:
                canvas.itemconfigure(window, width=max(1, int(event.width)))
                self.after_idle(update_region)
            except tk.TclError:
                pass

        body.bind("<Configure>", update_region, add="+")
        canvas.bind("<Configure>", resize_body, add="+")

        tag = f"GPHScroll_{key}"

        def route_wheel(event):
            units = self._wheel_units(event)
            if not units:
                return
            if self._play_scroll_child_if_possible(event.widget, units):
                return "break"
            try:
                first, last = canvas.yview()
                can_scroll = (units < 0 and first > 0.0) or (units > 0 and last < 1.0)
                if can_scroll:
                    canvas.yview_scroll(units, "units")
                # Sempre consome a roda dentro da página para não alterar Combobox/Spinbox por acidente.
                return "break"
            except tk.TclError:
                return

        self.bind_class(tag, "<MouseWheel>", route_wheel)
        self.bind_class(tag, "<Button-4>", route_wheel)
        self.bind_class(tag, "<Button-5>", route_wheel)

        def install_tags():
            try:
                stack = [host]
                while stack:
                    widget = stack.pop()
                    tags = list(widget.bindtags())
                    if tag not in tags:
                        tags.insert(1 if len(tags) > 1 else 0, tag)
                        widget.bindtags(tuple(tags))
                    stack.extend(widget.winfo_children())
            except tk.TclError:
                pass
            update_region()

        self.after_idle(install_tags)
        return body

    def _install_smart_scroll_policy(self):
        """Padrão global: toda tela/janela atual ou futura recebe roteamento inteligente da roda."""
        tag = "GPHSmartWheel"
        self._smart_scroll_tag = tag
        if not getattr(self, "_smart_scroll_policy_installed", False):
            self.bind_class(tag, "<MouseWheel>", self._smart_scroll_route, add="+")
            self.bind_class(tag, "<Button-4>", self._smart_scroll_route, add="+")
            self.bind_class(tag, "<Button-5>", self._smart_scroll_route, add="+")
            self.bind_all("<Map>", self._smart_scroll_on_map, add="+")
            self._smart_scroll_policy_installed = True
        self.after_idle(lambda: self._smart_scroll_install_tags(self))

    def _smart_scroll_install_tags(self, root):
        tag = getattr(self, "_smart_scroll_tag", "GPHSmartWheel")
        try:
            stack = [root]
            while stack:
                widget = stack.pop()
                try:
                    tags = list(widget.bindtags())
                    if tag not in tags:
                        tags.insert(1 if len(tags) > 1 else 0, tag)
                        widget.bindtags(tuple(tags))
                    stack.extend(widget.winfo_children())
                except tk.TclError:
                    continue
        except Exception:
            pass

    def _smart_scroll_on_map(self, event):
        try:
            self._smart_scroll_install_tags(event.widget)
        except Exception:
            pass

    @staticmethod
    def _smart_scroll_can_move(widget, units):
        try:
            first, last = widget.yview()
            return (units < 0 and first > 0.0) or (units > 0 and last < 1.0)
        except Exception:
            return False

    def _smart_scroll_find_candidate(self, root, units, skip=None):
        candidates = []
        try:
            stack = list(root.winfo_children())
            while stack:
                widget = stack.pop()
                try:
                    stack.extend(widget.winfo_children())
                    if widget is skip or not widget.winfo_ismapped():
                        continue
                    cls = widget.winfo_class()
                    if cls not in {"Treeview", "Text", "Listbox", "Canvas"}:
                        continue
                    if not self._smart_scroll_can_move(widget, units):
                        continue
                    priority = {"Treeview": 4, "Text": 3, "Listbox": 3, "Canvas": 2}.get(cls, 1)
                    area = max(1, widget.winfo_width()) * max(1, widget.winfo_height())
                    candidates.append((priority, area, widget))
                except Exception:
                    continue
        except Exception:
            return None
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][2]

    def _smart_scroll_route(self, event):
        units = self._wheel_units(event)
        if not units:
            return
        widget = getattr(event, "widget", None)
        if widget is None:
            return

        # Controles que têm conteúdo próprio rolável recebem prioridade.
        if self._play_scroll_child_if_possible(widget, units):
            return "break"

        # Depois procura um Canvas rolável na cadeia de pais: é a página/janela atual.
        current = widget
        visited = set()
        while current is not None and current not in visited:
            visited.add(current)
            try:
                if current.winfo_class() == "Canvas" and self._smart_scroll_can_move(current, units):
                    current.yview_scroll(units, "units")
                    return "break"
                parent_name = current.winfo_parent()
                if not parent_name:
                    break
                current = current._nametowidget(parent_name)
            except Exception:
                break

        # Em diálogos antigos sem Canvas externo, rola o principal Text/Tree/Listbox disponível.
        try:
            top = widget.winfo_toplevel()
        except Exception:
            top = None
        if top is not None:
            candidate = self._smart_scroll_find_candidate(top, units, skip=widget)
            if candidate is not None:
                try:
                    candidate.yview_scroll(units, "units")
                    return "break"
                except Exception:
                    pass

        # Evita que a roda altere valores de seleção quando não há conteúdo para rolar.
        try:
            if widget.winfo_class() in {"TCombobox", "TSpinbox", "Spinbox"}:
                return "break"
        except Exception:
            pass
        return

    def _bind_wraplength(self, label, container, margin=18, minimum=180, maximum=None):
        """Mantém textos longos dentro do cartão sem empurrar botões/vizinhos."""
        def _resize(event):
            try:
                width = max(int(minimum), int(event.width) - int(margin))
                if maximum is not None:
                    width = min(width, int(maximum))
                label.configure(wraplength=width)
            except Exception:
                pass
        container.bind("<Configure>", _resize, add="+")

    def show_home(self):
        self._set_active_nav("Início")
        self._clear_content()
        self._page = "home"
        body = self._make_scrollable_page_body(self.content, "home")

        summary = self.db.home_summary()
        delays = self.db.delay_leaders()
        latest = summary["latest"]
        operational = self.db.latest_operational_draw()
        next_target = self.db.next_operational_target()
        pending_target_games = (
            self.db.pending_operational_games_for_target(next_target)
            if next_target else []
        )

        # v0.33: Home reorganizada em duas áreas. Os 25 bichos voltam a ser
        # protagonistas, com cartões quase quadrados; o painel operacional fica
        # à direita. Os indicadores financeiros saíram daqui e vivem no Financeiro.
        header = ttk.Frame(body)
        header.pack(fill="x", pady=(0, 5))
        ttk.Label(
            header,
            text="Visão geral",
            style="Title.TLabel",
            font=("Segoe UI Semibold", 16),
        ).pack(side="left")
        ttk.Label(
            header,
            text=f'{summary["draws"]:,}'.replace(",", ".") + " extrações na base",
            style="Sub.TLabel",
            font=("Segoe UI", 8),
        ).pack(side="right", anchor="e")

        main = ttk.Frame(body)
        main.pack(fill="both", expand=True)
        main.grid_columnconfigure(0, weight=59, uniform="homecols")
        main.grid_columnconfigure(1, weight=41, uniform="homecols")
        main.grid_rowconfigure(0, weight=1)

        # ------------------------------------------------------------------
        # ESQUERDA — 25 bichos, sempre com Grupo + Nome + 4 dezenas visíveis.
        animals_panel = ttk.Frame(main, style="Card.TFrame", padding=(7, 6))
        animals_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        animal_header = ttk.Frame(animals_panel, style="Card.TFrame")
        animal_header.pack(fill="x", pady=(0, 4))
        ttk.Label(
            animal_header,
            text="OS 25 BICHOS",
            style="Section.TLabel",
            font=("Segoe UI Semibold", 12),
        ).pack(side="left")
        ttk.Label(
            animal_header,
            text="Grupo • Bicho • 4 dezenas",
            style="CardMuted.TLabel",
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(8, 0))

        grid = tk.Frame(animals_panel, bg=self.colors["card"])
        grid.pack(fill="both", expand=True)
        self.home_grid = grid
        self.home_cards = []
        for row in range(5):
            grid.grid_rowconfigure(row, weight=1, uniform="animalrows", minsize=82)
        for col in range(5):
            grid.grid_columnconfigure(col, weight=1, uniform="animalcols", minsize=94)

        for idx, info in enumerate(self.db.home_animal_cards()):
            row = idx // 5
            col = idx % 5
            card = self._make_animal_card(grid, info, compact=True)
            card.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
            self.home_cards.append(card)

        # ------------------------------------------------------------------
        # DIREITA — próxima rodada, último resultado vertical e atrasos atuais.
        side = ttk.Frame(main)
        side.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        side.grid_columnconfigure(0, weight=1)

        # Próxima rodada + atualização dos RESULTADOS no mesmo cartão.
        hero = ttk.Frame(side, style="Card.TFrame", padding=(11, 8))
        hero.pack(fill="x", pady=(0, 6))

        ttk.Label(
            hero,
            text="PRÓXIMA RODADA",
            style="CardMuted.TLabel",
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w")

        if next_target:
            target_date = datetime.strptime(next_target["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            target_main = f"{next_target['sorteio']} {next_target['hora']}  •  {target_date}"
        else:
            target_main = "Ainda não identificada"

        ttk.Label(
            hero,
            text=target_main,
            style="Card.TLabel",
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w", pady=(1, 1))

        if operational:
            op_date = datetime.strptime(operational["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            base_text = f"Base: {operational['sorteio']} {operational['hora']} • {op_date}"
        else:
            base_text = "Base: —"

        pending_text = (
            f"{len(pending_target_games)} jogo(s) aguardando"
            if pending_target_games else "Nenhum jogo congelado"
        )
        ttk.Label(
            hero,
            text=f"{base_text}   •   {pending_text}",
            style="CardMuted.TLabel",
            font=("Segoe UI", 8),
        ).pack(anchor="w")

        hero_actions = ttk.Frame(hero, style="Card.TFrame")
        hero_actions.pack(fill="x", pady=(7, 0))
        ttk.Button(
            hero_actions,
            text="JOGAR AGORA",
            style="Accent.TButton",
            command=self.show_play_page,
        ).pack(side="left")
        ttk.Button(
            hero_actions,
            text="Buscar atualização",
            command=self.start_update_search,
        ).pack(side="left", padx=(5, 0))
        ttk.Button(
            hero_actions,
            text="Resultados",
            command=self.show_results,
        ).pack(side="right")

        # Último resultado — destaque maior e leitura VERTICAL, prêmio por prêmio.
        latest_card = tk.Frame(
            side,
            bg=self.colors["card"],
            highlightbackground=self.colors["accent"],
            highlightthickness=1,
            bd=0,
            padx=10,
            pady=8,
        )
        latest_card.pack(fill="both", expand=True, pady=(0, 6))

        latest_head = tk.Frame(latest_card, bg=self.colors["card"])
        latest_head.pack(fill="x", pady=(0, 5))
        tk.Label(
            latest_head,
            text="ÚLTIMO RESULTADO",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 12),
        ).pack(side="left")
        if latest:
            d = datetime.strptime(latest["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            tk.Label(
                latest_head,
                text=f"{d} • {latest['sorteio']} {latest['hora']}",
                bg=self.colors["card"],
                fg=self.colors["muted"],
                font=("Segoe UI", 8),
            ).pack(side="right")

            prizes_box = tk.Frame(latest_card, bg=self.colors["card"])
            prizes_box.pack(fill="both", expand=True)
            for p in latest["prizes"]:
                row = tk.Frame(
                    prizes_box,
                    bg=self.colors["card2"],
                    highlightbackground=self.colors["border"],
                    highlightthickness=1,
                    bd=0,
                    padx=7,
                    pady=3,
                )
                row.pack(fill="both", expand=True, pady=(0, 3))

                prize_badge = tk.Label(
                    row,
                    text=f"{p['premio']}º",
                    bg=self.colors["accent"],
                    fg="#FFFFFF",
                    font=("Segoe UI Semibold", 9),
                    width=3,
                    padx=2,
                    pady=2,
                )
                prize_badge.pack(side="left", padx=(0, 7))

                tiny = self.animal_images_tiny.get(p["grupo"])
                if tiny is not None:
                    tk.Label(row, image=tiny, bg=self.colors["card2"], bd=0).pack(side="left", padx=(0, 7))

                ident = tk.Frame(row, bg=self.colors["card2"])
                ident.pack(side="left", fill="x", expand=True)
                tk.Label(
                    ident,
                    text=f"{p['bicho']}  •  Grupo {p['grupo']:02d}",
                    bg=self.colors["card2"],
                    fg=self.colors["text"],
                    font=("Segoe UI Semibold", 9),
                    anchor="w",
                ).pack(fill="x")
                tk.Label(
                    ident,
                    text=f"Centena {p['centena']}  •  Dezena {p['dezena']}",
                    bg=self.colors["card2"],
                    fg=self.colors["muted"],
                    font=("Segoe UI", 7),
                    anchor="w",
                ).pack(fill="x")

                tk.Label(
                    row,
                    text=p["milhar"],
                    bg=self.colors["card2"],
                    fg=self.colors["accent"],
                    font=("Consolas", 17, "bold"),
                    anchor="e",
                ).pack(side="right", padx=(8, 2))
        else:
            tk.Label(
                latest_card,
                text="Base ainda vazia.",
                bg=self.colors["card"],
                fg=self.colors["muted"],
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=(3, 0))

        # Atrasos atuais — mais legíveis, abaixo do último resultado.
        delay_card = ttk.Frame(side, style="Card.TFrame", padding=(10, 7))
        delay_card.pack(fill="x")
        delay_head = ttk.Frame(delay_card, style="Card.TFrame")
        delay_head.pack(fill="x", pady=(0, 5))
        ttk.Label(
            delay_head,
            text="ATRASOS ATUAIS",
            style="Section.TLabel",
            font=("Segoe UI Semibold", 11),
        ).pack(side="left")
        ttk.Label(
            delay_head,
            text="extrações desde a última aparição",
            style="CardMuted.TLabel",
            font=("Segoe UI", 7),
        ).pack(side="right")

        def _delay_text(field, caption):
            item = delays.get(field)
            if not item:
                return "—", "—", "Sem dados suficientes na base."
            raw = item["value"]
            if field == "bicho":
                shown = BICHOS.get(int(raw), str(raw))
            else:
                shown = str(raw).zfill(3 if field == "centena" else 2)
            plural = "extração" if item["delay"] == 1 else "extrações"
            tie = f" +{item['tie_count'] - 1} emp." if item["tie_count"] > 1 else ""
            delay_value = f"{item['delay']} {plural}{tie}"
            last = item["last"]
            d = datetime.strptime(last["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            tied_values = []
            for v in item["ties"][:6]:
                if field == "bicho":
                    tied_values.append(BICHOS.get(int(v), str(v)))
                else:
                    tied_values.append(str(v).zfill(3 if field == "centena" else 2))
            tie_detail = ""
            if item["tie_count"] > 1:
                rest = item["tie_count"] - len(tied_values)
                tie_detail = "\nEmpate: " + ", ".join(tied_values) + (f" +{rest}" if rest > 0 else "")
            tip = (
                f"{caption}: {shown}\n"
                f"{item['delay']} {plural} sem aparecer\n"
                f"Última: {d} • {last['sorteio']} {last['hora']} • "
                f"{last['premio']}º prêmio • Milhar {last['milhar']}" + tie_detail
            )
            return shown, delay_value, tip

        delays_row = ttk.Frame(delay_card, style="Card.TFrame")
        delays_row.pack(fill="x")
        for idx, (field, caption) in enumerate((("bicho", "Bicho"), ("centena", "Centena"), ("dezena", "Dezena"))):
            shown, delay_value, tip = _delay_text(field, caption)
            box = tk.Frame(
                delays_row,
                bg=self.colors["card2"],
                highlightbackground=self.colors["border"],
                highlightthickness=1,
                bd=0,
                padx=6,
                pady=5,
            )
            box.pack(side="left", fill="x", expand=True, padx=(0, 4 if idx < 2 else 0))
            cap = tk.Label(
                box,
                text=caption,
                bg=self.colors["card2"],
                fg=self.colors["muted"],
                font=("Segoe UI", 7),
            )
            cap.pack(anchor="w")
            val = tk.Label(
                box,
                text=shown,
                bg=self.colors["card2"],
                fg=self.colors["text"],
                font=("Segoe UI Semibold", 10),
            )
            val.pack(anchor="w")
            delay_lab = tk.Label(
                box,
                text=delay_value,
                bg=self.colors["card2"],
                fg=self.colors["accent"],
                font=("Segoe UI Semibold", 7),
            )
            delay_lab.pack(anchor="w")
            for widget in (box, cap, val, delay_lab):
                self._bind_delay_tooltip(widget, tip)

    def show_home_animals(self):
        """Painel dedicado: preserva a grade 5x5 sem poluir a abertura."""
        self._set_active_nav("Início")
        self._clear_content()
        self._page = "home_animals"
        body = self._make_scrollable_page_body(self.content, "home_animals")

        header = ttk.Frame(body)
        header.pack(fill="x", pady=(0, 8))
        left = ttk.Frame(header)
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text="Os 25 bichos", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            left,
            text="Passe o mouse para a última ocorrência; clique no cartão para abrir os detalhes.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Button(header, text="← Voltar ao Início", command=self.show_home).pack(side="right")

        grid = tk.Frame(body, bg=self.colors["bg"])
        grid.pack(fill="both", expand=True)
        self.home_grid = grid
        self.home_cards = []
        for row in range(5):
            grid.grid_rowconfigure(row, weight=1, uniform="animalrows")
        for col in range(5):
            grid.grid_columnconfigure(col, weight=1, uniform="animalcols")

        for idx, info in enumerate(self.db.home_animal_cards()):
            row = idx // 5
            col = idx % 5
            card = self._make_animal_card(grid, info)
            card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            self.home_cards.append(card)

    def home_prepare_next_game(self):
        try:
            target = self.db.next_operational_target()
            if not target:
                raise ValueError(
                    "Não foi possível determinar a próxima rodada operacional."
                )

            self.show_generator_page()
            self.gen_source.set("Método oficial — Reset")
            self.gen_num_animals.set("5")
            self.gen_kind.set("Centena")
            self.gen_strategy.set("Oficial 3+1")
            self.gen_scope.set("1º–5º")
            self.gen_total.set("20")

            self.generator_refresh_control_states()
            self.generator_generate()

            target_date = datetime.strptime(
                target["data"], "%Y-%m-%d"
            ).strftime("%d/%m/%Y")

            self.status.configure(
                text=(
                    f"Próximo jogo preparado para "
                    f"{target['sorteio']} {target['hora']} • {target_date}. "
                    "Confira e congele quando estiver satisfeito."
                )
            )
        except Exception as exc:
            messagebox.showerror(
                "Preparar próximo jogo",
                str(exc),
                parent=self,
            )

    def _make_animal_card(self, parent, info, compact=False):
        """Cartão v0.25: imagem dominante + faixa inferior com grupo/nome/dezenas."""
        card_bg = self.colors["card"]
        band_bg = self.colors["band"]
        card = tk.Frame(
            parent,
            bg=card_bg,
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            bd=0,
            cursor="hand2",
        )

        visual = tk.Frame(card, bg=card_bg, bd=0)
        visual.pack(fill="both", expand=True)
        image = self.animal_images_medium.get(info["grupo"]) if compact else self.animal_images_large.get(info["grupo"])
        if image is not None:
            animal = tk.Label(visual, image=image, bg=card_bg, bd=0)
        else:
            animal = tk.Label(
                visual, text=BICHO_ICONS.get(info["grupo"], "●"), bg=card_bg, fg=self.colors["text"],
                font=("Segoe UI Emoji", 24 if compact else 30), bd=0,
            )
        animal.pack(expand=True, pady=(1 if compact else 3, 0))

        band = tk.Frame(card, bg=band_bg, bd=0)
        band.pack(fill="x", side="bottom")
        title = tk.Label(
            band,
            text=f"{info['grupo']:02d} · {info['bicho']}",
            bg=band_bg, fg=self.colors["text"],
            font=("Segoe UI Semibold", 7 if compact else 9),
            anchor="center",
        )
        title.pack(fill="x", pady=(2, 0))
        dezenas = tk.Label(
            band,
            text="  ".join(info["dezenas"]),
            bg=band_bg, fg=self.colors["accent"],
            font=("Segoe UI Semibold", 7 if compact else 8),
            anchor="center",
        )
        dezenas.pack(fill="x", pady=(0, 2 if compact else 3))

        def enter(_event):
            self._cancel_hover_hide()
            card.configure(highlightbackground=self.colors["accent_hover"], highlightthickness=1, bg=self.colors["hover"])
            visual.configure(bg=self.colors["hover"])
            animal.configure(bg=self.colors["hover"])
            self._show_animal_hover(card, info)

        def leave(_event):
            card.configure(highlightbackground=self.colors["border"], bg=card_bg)
            visual.configure(bg=card_bg)
            animal.configure(bg=card_bg)
            self._schedule_hover_hide()

        def click(_event):
            self._hide_animal_hover()
            AnimalQuickDetailsDialog(self, self.db, info["grupo"])

        for widget in (card, visual, animal, band, title, dezenas):
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)
            widget.bind("<Button-1>", click)

        return card

    def _set_card_bg(self, card, bg):
        try:
            card.configure(bg=bg)
            for child in card.winfo_children():
                try:
                    child.configure(bg=bg)
                except tk.TclError:
                    pass
        except tk.TclError:
            pass

    def _cancel_hover_hide(self):
        if self._hover_after_id:
            try:
                self.after_cancel(self._hover_after_id)
            except Exception:
                pass
            self._hover_after_id = None

    def _schedule_hover_hide(self):
        self._cancel_hover_hide()
        self._hover_after_id = self.after(120, self._hide_animal_hover)

    def _show_animal_hover(self, widget, info):
        self._hide_animal_hover()

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)

        frame = tk.Frame(
            popup,
            bg=self.colors["tooltip"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        frame.pack()

        hover_head = tk.Frame(frame, bg=self.colors["tooltip"])
        hover_head.pack(fill="x")
        hover_img = self.animal_images_small.get(info["grupo"])
        if hover_img is not None:
            tk.Label(hover_head, image=hover_img, bg=self.colors["tooltip"], bd=0).pack(side="left", padx=(0, 6))
        tk.Label(
            hover_head,
            text=f"{info['bicho']} • Grupo {info['grupo']:02d}",
            bg=self.colors["tooltip"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 9),
        ).pack(side="left", anchor="w")

        last = info["ultima"]
        if last:
            d = datetime.strptime(last["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            details = (
                f"Última milhar: {last['milhar']}\n"
                f"{d} • {last['sorteio']} {last['hora']} • {last['premio']}º prêmio"
            )
        else:
            details = "Sem ocorrência na base."

        tk.Label(
            frame,
            text=details,
            bg=self.colors["tooltip"],
            fg=self.colors["muted"],
            justify="left",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(4, 0))

        # Mede o tooltip antes de decidir em qual lado colocá-lo.
        popup.update_idletasks()
        popup_w = popup.winfo_reqwidth()
        popup_h = popup.winfo_reqheight()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        card_x = widget.winfo_rootx()
        card_y = widget.winfo_rooty()
        card_w = widget.winfo_width()

        margin = 8

        # Preferência: abrir à direita.
        x = card_x + card_w + margin

        # Se não couber, abre à esquerda do cartão.
        if x + popup_w > screen_w - margin:
            x = card_x - popup_w - margin

        # Proteção final para telas pequenas / janela próxima às bordas.
        x = max(margin, min(x, screen_w - popup_w - margin))

        y = card_y
        if y + popup_h > screen_h - margin:
            y = screen_h - popup_h - margin
        y = max(margin, y)

        popup.geometry(f"+{int(x)}+{int(y)}")

        popup.bind("<Enter>", lambda e: self._cancel_hover_hide())
        popup.bind("<Leave>", lambda e: self._schedule_hover_hide())
        self._hover_popup = popup

    def _hide_animal_hover(self):
        self._cancel_hover_hide()
        if self._hover_popup is not None:
            try:
                self._hover_popup.destroy()
            except Exception:
                pass
            self._hover_popup = None

    def _bind_delay_tooltip(self, widget, text):
        """Tooltip compacto para indicadores de atraso; respeita as bordas da tela."""
        state = {"popup": None}

        def hide(_event=None):
            pop = state.get("popup")
            if pop is not None:
                try:
                    pop.destroy()
                except Exception:
                    pass
                state["popup"] = None

        def show(_event=None):
            hide()
            pop = tk.Toplevel(self)
            pop.overrideredirect(True)
            pop.attributes("-topmost", True)
            frame = tk.Frame(
                pop,
                bg=self.colors["tooltip"],
                highlightbackground=self.colors["border"],
                highlightthickness=1,
                padx=9,
                pady=7,
            )
            frame.pack()
            tk.Label(
                frame,
                text=text,
                bg=self.colors["tooltip"],
                fg=self.colors["text"],
                justify="left",
                font=("Segoe UI", 8),
            ).pack(anchor="w")
            pop.update_idletasks()
            pw, ph = pop.winfo_reqwidth(), pop.winfo_reqheight()
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            margin = 8
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height() + 5
            if x + pw > sw - margin:
                x = sw - pw - margin
            if y + ph > sh - margin:
                y = widget.winfo_rooty() - ph - 5
            x = max(margin, x)
            y = max(margin, y)
            pop.geometry(f"+{int(x)}+{int(y)}")
            state["popup"] = pop

        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", hide, add="+")

    def show_search(self):
        self._set_active_nav("Pesquisa")
        self._clear_content()
        self._page = "search"

        self._page_title(
            "Pesquisa",
            "Bicho, Grupo, Dezena, Centena e Milhar com filtros inteligentes.",
        )
        body = self._make_scrollable_page_body(self.content, "search")

        self.var_type = tk.StringVar(value="Todos")
        self.var_value = tk.StringVar()
        self.var_date = tk.StringVar()
        self.var_from = tk.StringVar()
        self.var_to = tk.StringVar()
        self.var_draw = tk.StringVar(value="Todos")
        self.var_prize = tk.StringVar(value="Todos")

        filt = ttk.Frame(body, style="Card.TFrame", padding=10)
        filt.pack(fill="x", pady=(0, 8))

        ttk.Label(filt, text="Pesquisar por", style="Card.TLabel").grid(row=0,column=0,sticky="w",padx=(0,8))
        ttk.Combobox(
            filt, textvariable=self.var_type,
            values=["Todos","Bicho","Grupo","Dezena","Centena","Milhar"],
            width=12, state="readonly"
        ).grid(row=1,column=0,sticky="w",padx=(0,8),pady=(3,0))

        ttk.Label(filt, text="Valor", style="Card.TLabel").grid(row=0,column=1,sticky="w",padx=(0,8))
        ttk.Entry(filt,textvariable=self.var_value,width=16).grid(row=1,column=1,sticky="w",padx=(0,8),pady=(3,0))

        ttk.Label(filt, text="Data", style="Card.TLabel").grid(row=0,column=2,sticky="w",padx=(0,8))
        CalendarField(filt,self.var_date,width=10,on_change=self.on_exact_date_changed).grid(row=1,column=2,sticky="w",padx=(0,8),pady=(3,0))

        ttk.Label(filt, text="De", style="Card.TLabel").grid(row=0,column=3,sticky="w",padx=(0,8))
        CalendarField(filt,self.var_from,width=10,on_change=self.on_range_date_changed).grid(row=1,column=3,sticky="w",padx=(0,8),pady=(3,0))

        ttk.Label(filt, text="Até", style="Card.TLabel").grid(row=0,column=4,sticky="w",padx=(0,8))
        CalendarField(filt,self.var_to,width=10,on_change=self.on_range_date_changed).grid(row=1,column=4,sticky="w",padx=(0,8),pady=(3,0))

        ttk.Label(filt, text="Sorteio / Hora", style="Card.TLabel").grid(row=0,column=5,sticky="w",padx=(0,8))
        self.cb_draw = ttk.Combobox(
            filt, textvariable=self.var_draw, width=18, state="readonly"
        )
        self.cb_draw.grid(row=1,column=5,sticky="w",padx=(0,8),pady=(3,0))

        ttk.Label(filt, text="Prêmio", style="Card.TLabel").grid(row=0,column=6,sticky="w")
        ttk.Combobox(
            filt,textvariable=self.var_prize,
            values=["Todos","1","2","3","4","5"],
            width=7,state="readonly"
        ).grid(row=1,column=6,sticky="w",pady=(3,0))

        buttons = ttk.Frame(filt, style="Card.TFrame")
        buttons.grid(row=2,column=0,columnspan=7,sticky="w",pady=(8,0))
        ttk.Button(buttons,text="Pesquisar",style="Accent.TButton",command=self.search).pack(side="left")
        ttk.Button(buttons,text="Limpar",command=self.clear_filters).pack(side="left",padx=(7,0))
        ttk.Label(
            buttons,
            text="Sorteio/Hora mostra somente combinações reais do período.",
            style="Card.TLabel"
        ).pack(side="left",padx=(12,0))

        self.summary = tk.Text(
            body,
            height=4,
            bg=self.colors["card"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
            wrap="word",
        )
        self.summary.pack(fill="x", pady=(0, 8))
        self.summary.configure(state="disabled")

        table_frame = ttk.Frame(body)
        table_frame.pack(fill="both", expand=True)

        cols = ("data","sorteio","hora","premio","milhar","centena","dezena","grupo","bicho")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        labels = {
            "data":"Data","sorteio":"Sorteio","hora":"Hora","premio":"Prêmio",
            "milhar":"Milhar","centena":"Centena","dezena":"Dezena","grupo":"Grupo","bicho":"Bicho"
        }
        widths = {
            "data":95,"sorteio":85,"hora":65,"premio":65,"milhar":75,
            "centena":75,"dezena":65,"grupo":65,"bicho":110
        }

        for c in cols:
            self.tree.heading(c, text=labels[c])
            self.tree.column(c, width=widths[c], anchor="center" if c != "bicho" else "w")

        y = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.tree.grid(row=0,column=0,sticky="nsew")
        y.grid(row=0,column=1,sticky="ns")
        x.grid(row=1,column=0,sticky="ew")
        table_frame.rowconfigure(0,weight=1)
        table_frame.columnconfigure(0,weight=1)

        footer = ttk.Frame(body, padding=(0,8,0,0))
        footer.pack(fill="x")
        ttk.Button(footer,text="Exportar CSV",command=self.export_csv).pack(side="right")

        self.refresh_filters()
        self.search()


    def _csv_text(self, value, width=None):
        """
        Exporta como texto reconhecível pelo Excel, preservando zeros à esquerda.
        CSV não possui tipo de célula; por isso usamos uma fórmula de texto segura
        (="...") em todos os campos exportados.
        """
        if value is None:
            value = ""
        text = str(value)
        if width is not None and text.isdigit():
            text = text.zfill(int(width))
        text = text.replace('"', '""')
        return f'="{text}"'

    def _money(self, value):
        if value is None:
            return "—"
        try:
            value = float(value)
        except Exception:
            return "—"
        text = f"{value:,.2f}"
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {text}"

    def _parse_money(self, text):
        value = str(text or "").strip()
        if not value:
            return 0.0
        value = value.replace("R$", "").replace(" ", "")
        if "," in value:
            value = value.replace(".", "").replace(",", ".")
        return float(value)

    def _format_target(self, target):
        if not target:
            return "Alvo ainda não identificado"

        d = datetime.strptime(
            target["data"], "%Y-%m-%d"
        ).strftime("%d/%m/%Y")

        if target.get("whole_day"):
            return f"{d} • dia inteiro • somente 1º prêmio"

        return (
            f"{d} • {target.get('sorteio') or '—'} "
            f"{target.get('hora') or ''}"
        ).strip()

    def show_play_page(self):
        self._set_active_nav("Jogar")
        self._clear_content()
        self._page = "play"
        self.play_view = "new"
        self.play_generation = None
        self.play_generation_groups = []

        if not hasattr(self, "play_ticket_draft"):
            self.play_ticket_draft = []

        self._page_title(
            "Jogar",
            "Monte a aposta por etapas: rodada, jogo, valor e bilhete.",
        )

        switch = ttk.Frame(self.content)
        switch.pack(fill="x", pady=(0, 9))
        self.play_nav_buttons = {}

        for key, text, command in (
            ("new", "Nova aposta", self.play_show_new),
            ("manual_builder", "Jogo manual", self.play_show_manual_builder),
            ("games", "Bilhetes", self.play_show_games),
            ("summary", "Financeiro", self.play_show_summary),
        ):
            btn = ttk.Button(
                switch, text=text, style="Subnav.TButton", command=command
            )
            btn.pack(side="left", padx=(0 if key == "new" else 5, 0))
            self.play_nav_buttons[key] = btn
        ttk.Button(
            switch,
            text="Cotações",
            command=self.play_open_payout_config,
        ).pack(side="right")

        # Área principal da tela Jogar com rolagem vertical.
        # A quantidade de palpites pode crescer bastante; sem rolagem,
        # as últimas linhas e o Bilhete em montagem ficavam fora da tela.
        self.play_scroll_host = ttk.Frame(self.content)
        self.play_scroll_host.pack(fill="both", expand=True)

        self.play_body_canvas = tk.Canvas(
            self.play_scroll_host,
            highlightthickness=0,
            borderwidth=0,
            bg=self.colors["bg"],
        )
        self.play_body_scrollbar = ttk.Scrollbar(
            self.play_scroll_host,
            orient="vertical",
            command=self.play_body_canvas.yview,
        )
        self.play_body_canvas.configure(
            yscrollcommand=self.play_body_scrollbar.set
        )
        self.play_body_canvas.pack(side="left", fill="both", expand=True)
        self.play_body_scrollbar.pack(side="right", fill="y")

        self.play_body = ttk.Frame(self.play_body_canvas)
        self._play_body_window = self.play_body_canvas.create_window(
            (0, 0),
            window=self.play_body,
            anchor="nw",
        )
        self.play_body.bind(
            "<Configure>", self._play_update_scrollregion
        )
        self.play_body_canvas.bind(
            "<Configure>", self._play_resize_body_window
        )

        # A roda do mouse é roteada por um bindtag próprio, instalado nos
        # controles da página. Isso faz a rolagem responder sob labels,
        # botões, entradas e comboboxes sem exigir clique/foco prévio.
        # Se o ponteiro estiver sobre Treeview/Text/Listbox, o próprio
        # controle rola enquanto puder; ao chegar ao limite, a página assume.
        self._play_wheel_tag = "GPHPlayWheel"
        if not getattr(self, "_play_mousewheel_bound", False):
            self.bind_class(self._play_wheel_tag, "<MouseWheel>", self._play_mousewheel, add="+")
            self.bind_class(self._play_wheel_tag, "<Button-4>", self._play_mousewheel, add="+")
            self.bind_class(self._play_wheel_tag, "<Button-5>", self._play_mousewheel, add="+")
            self._play_mousewheel_bound = True

        self.play_show_new()
        self.after_idle(self._play_finalize_layout)

    def _set_play_subnav_active(self, view):
        """Mantém a aba interna selecionada visível em qualquer paleta."""
        for key, btn in getattr(self, "play_nav_buttons", {}).items():
            try:
                btn.configure(style="SubnavActive.TButton" if key == view else "Subnav.TButton")
            except tk.TclError:
                pass

    def _play_install_wheel_bindtag(self, root):
        tag = getattr(self, "_play_wheel_tag", "GPHPlayWheel")
        try:
            stack = [root]
            while stack:
                widget = stack.pop()
                try:
                    tags = list(widget.bindtags())
                    if tag not in tags:
                        # Antes do bindtag de classe: evita que Combobox/Spinbox
                        # consumam a roda e alterem valores acidentalmente.
                        tags.insert(1 if len(tags) > 1 else 0, tag)
                        widget.bindtags(tuple(tags))
                    stack.extend(widget.winfo_children())
                except tk.TclError:
                    continue
        except Exception:
            pass

    @staticmethod
    def _wheel_units(event):
        if getattr(event, "num", None) == 4:
            return -3
        if getattr(event, "num", None) == 5:
            return 3
        delta = getattr(event, "delta", 0)
        if not delta:
            return 0
        steps = max(1, abs(int(delta / 120)))
        return -steps if delta > 0 else steps

    def _play_scroll_child_if_possible(self, widget, units):
        try:
            widget_class = widget.winfo_class()
        except Exception:
            return False

        if widget_class not in {"Treeview", "Text", "Listbox"}:
            return False

        try:
            first, last = widget.yview()
            can_scroll = (units < 0 and first > 0.0) or (units > 0 and last < 1.0)
            if not can_scroll:
                return False
            widget.yview_scroll(units, "units")
            return True
        except Exception:
            return False

    def _play_mousewheel(self, event):
        if getattr(self, "_page", None) != "play":
            return

        units = self._wheel_units(event)
        if not units:
            return

        # Primeiro tenta o controle sob o mouse. Se ele não tiver conteúdo
        # rolável (ou já estiver no começo/fim), a rolagem continua na página.
        if self._play_scroll_child_if_possible(event.widget, units):
            return "break"

        canvas = getattr(self, "play_body_canvas", None)
        if canvas is None:
            return

        try:
            first, last = canvas.yview()
            can_scroll = (units < 0 and first > 0.0) or (units > 0 and last < 1.0)
            if not can_scroll:
                return "break"
            canvas.yview_scroll(units, "units")
            return "break"
        except tk.TclError:
            return

    def _play_finalize_layout(self):
        if getattr(self, "_page", None) != "play":
            return
        host = getattr(self, "play_scroll_host", None)
        if host is not None:
            self._play_install_wheel_bindtag(host)
        self._play_update_scrollregion()

    def _play_update_scrollregion(self, _event=None):
        canvas = getattr(self, "play_body_canvas", None)
        if canvas is None:
            return
        try:
            bbox = canvas.bbox("all")
            if bbox:
                canvas.configure(scrollregion=bbox)
        except tk.TclError:
            pass

    def _play_resize_body_window(self, event):
        canvas = getattr(self, "play_body_canvas", None)
        window = getattr(self, "_play_body_window", None)
        if canvas is None or window is None:
            return
        try:
            canvas.itemconfigure(window, width=max(1, event.width))
        except tk.TclError:
            pass

    def _clear_play_body(self):
        for child in self.play_body.winfo_children():
            child.destroy()
        canvas = getattr(self, "play_body_canvas", None)
        if canvas is not None:
            try:
                canvas.yview_moveto(0.0)
            except tk.TclError:
                pass

    def play_show_new(self):
        self.play_view = "new"
        self._set_play_subnav_active("new")
        self._clear_play_body()

        if not hasattr(self, "play_ticket_draft"):
            self.play_ticket_draft = []

        # O motor continua trabalhando com os nomes antigos de modalidade;
        # família/variação são apenas uma camada de interface mais limpa.
        self.play_family = tk.StringVar(value="Centena")
        self.play_variant = tk.StringVar(value="Normal")
        self.play_kind = tk.StringVar(value="Centena")
        self.play_submode = tk.StringVar(value="Milhar")
        self.play_scope = tk.StringVar(value="1º–5º")
        self.play_method = tk.StringVar(value="Oficial • Reset + 3+1")
        self.play_total = tk.StringVar(value="20")
        self.play_value_mode = tk.StringVar(value="Por palpite")
        self.play_stake = tk.StringVar(value="0,20")
        self.play_target_var = tk.StringVar()

        self.play_target_map = {}
        targets = self.db.future_operational_targets(14)
        target_values = []
        for target in targets:
            date_br = datetime.strptime(target["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            label = f"{date_br} • {target['sorteio']} {target['hora']}"
            self.play_target_map[label] = dict(target)
            target_values.append(label)
        if target_values:
            self.play_target_var.set(target_values[0])

        # 1) RODADA
        target_box = ttk.Frame(self.play_body, style="Card.TFrame", padding=(12, 8))
        target_box.pack(fill="x", pady=(0, 6))
        ttk.Label(target_box, text="RODADA", style="CardMuted.TLabel").pack(anchor="w")
        self.play_target_cb = ttk.Combobox(
            target_box,
            textvariable=self.play_target_var,
            values=target_values,
            width=34,
            state="readonly",
        )
        self.play_target_cb.pack(anchor="w", pady=(3, 0))
        self.play_target_cb.bind("<<ComboboxSelected>>", self.play_target_changed)

        self.play_target_hint = ttk.Label(
            target_box, text="", style="CardMuted.TLabel", wraplength=1040, justify="left"
        )
        self.play_target_hint.pack(fill="x", anchor="w", pady=(4, 0))
        self._bind_wraplength(self.play_target_hint, target_box, margin=12, minimum=240)

        # Recomendação prospectiva alimentada pelo Laboratório Sombra.
        # Mostra somente qual leitura tem melhor evidência ANTES da rodada;
        # nunca exibe mensagens retrospectivas do tipo "se tivesse jogado".
        rec_card = ttk.Frame(self.play_body, style="Card.TFrame", padding=(12, 9))
        rec_card.pack(fill="x", pady=(0, 6))
        ttk.Label(rec_card, text="RECOMENDAÇÃO DA RODADA", style="CardMuted.TLabel").pack(anchor="w")
        self.play_recommendation_label = ttk.Label(
            rec_card, text="", style="Recommendation.TLabel", wraplength=1040, justify="left"
        )
        self.play_recommendation_label.pack(fill="x", anchor="w", pady=(4, 0))
        self.play_recommendation_note = ttk.Label(
            rec_card, text="", style="CardMuted.TLabel", wraplength=1040, justify="left"
        )
        self.play_recommendation_note.pack(fill="x", anchor="w", pady=(2, 0))
        self._bind_wraplength(self.play_recommendation_label, rec_card, margin=12, minimum=240)
        self._bind_wraplength(self.play_recommendation_note, rec_card, margin=12, minimum=240)

        # 2) JOGO
        game_card = ttk.Frame(self.play_body, style="Card.TFrame", padding=(12, 10))
        game_card.pack(fill="x", pady=(0, 6))
        ttk.Label(game_card, text="JOGO", style="CardMuted.TLabel").grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 4))

        ttk.Label(game_card, text="Família", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 6))
        self.play_family_cb = ttk.Combobox(
            game_card,
            textvariable=self.play_family,
            values=["Grupo", "Dezena", "Centena", "Milhar"],
            width=12,
            state="readonly",
        )
        self.play_family_cb.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(2, 0))
        self.play_family_cb.bind("<<ComboboxSelected>>", self.play_family_changed)

        ttk.Label(game_card, text="Variação", style="Card.TLabel").grid(row=1, column=1, sticky="w", padx=(0, 6))
        self.play_variant_cb = ttk.Combobox(
            game_card,
            textvariable=self.play_variant,
            width=17,
            state="readonly",
        )
        self.play_variant_cb.grid(row=2, column=1, sticky="w", padx=(0, 8), pady=(2, 0))
        self.play_variant_cb.bind("<<ComboboxSelected>>", self.play_variant_changed)

        self.play_submode_label = ttk.Label(game_card, text="Modalidade", style="Card.TLabel")
        self.play_submode_label.grid(row=1, column=2, sticky="w", padx=(0, 6))
        self.play_submode_cb = ttk.Combobox(
            game_card,
            textvariable=self.play_submode,
            values=["Milhar", "Milhar/Centena"],
            width=15,
            state="disabled",
        )
        self.play_submode_cb.grid(row=2, column=2, sticky="w", padx=(0, 8), pady=(2, 0))
        self.play_submode_cb.bind("<<ComboboxSelected>>", self.play_financial_refresh)

        ttk.Label(game_card, text="Colocação", style="Card.TLabel").grid(row=1, column=3, sticky="w", padx=(0, 6))
        self.play_scope_cb = ttk.Combobox(
            game_card,
            textvariable=self.play_scope,
            values=["1º", "1º–5º"],
            width=9,
            state="readonly",
        )
        self.play_scope_cb.grid(row=2, column=3, sticky="w", padx=(0, 8), pady=(2, 0))
        self.play_scope_cb.bind("<<ComboboxSelected>>", self.play_scope_changed)

        ttk.Label(game_card, text="Método", style="Card.TLabel").grid(row=1, column=4, sticky="w", padx=(0, 6))
        self.play_method_cb = ttk.Combobox(
            game_card,
            textvariable=self.play_method,
            width=31,
            state="readonly",
        )
        self.play_method_cb.grid(row=2, column=4, sticky="ew", padx=(0, 8), pady=(2, 0))
        self.play_method_cb.bind("<<ComboboxSelected>>", self.play_controls_changed)
        game_card.grid_columnconfigure(4, weight=1)

        self.play_method_badge = tk.Label(
            game_card,
            text="OFICIAL",
            bg="#124A7A",
            fg="#DCEEFF",
            font=("Segoe UI Semibold", 8),
            padx=8,
            pady=3,
        )
        self.play_method_badge.grid(row=2, column=5, sticky="w", pady=(2, 0))

        # 3) APOSTA / VALOR
        stake_card = ttk.Frame(self.play_body, style="Card.TFrame", padding=(12, 10))
        stake_card.pack(fill="x", pady=(0, 6))
        ttk.Label(stake_card, text="APOSTA", style="CardMuted.TLabel").grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 4))

        ttk.Label(stake_card, text="Quantidade", style="Card.TLabel").grid(row=1, column=0, sticky="w")
        self.play_total_spin = ttk.Spinbox(stake_card, from_=1, to=100, textvariable=self.play_total, width=8)
        self.play_total_spin.grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(2, 0))

        ttk.Label(stake_card, text="Forma do valor", style="Card.TLabel").grid(row=1, column=1, sticky="w")
        self.play_value_mode_cb = ttk.Combobox(
            stake_card,
            textvariable=self.play_value_mode,
            values=["Por palpite", "Valor total"],
            width=14,
            state="readonly",
        )
        self.play_value_mode_cb.grid(row=2, column=1, sticky="w", padx=(0, 10), pady=(2, 0))
        self.play_value_mode_cb.bind("<<ComboboxSelected>>", self.play_financial_refresh)

        ttk.Label(stake_card, text="Valor", style="Card.TLabel").grid(row=1, column=2, sticky="w")
        self.play_stake_entry = ttk.Entry(stake_card, textvariable=self.play_stake, width=11)
        self.play_stake_entry.grid(row=2, column=2, sticky="w", padx=(0, 12), pady=(2, 0))
        self.play_stake_entry.bind("<KeyRelease>", self.play_financial_refresh)

        self.play_generate_btn = ttk.Button(
            stake_card,
            text="GERAR JOGO",
            style="Accent.TButton",
            command=self.play_generate,
        )
        self.play_generate_btn.grid(row=2, column=3, sticky="w", pady=(2, 0))

        self.play_method_help = ttk.Label(stake_card, text="", style="CardMuted.TLabel", wraplength=650)
        self.play_method_help.grid(row=1, column=4, rowspan=2, sticky="w", padx=(16, 0))
        stake_card.grid_columnconfigure(4, weight=1)

        # 4) PALPITES
        generation_card = ttk.Frame(self.play_body, style="Card.TFrame", padding=(10, 8))
        generation_card.pack(fill="x", pady=(0, 6))

        # Ações ficam em uma faixa própria. Textos financeiros longos nunca
        # empurram ou escondem os botões, mesmo em janela estreita.
        generation_head = ttk.Frame(generation_card, style="Card.TFrame")
        generation_head.pack(fill="x", pady=(0, 3))
        ttk.Label(generation_head, text="Palpites", style="Section.TLabel").pack(side="left")
        generation_actions = ttk.Frame(generation_head, style="Card.TFrame")
        generation_actions.pack(side="right")
        self.play_copy_btn = ttk.Button(
            generation_actions,
            text="Copiar palpites",
            command=self.play_copy_numbers,
            width=17,
        )
        self.play_copy_btn.pack(side="left", padx=(0, 6))
        self.play_add_ticket_btn = ttk.Button(
            generation_actions,
            text="Adicionar ao bilhete",
            style="Accent.TButton",
            command=self.play_add_to_ticket,
            width=20,
        )
        self.play_add_ticket_btn.pack(side="left")

        generation_info = ttk.Frame(generation_card, style="Card.TFrame")
        generation_info.pack(fill="x", pady=(0, 4))
        self.play_financial_label = ttk.Label(
            generation_info, text="", style="Card.TLabel",
            font=("Segoe UI Semibold", 9), wraplength=1040, justify="left",
        )
        self.play_financial_label.pack(fill="x", anchor="w")
        self.play_payout_label = ttk.Label(
            generation_info, text="", style="CardMuted.TLabel",
            wraplength=1040, justify="left",
        )
        self.play_payout_label.pack(fill="x", anchor="w", pady=(1, 0))
        self.play_concentration_label = ttk.Label(
            generation_info, text="", style="CardMuted.TLabel",
            wraplength=1040, justify="left",
        )
        self.play_concentration_label.pack(fill="x", anchor="w", pady=(2, 0))
        self._bind_wraplength(self.play_financial_label, generation_info, margin=12, minimum=240)
        self._bind_wraplength(self.play_payout_label, generation_info, margin=12, minimum=240)
        self._bind_wraplength(self.play_concentration_label, generation_info, margin=12, minimum=240)

        self.play_grid_container = ttk.Frame(generation_card, style="Card.TFrame", padding=3)
        self.play_grid_container.pack(fill="x")
        self.play_grid_container.bind("<Configure>", self._play_grid_container_resized, add="+")
        ttk.Label(
            self.play_grid_container,
            text="Escolha o jogo acima e clique em Gerar jogo.",
            style="CardMuted.TLabel",
        ).pack(pady=10)

        # 5) BILHETE
        ticket = ttk.Frame(self.play_body, style="Card.TFrame", padding=(10, 8))
        ticket.pack(fill="both", expand=True)
        ticket_head = ttk.Frame(ticket, style="Card.TFrame")
        ticket_head.pack(fill="x", pady=(0, 5))
        title_box = ttk.Frame(ticket_head, style="Card.TFrame")
        title_box.pack(fill="x")
        ttk.Label(title_box, text="BILHETE EM MONTAGEM", style="CardMuted.TLabel").pack(anchor="w")
        self.play_ticket_target_label = ttk.Label(
            title_box, text="", style="Section.TLabel", wraplength=980, justify="left"
        )
        self.play_ticket_target_label.pack(anchor="w", pady=(1, 0))
        self.play_ticket_summary_label = ttk.Label(
            title_box, text="", style="Card.TLabel", font=("Segoe UI Semibold", 10),
            wraplength=980, justify="left",
        )
        self.play_ticket_summary_label.pack(anchor="w", pady=(2, 0))
        self._bind_wraplength(self.play_ticket_target_label, title_box, margin=10, minimum=240)
        self._bind_wraplength(self.play_ticket_summary_label, title_box, margin=10, minimum=240)

        ticket_actions = ttk.Frame(ticket_head, style="Card.TFrame")
        ticket_actions.pack(fill="x", pady=(5, 0))
        ttk.Button(ticket_actions, text="Remover", command=self.play_remove_ticket_item).pack(side="right")
        ttk.Button(ticket_actions, text="Limpar", command=self.play_clear_ticket).pack(side="right", padx=(0, 5))
        ttk.Button(
            ticket_actions,
            text="REGISTRAR BILHETE",
            style="Accent.TButton",
            command=self.play_register_ticket,
        ).pack(side="right", padx=(0, 5))
        ttk.Button(
            ticket_actions,
            text="VÁRIOS HORÁRIOS...",
            command=self.play_register_ticket_multi,
        ).pack(side="right", padx=(0, 5))

        cols = ("tipo", "metodo", "qtd", "unit", "total")
        self.play_ticket_tree = ttk.Treeview(ticket, columns=cols, show="headings", height=4, selectmode="browse")
        labels = {"tipo":"Jogo", "metodo":"Método", "qtd":"Qtd.", "unit":"Valor/palpite", "total":"Total"}
        widths = {"tipo":210, "metodo":290, "qtd":55, "unit":100, "total":100}
        for c in cols:
            self.play_ticket_tree.heading(c, text=labels[c])
            self.play_ticket_tree.column(c, width=widths[c], anchor="w" if c in ("tipo", "metodo") else "center")
        self.play_ticket_tree.pack(fill="both", expand=True)

        self.play_family_changed()
        self.play_refresh_ticket()
        self._play_refresh_shadow_recommendation()
        self.after_idle(self._play_finalize_layout)

    def _shadow_freeze_async(self, target, base_draw):
        """Congela o Laboratório Sombra sem atrasar a geração visível do usuário."""
        if not target or not base_draw:
            return
        target_copy = copy.deepcopy(target)
        base_copy = {k: base_draw.get(k) for k in ("data","sorteio","hora")}
        def worker():
            try:
                self.db.ensure_shadow_snapshot(target_copy, base_copy, trigger="GERAR_JOGO")
            except Exception:
                # Laboratório é diagnóstico; nunca pode impedir uma aposta real.
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _shadow_recommendation_current_context(self, target, scope, best_name):
        # Explica a recomendação com sinais atuais sem mudar o vencedor histórico.
        try:
            status = self.db.shadow_lab_status(target)
            current = (status or {}).get("current") or {}
            payload = current.get("payload") or {}
            bpayload = payload.get("bichos") or {}

            method_groups = {}
            support = Counter()
            for method in ("Reset Cobertura", "Puxada Combinada", "Similaridade"):
                rec = bpayload.get(method) or {}
                groups = []
                for value in rec.get("groups") or []:
                    try:
                        group = int(value)
                    except Exception:
                        continue
                    if 1 <= group <= 25 and group not in groups:
                        groups.append(group)
                groups = groups[:5]
                if groups:
                    method_groups[method] = groups
                    support.update(groups)

            parts = []
            available_count = len(method_groups)
            convergent = sorted(
                ((group, count) for group, count in support.items() if count >= 2),
                key=lambda item: (-item[1], item[0]),
            )
            if available_count >= 2:
                if convergent:
                    labels = [
                        f"{BICHOS.get(group, str(group)).title()} {count}/{available_count}"
                        for group, count in convergent[:5]
                    ]
                    parts.append("Convergência atual: " + ", ".join(labels))
                else:
                    parts.append(f"Convergência atual: nenhuma coincidência entre {available_count} métodos")

            method_map = {
                "Reset + Histórica": "Reset Cobertura",
                "Puxada + Histórica": "Puxada Combinada",
                "Similaridade + Histórica": "Similaridade",
            }
            chosen_method = method_map.get(best_name, best_name if best_name in method_groups else None)
            if chosen_method in method_groups and available_count >= 2:
                groups = method_groups[chosen_method]
                shared = [group for group in groups if support.get(group, 0) >= 2]
                parts.append(f"Apoio ao recomendado: {len(shared)}/{len(groups)} bichos reforçados por outro método")

            if str(scope or "") == "1º":
                dry = ((payload.get("seca_1p") or {}).get("Seca do Dia 1º") or {})
                dry_groups = []
                for value in dry.get("groups") or []:
                    try:
                        group = int(value)
                    except Exception:
                        continue
                    if 1 <= group <= 25 and group not in dry_groups:
                        dry_groups.append(group)
                dry_groups = dry_groups[:5]
                if dry_groups:
                    dry_names = ", ".join(BICHOS.get(group, str(group)).title() for group in dry_groups)
                    overlap = [group for group in dry_groups if support.get(group, 0) >= 2]
                    suffix = f" • {len(overlap)} também na convergência" if convergent else ""
                    parts.append(f"Seca 1º atual: {dry_names}{suffix}")

            return " • ".join(parts)
        except Exception:
            return ""

    def _play_refresh_shadow_recommendation(self):
        label = getattr(self, "play_recommendation_label", None)
        note = getattr(self, "play_recommendation_note", None)
        if label is None:
            return
        target = self.play_get_selected_target()
        if not target:
            label.configure(text="Selecione uma rodada para consultar a recomendação.")
            if note is not None:
                note.configure(text="")
            return

        try:
            self.db.audit_shadow_snapshots()
            rec = self.db.shadow_recommendation(target, window=120, scope=self.play_scope.get())
            family = self.play_family.get() if hasattr(self, "play_family") else "Centena"
            scope = self.play_scope.get() if hasattr(self, "play_scope") else "1º–5º"
            rank = {"FORTE": 4, "MODERADA": 3, "BAIXA": 2, "AMOSTRA INSUFICIENTE": 1, "SEM DADOS": 0}
            candidates = []

            # Para Centena, compara as construções de Centenas. Nas demais famílias,
            # usa o seletor de bichos como sinal operacional mais compatível.
            if family == "Centena":
                cent = rec.get("centena") or {}
                best = cent.get("best")
                if best:
                    status = cent.get("status", "SEM DADOS")
                    candidates.append({
                        "name": best.get("name") or "Centenas",
                        "status": status,
                        "rounds": int(best.get("rounds") or 0),
                        "score": rank.get(status, 0),
                        "detail": f"{float(best.get('win_rate') or 0):.1f}% de rodadas com ao menos uma Centena no recorte prospectivo",
                    })
            else:
                bichos = rec.get("bichos") or {}
                best = bichos.get("best")
                if best:
                    status = bichos.get("status", "SEM DADOS")
                    avg = float(best.get("avg_coverage") or 0)
                    candidates.append({
                        "name": best.get("name") or "Bichos",
                        "status": status,
                        "rounds": int(best.get("rounds") or 0),
                        "score": rank.get(status, 0),
                        "detail": (
                            f"{avg*100:.1f}% de acerto do 1º prêmio no recorte"
                            if scope == "1º"
                            else f"cobertura média {avg:.2f}/5 no recorte prospectivo"
                        ),
                    })

            # A Seca só concorre como indicação principal quando o bilhete está no 1º prêmio.
            dry = rec.get("seca_1p") or {}
            if scope == "1º" and int(dry.get("rounds") or 0):
                status = dry.get("status", "SEM DADOS")
                candidates.append({
                    "name": "Seca do Dia 1º",
                    "status": status,
                    "rounds": int(dry.get("rounds") or 0),
                    "score": rank.get(status, 0),
                    "detail": f"{float(dry.get('hit_rate') or 0):.1f}% de acerto do 1º prêmio no recorte prospectivo",
                })

            if not candidates:
                label.configure(text="Ainda não há amostra suficiente para recomendar um método nesta rodada.")
                if note is not None:
                    note.configure(text="A Central continua coletando jogos-sombra antes dos resultados.")
                return

            # Primeiro qualidade da evidência; depois tamanho da amostra.
            candidates.sort(key=lambda c: (-c["score"], -c["rounds"], c["name"]))
            best = candidates[0]
            if best["score"] <= 1:
                label.configure(text="Ainda não há um método claramente superior para esta rodada.")
                if note is not None:
                    note.configure(text=f"Melhor sinal provisório: {best['name']} • {best['rounds']} rodadas. Amostra insuficiente.")
                return

            label.configure(
                text=f"Melhor indicação agora: {best['name']} • evidência {best['status']}"
            )
            if note is not None:
                base_note = f"{best['rounds']} rodadas prospectivas neste horário • {best['detail']}."
                current_context = self._shadow_recommendation_current_context(target, scope, best.get("name"))
                if current_context:
                    base_note += f" • {current_context}."
                base_note += " Evidência histórica, não garantia de acerto."
                note.configure(text=base_note)
        except Exception:
            label.configure(text="Ainda não há amostra suficiente para recomendar um método nesta rodada.")
            if note is not None:
                note.configure(text="A recomendação aparece somente quando existe evidência prospectiva anterior ao resultado.")

    def play_show_manual_builder(self):
        """Montagem de bilhete 100% manual, sem método de seleção."""
        self.play_view = "manual_builder"
        self._set_play_subnav_active("manual_builder")
        self._clear_play_body()

        self.manual_builder_rows = []
        self.manual_family = tk.StringVar(value="Milhar")
        self.manual_variant = tk.StringVar(value="Normal")
        self.manual_kind = tk.StringVar(value="Milhar")
        self.manual_submode = tk.StringVar(value="Milhar")
        self.manual_scope = tk.StringVar(value="1º–5º")
        self.manual_number = tk.StringVar()
        self.manual_value_mode = tk.StringVar(value="Por palpite")
        self.manual_stake = tk.StringVar(value="0,20")
        self.manual_target_var = tk.StringVar()
        self.manual_target_map = {}

        targets = self.db.future_operational_targets(14)
        target_values = []
        for target in targets:
            date_br = datetime.strptime(target["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            label = f"{date_br} • {target['sorteio']} {target['hora']}"
            self.manual_target_map[label] = dict(target)
            target_values.append(label)
        if target_values:
            self.manual_target_var.set(target_values[0])

        target_box = ttk.Frame(self.play_body, style="Card.TFrame", padding=(12, 9))
        target_box.pack(fill="x", pady=(0, 6))
        ttk.Label(target_box, text="RODADA", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        self.manual_target_cb = ttk.Combobox(
            target_box,
            textvariable=self.manual_target_var,
            values=target_values,
            width=31,
            state="readonly",
        )
        self.manual_target_cb.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.manual_target_cb.bind("<<ComboboxSelected>>", self.manual_builder_refresh)
        manual_target_hint = ttk.Label(
            target_box,
            text="Você escolhe os números. Nenhum método do GP-H interfere neste bilhete.",
            style="CardMuted.TLabel", justify="left", wraplength=560,
        )
        manual_target_hint.grid(row=1, column=1, sticky="ew", padx=(16, 0))
        self._bind_wraplength(manual_target_hint, target_box, margin=350, minimum=220, maximum=650)
        target_box.grid_columnconfigure(1, weight=1)

        game_card = ttk.Frame(self.play_body, style="Card.TFrame", padding=(12, 10))
        game_card.pack(fill="x", pady=(0, 6))
        ttk.Label(game_card, text="MODALIDADE MANUAL", style="CardMuted.TLabel").grid(
            row=0, column=0, columnspan=6, sticky="w", pady=(0, 4)
        )

        ttk.Label(game_card, text="Família", style="Card.TLabel").grid(row=1, column=0, sticky="w")
        self.manual_family_cb = ttk.Combobox(
            game_card,
            textvariable=self.manual_family,
            values=["Grupo", "Dezena", "Centena", "Milhar"],
            width=12,
            state="readonly",
        )
        self.manual_family_cb.grid(row=2, column=0, sticky="w", padx=(0, 9), pady=(2, 0))
        self.manual_family_cb.bind("<<ComboboxSelected>>", self.manual_builder_family_changed)

        ttk.Label(game_card, text="Variação", style="Card.TLabel").grid(row=1, column=1, sticky="w")
        self.manual_variant_cb = ttk.Combobox(
            game_card,
            textvariable=self.manual_variant,
            width=17,
            state="readonly",
        )
        self.manual_variant_cb.grid(row=2, column=1, sticky="w", padx=(0, 9), pady=(2, 0))
        self.manual_variant_cb.bind("<<ComboboxSelected>>", self.manual_builder_variant_changed)

        self.manual_submode_label = ttk.Label(game_card, text="Modalidade", style="Card.TLabel")
        self.manual_submode_label.grid(row=1, column=2, sticky="w")
        self.manual_submode_cb = ttk.Combobox(
            game_card,
            textvariable=self.manual_submode,
            values=["Milhar", "Milhar/Centena"],
            width=16,
            state="readonly",
        )
        self.manual_submode_cb.grid(row=2, column=2, sticky="w", padx=(0, 9), pady=(2, 0))
        self.manual_submode_cb.bind("<<ComboboxSelected>>", self.manual_builder_refresh)

        ttk.Label(game_card, text="Colocação", style="Card.TLabel").grid(row=1, column=3, sticky="w")
        self.manual_scope_cb = ttk.Combobox(
            game_card,
            textvariable=self.manual_scope,
            values=["1º", "1º–5º"],
            width=9,
            state="readonly",
        )
        self.manual_scope_cb.grid(row=2, column=3, sticky="w", padx=(0, 9), pady=(2, 0))
        self.manual_scope_cb.bind("<<ComboboxSelected>>", self.manual_builder_refresh)

        self.manual_kind_hint = ttk.Label(game_card, text="", style="CardMuted.TLabel", wraplength=520)
        self.manual_kind_hint.grid(row=1, column=4, rowspan=2, sticky="w", padx=(10, 0))
        game_card.grid_columnconfigure(4, weight=1)

        numbers_card = ttk.Frame(self.play_body, style="Card.TFrame", padding=(12, 10))
        numbers_card.pack(fill="both", expand=True, pady=(0, 6))
        top = ttk.Frame(numbers_card, style="Card.TFrame")
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="SEUS NÚMEROS", style="CardMuted.TLabel").pack(side="left")
        self.manual_count_label = ttk.Label(top, text="0 palpites", style="Card.TLabel")
        self.manual_count_label.pack(side="left", padx=(12, 0))

        entry_line = ttk.Frame(numbers_card, style="Card.TFrame")
        entry_line.pack(fill="x", pady=(0, 6))
        self.manual_number_entry = ttk.Entry(entry_line, textvariable=self.manual_number, width=24)
        self.manual_number_entry.pack(side="left")
        self.manual_number_entry.bind("<Return>", lambda _e: self.manual_builder_add_number())
        ttk.Button(
            entry_line,
            text="ADICIONAR",
            style="Accent.TButton",
            command=self.manual_builder_add_number,
        ).pack(side="left", padx=(6, 0))
        self.manual_add_status = ttk.Label(entry_line, text="", style="CardMuted.TLabel")
        self.manual_add_status.pack(side="left", padx=(12, 0))

        cols = ("ordem", "numero", "detalhe")
        self.manual_numbers_tree = ttk.Treeview(
            numbers_card,
            columns=cols,
            show="headings",
            height=7,
            selectmode="browse",
        )
        self.manual_numbers_tree.heading("ordem", text="#")
        self.manual_numbers_tree.heading("numero", text="Palpite")
        self.manual_numbers_tree.heading("detalhe", text="Grupo / referência")
        self.manual_numbers_tree.column("ordem", width=50, anchor="center")
        self.manual_numbers_tree.column("numero", width=180, anchor="center")
        self.manual_numbers_tree.column("detalhe", width=520, anchor="w")
        self.manual_numbers_tree.pack(fill="both", expand=True)

        list_actions = ttk.Frame(numbers_card, style="Card.TFrame")
        list_actions.pack(fill="x", pady=(6, 0))
        ttk.Button(list_actions, text="Remover selecionado", command=self.manual_builder_remove_selected).pack(side="left")
        ttk.Button(list_actions, text="Limpar lista", command=self.manual_builder_clear).pack(side="left", padx=(5, 0))

        value_card = ttk.Frame(self.play_body, style="Card.TFrame", padding=(12, 10))
        value_card.pack(fill="x")
        ttk.Label(value_card, text="VALOR E BILHETE", style="CardMuted.TLabel").grid(
            row=0, column=0, columnspan=6, sticky="w", pady=(0, 4)
        )
        ttk.Label(value_card, text="Forma do valor", style="Card.TLabel").grid(row=1, column=0, sticky="w")
        self.manual_value_mode_cb = ttk.Combobox(
            value_card,
            textvariable=self.manual_value_mode,
            values=["Por palpite", "Valor total"],
            width=14,
            state="readonly",
        )
        self.manual_value_mode_cb.grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(2, 0))
        self.manual_value_mode_cb.bind("<<ComboboxSelected>>", self.manual_builder_refresh)

        ttk.Label(value_card, text="Valor", style="Card.TLabel").grid(row=1, column=1, sticky="w")
        self.manual_stake_entry = ttk.Entry(value_card, textvariable=self.manual_stake, width=12)
        self.manual_stake_entry.grid(row=2, column=1, sticky="w", padx=(0, 12), pady=(2, 0))
        self.manual_stake_entry.bind("<KeyRelease>", self.manual_builder_refresh)

        self.manual_summary_label = ttk.Label(
            value_card, text="", style="Card.TLabel", justify="left", wraplength=560
        )
        self.manual_summary_label.grid(row=1, column=2, rowspan=2, sticky="ew", padx=(8, 12))
        value_card.grid_columnconfigure(2, weight=1)
        self._bind_wraplength(self.manual_summary_label, value_card, margin=410, minimum=220, maximum=650)

        manual_actions = ttk.Frame(value_card, style="Card.TFrame")
        manual_actions.grid(row=3, column=0, columnspan=4, sticky="e", pady=(8, 0))
        ttk.Button(
            manual_actions,
            text="JOGAR / SALVAR BILHETE",
            style="Accent.TButton",
            command=self.manual_builder_register,
        ).pack(side="right")

        self.manual_builder_family_changed(clear_rows=False)
        self.manual_number_entry.focus_set()
        self.after_idle(self._play_finalize_layout)

    def manual_builder_get_target(self):
        target = self.manual_target_map.get(self.manual_target_var.get())
        return dict(target) if target else None

    def manual_builder_family_changed(self, _event=None, clear_rows=True):
        variants = {
            "Grupo": ["Simples", "Dupla", "Terno", "Quadra", "Quina", "Passe vai", "Passe vai e vem"],
            "Dezena": ["Normal", "Duque", "Terno", "Invertida"],
            "Centena": ["Normal", "Invertida"],
            "Milhar": ["Normal", "Invertida"],
        }.get(self.manual_family.get(), ["Normal"])
        self.manual_variant_cb.configure(values=variants)
        if self.manual_variant.get() not in variants:
            self.manual_variant.set(variants[0])
        self.manual_builder_variant_changed(clear_rows=clear_rows)

    def manual_builder_variant_changed(self, _event=None, clear_rows=True):
        mapping = {
            ("Grupo", "Simples"): "Grupo",
            ("Grupo", "Dupla"): "Dupla de Grupo",
            ("Grupo", "Terno"): "Terno de Grupo",
            ("Grupo", "Quadra"): "Quadra de Grupo",
            ("Grupo", "Quina"): "Quina de Grupo",
            ("Grupo", "Passe vai"): "Passe vai",
            ("Grupo", "Passe vai e vem"): "Passe vai e vem",
            ("Dezena", "Normal"): "Dezena",
            ("Dezena", "Duque"): "Duque de Dezena",
            ("Dezena", "Terno"): "Terno de Dezena",
            ("Dezena", "Invertida"): "Dezena Invertida",
            ("Centena", "Normal"): "Centena",
            ("Centena", "Invertida"): "Centena Invertida",
            ("Milhar", "Normal"): "Milhar",
            ("Milhar", "Invertida"): "Milhar Invertida",
        }
        kind = mapping.get((self.manual_family.get(), self.manual_variant.get()), self.manual_family.get())
        changed = self.manual_kind.get() != kind
        self.manual_kind.set(kind)
        if clear_rows and changed and self.manual_builder_rows:
            self.manual_builder_rows.clear()
            self.manual_add_status.configure(text="Lista limpa porque a modalidade mudou.", style="CardMuted.TLabel")
        self.manual_builder_controls_changed()

    def manual_builder_controls_changed(self):
        kind = self.manual_kind.get()
        if kind == "Milhar":
            self.manual_submode_label.grid()
            self.manual_submode_cb.grid()
            self.manual_submode_cb.configure(state="readonly")
        else:
            self.manual_submode_label.grid_remove()
            self.manual_submode_cb.grid_remove()

        if kind in FIXED_PLACEMENT_MODALITIES:
            self.manual_scope.set("1º–5º")
            self.manual_scope_cb.configure(state="disabled")
        else:
            self.manual_scope_cb.configure(state="readonly")

        hints = {
            "Grupo": "Digite um grupo por vez. Ex.: 01",
            "Dupla de Grupo": "Digite os dois grupos. Ex.: 01-10",
            "Terno de Grupo": "Ex.: 01-10-23",
            "Quadra de Grupo": "Ex.: 01-05-10-23",
            "Quina de Grupo": "Ex.: 01-05-10-19-23",
            "Passe vai": "Ordem importa. Ex.: 05-22",
            "Passe vai e vem": "Ex.: 05-22",
            "Dezena": "Digite uma dezena por vez. Ex.: 38",
            "Duque de Dezena": "Ex.: 23-71",
            "Terno de Dezena": "Ex.: 23-71-05",
            "Dezena Invertida": "Ex.: 38",
            "Centena": "Digite uma centena por vez. Ex.: 904",
            "Centena Invertida": "Ex.: 538",
            "Milhar": "Digite uma milhar por vez. Ex.: 1000",
            "Milhar Invertida": "Ex.: 4825",
        }
        self.manual_kind_hint.configure(text=hints.get(kind, "Digite o palpite e pressione Adicionar."))
        self.manual_builder_refresh()

    def manual_builder_add_number(self):
        raw = self.manual_number.get().strip()
        if not raw:
            return
        kind = self.manual_kind.get()
        try:
            generation = self.db.manual_generation(
                kind,
                raw,
                scope=self.manual_scope.get(),
                submodalidade=(self.manual_submode.get() if kind == "Milhar" else None),
            )
        except Exception as exc:
            self.manual_add_status.configure(text=str(exc), style="Danger.TLabel")
            return

        existing = {str(r.get("numero")) for r in self.manual_builder_rows}
        added = 0
        last = None
        for row in generation["rows"]:
            number = str(row.get("numero"))
            if number in existing:
                continue
            self.manual_builder_rows.append(dict(row))
            existing.add(number)
            added += 1
            last = number

        if added:
            self.manual_number.set("")
            self.manual_add_status.configure(
                text=f"✓ {last} adicionado" if added == 1 else f"✓ {added} palpites adicionados",
                style="Success.TLabel",
            )
        else:
            self.manual_add_status.configure(text="Esse palpite já está na lista.", style="CardMuted.TLabel")
        self.manual_builder_refresh()
        self.manual_number_entry.focus_set()

    def manual_builder_remove_selected(self):
        sel = self.manual_numbers_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.manual_builder_rows):
            self.manual_builder_rows.pop(idx)
        self.manual_builder_refresh()

    def manual_builder_clear(self):
        if not self.manual_builder_rows:
            return
        if messagebox.askyesno("Limpar lista", "Remover todos os palpites manuais?", parent=self):
            self.manual_builder_rows.clear()
            self.manual_add_status.configure(text="Lista limpa.", style="CardMuted.TLabel")
            self.manual_builder_refresh()

    def manual_builder_value_details(self):
        count = len(self.manual_builder_rows)
        raw = self._parse_money(self.manual_stake.get())
        if raw < 0:
            raise ValueError("O valor não pode ser negativo.")
        if self.manual_value_mode.get() == "Valor total":
            total = raw
            unit = total / count if count else 0.0
        else:
            unit = raw
            total = unit * count
        return unit, total

    def manual_builder_refresh(self, _event=None):
        if not hasattr(self, "manual_numbers_tree"):
            return
        for item in self.manual_numbers_tree.get_children():
            self.manual_numbers_tree.delete(item)
        for idx, row in enumerate(self.manual_builder_rows):
            detail = row.get("bicho") or "—"
            if row.get("grupo"):
                detail = f"G{int(row['grupo']):02d} • {detail}"
            self.manual_numbers_tree.insert(
                "", "end", iid=str(idx), values=(idx + 1, row.get("numero"), detail)
            )
        count = len(self.manual_builder_rows)
        self.manual_count_label.configure(text=f"{count} palpite{'s' if count != 1 else ''}")
        try:
            unit, total = self.manual_builder_value_details()
            if count:
                self.manual_summary_label.configure(
                    text=f"{count} palpites • {self._money(unit)} cada • TOTAL {self._money(total)}"
                )
            else:
                self.manual_summary_label.configure(text="Adicione seus números para montar o bilhete.")
        except Exception:
            self.manual_summary_label.configure(text="Informe um valor válido.")

    def manual_builder_register(self):
        target = self.manual_builder_get_target()
        if not target:
            messagebox.showerror("Jogo manual", "Selecione a rodada-alvo.", parent=self)
            return
        if not self.manual_builder_rows:
            messagebox.showinfo("Jogo manual", "Adicione pelo menos um palpite.", parent=self)
            return
        try:
            unit, total = self.manual_builder_value_details()
        except Exception:
            messagebox.showerror("Jogo manual", "Informe um valor válido.", parent=self)
            return
        if unit <= 0:
            messagebox.showerror("Jogo manual", "O valor por palpite deve ser maior que zero.", parent=self)
            return

        kind = self.manual_kind.get()
        scope = "1º–5º" if kind in FIXED_PLACEMENT_MODALITIES else self.manual_scope.get()
        submode = self.manual_submode.get() if kind == "Milhar" else None
        generation = {
            "kind": kind,
            "strategy": "Jogo Manual",
            "selector": "Jogo Manual",
            "scope": scope,
            "submodalidade": submode,
            "rows": copy.deepcopy(self.manual_builder_rows),
            "intended_target": target,
            "target_mode": "ALVO_ESPECIFICO",
            "origem_jogada": "Manual",
        }

        label = kind + (f" / {submode}" if submode else "")
        numbers = "  ".join(str(r.get("numero")) for r in self.manual_builder_rows)
        preview = numbers if len(numbers) <= 150 else numbers[:147] + "..."
        if not messagebox.askyesno(
            "Salvar bilhete manual",
            (
                f"{self._format_target(target)}\n\n"
                f"{label} • {scope}\n"
                f"{len(self.manual_builder_rows)} palpites\n"
                f"{preview}\n\n"
                f"Valor por palpite: {self._money(unit)}\n"
                f"TOTAL: {self._money(total)}\n\n"
                "Registrar como jogada REAL e salvar em Bilhetes?"
            ),
            parent=self,
        ):
            return

        try:
            report = self.db.register_ticket(
                [{
                    "generation": generation,
                    "stake_per_item": unit,
                    "origem_jogada": "Manual",
                }],
                base_draw=self.db.latest_operational_draw(),
            )
        except Exception as exc:
            messagebox.showerror("Jogo manual", str(exc), parent=self)
            return

        ticket_id = report["ticket_id"]
        self.manual_builder_rows.clear()
        self._update_results_nav_badge()
        messagebox.showinfo(
            "Bilhete salvo",
            f"Bilhete #{ticket_id} registrado.\nTotal apostado: {self._money(total)}.",
            parent=self,
        )
        self.play_show_games(select_ticket_id=ticket_id)

    def play_family_changed(self, _event=None):
        variants = {
            "Grupo": ["Simples", "Dupla", "Terno", "Quadra", "Quina", "Passe vai", "Passe vai e vem"],
            "Dezena": ["Normal", "Duque", "Terno", "Invertida"],
            "Centena": ["Normal", "Invertida"],
            "Milhar": ["Normal", "Invertida"],
        }.get(self.play_family.get(), ["Normal"])
        self.play_variant_cb.configure(values=variants)
        if self.play_variant.get() not in variants:
            self.play_variant.set(variants[0])
        self.play_variant_changed()

    def play_variant_changed(self, _event=None):
        family = self.play_family.get()
        variant = self.play_variant.get()
        mapping = {
            ("Grupo", "Simples"): "Grupo",
            ("Grupo", "Dupla"): "Dupla de Grupo",
            ("Grupo", "Terno"): "Terno de Grupo",
            ("Grupo", "Quadra"): "Quadra de Grupo",
            ("Grupo", "Quina"): "Quina de Grupo",
            ("Grupo", "Passe vai"): "Passe vai",
            ("Grupo", "Passe vai e vem"): "Passe vai e vem",
            ("Dezena", "Normal"): "Dezena",
            ("Dezena", "Duque"): "Duque de Dezena",
            ("Dezena", "Terno"): "Terno de Dezena",
            ("Dezena", "Invertida"): "Dezena Invertida",
            ("Centena", "Normal"): "Centena",
            ("Centena", "Invertida"): "Centena Invertida",
            ("Milhar", "Normal"): "Milhar",
            ("Milhar", "Invertida"): "Milhar Invertida",
        }
        self.play_kind.set(mapping.get((family, variant), family))
        self.play_controls_changed()

    def play_get_selected_target(self):
        label = self.play_target_var.get()
        target = self.play_target_map.get(label)
        return dict(target) if target else None

    def play_target_changed(self, _event=None):
        self.play_generation = None

        for child in self.play_grid_container.winfo_children():
            child.destroy()

        target = self.play_get_selected_target()
        ttk.Label(
            self.play_grid_container,
            text="Alvo alterado para " + self._format_target(target) + ". Gere novamente os palpites.",
            style="CardMuted.TLabel",
        ).pack(pady=10)

        self.play_controls_changed()
        self.play_refresh_ticket()
        self._play_refresh_shadow_recommendation()

    def play_scope_changed(self, _event=None):
        self.play_financial_refresh()
        self._play_refresh_shadow_recommendation()

    def play_value_details(self, count=None):
        if count is None:
            count = (
                len(self.play_generation.get("rows", []))
                if self.play_generation
                else int(self.play_total.get() or 0)
            )

        raw = self._parse_money(self.play_stake.get())
        if raw < 0:
            raise ValueError("O valor não pode ser negativo.")

        if self.play_value_mode.get() == "Valor total":
            total = raw
            stake = (
                total / count
                if count > 0
                else 0.0
            )
        else:
            stake = raw
            total = stake * count

        return {
            "stake_per_item": stake,
            "total": total,
            "input_value": raw,
            "mode": self.play_value_mode.get(),
        }

    def play_manual_input(self):
        kind = self.play_kind.get()
        target = self.play_get_selected_target()

        if not target:
            messagebox.showerror(
                "Entrada manual",
                "Selecione a rodada-alvo.",
                parent=self,
            )
            return

        hints = {
            "Grupo":"Ex.: 01, 10, 23",
            "Dupla de Grupo":"Ex.: 01-10, 05-23",
            "Terno de Grupo":"Ex.: 01-02-03, 05-10-22",
            "Quadra de Grupo":"Ex.: 01-02-03-04",
            "Quina de Grupo":"Ex.: 01-02-03-04-05",
            "Passe vai":"Ex.: 05-22 (primeiro grupo → segundo)",
            "Passe vai e vem":"Ex.: 05-22",
            "Dezena":"Ex.: 05, 38, 90",
            "Duque de Dezena":"Ex.: 23-71, 05-38",
            "Terno de Dezena":"Ex.: 23-71-05",
            "Dezena Invertida":"Ex.: 38, 25",
            "Centena":"Ex.: 238, 904, 167",
            "Centena Invertida":"Ex.: 538, 774",
            "Milhar":"Ex.: 1238, 5904, 0167",
            "Milhar Invertida":"Ex.: 4825, 1123",
        }

        text = simpledialog.askstring(
            "Entrada manual",
            (
                f"{kind} • {self.play_scope.get()}\n"
                f"{hints.get(kind, '')}\n\n"
                "Cole ou digite os palpites:"
            ),
            parent=self,
        )

        if text is None:
            return

        try:
            generation = self.db.manual_generation(
                kind,
                text,
                scope=self.play_scope.get(),
                submodalidade=(
                    self.play_submode.get()
                    if kind == "Milhar"
                    else None
                ),
            )

            generation["intended_target"] = target
            generation["target_mode"] = "ALVO_ESPECIFICO"
            generation["selector"] = "Manual"
            generation["strategy"] = "Manual"

            self.play_generation = generation
            self.play_total.set(
                str(len(generation["rows"]))
            )
            self.play_render_generation()
            self.play_financial_refresh()

        except Exception as exc:
            messagebox.showerror(
                "Entrada manual",
                str(exc),
                parent=self,
            )

    def play_add_to_ticket(self):
        if not self.play_generation:
            messagebox.showinfo(
                "Bilhete",
                "Gere ou informe manualmente uma jogada primeiro.",
                parent=self,
            )
            return

        count = len(self.play_generation.get("rows", []))
        try:
            values = self.play_value_details(count)
        except Exception:
            messagebox.showerror(
                "Valor",
                "Informe um valor válido.",
                parent=self,
            )
            return

        if values["stake_per_item"] <= 0:
            messagebox.showerror(
                "Valor",
                "O valor por palpite deve ser maior que zero.",
                parent=self,
            )
            return

        generation = copy.deepcopy(self.play_generation)
        target = generation.get(
            "intended_target"
        ) or self.db.next_operational_target()

        if self.play_ticket_draft:
            old_target = self.play_ticket_draft[0]["generation"].get(
                "intended_target"
            )
            if (
                old_target
                and target
                and (
                    old_target.get("data"),
                    old_target.get("sorteio"),
                    old_target.get("hora"),
                ) != (
                    target.get("data"),
                    target.get("sorteio"),
                    target.get("hora"),
                )
            ):
                messagebox.showerror(
                    "Bilhete",
                    (
                        "O bilhete em montagem pertence a outra rodada. "
                        "Para repetir o mesmo jogo em vários horários, use 'VÁRIOS HORÁRIOS...'. "
                        "Caso contrário, registre ou limpe o bilhete anterior."
                    ),
                    parent=self,
                )
                return

        self.play_ticket_draft.append({
            "generation": generation,
            "stake_per_item": values["stake_per_item"],
            "value_mode": values["mode"],
            "input_value": values["input_value"],
            "origem_jogada": (
                "Manual"
                if generation.get("strategy") == "Manual"
                else "Gerada"
            ),
        })

        self.play_generation = None
        self.play_refresh_ticket()

        for child in self.play_grid_container.winfo_children():
            child.destroy()
        ttk.Label(
            self.play_grid_container,
            text="Adicionado ao bilhete. Você pode montar outra modalidade para a mesma rodada.",
            style="Card.TLabel",
        ).pack(pady=18)

        self.play_financial_refresh()

    def play_refresh_ticket(self):
        if not hasattr(self, "play_ticket_tree"):
            return

        for item in self.play_ticket_tree.get_children():
            self.play_ticket_tree.delete(item)

        total = 0.0

        for idx, entry in enumerate(self.play_ticket_draft):
            generation = entry["generation"]
            count = len(generation["rows"])
            stake = float(entry["stake_per_item"])
            subtotal = stake * count
            total += subtotal

            kind = generation["kind"]
            if generation.get("submodalidade"):
                kind += f" / {generation['submodalidade']}"
            kind += f" • {generation['scope']}"

            self.play_ticket_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    kind,
                    generation.get("strategy", "—"),
                    count,
                    self._money(stake),
                    self._money(subtotal),
                ),
            )

        multi_targets = getattr(self, "play_ticket_multi_targets", []) or []
        if hasattr(self, "play_ticket_target_label"):
            if self.play_ticket_draft:
                if multi_targets:
                    formatted = [self._format_target(target) for target in multi_targets]
                    self.play_ticket_target_label.configure(
                        text=(
                            f"VÁRIOS HORÁRIOS • {len(formatted)} rodadas selecionadas\n"
                            + "  •  ".join(formatted)
                        )
                    )
                else:
                    target = self.play_ticket_draft[0]["generation"].get("intended_target")
                    self.play_ticket_target_label.configure(text=self._format_target(target))
            else:
                self.play_ticket_target_label.configure(text="Nenhuma modalidade adicionada")

        if multi_targets and self.play_ticket_draft:
            self.play_ticket_summary_label.configure(
                text=(
                    f"{len(self.play_ticket_draft)} modalidade(s)  •  "
                    f"{self._money(total)} por rodada  •  "
                    f"{len(multi_targets)} rodadas  •  "
                    f"TOTAL {self._money(total * len(multi_targets))}"
                )
            )
        else:
            self.play_ticket_summary_label.configure(
                text=(
                    f"{len(self.play_ticket_draft)} modalidade(s)  •  TOTAL {self._money(total)}"
                )
            )

    def play_remove_ticket_item(self):
        sel = self.play_ticket_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.play_ticket_draft):
            self.play_ticket_draft.pop(idx)
            if not self.play_ticket_draft:
                self.play_ticket_multi_targets = []
            self.play_refresh_ticket()

    def play_clear_ticket(self):
        if not self.play_ticket_draft:
            return

        if messagebox.askyesno(
            "Limpar bilhete",
            "Remover todas as modalidades do bilhete atual?",
            parent=self,
        ):
            self.play_ticket_draft.clear()
            self.play_ticket_multi_targets = []
            self.play_refresh_ticket()

    def play_register_ticket_multi(self):
        """Seleciona rodadas para o rascunho; não registra nada no banco."""
        if not self.play_ticket_draft:
            messagebox.showinfo(
                "Vários horários",
                "Adicione pelo menos uma modalidade ao bilhete antes de escolher os horários.",
                parent=self,
            )
            return

        options = [
            (label, dict(target))
            for label, target in getattr(self, "play_target_map", {}).items()
        ]
        if not options:
            messagebox.showinfo(
                "Vários horários",
                "Não há rodadas futuras disponíveis para selecionar.",
                parent=self,
            )
            return

        def target_key(target):
            target = target or {}
            return (
                target.get("data"),
                target.get("sorteio"),
                target.get("hora"),
            )

        draft_target = self.play_ticket_draft[0]["generation"].get("intended_target")
        draft_key = target_key(draft_target)
        base_idx = 0
        for idx, (_label, target) in enumerate(options):
            if target_key(target) == draft_key:
                base_idx = idx
                break

        existing_targets = getattr(self, "play_ticket_multi_targets", []) or []
        existing_keys = {target_key(target) for target in existing_targets}

        dialog = tk.Toplevel(self)
        dialog.title("Selecionar vários horários")
        dialog.transient(self)
        dialog.grab_set()
        dialog.minsize(510, 390)
        dialog.geometry("560x470")

        body = ttk.Frame(dialog, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="Escolha as rodadas deste bilhete.",
            style="Section.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            body,
            text=(
                "CONTINUAR apenas prepara os horários no bilhete em montagem. "
                "Nada será registrado até você clicar em REGISTRAR BILHETE."
            ),
            wraplength=500,
            justify="left",
        ).pack(anchor="w", pady=(4, 10))

        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        listbox = tk.Listbox(
            list_frame,
            selectmode="multiple",
            exportselection=False,
            activestyle="none",
            height=12,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.configure(command=listbox.yview)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for label, _target in options:
            listbox.insert("end", label)

        if existing_keys:
            for idx, (_label, target) in enumerate(options):
                if target_key(target) in existing_keys:
                    listbox.selection_set(idx)
        else:
            end_default = min(len(options), base_idx + 5)
            for idx in range(base_idx, end_default):
                listbox.selection_set(idx)

        if base_idx < len(options):
            listbox.see(base_idx)

        def on_wheel(event):
            delta = int(-1 * (event.delta / 120)) if event.delta else 0
            if delta:
                listbox.yview_scroll(delta, "units")
            return "break"

        listbox.bind("<MouseWheel>", on_wheel)

        chosen = {"indices": None}

        def confirm():
            indices = list(listbox.curselection())
            if not indices:
                messagebox.showinfo(
                    "Vários horários",
                    "Selecione pelo menos uma rodada.",
                    parent=dialog,
                )
                return
            chosen["indices"] = indices
            dialog.destroy()

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Cancelar", command=dialog.destroy).pack(side="right")
        ttk.Button(
            actions,
            text="CONTINUAR",
            style="Accent.TButton",
            command=confirm,
        ).pack(side="right", padx=(0, 6))

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.wait_window()

        indices = chosen["indices"]
        if not indices:
            return

        selected = [options[idx] for idx in indices]
        self.play_ticket_multi_targets = [dict(target) for _label, target in selected]
        self.play_refresh_ticket()
        self.status.configure(
            text=(
                f"Bilhete preparado para {len(selected)} rodada(s). "
                "Ainda não foi registrado."
            )
        )
        messagebox.showinfo(
            "Horários preparados",
            (
                f"{len(selected)} rodada(s) foram adicionadas ao bilhete em montagem.\n\n"
                "Nenhum bilhete foi registrado ainda.\n"
                "Revise o bilhete e clique em REGISTRAR BILHETE quando quiser confirmar."
            ),
            parent=self,
        )

    def play_register_ticket(self):
        if not self.play_ticket_draft:
            messagebox.showinfo(
                "Bilhete",
                "O bilhete está vazio.",
                parent=self,
            )
            return

        base_target = self.play_ticket_draft[0]["generation"].get(
            "intended_target"
        )
        multi_targets = [
            dict(target)
            for target in (getattr(self, "play_ticket_multi_targets", []) or [])
            if target
        ]
        targets = multi_targets or ([dict(base_target)] if base_target else [])
        if not targets:
            messagebox.showerror(
                "Bilhete",
                "Não foi possível identificar a rodada do bilhete.",
                parent=self,
            )
            return

        total_per_ticket = sum(
            len(e["generation"]["rows"])
            * float(e["stake_per_item"])
            for e in self.play_ticket_draft
        )
        grand_total = total_per_ticket * len(targets)

        lines = []
        for entry in self.play_ticket_draft:
            generation = entry["generation"]
            kind = generation["kind"]
            if generation.get("submodalidade"):
                kind += f"/{generation['submodalidade']}"
            lines.append(
                f"• {kind} • {generation['scope']} • "
                f"{len(generation['rows'])} palpites • "
                f"{self._money(len(generation['rows']) * float(entry['stake_per_item']))}"
            )

        if multi_targets:
            target_lines = "\n".join(
                f"• {self._format_target(target)}"
                for target in targets
            )
            confirm_text = (
                f"MESMO BILHETE EM {len(targets)} RODADAS:\n\n"
                f"{target_lines}\n\n"
                + "\n".join(lines)
                + (
                    f"\n\nVALOR POR RODADA: {self._money(total_per_ticket)}\n"
                    f"TOTAL GERAL: {self._money(grand_total)}\n\n"
                    "Registrar agora todos esses bilhetes como jogadas REAIS?"
                )
            )
        else:
            confirm_text = (
                f"{self._format_target(targets[0])}\n\n"
                + "\n".join(lines)
                + (
                    f"\n\nTOTAL DO BILHETE: {self._money(total_per_ticket)}\n\n"
                    "Registrar todas como jogadas REAIS?"
                )
            )

        if not messagebox.askyesno(
            "Registrar bilhete",
            confirm_text,
            parent=self,
        ):
            return

        base_draw = self.db.latest_operational_draw()
        registered = []
        game_ids = []
        try:
            for target in targets:
                entries = copy.deepcopy(self.play_ticket_draft)
                for entry in entries:
                    entry["generation"]["intended_target"] = dict(target)
                    if multi_targets:
                        entry["origem_jogada"] = "Bilhete multi-horário"
                report = self.db.register_ticket(
                    entries,
                    base_draw=base_draw,
                )
                registered.append(int(report["ticket_id"]))
                game_ids.extend(report["game_ids"])
        except Exception as exc:
            # Multi-horário deve ser tudo ou nada. Se alguma rodada falhar,
            # remove os bilhetes já criados nesta tentativa.
            for ticket_id in registered:
                try:
                    self.db.delete_ticket(ticket_id)
                except Exception:
                    pass
            self._update_results_nav_badge()
            messagebox.showerror(
                "Bilhete",
                (
                    "Não foi possível concluir o registro. "
                    "Os bilhetes desta tentativa foram desfeitos.\n\n"
                    f"{exc}"
                ),
                parent=self,
            )
            return

        self.play_ticket_draft.clear()
        self.play_ticket_multi_targets = []
        self._update_results_nav_badge()

        if multi_targets:
            messagebox.showinfo(
                "Bilhetes registrados",
                (
                    f"{len(registered)} bilhetes separados foram registrados.\n"
                    f"{len(game_ids)} modalidade(s) no total.\n"
                    f"Total apostado: {self._money(grand_total)}."
                ),
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Bilhete registrado",
                (
                    f"Bilhete #{registered[0]} registrado.\n"
                    f"{len(game_ids)} modalidade(s).\n"
                    f"Total apostado: {self._money(total_per_ticket)}."
                ),
                parent=self,
            )

        self.play_show_games(
            select_ticket_id=registered[0]
        )

    def play_controls_changed(self, _event=None):
        kind = self.play_kind.get()
        method = self.play_method.get()

        fixed = kind in FIXED_PLACEMENT_MODALITIES

        if kind == "Centena":
            methods = [
                "Oficial • Reset + 3+1",
                "Oficial • Reset + Histórica",
                "Especial • Seca do Dia 1º",
                "Experimental • Puxada Combinada",
                "Experimental • Similaridade do Dia",
                "Manual",
            ]
        elif kind == "Milhar":
            methods = [
                "Oficial • Reset + Histórica",
                "Especial • Seca do Dia 1º",
                "Experimental • Puxada Combinada",
                "Experimental • Similaridade do Dia",
                "Manual",
            ]
        elif kind == "Grupo":
            methods = [
                "Oficial • Reset",
                "Experimental • Puxada Combinada",
                "Experimental • Similaridade do Dia",
                "Manual",
            ]
        elif kind in GROUP_COMBO_SIZES or kind in PASSE_MODALITIES:
            methods = [
                "Oficial • Reset combinações",
                "Experimental • Puxada Combinada",
                "Experimental • Similaridade combinações",
                "Manual",
            ]
        elif kind in DEZENA_COMBO_SIZES or kind in INVERTED_MODALITIES or kind == "Dezena":
            methods = [
                "Oficial • Reset + Histórica",
                "Experimental • Puxada Combinada",
                "Experimental • Similaridade do Dia",
                "Manual",
            ]
        else:
            methods = ["Manual"]

        if method not in methods:
            self.play_method.set(methods[0])
            method = methods[0]
        self.play_method_cb.configure(values=methods, state="readonly")

        # Milhar/Centena só faz sentido na Milhar normal.
        if kind == "Milhar":
            self.play_submode_label.grid()
            self.play_submode_cb.grid()
            self.play_submode_cb.configure(state="readonly")
        else:
            self.play_submode_cb.configure(state="disabled")
            self.play_submode_label.grid_remove()
            self.play_submode_cb.grid_remove()

        # A colocação é escolha do bilhete, não uma trava do método.
        # Somente modalidades que são estruturalmente de colocação fixa
        # continuam bloqueadas por regra própria da modalidade.
        if fixed:
            self.play_scope.set("1º–5º")
            self.play_scope_cb.configure(state="disabled")
        else:
            self.play_scope_cb.configure(state="readonly")

        if kind == "Centena" and method == "Oficial • Reset + 3+1":
            self.play_total.set("20")
            self.play_total_spin.configure(state="disabled")
        else:
            self.play_total_spin.configure(state="normal")

        if kind == "Grupo" and self.play_total.get() == "20":
            self.play_total.set("5")
        if kind in GROUP_COMBO_SIZES:
            default_qty = {
                "Dupla de Grupo":"5", "Terno de Grupo":"3", "Quadra de Grupo":"2", "Quina de Grupo":"1"
            }[kind]
            if self.play_total.get() == "20":
                self.play_total.set(default_qty)

        target = self.play_get_selected_target()
        is_next = self.db.is_next_operational_target(target)

        # Etiqueta visual de origem do método.
        if method.startswith("Oficial"):
            badge = ("OFICIAL", "#124A7A", "#DCEEFF")
            help_text = "Reset é o seletor oficial. Métodos oficiais geram apenas para a próxima rodada operacional."
        elif method.startswith("Experimental"):
            badge = ("EXPERIMENTAL", "#4C2A78", "#E9D9FF")
            if "Puxada" in method:
                help_text = "Puxada Combinada usa convergência histórica por estado ×1/×2/×3+ e permanece em avaliação prospectiva."
            else:
                help_text = "Similaridade do Dia permanece separada do desempenho oficial e só gera para a próxima rodada."
        elif method.startswith("Especial"):
            badge = ("ESPECIAL", "#7A4D10", "#FFE7B0")
            help_text = "Seca do Dia usa o dia anterior ao alvo e joga somente no 1º prêmio da rodada escolhida."
        else:
            badge = ("MANUAL", "#34465A", "#E3EDF6")
            help_text = "Você informa os números. O modo Manual permite preparar qualquer rodada futura exibida."

        self.play_method_badge.configure(text=badge[0], bg=badge[1], fg=badge[2])
        self.play_generate_btn.configure(text="INSERIR NÚMEROS" if method == "Manual" else "GERAR JOGO")

        if target and not is_next and method != "Manual" and method != "Especial • Seca do Dia 1º":
            help_text += " O alvo escolhido não é o próximo; selecione Manual ou volte para a próxima rodada."
        self.play_method_help.configure(text=help_text)

        if hasattr(self, "play_target_hint"):
            if target:
                prefix = "PRÓXIMA • " if is_next else "FUTURA • "
                hint = prefix + self._format_target(target)
                if not is_next:
                    hint += " — oficial/experimental ficam bloqueados para preservar o teste prospectivo."
            else:
                hint = "Selecione uma rodada."
            self.play_target_hint.configure(text=hint)

        self.play_generation = None
        self.play_financial_refresh()
        if hasattr(self, "play_recommendation_label"):
            self._play_refresh_shadow_recommendation()

    def play_generate(self):
        try:
            kind = self.play_kind.get()
            method = self.play_method.get()
            fixed = kind in FIXED_PLACEMENT_MODALITIES
            target = self.play_get_selected_target()

            if not target:
                raise ValueError(
                    "Selecione a rodada-alvo."
                )

            if method == "Manual":
                self.play_manual_input()
                return

            next_target = self.db.next_operational_target()

            if (
                method != "Especial • Seca do Dia 1º"
                and not self.db.is_next_operational_target(target)
            ):
                raise ValueError(
                    "Métodos oficiais e experimentais só podem gerar "
                    "para a próxima rodada operacional. "
                    "Para preparar uma rodada posterior, use Manual."
                )

            latest = self.db.latest_operational_draw()

            if not latest:
                raise ValueError(
                    "Não foi possível identificar a base operacional."
                )

            total = max(1, int(self.play_total.get()))

            if method == "Especial • Seca do Dia 1º":
                if kind not in ("Centena", "Milhar"):
                    raise ValueError(
                        "A Seca do Dia gera apenas Centena ou Milhar."
                    )

                target_date = datetime.strptime(
                    target["data"],
                    "%Y-%m-%d",
                ).date()

                base_date = (
                    target_date - timedelta(days=1)
                ).isoformat()

                generation = self.db.generate_dry_day_numbers(
                    base_date=base_date,
                    kind=kind,
                    total=total,
                    top_animals=min(5, max(2, total)),
                )
                generation["selector"] = "Seca do Dia 1º"
                generation["strategy"] = "Seca do Dia 1º"
                # A Seca continua calculada com histórico de 1º prêmio,
                # mas a colocação efetiva do bilhete é escolhida pelo usuário.
                generation["scope"] = self.play_scope.get()
                generation["intended_target"] = target
                generation["target_mode"] = "ALVO_ESPECIFICO"

                if kind == "Milhar":
                    generation["submodalidade"] = (
                        self.play_submode.get()
                    )

                self.play_generation = generation
                self.play_generation_groups = list(
                    generation.get("groups", [])
                )
                self._shadow_freeze_async(target, latest)
                self.play_render_generation()
                self.play_financial_refresh()
                return

            if method.startswith("Experimental"):
                if "Puxada" in method:
                    pull = self.db.method_convergencia_g5(
                        latest["data"], latest["sorteio"], latest["hora"], top_n=5
                    )
                    groups = [int(r["grupo"]) for r in pull.get("selected", [])]
                    selector = "Puxada Combinada"
                else:
                    similarity = self.db.method_similarity_day(
                        latest["data"],
                        latest["sorteio"],
                        latest["hora"],
                    )

                    groups = []
                    for row in similarity["selected"]:
                        g = int(row["grupo"])
                        if g not in groups:
                            groups.append(g)

                    selector = "Sombra Similaridade do Dia"

            else:
                reset = self.db.method_reset_coverage_v1(
                    latest["data"],
                    latest["sorteio"],
                    latest["hora"],
                    top_n=5,
                )
                groups = [
                    int(r["grupo"])
                    for r in reset["selected"]
                ]
                selector = "GP-H Reset Cobertura v1"

            if not groups:
                raise ValueError(
                    "O método não produziu bichos suficientes."
                )

            if kind == "Grupo":
                use_groups = groups[:min(total, len(groups))]
                generation = {
                    "kind":"Grupo",
                    "strategy":method,
                    "scope":self.play_scope.get(),
                    "selector":selector,
                    "groups":use_groups,
                    "rows":[
                        {
                            "grupo":g,
                            "bicho":BICHOS[g],
                            "numero":f"{g:02d}",
                            "dezena_base":"—",
                            "regra":method,
                        }
                        for g in use_groups
                    ],
                }

            elif kind in GROUP_COMBO_SIZES:
                generation = self.db.generate_group_combinations(
                    groups,
                    kind,
                    total=total,
                )
                generation["selector"] = selector
                generation["strategy"] = method

            elif kind in PASSE_MODALITIES:
                generation = self.db.generate_passe_combinations(
                    groups,
                    kind,
                    total=total,
                )
                generation["selector"] = selector
                generation["strategy"] = method

            elif kind in DEZENA_COMBO_SIZES:
                generation = self.db.generate_dezena_combinations(
                    groups,
                    kind,
                    total=total,
                )
                generation["selector"] = selector
                generation["strategy"] = method

            elif kind in INVERTED_MODALITIES:
                generation = self.db.generate_inverted_numbers(
                    groups,
                    kind,
                    total=total,
                    scope=self.play_scope.get(),
                )
                generation["selector"] = selector
                generation["strategy"] = method

            elif (
                kind == "Centena"
                and method == "Oficial • Reset + 3+1"
            ):
                generation = self.db.generate_centenas_3plus1(
                    groups=groups[:5],
                    previous_draw=latest,
                )
                generation["selector"] = selector
                generation["strategy"] = "Oficial 3+1"

            else:
                generation = self.db.generate_historical_numbers(
                    groups=groups,
                    kind=kind,
                    total=total,
                    scope=self.play_scope.get(),
                )
                generation["selector"] = selector
                generation["strategy"] = method

            # A fórmula interna pode ter um escopo estatístico próprio
            # (ex.: 3+1 usa histórico 1º–5º; Seca usa histórico de 1º),
            # mas a colocação efetiva do BILHETE é a escolhida pelo usuário.
            if not fixed:
                generation["scope"] = self.play_scope.get()

            if kind == "Milhar":
                generation["submodalidade"] = (
                    self.play_submode.get()
                )

            generation["intended_target"] = target
            generation["target_mode"] = "ALVO_ESPECIFICO"

            self.play_generation = generation
            self.play_generation_groups = list(
                generation.get("groups", groups)
            )

            # Em paralelo, congela jogos/leitura sombra da MESMA rodada.
            # Isso não aparece no bilhete real nem gera mensagem retrospectiva.
            self._shadow_freeze_async(target, latest)
            self.play_render_generation()
            self.play_financial_refresh()

        except Exception as exc:
            messagebox.showerror(
                "Gerar jogada",
                str(exc),
                parent=self,
            )

    def _play_grid_container_resized(self, event):
        if getattr(self, "_page", None) != "play" or getattr(self, "play_view", None) != "new":
            return
        rows = (self.play_generation or {}).get("rows", []) if getattr(self, "play_generation", None) else []
        if not rows:
            return
        width = max(1, int(getattr(event, "width", 1)))
        previous = getattr(self, "_play_grid_last_width", 0)
        if previous and abs(width - previous) < 28:
            return
        self._play_grid_last_width = width
        job = getattr(self, "_play_grid_resize_job", None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._play_grid_resize_job = self.after(90, self._play_rerender_after_resize)

    def _play_rerender_after_resize(self):
        self._play_grid_resize_job = None
        if getattr(self, "_page", None) == "play" and getattr(self, "play_view", None) == "new":
            self.play_render_generation()

    def play_render_generation(self):
        for child in self.play_grid_container.winfo_children():
            child.destroy()

        rows = (
            self.play_generation.get("rows", [])
            if self.play_generation else []
        )

        if not rows:
            label=getattr(self,"play_concentration_label",None)
            if label is not None:
                label.configure(text="")
            ttk.Label(
                self.play_grid_container,
                text="Nenhum número gerado.",
                style="Card.TLabel",
            ).pack(expand=True)
            return

        grid = ttk.Frame(
            self.play_grid_container,
            style="Card.TFrame",
        )
        grid.pack(anchor="n", fill="x")

        # Regra visual: no máximo 4 palpites por coluna.
        # Quantidades maiores criam novas colunas para a direita.
        # Quando o número de colunas cresce, fonte/padding diminuem
        # progressivamente para manter todos os palpites dentro da largura.
        max_rows_per_column = 4
        grid_columns = max(1, (len(rows) + max_rows_per_column - 1) // max_rows_per_column)

        try:
            available_width = int(self.play_grid_container.winfo_width()) - 8
        except Exception:
            available_width = 960
        if available_width < 300:
            available_width = 960
        self._play_grid_last_width = available_width + 8

        # Largura-alvo de cada coluna. Em 50 palpites são 13 colunas;
        # a tipografia reduz automaticamente para evitar corte dos números.
        column_width = max(34, available_width // grid_columns - 4)
        if column_width >= 150:
            number_font, subtitle_font, cell_pad, gap = 14, 8, (8, 5), 4
        elif column_width >= 115:
            number_font, subtitle_font, cell_pad, gap = 13, 8, (6, 4), 3
        elif column_width >= 90:
            number_font, subtitle_font, cell_pad, gap = 12, 7, (5, 4), 3
        elif column_width >= 72:
            number_font, subtitle_font, cell_pad, gap = 11, 7, (4, 3), 2
        elif column_width >= 56:
            number_font, subtitle_font, cell_pad, gap = 10, 6, (3, 2), 2
        elif column_width >= 44:
            number_font, subtitle_font, cell_pad, gap = 9, 6, (2, 2), 1
        else:
            number_font, subtitle_font, cell_pad, gap = 8, 5, (1, 1), 1

        compact_subtitle = column_width < 92
        cell_height = (
            62 if number_font >= 12 else
            58 if number_font >= 10 else
            54 if compact_subtitle else 46
        )

        for i, row in enumerate(rows):
            col = i // max_rows_per_column
            rr = i % max_rows_per_column

            cell = ttk.Frame(
                grid,
                style="Card.TFrame",
                padding=cell_pad,
                width=column_width,
                height=cell_height,
            )
            cell.grid(
                row=rr,
                column=col,
                sticky="nsew",
                padx=gap,
                pady=2,
            )
            # Impede que textos longos forcem a coluna a crescer além da
            # largura calculada. O conteúdo se adapta ao espaço disponível.
            cell.grid_propagate(False)

            ttk.Label(
                cell,
                text=row["numero"],
                style="Card.TLabel",
                font=("Segoe UI Semibold", number_font),
                anchor="center",
            ).pack(fill="x")

            if row.get("grupo"):
                subtitle = (
                    f"{row['bicho']}\nG{int(row['grupo']):02d}"
                    if compact_subtitle
                    else f"{row['bicho']} • G{int(row['grupo']):02d}"
                )
            else:
                subtitle = row.get("bicho", "")

            ttk.Label(
                cell,
                text=subtitle,
                style="Card.TLabel",
                font=("Segoe UI", subtitle_font),
                anchor="center",
                justify="center",
                wraplength=max(28, column_width - 6),
            ).pack(fill="x")

        for col in range(grid_columns):
            grid.grid_columnconfigure(col, weight=1, uniform="playcols")

        # Alerta de concentração ANTES de registrar o jogo.
        label=getattr(self,"play_concentration_label",None)
        if label is not None:
            conc=self.db.decision_concentration_from_generation(self.play_generation)
            if conc.get("group_mentions"):
                lead=" + ".join(r["bicho"] for r in (conc.get("top") or [])[:2])
                text=(f"Concentração: {conc.get('label')} • índice {conc.get('score',0):.0f}/100 • "
                      f"dois líderes = {conc.get('top2_share',0):.0f}%")
                if lead:
                    text += f" ({lead})"
                if conc.get("label") == "ALTA":
                    text += " • atenção: muitos palpites dependem dos mesmos bichos."
                label.configure(text=text)
            else:
                label.configure(text="Concentração: sem leitura para esta modalidade.")

        # Atualiza bindtags/rolagem depois que os palpites foram criados.
        self.after_idle(self._play_finalize_layout)

    def play_financial_refresh(self, _event=None):
        if self.play_generation:
            count = len(
                self.play_generation.get("rows", [])
            )
            kind = self.play_generation.get(
                "kind",
                self.play_kind.get(),
            )
            scope = self.play_generation.get(
                "scope",
                self.play_scope.get(),
            )
            sub = self.play_generation.get(
                "submodalidade"
            )
            rows = self.play_generation.get(
                "rows",
                [],
            )
        else:
            try:
                count = int(self.play_total.get())
            except Exception:
                count = 0
            kind = self.play_kind.get()
            scope = self.play_scope.get()
            sub = (
                self.play_submode.get()
                if kind == "Milhar"
                else None
            )
            rows = []

        try:
            values = self.play_value_details(count)
            stake = values["stake_per_item"]
            input_total = values["total"]
        except Exception:
            stake = 0.0
            input_total = 0.0
            values = {
                "mode": self.play_value_mode.get(),
                "input_value": 0.0,
            }

        if rows:
            snap = self.db._financial_bounds_for_rows(
                kind,
                scope,
                rows,
                stake,
                submodalidade=sub,
            )
        else:
            snap = self.db._financial_snapshot(
                kind,
                scope,
                count,
                stake,
                submodalidade=sub,
            )

        if values["mode"] == "Valor total":
            base_text = (
                f"Total {self._money(values['input_value'])} ÷ "
                f"{count} palpite(s) = "
                f"{self._money(stake)} por palpite"
                if count
                else "Informe a quantidade."
            )
        else:
            base_text = (
                f"{count} palpite(s) × {self._money(stake)} "
                f"= {self._money(input_total)}"
            )

        if snap["divisor_posicoes"] > 1:
            base_text += (
                f" • por posição "
                f"{self._money(snap['valor_posicao'])} "
                f"(÷{snap['divisor_posicoes']})"
            )
        elif snap["fixed_placement"]:
            base_text += (
                " • colocação fixa: sem divisão por 5"
            )

        self.play_financial_label.configure(
            text=base_text
        )

        if kind in INVERTED_MODALITIES:
            quote = self.db.get_quote(kind)
            if rows:
                inv_counts = sorted({
                    self.db._unique_permutation_count(
                        str(r["numero"])
                    )
                    for r in rows
                })
                inv_text = "/".join(
                    str(v) for v in inv_counts
                )
            else:
                inv_text = "depende dos dígitos"

            detail = (
                f"Cotação-base {quote:g}× • "
                f"divisão por inversões: {inv_text}"
            )

            if snap["retorno_min"] is not None:
                if snap["single_position"]:
                    detail += (
                        f" • retorno de um acerto entre "
                        f"{self._money(snap['retorno_min'])} e "
                        f"{self._money(snap['retorno_max'])}"
                    )
                else:
                    detail += (
                        f" • menor acerto "
                        f"{self._money(snap['retorno_min'])} • "
                        f"máximo teórico 5 posições "
                        f"{self._money(snap['retorno_max'])}"
                    )

        elif kind == "Milhar" and sub == "Milhar/Centena":
            q = self.db.get_milhar_centena_quotes()

            if snap["single_position"]:
                detail = (
                    f"1º prêmio • Centena: "
                    f"{self._money(stake * q['centena'])} • "
                    f"Milhar+Centena: "
                    f"{self._money(stake * q['ambos'])}"
                )
            else:
                detail = (
                    f"Centena {q['centena']:g}× • "
                    f"Milhar {q['milhar']:g}× • "
                    f"ambos {q['ambos']:g}×"
                )
                if snap["retorno_min"] is not None:
                    detail += (
                        f" • mínimo vencedor "
                        f"{self._money(snap['retorno_min'])} • "
                        f"máximo 5 posições "
                        f"{self._money(snap['retorno_max'])}"
                    )

        else:
            quote = self.db.get_quote(kind)

            if quote <= 0:
                detail = "Cotação não configurada"

            elif snap["single_position"]:
                detail = (
                    f"Cotação {quote:g}× • "
                    f"retorno por acerto "
                    f"{self._money(snap['retorno_min'])}"
                )

            elif snap["fixed_placement"]:
                detail = (
                    f"Cotação {quote:g}× • "
                    f"retorno por palpite vencedor "
                    f"{self._money(snap['retorno_min'])}"
                )

            else:
                detail = (
                    f"Cotação {quote:g}× • "
                    f"1 acerto {self._money(snap['retorno_min'])} • "
                    f"máximo 5 posições "
                    f"{self._money(snap['retorno_max'])}"
                )

        self.play_payout_label.configure(
            text=detail
        )

    def play_copy_numbers(self):
        if not self.play_generation:
            messagebox.showinfo(
                "Copiar números",
                "Gere a jogada primeiro.",
                parent=self,
            )
            return

        numbers = [
            str(r["numero"])
            for r in self.play_generation.get("rows", [])
        ]
        self.clipboard_clear()
        self.clipboard_append(", ".join(numbers))
        self.status.configure(
            text=f"{len(numbers)} número(s) copiado(s)."
        )

    def play_register(self):
        if not self.play_generation:
            messagebox.showinfo(
                "Registrar jogada",
                "Gere a jogada primeiro.",
                parent=self,
            )
            return

        try:
            stake = self._parse_money(self.play_stake.get())
        except Exception:
            messagebox.showerror(
                "Valor",
                "Informe um valor válido por palpite.",
                parent=self,
            )
            return

        if stake <= 0:
            messagebox.showerror(
                "Valor",
                "Informe quanto foi apostado em cada palpite.",
                parent=self,
            )
            return

        target = self.db.next_operational_target()
        already = self.db.pending_operational_games_for_target(target)

        if already:
            if not messagebox.askyesno(
                "Já existe jogo para esta rodada",
                (
                    f"Já existe(m) {len(already)} jogo(s) congelado(s) "
                    "aguardando esta rodada.\n\n"
                    "Deseja registrar outra jogada mesmo assim?"
                ),
                parent=self,
            ):
                return

        kind = self.play_generation.get("kind", self.play_kind.get())
        scope = self.play_generation.get("scope", self.play_scope.get())
        sub = self.play_generation.get("submodalidade")

        snap = self.db._financial_snapshot(
            kind,
            scope,
            len(self.play_generation["rows"]),
            stake,
            submodalidade=sub,
        )

        rows = self.play_generation["rows"]
        target_text = self._format_target(target)

        modality_text = (
            f"{kind} • {sub}"
            if kind == "Milhar" and sub
            else kind
        )

        position_text = (
            f"\nValor por posição: {self._money(snap['valor_posicao'])}"
            if snap["divisor_posicoes"] > 1
            else ""
        )

        if not messagebox.askyesno(
            "Confirmar jogada",
            (
                f"{target_text}\n"
                f"{modality_text} • {scope}\n"
                f"Método: {self.play_method.get()}\n"
                f"{len(rows)} palpite(s)\n"
                f"{self._money(stake)} por palpite"
                f"{position_text}\n"
                f"Total apostado: {self._money(snap['valor_total'])}\n\n"
                "Registrar esta jogada como REAL?"
            ),
            parent=self,
        ):
            return

        game_id = self.db.register_play(
            self.play_generation,
            stake,
            base_draw=self.db.latest_operational_draw(),
        )

        self._update_results_nav_badge()
        self.play_show_games(select_game_id=game_id)

    def play_open_payout_config(self):
        PayoutConfigDialog(
            self,
            self.db,
            on_saved=self.play_after_payout_saved,
        )

    def play_after_payout_saved(self):
        if self.play_view == "new":
            self.play_financial_refresh()
        elif self.play_view == "games":
            self.play_refresh_games()
            if getattr(self, "play_selected_game_id", None):
                try:
                    self.db.refresh_game_financial_snapshot(
                        self.play_selected_game_id
                    )
                except Exception:
                    pass
                self.play_show_game_detail(
                    self.play_selected_game_id
                )

    def play_show_summary(self):
        self.play_view = "summary"
        self._set_play_subnav_active("summary")
        self._clear_play_body()

        top = ttk.Frame(self.play_body)
        top.pack(fill="x", pady=(0,5))

        ttk.Label(
            top,
            text="Resumo financeiro",
            font=("Segoe UI Semibold", 14),
        ).pack(side="left")

        ttk.Button(
            top,
            text="Configurar banca",
            command=self.play_configure_bankroll,
        ).pack(side="right")

        # v0.33 — os indicadores monetários que antes ocupavam a Home passam
        # a morar no Financeiro. "Apostado no dia" fica explícito para não
        # confundir com os totais de semana/mês/histórico.
        today_kpi = self.db.financial_summary("today")
        daily_kpis = ttk.Frame(self.play_body)
        daily_kpis.pack(fill="x", pady=(0, 6))
        kpi_data = [
            ("Apostado no dia", self._money(today_kpi["apostado"]), None),
            ("Retorno no dia", self._money(today_kpi["retorno"]), None),
            ("Saldo fechado hoje", self._money(today_kpi["liquido_fechado"]), today_kpi["liquido_fechado"]),
            ("Em aberto hoje", self._money(today_kpi["em_aberto"]), None),
        ]
        for idx, (caption, value, signed) in enumerate(kpi_data):
            box = ttk.Frame(daily_kpis, style="Card.TFrame", padding=(10, 7))
            box.pack(
                side="left", fill="x", expand=True,
                padx=(0, 4) if idx < len(kpi_data) - 1 else 0,
            )
            ttk.Label(box, text=caption, style="KpiCaption.TLabel").pack(anchor="w")
            style_name = "Kpi.TLabel"
            if signed is not None and signed > 0:
                style_name = "Success.TLabel"
            elif signed is not None and signed < 0:
                style_name = "Danger.TLabel"
            ttk.Label(
                box, text=value, style=style_name,
                font=("Segoe UI Semibold", 13),
            ).pack(anchor="w", pady=(1, 0))

        # ------------------- cartões Hoje / Semana / Mês
        cards = ttk.Frame(self.play_body)
        cards.pack(fill="x", pady=(0,6))

        summaries = [
            ("Hoje", self.db.financial_summary("today")),
            ("Semana", self.db.financial_summary("week")),
            ("Mês", self.db.financial_summary("month")),
        ]

        for idx, (title, data) in enumerate(summaries):
            box = ttk.Frame(
                cards,
                style="Card.TFrame",
                padding=9,
            )
            box.pack(
                side="left",
                fill="x",
                expand=True,
                padx=(0,5) if idx < 2 else 0,
            )

            ttk.Label(
                box,
                text=title,
                style="Card.TLabel",
                font=("Segoe UI Semibold", 10),
            ).pack(anchor="w")

            card_line1 = ttk.Label(
                box,
                text=(
                    f"Apostado {self._money(data['apostado'])} • "
                    f"Retorno {self._money(data['retorno'])}"
                ),
                style="Card.TLabel", justify="left", wraplength=300,
            )
            card_line1.pack(anchor="w", fill="x", pady=(2,0))
            self._bind_wraplength(card_line1, box, margin=12, minimum=150, maximum=360)

            card_line2 = ttk.Label(
                box,
                text=(
                    f"Saldo fechado {self._money(data['liquido_fechado'])} • "
                    f"Em aberto {self._money(data['em_aberto'])}"
                ),
                style="Card.TLabel", justify="left", wraplength=300,
            )
            card_line2.pack(anchor="w", fill="x")
            self._bind_wraplength(card_line2, box, margin=12, minimum=150, maximum=360)

            roi = (
                f"{data['roi']:.1f}%"
                if data["roi"] is not None
                else "—"
            )
            card_line3 = ttk.Label(
                box,
                text=(
                    f"{data['round_count']} rodada(s) • "
                    f"{data['positivas']} positiva(s) • ROI {roi}"
                ),
                style="Card.TLabel", justify="left", wraplength=300,
            )
            card_line3.pack(anchor="w", fill="x")
            self._bind_wraplength(card_line3, box, margin=12, minimum=150, maximum=360)

        # ------------------- banca + fechamento
        utility = ttk.Frame(
            self.play_body,
            style="Card.TFrame",
            padding=8,
        )
        utility.pack(fill="x", pady=(0,6))

        bankroll = self.db.bankroll_status()

        if bankroll["configured"]:
            start_br = datetime.strptime(
                bankroll["start_date"],
                "%Y-%m-%d",
            ).strftime("%d/%m/%Y")

            bankroll_text = (
                f"Banca desde {start_br}: "
                f"inicial {self._money(bankroll['initial'])} • "
                f"saldo atual {self._money(bankroll['saldo'])} • "
                f"resultado {self._money(bankroll['lucro_liquido'])} • "
                f"em aberto {self._money(bankroll['em_aberto'])}"
            )
        else:
            bankroll_text = (
                "Banca: ainda não configurada. "
                "Ela é opcional e usa somente jogadas reais."
            )

        self.play_bankroll_label = ttk.Label(
            utility,
            text=bankroll_text,
            style="Card.TLabel",
            font=("Segoe UI Semibold", 9),
            justify="left", wraplength=980,
        )
        self.play_bankroll_label.pack(fill="x", anchor="w")
        self._bind_wraplength(self.play_bankroll_label, utility, margin=12, minimum=260)

        closing_actions = ttk.Frame(utility, style="Card.TFrame")
        closing_actions.pack(fill="x", pady=(7, 0))
        ttk.Label(
            closing_actions,
            text="Fechamento:",
            style="Card.TLabel",
        ).pack(side="left", padx=(0,4))

        self.play_closing_date = tk.StringVar(
            value=datetime.now().strftime("%d/%m/%Y")
        )

        ttk.Entry(
            closing_actions,
            textvariable=self.play_closing_date,
            width=11,
        ).pack(side="left")

        ttk.Button(
            closing_actions,
            text="Gerar fechamento do dia",
            command=self.play_show_daily_closing,
        ).pack(side="left", padx=(6,0))

        # ------------------- filtros de histórico
        filters = self.db.financial_filter_options()

        self.play_hist_from = tk.StringVar(
            value=datetime.now().replace(day=1).strftime("%d/%m/%Y")
        )
        self.play_hist_to = tk.StringVar(
            value=datetime.now().strftime("%d/%m/%Y")
        )
        self.play_hist_modality = tk.StringVar(value="Todos")
        self.play_hist_method = tk.StringVar(value="Todos")
        self.play_hist_status = tk.StringVar(value="Todos")

        fbar = ttk.Frame(
            self.play_body,
            style="Card.TFrame",
            padding=7,
        )
        fbar.pack(fill="x", pady=(0,5))

        # Filtros em duas faixas: evita estouro horizontal quando o nome do
        # método é comprido ou a janela está próxima da largura mínima.
        filter_row1 = ttk.Frame(fbar, style="Card.TFrame")
        filter_row1.pack(fill="x")
        for text, var, width in [
            ("De", self.play_hist_from, 11),
            ("Até", self.play_hist_to, 11),
        ]:
            ttk.Label(filter_row1, text=text, style="Card.TLabel").pack(side="left", padx=(0,3))
            ttk.Entry(filter_row1, textvariable=var, width=width).pack(side="left", padx=(0,7))

        ttk.Label(filter_row1, text="Modalidade", style="Card.TLabel").pack(side="left", padx=(0,3))
        ttk.Combobox(
            filter_row1, textvariable=self.play_hist_modality,
            values=filters["modalidades"], width=20, state="readonly",
        ).pack(side="left", padx=(0,7))

        filter_row2 = ttk.Frame(fbar, style="Card.TFrame")
        filter_row2.pack(fill="x", pady=(5, 0))
        ttk.Label(filter_row2, text="Método", style="Card.TLabel").pack(side="left", padx=(0,3))
        ttk.Combobox(
            filter_row2, textvariable=self.play_hist_method,
            values=filters["metodos"], width=34, state="readonly",
        ).pack(side="left", padx=(0,7))
        ttk.Label(filter_row2, text="Status", style="Card.TLabel").pack(side="left", padx=(0,3))
        ttk.Combobox(
            filter_row2, textvariable=self.play_hist_status,
            values=filters["status"], width=12, state="readonly",
        ).pack(side="left", padx=(0,7))
        ttk.Button(
            filter_row2, text="Aplicar", style="Accent.TButton",
            command=self.play_refresh_financial_history,
        ).pack(side="left")

        # ------------------- histórico
        ttk.Label(
            self.play_body,
            text="Histórico financeiro de jogadas reais",
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", pady=(1,3))

        hist_cols = (
            "ticket","rodada","modalidade","metodo",
            "apostado","retorno","liquido","status",
        )
        self.play_financial_tree = ttk.Treeview(
            self.play_body,
            columns=hist_cols,
            show="headings",
            height=7,
        )

        hist_labels = {
            "ticket":"Bilhete",
            "rodada":"Rodada",
            "modalidade":"Modalidade",
            "metodo":"Método",
            "apostado":"Apostado",
            "retorno":"Retorno",
            "liquido":"Líquido",
            "status":"Status",
        }
        hist_widths = {
            "ticket":70,
            "rodada":150,
            "modalidade":170,
            "metodo":280,
            "apostado":85,
            "retorno":85,
            "liquido":85,
            "status":85,
        }

        for c in hist_cols:
            self.play_financial_tree.heading(
                c,
                text=hist_labels[c],
            )
            self.play_financial_tree.column(
                c,
                width=hist_widths[c],
                anchor="w"
                if c in ("rodada","modalidade","metodo")
                else "center",
            )

        for tag, color in (
            ("positive","#22C55E"),
            ("negative","#EF4444"),
            ("pending","#F59E0B"),
        ):
            self.play_financial_tree.tag_configure(
                tag,
                foreground=color,
            )

        self.play_financial_tree.pack(
            fill="x",
            pady=(0,6),
        )

        # ------------------- método x dinheiro
        ttk.Label(
            self.play_body,
            text="Método × desempenho financeiro",
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", pady=(0,3))

        perf_cols = (
            "metodo","fechados","positivos","acertos",
            "apostado","retorno","liquido","roi",
        )
        self.play_method_finance_tree = ttk.Treeview(
            self.play_body,
            columns=perf_cols,
            show="headings",
            height=6,
        )

        perf_labels = {
            "metodo":"Método",
            "fechados":"Fechados",
            "positivos":"Positivos",
            "acertos":"Acertos",
            "apostado":"Apostado",
            "retorno":"Retorno",
            "liquido":"Líquido",
            "roi":"ROI",
        }
        perf_widths = {
            "metodo":350,
            "fechados":70,
            "positivos":70,
            "acertos":70,
            "apostado":90,
            "retorno":90,
            "liquido":90,
            "roi":70,
        }

        for c in perf_cols:
            self.play_method_finance_tree.heading(
                c,
                text=perf_labels[c],
            )
            self.play_method_finance_tree.column(
                c,
                width=perf_widths[c],
                anchor="w" if c == "metodo" else "center",
            )

        for tag, color in (
            ("positive","#22C55E"),
            ("negative","#EF4444"),
        ):
            self.play_method_finance_tree.tag_configure(
                tag,
                foreground=color,
            )

        self.play_method_finance_tree.pack(
            fill="both",
            expand=True,
        )

        self.play_refresh_financial_history()
        self.after_idle(self._play_finalize_layout)

    def play_refresh_financial_history(self):
        if not hasattr(self, "play_financial_tree"):
            return

        try:
            date_from = parse_br_date(
                self.play_hist_from.get()
            )
            date_to = parse_br_date(
                self.play_hist_to.get()
            )

            if not date_from or not date_to:
                raise ValueError(
                    "Informe as datas no formato DD/MM/AAAA."
                )

            if date_from > date_to:
                raise ValueError(
                    "A data inicial não pode ser maior que a final."
                )

        except Exception as exc:
            messagebox.showerror(
                "Histórico financeiro",
                str(exc),
                parent=self,
            )
            return

        for tree in (
            self.play_financial_tree,
            self.play_method_finance_tree,
        ):
            for item in tree.get_children():
                tree.delete(item)

        rows = self.db.financial_history(
            date_from=date_from,
            date_to=date_to,
            modality=self.play_hist_modality.get(),
            method=self.play_hist_method.get(),
            status=self.play_hist_status.get(),
        )

        for idx, row in enumerate(rows):
            if row["status"] == "Aguardando":
                tag = "pending"
            elif row["status"] == "Positivo":
                tag = "positive"
            elif row["status"] == "Negativo":
                tag = "negative"
            else:
                tag = ""

            date_br = datetime.strptime(
                row["data"],
                "%Y-%m-%d",
            ).strftime("%d/%m/%Y")

            round_text = (
                f"{date_br} • {row['sorteio']} "
                f"{row['hora']}"
            ).strip()

            self.play_financial_tree.insert(
                "",
                "end",
                iid=f"hist-{idx}",
                tags=(tag,) if tag else (),
                values=(
                    (
                        f"#{row['bilhete_id']}"
                        if row["bilhete_id"]
                        else "Legado"
                    ),
                    round_text,
                    row["modalidade"],
                    row["metodo"],
                    self._money(row["apostado"]),
                    (
                        self._money(row["retorno"])
                        if row["retorno"] is not None
                        else "—"
                    ),
                    (
                        self._money(row["liquido"])
                        if row["liquido"] is not None
                        else "—"
                    ),
                    row["status"],
                ),
            )

        perf = self.db.method_financial_performance(
            date_from=date_from,
            date_to=date_to,
        )

        for idx, row in enumerate(perf):
            roi = row["roi"]
            tag = (
                "positive"
                if roi is not None and roi > 0
                else (
                    "negative"
                    if roi is not None and roi < 0
                    else ""
                )
            )

            self.play_method_finance_tree.insert(
                "",
                "end",
                iid=f"perf-{idx}",
                tags=(tag,) if tag else (),
                values=(
                    f"{row['seletor']} | {row['estrategia']}",
                    row["fechados"],
                    row["vencedores"],
                    row["acertos"],
                    self._money(row["apostado"]),
                    self._money(row["retorno"]),
                    self._money(row["liquido"]),
                    (
                        f"{roi:.1f}%"
                        if roi is not None
                        else "—"
                    ),
                ),
            )

    def play_configure_bankroll(self):
        current = self.db.bankroll_status()

        initial = simpledialog.askstring(
            "Configurar banca",
            (
                "Informe o valor inicial da banca.\n\n"
                "A Central calcula:\n"
                "banca inicial - apostas + retornos."
            ),
            initialvalue=(
                str(current["initial"]).replace(".", ",")
                if current["configured"]
                else ""
            ),
            parent=self,
        )

        if initial is None:
            return

        start_default = (
            datetime.strptime(
                current["start_date"],
                "%Y-%m-%d",
            ).strftime("%d/%m/%Y")
            if current["configured"]
            else datetime.now().strftime("%d/%m/%Y")
        )

        start = simpledialog.askstring(
            "Início da banca",
            (
                "A partir de qual dia a Central deve considerar "
                "as jogadas para essa banca?"
            ),
            initialvalue=start_default,
            parent=self,
        )

        if start is None:
            return

        try:
            value = self._parse_money(initial)
            start_iso = parse_br_date(start)

            if not start_iso:
                raise ValueError(
                    "Data inválida. Use DD/MM/AAAA."
                )

            self.db.set_bankroll(
                value,
                start_iso,
            )

        except Exception as exc:
            messagebox.showerror(
                "Configurar banca",
                str(exc),
                parent=self,
            )
            return

        self.play_show_summary()

    def play_show_daily_closing(self):
        try:
            date_iso = parse_br_date(
                self.play_closing_date.get()
            )
            if not date_iso:
                raise ValueError(
                    "Data inválida. Use DD/MM/AAAA."
                )

            report = self.db.daily_closing_report(
                date_iso
            )

        except Exception as exc:
            messagebox.showerror(
                "Fechamento do dia",
                str(exc),
                parent=self,
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title("Fechamento do dia")
        dialog.geometry("760x620")
        dialog.minsize(650,520)

        outer = ttk.Frame(self._make_scrollable_page_body(dialog, "daily_closing"), padding=12,
        )
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Fechamento do dia",
            font=("Segoe UI Semibold", 15),
        ).pack(anchor="w")

        text = tk.Text(
            outer,
            wrap="word",
        )
        text.pack(fill="both", expand=True, pady=(7,7))
        text.insert("1.0", report["text"])
        text.configure(state="disabled")

        footer = ttk.Frame(outer)
        footer.pack(fill="x")

        def copy_report():
            self.clipboard_clear()
            self.clipboard_append(
                report["text"]
            )
            self.status.configure(
                text="Fechamento do dia copiado."
            )

        ttk.Button(
            footer,
            text="Copiar",
            command=copy_report,
        ).pack(side="right")

        ttk.Button(
            footer,
            text="Fechar",
            command=dialog.destroy,
        ).pack(side="right", padx=(0,5))

    def play_show_games(
        self,
        select_game_id=None,
        select_ticket_id=None,
    ):
        self.play_view = "games"
        self._set_play_subnav_active("games")
        self._clear_play_body()
        self.play_selected_game_id = None
        self.play_selected_ticket_id = None
        self.play_round_map = {}
        self.play_ticket_history_map = {}

        head = ttk.Frame(self.play_body)
        head.pack(fill="x", pady=(0,5))

        head_top = ttk.Frame(head)
        head_top.pack(fill="x")
        ttk.Label(
            head_top,
            text="Bilhetes",
            font=("Segoe UI Semibold", 14),
        ).pack(side="left")
        head_actions = ttk.Frame(head_top)
        head_actions.pack(side="right")
        ttk.Button(
            head_actions,
            text="Financeiro",
            command=self.play_show_summary,
        ).pack(side="left", padx=(0,5))
        ttk.Button(
            head_actions,
            text="Copiar bilhete",
            command=self.play_copy_selected_ticket,
        ).pack(side="left")
        ttk.Button(
            head_actions,
            text="Excluir bilhete",
            command=self.play_delete_selected_ticket,
        ).pack(side="left", padx=(5, 0))

        today = self.db.financial_summary("today")
        today_label = ttk.Label(
            head,
            text=(
                f"Hoje: {self._money(today['apostado'])} apostados • "
                f"{self._money(today['retorno'])} retornados • "
                f"{self._money(today['em_aberto'])} em aberto"
            ),
            justify="left", wraplength=980,
        )
        today_label.pack(fill="x", anchor="w", pady=(2, 0))
        self._bind_wraplength(today_label, head, margin=8, minimum=220)

        # ------------------------- Rodadas
        round_cols = (
            "alvo",
            "bilhetes",
            "modalidades",
            "apostado",
            "retorno",
            "liquido",
            "status",
        )

        self.play_round_tree = ttk.Treeview(
            self.play_body,
            columns=round_cols,
            show="headings",
            height=4,
            selectmode="browse",
        )

        round_labels = {
            "alvo":"Rodada",
            "bilhetes":"Bilhetes",
            "modalidades":"Modalidades",
            "apostado":"Apostado",
            "retorno":"Retorno",
            "liquido":"Saldo fechado",
            "status":"Status",
        }
        round_widths = {
            "alvo":165,
            "bilhetes":65,
            "modalidades":260,
            "apostado":90,
            "retorno":90,
            "liquido":100,
            "status":90,
        }

        for c in round_cols:
            self.play_round_tree.heading(
                c,
                text=round_labels[c],
            )
            self.play_round_tree.column(
                c,
                width=round_widths[c],
                anchor="w"
                if c in ("alvo","modalidades")
                else "center",
            )

        self.play_round_tree.tag_configure(
            "positive",
            foreground="#22C55E",
        )
        self.play_round_tree.tag_configure(
            "negative",
            foreground="#EF4444",
        )
        self.play_round_tree.tag_configure(
            "pending",
            foreground="#F59E0B",
        )

        self.play_round_tree.pack(
            fill="x",
            pady=(0,4),
        )
        self.play_round_tree.bind(
            "<<TreeviewSelect>>",
            self.play_round_selected,
        )

        # ------------------------- Bilhetes
        ticket_cols = (
            "ticket",
            "modalidades",
            "apostado",
            "retorno",
            "liquido",
            "status",
        )

        self.play_ticket_history_tree = ttk.Treeview(
            self.play_body,
            columns=ticket_cols,
            show="headings",
            height=4,
            selectmode="browse",
        )

        ticket_labels = {
            "ticket":"Bilhete",
            "modalidades":"Modalidades",
            "apostado":"Apostado",
            "retorno":"Retorno",
            "liquido":"Saldo fechado",
            "status":"Status",
        }
        ticket_widths = {
            "ticket":110,
            "modalidades":330,
            "apostado":95,
            "retorno":95,
            "liquido":105,
            "status":90,
        }

        for c in ticket_cols:
            self.play_ticket_history_tree.heading(
                c,
                text=ticket_labels[c],
            )
            self.play_ticket_history_tree.column(
                c,
                width=ticket_widths[c],
                anchor="w"
                if c == "modalidades"
                else "center",
            )

        for tag, color in (
            ("positive","#22C55E"),
            ("negative","#EF4444"),
            ("pending","#F59E0B"),
        ):
            self.play_ticket_history_tree.tag_configure(
                tag,
                foreground=color,
            )

        self.play_ticket_history_tree.pack(
            fill="x",
            pady=(0,4),
        )
        self.play_ticket_history_tree.bind(
            "<<TreeviewSelect>>",
            self.play_ticket_history_selected,
        )

        # ------------------------- Modalidades do bilhete
        game_cols = (
            "id",
            "tipo",
            "metodo",
            "qtd",
            "unit",
            "total",
            "status",
            "acertos",
            "retorno",
            "liquido",
        )

        self.play_games_tree = ttk.Treeview(
            self.play_body,
            columns=game_cols,
            show="headings",
            height=4,
            selectmode="browse",
        )

        game_labels = {
            "id":"#",
            "tipo":"Jogo",
            "metodo":"Método",
            "qtd":"Qtd.",
            "unit":"Valor/unid.",
            "total":"Apostado",
            "status":"Status",
            "acertos":"Acertos",
            "retorno":"Retorno",
            "liquido":"Líquido",
        }
        game_widths = {
            "id":38,
            "tipo":150,
            "metodo":200,
            "qtd":48,
            "unit":82,
            "total":82,
            "status":85,
            "acertos":60,
            "retorno":82,
            "liquido":82,
        }

        for c in game_cols:
            self.play_games_tree.heading(
                c,
                text=game_labels[c],
            )
            self.play_games_tree.column(
                c,
                width=game_widths[c],
                anchor="w"
                if c in ("tipo","metodo")
                else "center",
            )

        for tag, color in (
            ("positive","#22C55E"),
            ("negative","#EF4444"),
            ("pending","#F59E0B"),
        ):
            self.play_games_tree.tag_configure(
                tag,
                foreground=color,
            )

        self.play_games_tree.pack(
            fill="x",
            pady=(0,4),
        )
        self.play_games_tree.bind(
            "<<TreeviewSelect>>",
            self.play_game_selected,
        )

        # Ordem visual solicitada: Rodadas → Jogos da seleção → Bilhetes da rodada.
        # A árvore de jogos era a última; agora fica na segunda linha operacional.
        self.play_round_tree.pack_forget()
        self.play_ticket_history_tree.pack_forget()
        self.play_games_tree.pack_forget()
        self.play_round_tree.pack(fill="x", pady=(0,4))
        self.play_games_tree.pack(fill="x", pady=(0,4))
        self.play_ticket_history_tree.pack(fill="x", pady=(0,4))

        self.play_detail = ttk.Frame(
            self.play_body,
            style="Card.TFrame",
            padding=8,
        )
        self.play_detail.pack(
            fill="both",
            expand=True,
        )

        self.play_refresh_games()

        if select_ticket_id is not None:
            self.play_select_ticket_across_rounds(
                int(select_ticket_id)
            )
        elif select_game_id is not None:
            self.play_select_game_across_rounds(
                int(select_game_id)
            )

        self.after_idle(self._play_finalize_layout)

    def play_refresh_games(self):
        if not hasattr(self, "play_round_tree"):
            return

        for tree in (
            self.play_round_tree,
            self.play_ticket_history_tree,
            self.play_games_tree,
        ):
            for item in tree.get_children():
                tree.delete(item)

        self.play_round_map = {}
        self.play_ticket_history_map = {}

        rounds = self.db.play_round_summaries()

        for idx, row in enumerate(rounds):
            iid = f"round-{idx}"
            self.play_round_map[iid] = row["key"]

            target = {
                "data": row["data"],
                "sorteio": (
                    None
                    if row["sorteio"] == "DIA"
                    else row["sorteio"]
                ),
                "hora": row["hora"],
                "whole_day": row["sorteio"] == "DIA",
            }

            if row["status"] == "Aguardando":
                tag = "pending"
            elif row["liquido_fechado"] > 0:
                tag = "positive"
            elif row["liquido_fechado"] < 0:
                tag = "negative"
            else:
                tag = ""

            self.play_round_tree.insert(
                "",
                "end",
                iid=iid,
                tags=(tag,) if tag else (),
                values=(
                    self._format_target(target),
                    row["ticket_count"],
                    row["modalidades_text"] or "—",
                    self._money(row["apostado"]),
                    self._money(row["retorno"]),
                    self._money(row["liquido_fechado"]),
                    row["status"],
                ),
            )

        if rounds:
            first = self.play_round_tree.get_children()[0]
            self.play_round_tree.selection_set(first)
            self.play_round_tree.focus(first)
            self.play_round_selected()

    def play_round_selected(self, _event=None):
        sel = self.play_round_tree.selection()
        if not sel:
            return

        key = self.play_round_map.get(sel[0])
        if not key:
            return

        for tree in (
            self.play_ticket_history_tree,
            self.play_games_tree,
        ):
            for item in tree.get_children():
                tree.delete(item)

        for child in self.play_detail.winfo_children():
            child.destroy()

        self.play_ticket_history_map = {}

        tickets = self.db.tickets_for_round(key)

        for idx, ticket in enumerate(tickets):
            if ticket.get("legacy"):
                iid = f"legacy-{idx}"
                ticket_label = "Legado"
                map_value = (None, key)
            else:
                iid = f"ticket-{ticket['id']}"
                ticket_label = f"Bilhete #{ticket['id']}"
                map_value = (int(ticket["id"]), key)

            self.play_ticket_history_map[iid] = map_value

            if ticket["status"] == "PENDENTE":
                tag = "pending"
                status = "Aguardando"
            else:
                status = "Finalizado"
                net = float(
                    ticket.get("resultado_liquido") or 0
                )
                tag = (
                    "positive"
                    if net > 0
                    else (
                        "negative"
                        if net < 0
                        else ""
                    )
                )

            self.play_ticket_history_tree.insert(
                "",
                "end",
                iid=iid,
                tags=(tag,) if tag else (),
                values=(
                    ticket_label,
                    ticket.get("modalidades") or "—",
                    self._money(
                        ticket.get("total_apostado")
                    ),
                    self._money(
                        ticket.get("retorno_real")
                    ),
                    self._money(
                        ticket.get("resultado_liquido")
                    ),
                    status,
                ),
            )

        if tickets:
            preferred_id = getattr(
                self,
                "_preferred_ticket_id",
                None,
            )
            if preferred_id is None:
                preferred_id = getattr(
                    self,
                    "play_selected_ticket_id",
                    None,
                )

            preferred_iid = (
                f"ticket-{preferred_id}"
                if preferred_id is not None
                else None
            )

            if (
                preferred_iid
                and self.play_ticket_history_tree.exists(
                    preferred_iid
                )
            ):
                chosen = preferred_iid
            else:
                chosen = (
                    self.play_ticket_history_tree
                    .get_children()[0]
                )

            self._preferred_ticket_id = None
            self.play_ticket_history_tree.selection_set(
                chosen
            )
            self.play_ticket_history_tree.focus(chosen)
            self.play_ticket_history_selected()

    def play_select_game_across_rounds(self, game_id):
        game = self.db.frozen_game_details(
            game_id
        )["game"]
        target = self.db.game_planned_target(game)

        if not target:
            return

        wanted = (
            target.get("data") or "",
            target.get("sorteio") or "DIA",
            target.get("hora") or "",
        )

        for iid, key in self.play_round_map.items():
            if key != wanted:
                continue

            self.play_round_tree.selection_set(iid)
            self.play_round_tree.focus(iid)
            self.play_round_selected()

            if game.get("bilhete_id"):
                target_ticket = (
                    int(game["bilhete_id"])
                )
            else:
                target_ticket = None

            for ticket_iid, mapped in (
                self.play_ticket_history_map.items()
            ):
                ticket_id, _round_key = mapped

                if ticket_id == target_ticket:
                    self.play_ticket_history_tree.selection_set(
                        ticket_iid
                    )
                    self.play_ticket_history_tree.focus(
                        ticket_iid
                    )
                    self.play_ticket_history_selected()

                    if self.play_games_tree.exists(
                        str(game_id)
                    ):
                        self.play_games_tree.selection_set(
                            str(game_id)
                        )
                        self.play_games_tree.focus(
                            str(game_id)
                        )
                        self.play_show_game_detail(
                            game_id
                        )
                    return

    def play_select_ticket_across_rounds(
        self,
        ticket_id,
    ):
        detail = self.db.ticket_details(
            ticket_id
        )
        ticket = detail["ticket"]

        wanted = (
            ticket["alvo_data"],
            ticket["alvo_sorteio"] or "DIA",
            ticket["alvo_hora"] or "",
        )

        for iid, key in self.play_round_map.items():
            if key != wanted:
                continue

            self._preferred_ticket_id = int(ticket_id)
            self.play_selected_ticket_id = int(ticket_id)
            self.play_round_tree.selection_set(iid)
            self.play_round_tree.focus(iid)
            self.play_round_selected()
            return

    def play_delete_selected_ticket(self):
        ticket_id = getattr(self, "play_selected_ticket_id", None)
        if not ticket_id:
            messagebox.showinfo(
                "Excluir bilhete",
                "Selecione um bilhete na lista antes de excluir.",
                parent=self,
            )
            return

        games = self.db.games_for_ticket(ticket_id)
        total = sum(float(game.get("valor_total") or 0) for game in games)
        if not messagebox.askyesno(
            "Excluir bilhete",
            (
                f"Excluir permanentemente o bilhete #{ticket_id}?\n\n"
                f"Modalidades: {len(games)}\n"
                f"Valor registrado: {self._money(total)}\n\n"
                "As jogadas e os palpites ligados a este bilhete também serão removidos.\n"
                "Esta ação não pode ser desfeita."
            ),
            parent=self,
        ):
            return

        try:
            report = self.db.delete_ticket(ticket_id)
        except Exception as exc:
            messagebox.showerror(
                "Excluir bilhete",
                str(exc),
                parent=self,
            )
            return

        if not report.get("deleted"):
            messagebox.showinfo(
                "Excluir bilhete",
                "Esse bilhete já não existe na base.",
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Bilhete excluído",
                (
                    f"Bilhete #{ticket_id} excluído.\n"
                    f"{report.get('games_deleted', 0)} modalidade(s) removida(s)."
                ),
                parent=self,
            )

        self.play_selected_ticket_id = None
        self.play_selected_game_id = None
        self._update_results_nav_badge()
        self.play_refresh_games()
        self.status.configure(text=f"Bilhete #{ticket_id} excluído.")

    def play_ticket_history_selected(self, _event=None):
        sel = self.play_ticket_history_tree.selection()
        if not sel:
            return

        mapped = self.play_ticket_history_map.get(
            sel[0]
        )
        if not mapped:
            return

        ticket_id, round_key = mapped
        self.play_selected_ticket_id = ticket_id

        for item in self.play_games_tree.get_children():
            self.play_games_tree.delete(item)

        for child in self.play_detail.winfo_children():
            child.destroy()

        games = self.db.games_for_ticket(
            ticket_id,
            round_key=round_key,
        )

        for game in games:
            if game.get("jogado"):
                status = (
                    "Aguardando"
                    if game["status"] == "PENDENTE"
                    else "Resultado"
                )
                unit = self._money(
                    game.get("valor_unitario")
                )
                total = self._money(
                    game.get("valor_total")
                )
            else:
                status = (
                    "Congelado"
                    if game["status"] == "PENDENTE"
                    else "Auditado"
                )
                unit = "não informado"
                total = "—"

            modality = game["tipo"]
            if game.get("submodalidade"):
                modality += (
                    f" / {game['submodalidade']}"
                )
            modality += f" • {game['escopo']}"

            if game["status"] == "PENDENTE":
                tag = "pending"
            else:
                net = float(
                    game.get("resultado_liquido") or 0
                )
                tag = (
                    "positive"
                    if net > 0
                    else (
                        "negative"
                        if net < 0
                        else ""
                    )
                )

            self.play_games_tree.insert(
                "",
                "end",
                iid=str(game["id"]),
                tags=(tag,) if tag else (),
                values=(
                    game["id"],
                    modality,
                    game["estrategia"],
                    game["total_itens"],
                    unit,
                    total,
                    status,
                    (
                        f"{game['acertos']}/{game['total_itens']}"
                        if game["status"] == "AUDITADO"
                        else "—"
                    ),
                    (
                        self._money(
                            game.get("retorno_real")
                        )
                        if game.get("retorno_real")
                        is not None
                        else "—"
                    ),
                    (
                        self._money(
                            game.get("resultado_liquido")
                        )
                        if game.get(
                            "resultado_liquido"
                        ) is not None
                        else "—"
                    ),
                ),
            )

        if games:
            first = str(games[0]["id"])
            self.play_games_tree.selection_set(first)
            self.play_games_tree.focus(first)
            self.play_show_game_detail(
                int(first)
            )

    def play_copy_selected_ticket(self):
        sel = self.play_ticket_history_tree.selection()
        if not sel:
            messagebox.showinfo(
                "Copiar bilhete",
                "Selecione um bilhete.",
                parent=self,
            )
            return

        mapped = self.play_ticket_history_map.get(
            sel[0]
        )
        if not mapped:
            return

        ticket_id, round_key = mapped

        try:
            text = self.db.copy_ticket_text(
                ticket_id,
                round_key=round_key,
            )
        except Exception as exc:
            messagebox.showerror(
                "Copiar bilhete",
                str(exc),
                parent=self,
            )
            return

        self.clipboard_clear()
        self.clipboard_append(text)

        self.status.configure(
            text=(
                f"Bilhete #{ticket_id} copiado."
                if ticket_id
                else "Bilhete legado copiado."
            )
        )

    def play_game_selected(self, _event=None):
        sel = self.play_games_tree.selection()
        if not sel:
            return
        self.play_show_game_detail(int(sel[0]))

    def play_show_game_detail(self, game_id):
        self.play_selected_game_id = int(game_id)

        for child in self.play_detail.winfo_children():
            child.destroy()

        analysis = self.db.play_game_analysis(game_id)
        game = analysis["game"]
        target = analysis["target"]
        items = analysis["items"]
        results = analysis["result_rows"]

        top = ttk.Frame(
            self.play_detail,
            style="Card.TFrame",
        )
        top.pack(fill="x", pady=(0,6))

        modality = game["tipo"]
        if game.get("submodalidade"):
            modality += f" / {game['submodalidade']}"

        ticket_prefix = (
            f"Bilhete #{game['bilhete_id']} • "
            if game.get("bilhete_id")
            else ""
        )

        ttk.Label(
            top,
            text=(
                f"{ticket_prefix}Jogo #{game['id']} • "
                f"{modality} • {game['escopo']} • "
                f"{game['estrategia']}"
            ),
            style="Card.TLabel",
            font=("Segoe UI Semibold", 12),
        ).pack(side="left")

        ttk.Label(
            top,
            text=self._format_target(target),
            style="Card.TLabel",
        ).pack(side="right")

        if game.get("jogado"):
            financial = (
                f"Apostado: {self._money(game.get('valor_total'))} • "
                f"{self._money(game.get('valor_unitario'))} por palpite"
            )

            divisor = int(game.get("divisor_posicoes") or 1)

            if divisor > 1:
                financial += (
                    f" • {self._money(game.get('valor_posicao'))} "
                    "por posição"
                )
            elif game["tipo"] in FIXED_PLACEMENT_MODALITIES:
                financial += " • colocação fixa, sem divisão por 5"

            if game["status"] == "PENDENTE":
                if game["tipo"] == "Milhar" and game.get("submodalidade") == "Milhar/Centena":
                    q_cent = float(game.get("cotacao_secundaria") or 0)
                    q_both = float(game.get("cotacao_combinada") or 0)
                    value_pos = float(game.get("valor_posicao") or 0)

                    if game["escopo"] == "1º":
                        financial += (
                            f" • Centena {self._money(value_pos * q_cent)}"
                            f" • Milhar+Centena {self._money(value_pos * q_both)}"
                        )
                    else:
                        financial += (
                            f" • mínimo vencedor {self._money(game.get('retorno_min'))}"
                            f" • máximo 5 posições {self._money(game.get('retorno_max'))}"
                        )

                elif game["tipo"] in FIXED_PLACEMENT_MODALITIES:
                    financial += (
                        f" • por acerto {self._money(game.get('retorno_min'))}"
                    )

                elif game["escopo"] == "1º":
                    financial += (
                        f" • retorno por acerto "
                        f"{self._money(game.get('retorno_min'))}"
                    )

                else:
                    financial += (
                        f" • 1 acerto {self._money(game.get('retorno_min'))}"
                        f" • máximo 5 posições "
                        f"{self._money(game.get('retorno_max'))}"
                    )

            if game["status"] == "AUDITADO":
                if game.get("retorno_real") is not None:
                    financial += (
                        f" • retorno {self._money(game.get('retorno_real'))} "
                        f"• líquido {self._money(game.get('resultado_liquido'))}"
                    )

        else:
            financial = "Valor da aposta: não informado."

        ttk.Label(
            self.play_detail,
            text=financial,
            style="Card.TLabel",
            font=("Segoe UI Semibold", 10),
            wraplength=1120,
        ).pack(anchor="w", pady=(0,6))

        if results:
            result_frame = ttk.Frame(
                self.play_detail,
                style="Card.TFrame",
            )
            result_frame.pack(fill="x", pady=(0,6))

            ttk.Label(
                result_frame,
                text="Resultado:",
                style="Card.TLabel",
                font=("Segoe UI Semibold", 9),
            ).pack(side="left")

            ttk.Label(
                result_frame,
                text="   ".join(
                    f"{r['premio']}º {r['milhar']} {r['bicho']}"
                    for r in results
                ),
                style="Card.TLabel",
            ).pack(side="left", padx=(7,0))
        else:
            ttk.Label(
                self.play_detail,
                text="Resultado ainda não disponível.",
                style="Card.TLabel",
            ).pack(anchor="w", pady=(0,6))

        games_area = ttk.Frame(
            self.play_detail,
            style="Card.TFrame",
        )
        games_area.pack(fill="both", expand=True)

        for i, item in enumerate(items):
            col = i // 4
            row = i % 4

            cell = ttk.Frame(
                games_area,
                style="Card.TFrame",
                padding=(6,4),
            )
            cell.grid(
                row=row,
                column=col,
                sticky="nsew",
                padx=3,
                pady=3,
            )

            if game["status"] == "PENDENTE":
                status_text = "⏳ aguardando"
            elif item["hit"]:
                status_text = (
                    "✓ ACERTOU"
                    + (
                        f" • {item['where']}"
                        if item["where"]
                        else ""
                    )
                )
            else:
                status_text = "✗ não acertou"
                if item["proximity"]:
                    status_text += (
                        f" • {item['proximity']}"
                    )

            ttk.Label(
                cell,
                text=str(item["numero"]),
                style="Card.TLabel",
                font=("Segoe UI Semibold", 13),
            ).pack()

            ttk.Label(
                cell,
                text=status_text,
                style="Card.TLabel",
                font=("Segoe UI", 8),
                wraplength=205,
            ).pack()

        for col in range((len(items) + 3) // 4):
            games_area.grid_columnconfigure(
                col,
                weight=1,
                uniform="playedcols",
            )

        buttons = ttk.Frame(
            self.play_detail,
            style="Card.TFrame",
        )
        buttons.pack(fill="x", pady=(6,0))

        if game["status"] == "PENDENTE":
            ttk.Button(
                buttons,
                text=(
                    "Alterar valor"
                    if game.get("jogado")
                    else "Adicionar valor / marcar como jogado"
                ),
                command=lambda gid=game_id: self.play_add_value(gid),
            ).pack(side="left")

            if game.get("jogado"):
                ttk.Button(
                    buttons,
                    text="Editar jogada",
                    command=lambda gid=game_id: self.play_edit_game(gid),
                ).pack(side="left", padx=(5,0))

        ttk.Button(
            buttons,
            text="Auditar agora",
            command=lambda gid=game_id: self.play_audit_game(gid),
        ).pack(side="left", padx=(5,0))

        ttk.Button(
            buttons,
            text="Cotações",
            command=self.play_open_payout_config,
        ).pack(side="right")

    def play_edit_game(self, game_id):
        EditPlayDialog(
            self,
            self.db,
            int(game_id),
            on_saved=lambda: self.play_after_edit_saved(int(game_id)),
        )

    def play_after_edit_saved(self, game_id):
        self._update_results_nav_badge()
        self.play_refresh_games()
        self.play_select_game_across_rounds(game_id)

    def play_add_value(self, game_id):
        detail = self.db.frozen_game_details(game_id)
        game = detail["game"]

        if game["status"] != "PENDENTE":
            messagebox.showinfo(
                "Valor da jogada",
                "Esse resultado já foi auditado.",
                parent=self,
            )
            return

        submodalidade = game.get("submodalidade")

        if game["tipo"] == "Milhar" and not submodalidade:
            combined = messagebox.askyesno(
                "Modalidade da Milhar",
                (
                    "Essa jogada foi feita como MILHAR/CENTENA?\n\n"
                    "Sim = Milhar/Centena\n"
                    "Não = Milhar simples"
                ),
                parent=self,
            )
            submodalidade = (
                "Milhar/Centena" if combined else "Milhar"
            )

        initial = str(
            game.get("valor_unitario") or "0,20"
        ).replace(".", ",")

        value = simpledialog.askstring(
            "Valor por palpite",
            (
                f"{game['tipo']}"
                + (f" / {submodalidade}" if submodalidade else "")
                + f" • {game['escopo']}\n"
                f"{game['total_itens']} palpite(s)\n\n"
                "Quanto foi apostado em CADA palpite?"
            ),
            initialvalue=initial,
            parent=self,
        )

        if value is None:
            return

        try:
            stake = self._parse_money(value)
            if stake <= 0:
                raise ValueError
        except Exception:
            messagebox.showerror(
                "Valor",
                "Informe um valor maior que zero.",
                parent=self,
            )
            return

        try:
            self.db.mark_frozen_as_played(
                game_id,
                stake,
                submodalidade=submodalidade,
            )
        except Exception as exc:
            messagebox.showerror(
                "Valor da jogada",
                str(exc),
                parent=self,
            )
            self.play_refresh_games()
            return

        self.play_refresh_games()
        self.play_show_game_detail(game_id)

    def play_audit_game(self, game_id):
        result = self.db.audit_frozen_game(game_id)
        self._update_results_nav_badge()

        if result.get("audited"):
            messagebox.showinfo(
                "Auditoria",
                (
                    f"Resultado encontrado.\n"
                    f"{result['hits']}/{result['total']} acerto(s) exato(s)."
                ),
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Auditoria",
                result.get("reason", "Resultado ainda não disponível."),
                parent=self,
            )

        self.play_refresh_games()
        self.play_show_game_detail(game_id)


    def show_results(self):
        self._set_active_nav("Resultados")
        self._clear_content()
        self._page = "results"
        self.results_view = "games"

        self._page_title(
            "Resultados",
            "Atualizações, jogos congelados e desempenho prospectivo.",
        )
        body = self._make_scrollable_page_body(self.content, "results")

        latest = self.db.home_summary()["latest"]

        top = ttk.Frame(
            body,
            style="Card.TFrame",
            padding=8,
        )
        top.pack(fill="x", pady=(0, 6))

        if latest:
            d = datetime.strptime(
                latest["data"], "%Y-%m-%d"
            ).strftime("%d/%m/%Y")
            txt = (
                f"Base até {d} • "
                f"{latest['sorteio']} {latest['hora']}"
            )
        else:
            txt = "Base vazia."

        ttk.Label(
            top,
            text=txt,
            style="Card.TLabel",
            font=("Segoe UI Semibold", 9),
        ).pack(side="left")

        actions = ttk.Frame(
            top, style="Card.TFrame"
        )
        actions.pack(side="right")

        self.update_btn = ttk.Button(
            actions,
            text="Buscar atualizações",
            style="Accent.TButton",
            command=self.start_update_search,
        )
        self.update_btn.pack(side="left")

        ttk.Button(
            actions,
            text="Adicionar manual",
            command=self.open_manual,
        ).pack(side="left", padx=(5, 0))

        ttk.Button(
            actions,
            text="Auditar jogos",
            command=self.results_audit_games,
        ).pack(side="left", padx=(5, 0))

        # Navegação interna, sem abrir nova janela.
        switch = ttk.Frame(body)
        switch.pack(fill="x", pady=(0, 6))

        self.results_games_btn = ttk.Button(
            switch,
            text="Jogos congelados",
            command=self.results_show_games_view,
        )
        self.results_games_btn.pack(side="left")

        self.results_perf_btn = ttk.Button(
            switch,
            text="Desempenho",
            command=self.results_show_performance_view,
        )
        self.results_perf_btn.pack(side="left", padx=(5, 0))

        results_hint = ttk.Label(
            switch,
            text="Desempenho usa somente jogos congelados antes do resultado.",
            justify="left", wraplength=560,
        )
        results_hint.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self._bind_wraplength(results_hint, switch, margin=280, minimum=180, maximum=700)

        self.results_body = ttk.Frame(body)
        self.results_body.pack(fill="both", expand=True)

        self.results_show_games_view()

    def _clear_results_body(self):
        for child in self.results_body.winfo_children():
            child.destroy()

    def results_show_games_view(self):
        self.results_view = "games"
        self._clear_results_body()

        games_head = ttk.Frame(self.results_body)
        games_head.pack(fill="x", pady=(0, 4))

        ttk.Label(
            games_head,
            text="Jogos congelados",
            font=("Segoe UI Semibold", 13),
        ).pack(side="left")

        self.games_summary = ttk.Label(
            games_head, text=""
        )
        self.games_summary.pack(
            side="left", padx=(8, 0)
        )

        ttk.Button(
            games_head,
            text="Detalhes",
            command=self.results_open_game_details,
        ).pack(side="right")

        table = ttk.Frame(self.results_body)
        table.pack(fill="both", expand=True)

        cols = (
            "id","criado","seletor","estrategia","tipo",
            "base","alvo","qtd","acertos","status",
        )
        self.games_tree = ttk.Treeview(
            table,
            columns=cols,
            show="headings",
            selectmode="browse",
        )

        labels = {
            "id":"#",
            "criado":"Criado",
            "seletor":"Seletor",
            "estrategia":"Estratégia",
            "tipo":"Tipo",
            "base":"Base",
            "alvo":"Alvo real",
            "qtd":"Qtd.",
            "acertos":"Acertos",
            "status":"Status",
        }
        widths = {
            "id":42,
            "criado":118,
            "seletor":160,
            "estrategia":150,
            "tipo":70,
            "base":150,
            "alvo":175,
            "qtd":48,
            "acertos":60,
            "status":78,
        }

        for c in cols:
            self.games_tree.heading(
                c, text=labels[c]
            )
            self.games_tree.column(
                c,
                width=widths[c],
                anchor=(
                    "w"
                    if c in (
                        "seletor","estrategia","base","alvo"
                    )
                    else "center"
                ),
            )

        y = ttk.Scrollbar(
            table,
            orient="vertical",
            command=self.games_tree.yview,
        )
        x = ttk.Scrollbar(
            table,
            orient="horizontal",
            command=self.games_tree.xview,
        )
        self.games_tree.configure(
            yscrollcommand=y.set,
            xscrollcommand=x.set,
        )
        self.games_tree.grid(
            row=0,column=0,sticky="nsew"
        )
        y.grid(
            row=0,column=1,sticky="ns"
        )
        x.grid(
            row=1,column=0,sticky="ew"
        )
        table.rowconfigure(
            0, weight=1
        )
        table.columnconfigure(
            0, weight=1
        )

        self.games_tree.bind(
            "<Double-1>",
            self.results_open_game_details,
        )

        self.results_refresh_games()

    def results_show_performance_view(self):
        self.results_view = "performance"
        self._clear_results_body()

        options = self.db.frozen_performance_filter_options()

        self.perf_selector = tk.StringVar(value="Todos")
        self.perf_strategy = tk.StringVar(value="Todos")
        self.perf_kind = tk.StringVar(value="Todos")
        self.perf_scope = tk.StringVar(value="Todos")

        filt = ttk.Frame(
            self.results_body,
            style="Card.TFrame",
            padding=8,
        )
        filt.pack(fill="x", pady=(0, 6))

        controls = [
            (
                "Seletor",
                ttk.Combobox(
                    filt,
                    textvariable=self.perf_selector,
                    values=["Todos"] + options["selectors"],
                    width=23,
                    state="readonly",
                ),
            ),
            (
                "Estratégia",
                ttk.Combobox(
                    filt,
                    textvariable=self.perf_strategy,
                    values=["Todos"] + options["strategies"],
                    width=18,
                    state="readonly",
                ),
            ),
            (
                "Tipo",
                ttk.Combobox(
                    filt,
                    textvariable=self.perf_kind,
                    values=["Todos"] + options["kinds"],
                    width=10,
                    state="readonly",
                ),
            ),
            (
                "Escopo",
                ttk.Combobox(
                    filt,
                    textvariable=self.perf_scope,
                    values=["Todos"] + options["scopes"],
                    width=9,
                    state="readonly",
                ),
            ),
        ]

        for col, (label, widget) in enumerate(controls):
            ttk.Label(
                filt,
                text=label,
                style="Card.TLabel",
            ).grid(
                row=0,column=col,sticky="w",padx=(0,7)
            )
            widget.grid(
                row=1,column=col,sticky="w",padx=(0,7),pady=(2,0)
            )

        ttk.Button(
            filt,
            text="Atualizar",
            style="Accent.TButton",
            command=self.results_refresh_performance,
        ).grid(row=1,column=4,padx=(3,0),pady=(2,0))

        ttk.Button(
            filt,
            text="Limpar",
            command=self.results_clear_performance_filters,
        ).grid(row=1,column=5,padx=(5,0),pady=(2,0))

        cards = ttk.Frame(self.results_body)
        cards.pack(fill="x", pady=(0, 6))

        self.perf_cards = {}

        for key, title in [
            ("audited", "Jogos auditados"),
            ("winners", "Jogos vencedores"),
            ("hits", "Acertos exatos"),
            ("item_rate", "Taxa por item"),
        ]:
            box = ttk.Frame(
                cards,
                style="Card.TFrame",
                padding=(10, 6),
            )
            box.pack(
                side="left",
                fill="x",
                expand=True,
                padx=(0, 5) if key != "item_rate" else 0,
            )

            ttk.Label(
                box,
                text=title,
                style="Card.TLabel",
                font=("Segoe UI", 8),
            ).pack(anchor="w")

            value = ttk.Label(
                box,
                text="0",
                style="Card.TLabel",
                font=("Segoe UI Semibold", 14),
            )
            value.pack(anchor="w")
            self.perf_cards[key] = value

        note = ttk.Frame(self.results_body)
        note.pack(fill="x", pady=(0, 5))

        self.perf_summary = ttk.Label(
            note,
            text="",
        )
        self.perf_summary.pack(side="left", fill="x", expand=True)

        ttk.Label(
            note,
            text="Compare principalmente linhas do mesmo Tipo e Escopo.",
        ).pack(side="right")

        table = ttk.Frame(self.results_body)
        table.pack(fill="both", expand=True)

        cols = (
            "seletor","estrategia","tipo","escopo",
            "total","aud","pend","venc","taxa_jogos",
            "itens","hits","taxa_itens","media",
        )
        self.perf_tree = ttk.Treeview(
            table,
            columns=cols,
            show="headings",
            selectmode="browse",
        )

        labels = {
            "seletor":"Seletor",
            "estrategia":"Estratégia",
            "tipo":"Tipo",
            "escopo":"Escopo",
            "total":"Jogos",
            "aud":"Audit.",
            "pend":"Pend.",
            "venc":"Venc.",
            "taxa_jogos":"% jogos",
            "itens":"Itens",
            "hits":"Acertos",
            "taxa_itens":"% itens",
            "media":"Média/jogo",
        }
        widths = {
            "seletor":180,
            "estrategia":160,
            "tipo":75,
            "escopo":65,
            "total":55,
            "aud":55,
            "pend":55,
            "venc":55,
            "taxa_jogos":65,
            "itens":60,
            "hits":60,
            "taxa_itens":65,
            "media":75,
        }

        for c in cols:
            self.perf_tree.heading(
                c, text=labels[c]
            )
            self.perf_tree.column(
                c,
                width=widths[c],
                anchor="w" if c in ("seletor","estrategia") else "center",
            )

        y = ttk.Scrollbar(
            table,
            orient="vertical",
            command=self.perf_tree.yview,
        )
        x = ttk.Scrollbar(
            table,
            orient="horizontal",
            command=self.perf_tree.xview,
        )
        self.perf_tree.configure(
            yscrollcommand=y.set,
            xscrollcommand=x.set,
        )
        self.perf_tree.grid(
            row=0,column=0,sticky="nsew"
        )
        y.grid(
            row=0,column=1,sticky="ns"
        )
        x.grid(
            row=1,column=0,sticky="ew"
        )
        table.rowconfigure(
            0, weight=1
        )
        table.columnconfigure(
            0, weight=1
        )

        self.results_refresh_performance()

    def results_clear_performance_filters(self):
        self.perf_selector.set("Todos")
        self.perf_strategy.set("Todos")
        self.perf_kind.set("Todos")
        self.perf_scope.set("Todos")
        self.results_refresh_performance()

    def results_refresh_performance(self):
        if not hasattr(self, "perf_tree"):
            return

        data = self.db.frozen_performance(
            selector=self.perf_selector.get(),
            strategy=self.perf_strategy.get(),
            kind=self.perf_kind.get(),
            scope=self.perf_scope.get(),
        )
        summary = data["summary"]

        for item in self.perf_tree.get_children():
            self.perf_tree.delete(item)

        for idx, r in enumerate(data["rows"], start=1):
            self.perf_tree.insert(
                "", "end", iid=f"perf-{idx}",
                values=(
                    r["seletor"],
                    r["estrategia"],
                    r["tipo"],
                    r["escopo"],
                    r["jogos_total"],
                    r["jogos_auditados"],
                    r["jogos_pendentes"],
                    r["jogos_vencedores"],
                    f'{r["taxa_jogos"]:.1f}%',
                    r["itens_auditados"],
                    r["acertos"],
                    f'{r["taxa_itens"]:.2f}%',
                    f'{r["media_acertos"]:.2f}',
                ),
            )

        self.perf_cards["audited"].configure(
            text=str(summary["jogos_auditados"])
        )
        self.perf_cards["winners"].configure(
            text=str(summary["jogos_vencedores"])
        )
        self.perf_cards["hits"].configure(
            text=str(summary["acertos"])
        )
        self.perf_cards["item_rate"].configure(
            text=f'{summary["taxa_itens"]:.2f}%'
        )

        self.perf_summary.configure(
            text=(
                f"{summary['jogos_total']} jogo(s) congelado(s) • "
                f"{summary['jogos_pendentes']} pendente(s) • "
                f"{summary['taxa_jogos']:.1f}% dos jogos auditados "
                f"tiveram ao menos 1 acerto • "
                f"média {summary['media_acertos']:.2f} acerto(s)/jogo."
            )
        )


    def _format_game_date(self, iso_date):
        if not iso_date:
            return "—"
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d/%m/%Y")

    def results_refresh_games(self):
        if not hasattr(self, "games_tree"):
            return

        for item in self.games_tree.get_children():
            self.games_tree.delete(item)

        games = self.db.list_frozen_games()
        pending = 0
        audited = 0

        for g in games:
            if g["status"] == "PENDENTE":
                pending += 1
            else:
                audited += 1

            created = g["criado_em"]
            if created:
                try:
                    created = datetime.fromisoformat(
                        created
                    ).strftime("%d/%m/%Y %H:%M")
                except Exception:
                    pass

            base = self._format_game_date(
                g["base_data"]
            )
            if g["base_sorteio"]:
                base += (
                    f" • {g['base_sorteio']} "
                    f"{g['base_hora']}"
                )

            if g["alvo_data"]:
                target = self._format_game_date(
                    g["alvo_data"]
                )
                if g["alvo_sorteio"]:
                    target += (
                        f" • {g['alvo_sorteio']} "
                        f"{g['alvo_hora']}"
                    )
                else:
                    target += " • dia inteiro 1º"
            else:
                if g["alvo_modo"] == "PROXIMO_DIA_1P":
                    target = "Próximo dia • 1º"
                elif g["alvo_modo"] == "PROXIMA_OPERACIONAL":
                    target = "Próxima rodada operacional"
                else:
                    target = "Próxima extração"

            self.games_tree.insert(
                "",
                "end",
                iid=str(g["id"]),
                values=(
                    g["id"],
                    created,
                    g.get("seletor") or "Não registrado",
                    g["estrategia"],
                    g["tipo"],
                    base,
                    target,
                    g["total_itens"],
                    (
                        f"{g['acertos']}/{g['total_itens']}"
                        if g["status"] == "AUDITADO"
                        else "—"
                    ),
                    g["status"],
                ),
            )

        self.games_summary.configure(
            text=(
                f"{len(games)} total • "
                f"{pending} pendente(s) • "
                f"{audited} auditado(s)"
            )
        )

    def results_audit_games(self):
        report = self.db.audit_frozen_games()
        self._update_results_nav_badge()

        if getattr(self, "results_view", "games") == "performance":
            self.results_show_performance_view()
        else:
            self.results_refresh_games()

        if report["audited_count"]:
            text = (
                f"{report['audited_count']} jogo(s) "
                "auditado(s) agora."
            )
        else:
            text = (
                "Nenhum jogo pendente tinha alvo novo disponível."
            )

        if report["pending_count"]:
            text += (
                f"\n{report['pending_count']} "
                "continua(m) aguardando resultado."
            )

        messagebox.showinfo(
            "Auditoria de jogos",
            text,
            parent=self,
        )

    def results_open_game_details(self, _event=None):
        sel = self.games_tree.selection()
        if not sel:
            messagebox.showinfo(
                "Jogos congelados", "Selecione um jogo primeiro.", parent=self
            )
            return

        FrozenGameDetailsDialog(self, self.db, int(sel[0]))

    def _show_method_guide(self):
        win = tk.Toplevel(self)
        win.title("Como funcionam os métodos — GP-H")
        win.geometry("980x650")
        win.minsize(820, 520)
        win.configure(bg=self.colors["bg"])
        win.transient(self)

        outer = ttk.Frame(self._make_scrollable_page_body(win, "method_guide"), padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Como funcionam os métodos e modelos",
            font=("Segoe UI Semibold", 15),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "Selecione um modelo à esquerda. A descrição informa qual base ele usa, "
                "qual janela histórica entra no cálculo e o que cada camada realmente faz."
            ),
            style="Muted.TLabel",
            wraplength=900,
        ).pack(anchor="w", pady=(2, 10))

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = tk.Listbox(
            body,
            width=34,
            exportselection=False,
            bg=self.colors["card"],
            fg=self.colors["text"],
            selectbackground=self.colors["selection"],
            selectforeground=self.colors["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            font=("Segoe UI", 10),
        )
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        detail = tk.Text(
            body,
            wrap="word",
            bg=self.colors["card"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            padx=14,
            pady=12,
            font=("Segoe UI", 10),
        )
        detail.grid(row=0, column=1, sticky="nsew")
        scroll = ttk.Scrollbar(body, orient="vertical", command=detail.yview)
        scroll.grid(row=0, column=2, sticky="ns")
        detail.configure(yscrollcommand=scroll.set)

        for item in METHOD_GUIDE:
            left.insert("end", item["name"])

        def runtime_context(name):
            try:
                draws = self.db._draws_in_order()
                if not draws:
                    return "Base atual: vazia."

                first = draws[0]
                latest = self.db.latest_operational_draw() or draws[-1]
                first_txt = datetime.strptime(first["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
                latest_txt = datetime.strptime(latest["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
                base_line = (
                    f"Histórico carregado: {first_txt} até {latest_txt}. "
                    f"Última base operacional: {latest_txt} • {latest['sorteio']} {latest['hora']}."
                )

                if name == "GP-H Reset Cobertura v1":
                    idx = self.db._reset_find_draw_index(
                        draws, latest["data"], latest["sorteio"], latest["hora"]
                    )
                    if idx is not None:
                        start_idx = max(0, idx - 240)
                        start_draw = draws[start_idx]
                        start_txt = datetime.strptime(start_draw["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
                        used = idx - start_idx
                        base_line += (
                            f"\nJanela Reset disponível agora: {used} transições, "
                            f"aproximadamente de {start_txt} até a base atual."
                        )

                elif name in (
                    "Puxada Combinada",
                    "Oficial • Reset + Histórica",
                    "Oficial • Reset + 3+1",
                    "Oficial • Reset combinações",
                ):
                    base_line += (
                        "\nEssas camadas consultam o histórico disponível antes/do momento da base "
                        "conforme a regra descrita acima; não existe uma data fixa hard-coded."
                    )

                elif name.startswith("Experimental • Similaridade"):
                    base_line += (
                        f"\nNa próxima geração, o prefixo do dia {latest_txt} até "
                        f"{latest['sorteio']} {latest['hora']} será comparado com dias anteriores compatíveis."
                    )

                elif name == "Especial • Seca do Dia 1º":
                    target = self.db.next_operational_target()
                    if target and target.get("data"):
                        td = datetime.strptime(target["data"], "%Y-%m-%d").date()
                        bd = (td - timedelta(days=1)).strftime("%d/%m/%Y")
                        target_txt = td.strftime("%d/%m/%Y")
                        base_line += (
                            f"\nPara a próxima rodada ({target_txt}), o dia-base da Seca será {bd}."
                        )

                return base_line
            except Exception:
                return "A situação dinâmica da base não pôde ser calculada agora; a regra fixa abaixo continua válida."

        def show_selected(_event=None):
            sel = left.curselection()
            idx = sel[0] if sel else 0
            item = METHOD_GUIDE[idx]
            live = runtime_context(item["name"])
            text = (
                f"{item['name']}\n"
                f"{'=' * len(item['name'])}\n\n"
                f"SITUAÇÃO DA BASE AGORA\n{live}\n\n"
                f"STATUS / USO\n{item['status']}\n\n"
                f"BASE QUE ELE PUXA\n{item['base']}\n\n"
                f"HISTÓRICO / JANELA\n{item['history']}\n\n"
                f"O QUE ELE FAZ\n{item['does']}\n\n"
                f"O QUE ENTREGA\n{item['output']}\n\n"
                f"OBSERVAÇÃO\n{item['note']}"
            )
            detail.configure(state="normal")
            detail.delete("1.0", "end")
            detail.insert("1.0", text)
            detail.configure(state="disabled")

        left.bind("<<ListboxSelect>>", show_selected)
        left.selection_set(0)
        show_selected()

        ttk.Button(
            outer, text="Fechar", command=win.destroy
        ).pack(anchor="e", pady=(10, 0))

    def show_base_config(self):
        self._set_active_nav("Base / Configurações")
        self._clear_content()
        self._page = "base"

        self._page_title(
            "Base / Configurações",
            "Saúde, persistência, backup, importação e revisão da base.",
        )

        base_body = self._make_scrollable_page_body(self.content, "base")

        profile = self.account_profile or {}
        account_box = ttk.Frame(base_body, style="Card.TFrame", padding=10)
        account_box.pack(fill="x", pady=(0, 7))
        account_head = ttk.Frame(account_box, style="Card.TFrame")
        account_head.pack(fill="x")
        ttk.Label(account_head, text="Conta / Perfil", style="Section.TLabel").pack(side="left")
        ttk.Label(
            account_head, text="IDENTIDADE MULTI-PC", style="CardMuted.TLabel"
        ).pack(side="right")
        ttk.Label(
            account_box,
            text=(
                f"Perfil: {profile.get('profile_name', '—')}   •   "
                f"Código: {profile.get('profile_code', '—')}   •   "
                f"Este PC: {profile.get('device_name', '—')}"
            ),
            style="Card.TLabel", wraplength=980, justify="left",
        ).pack(anchor="w", pady=(4, 2))
        sync_enabled = bool(profile.get("sync_enabled") and profile.get("sync_folder"))
        last_sync = profile.get("last_sync_at")
        if last_sync:
            try:
                last_sync_txt = datetime.fromisoformat(str(last_sync)).strftime("%d/%m/%Y %H:%M")
            except Exception:
                last_sync_txt = str(last_sync)
        else:
            last_sync_txt = "nunca"
        if sync_enabled:
            sync_state = profile.get("sync_status") or "configured"
            state_label = {
                "ok": "SINCRONIZADO",
                "running": "SINCRONIZANDO...",
                "error": "ERRO",
            }.get(sync_state, "CONFIGURADO")
            sync_text = (
                f"Sincronização: {state_label} • Última: {last_sync_txt}\n"
                f"Pasta compartilhada: {profile.get('sync_folder')}"
            )
        else:
            sync_text = (
                "Sincronização: somente local. Para ver o mesmo histórico em outro PC, escolha uma pasta "
                "que já seja sincronizada pelo OneDrive, Google Drive ou Dropbox nos dois computadores."
            )
        ttk.Label(
            account_box, text=sync_text,
            style="CardMuted.TLabel", wraplength=980, justify="left",
        ).pack(anchor="w", pady=(0, 7))

        account_actions = ttk.Frame(account_box, style="Card.TFrame")
        account_actions.pack(fill="x")
        account_specs = [
            ("Copiar código", self.account_copy_code),
            ("Editar nome", self.account_edit_name),
            ("Renomear este PC", self.account_rename_device),
            ("Vincular outro perfil", self.account_relink),
            ("Configurar pasta sync", self.account_configure_sync),
            ("Sincronizar agora", lambda: self.account_sync_now(silent=False)),
            ("Ver dispositivos", self.account_show_devices),
            ("Abrir pasta sync", self.account_open_sync_folder),
        ]
        for idx, (text, command) in enumerate(account_specs):
            row, col = divmod(idx, 4)
            ttk.Button(account_actions, text=text, command=command).grid(
                row=row, column=col, sticky="ew",
                padx=(0 if col == 0 else 4, 0), pady=(0 if row == 0 else 4, 0),
            )
        for col in range(4):
            account_actions.grid_columnconfigure(col, weight=1, uniform="accountact")

        account_checks = ttk.Frame(account_box, style="Card.TFrame")
        account_checks.pack(fill="x", pady=(7, 0))
        remember_var = tk.BooleanVar(value=profile.get("remember_login", True))
        ttk.Checkbutton(
            account_checks, text="Manter conectado neste computador", variable=remember_var,
            command=lambda: self.account_set_remember(remember_var.get()),
        ).pack(side="left")
        sync_enabled_var = tk.BooleanVar(value=bool(profile.get("sync_enabled", False)))
        ttk.Checkbutton(
            account_checks, text="Sincronização ativa", variable=sync_enabled_var,
            command=lambda: self.account_set_sync_enabled(sync_enabled_var.get()),
        ).pack(side="left", padx=(14, 0))
        sync_auto_var = tk.BooleanVar(value=bool(profile.get("sync_auto", True)))
        ttk.Checkbutton(
            account_checks, text="Sincronizar automaticamente ao abrir", variable=sync_auto_var,
            command=lambda: self.account_set_sync_auto(sync_auto_var.get()),
        ).pack(side="left", padx=(14, 0))

        update_box = ttk.Frame(base_body, style="Card.TFrame", padding=10)
        update_box.pack(fill="x", pady=(0, 7))
        update_head = ttk.Frame(update_box, style="Card.TFrame")
        update_head.pack(fill="x")
        ttk.Label(update_head, text="Atualizações do programa", style="Section.TLabel").pack(side="left")
        ttk.Label(update_head, text=f"INSTALADA v{APP_VERSION}", style="CardMuted.TLabel").pack(side="right")

        self.program_update_available_var = tk.StringVar()
        self.program_update_status_var = tk.StringVar()
        ttk.Label(
            update_box, textvariable=self.program_update_available_var,
            style="Card.TLabel", font=("Segoe UI Semibold", 10), wraplength=960, justify="left",
        ).pack(anchor="w", pady=(4, 1))
        ttk.Label(
            update_box, textvariable=self.program_update_status_var,
            style="CardMuted.TLabel", wraplength=960, justify="left",
        ).pack(anchor="w", pady=(0, 7))

        update_options = ttk.Frame(update_box, style="Card.TFrame")
        update_options.pack(fill="x", pady=(0, 7))
        ttk.Label(update_options, text="Canal", style="Card.TLabel").pack(side="left")
        channel_var = tk.StringVar(value=self._program_update_channel_label())
        channel_combo = ttk.Combobox(
            update_options, textvariable=channel_var, values=("Estável", "Teste"),
            state="readonly", width=12,
        )
        channel_combo.pack(side="left", padx=(7, 16))
        channel_combo.bind("<<ComboboxSelected>>", lambda _e: self.program_update_set_channel(channel_var.get()))
        auto_update_var = tk.BooleanVar(value=bool(self.program_update_settings.get("auto_check", True)))
        ttk.Checkbutton(
            update_options, text="Verificar automaticamente ao abrir", variable=auto_update_var,
            command=lambda: self.program_update_set_auto_check(auto_update_var.get()),
        ).pack(side="left")

        update_actions = ttk.Frame(update_box, style="Card.TFrame")
        update_actions.pack(fill="x")
        ttk.Button(
            update_actions, text="BUSCAR ATUALIZAÇÃO", style="Accent.TButton",
            command=lambda: self.program_update_check(manual=True),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.program_update_install_btn = ttk.Button(
            update_actions, text="BAIXAR E INSTALAR", style="Accent.TButton",
            command=self.program_update_install_available,
        )
        self.program_update_install_btn.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(
            update_actions, text="Instalar pacote local...",
            command=self.program_update_install_local_package,
        ).grid(row=0, column=2, sticky="ew", padx=4)
        ttk.Button(
            update_actions, text="Restaurar versão anterior",
            command=self.program_update_rollback,
        ).grid(row=0, column=3, sticky="ew", padx=(4, 0))
        ttk.Button(
            update_actions, text="Configurar servidor...",
            command=self.program_update_configure_server,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0), padx=(0, 4))
        ttk.Button(
            update_actions, text="Abrir pasta de atualizações",
            command=self.program_update_open_folder,
        ).grid(row=1, column=2, columnspan=2, sticky="ew", pady=(5, 0), padx=(4, 0))
        for col in range(4):
            update_actions.grid_columnconfigure(col, weight=1, uniform="updateact")
        ttk.Label(
            update_box,
            text=(
                "O atualizador troca somente os arquivos do programa. Histórico, Bilhetes, Financeiro, perfil e configurações "
                "continuam em %LOCALAPPDATA% e não são substituídos. Antes de instalar, a versão anterior é guardada para rollback."
            ),
            style="CardMuted.TLabel", wraplength=960, justify="left",
        ).pack(anchor="w", pady=(7, 0))
        self._refresh_program_update_widgets()

        visual_box = ttk.Frame(base_body, style="Card.TFrame", padding=10)
        visual_box.pack(fill="x", pady=(0, 7))
        ttk.Label(visual_box, text="Aparência", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            visual_box,
            text="Escolha a paleta da Central e, separadamente, o estilo das ilustrações dos 25 bichos. As duas preferências ficam salvas.",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 7))

        theme_row = tk.Frame(visual_box, bg=self.colors["card"])
        theme_row.pack(fill="x")
        for idx, (theme_name, pal) in enumerate(THEME_PALETTES.items()):
            tile = tk.Frame(
                theme_row, bg=self.colors["card2"],
                highlightbackground=self.colors["accent"] if theme_name == self.theme_name else self.colors["border"],
                highlightthickness=2 if theme_name == self.theme_name else 1,
                bd=0, cursor="hand2",
            )
            tile.pack(side="left", fill="x", expand=True, padx=(0 if idx == 0 else 3, 3 if idx < 4 else 0))
            swatches = tk.Frame(tile, bg=self.colors["card2"])
            swatches.pack(fill="x", padx=7, pady=(7, 4))
            for color in (pal["bg"], pal["card"], pal["accent"], pal["success"]):
                tk.Frame(swatches, bg=color, height=8, width=18, bd=0).pack(side="left", fill="x", expand=True, padx=1)
            tk.Label(
                tile, text=theme_name, bg=self.colors["card2"], fg=self.colors["text"],
                font=("Segoe UI Semibold", 8), anchor="w",
            ).pack(fill="x", padx=8)
            tk.Label(
                tile, text="ATUAL" if theme_name == self.theme_name else "Aplicar",
                bg=self.colors["card2"],
                fg=self.colors["accent"] if theme_name == self.theme_name else self.colors["muted"],
                font=("Segoe UI Semibold", 7), anchor="w",
            ).pack(fill="x", padx=8, pady=(1, 7))
            for w in (tile, *tile.winfo_children()):
                w.bind("<Button-1>", lambda _e, n=theme_name: self._set_theme(n))

        ttk.Separator(visual_box, orient="horizontal").pack(fill="x", pady=(10, 8))
        ttk.Label(visual_box, text="Pacote dos bichos", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            visual_box,
            text="Escolha o desenho dos 25 bichos sem alterar o tema da Central. Veja os 25 ou use o botão USAR para trocar.",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 7))

        pack_row = tk.Frame(visual_box, bg=self.colors["card"])
        pack_row.pack(fill="x")
        for col in range(2):
            pack_row.grid_columnconfigure(col, weight=1, uniform="animalpack")

        pack_descriptions = {
            "Natural": "Animais mais fiéis à espécie, com aparência fotográfica e leitura rápida",
            "Cartoon Elegante": "Colorido, expressivo e com contorno mais definido",
            "Semi-realista": "Tons naturais, menos saturação e acabamento mais sóbrio",
            "Minimalista": "Formas simples e claras, sem desaparecer no tema escuro",
        }
        sample_names = {1:"Avestruz", 2:"Águia", 16:"Leão", 19:"Pavão"}

        for idx, pack_name in enumerate(ANIMAL_PACKS):
            selected = pack_name == self.animal_pack_name
            pack_row_idx, pack_col_idx = divmod(idx, 2)
            tile = tk.Frame(
                pack_row, bg=self.colors["card2"],
                highlightbackground=self.colors["accent"] if selected else self.colors["border"],
                highlightthickness=2 if selected else 1, bd=0,
            )
            tile.grid(
                row=pack_row_idx, column=pack_col_idx, sticky="nsew",
                padx=(0 if pack_col_idx == 0 else 4, 4 if pack_col_idx == 0 else 0),
                pady=(0 if pack_row_idx == 0 else 5, 0),
            )

            head = tk.Frame(tile, bg=self.colors["card2"])
            head.pack(fill="x", padx=10, pady=(9, 2))
            tk.Label(
                head, text=pack_name, bg=self.colors["card2"], fg=self.colors["text"],
                font=("Segoe UI Semibold", 10), anchor="w",
            ).pack(side="left")
            if selected:
                tk.Label(
                    head, text="  ATUAL  ", bg=self.colors["accent"], fg="#FFFFFF",
                    font=("Segoe UI Semibold", 7), padx=4, pady=2,
                ).pack(side="right")

            tk.Label(
                tile, text=pack_descriptions[pack_name],
                bg=self.colors["card2"], fg=self.colors["muted"],
                font=("Segoe UI", 7), anchor="w", justify="left",
            ).pack(fill="x", padx=10, pady=(0, 5))

            # Quatro animais GRANDES. A versão anterior usava miniaturas pequenas demais
            # e os três estilos pareciam iguais.
            preview = tk.Frame(tile, bg=self.colors["band"], height=88)
            preview.pack(fill="x", padx=9, pady=(2, 7))
            preview.pack_propagate(False)
            pimages = self.animal_pack_images.get(pack_name, {}).get("large", {})
            for grupo in ANIMAL_SAMPLE_GROUPS:
                sample = tk.Frame(preview, bg=self.colors["band"])
                sample.pack(side="left", fill="both", expand=True)
                img = pimages.get(grupo)
                if img is not None:
                    tk.Label(sample, image=img, bg=self.colors["band"], bd=0).pack(pady=(1, 0))
                tk.Label(
                    sample, text=sample_names[grupo], bg=self.colors["band"],
                    fg=self.colors["muted"], font=("Segoe UI", 6),
                ).pack(pady=(0, 1))

            actions = tk.Frame(tile, bg=self.colors["card2"])
            actions.pack(fill="x", padx=9, pady=(0, 9))
            ttk.Button(
                actions, text="VER OS 25", style="Quiet.TButton",
                command=lambda n=pack_name: self._show_animal_pack_preview(n),
            ).pack(side="left")
            if selected:
                tk.Label(
                    actions, text="SELECIONADO", bg=self.colors["card2"],
                    fg=self.colors["accent"], font=("Segoe UI Semibold", 8),
                ).pack(side="right", padx=6)
            else:
                ttk.Button(
                    actions, text="USAR", style="Accent.TButton",
                    command=lambda n=pack_name: self._set_animal_pack(n),
                ).pack(side="right")

        ttk.Label(
            visual_box,
            text=f"Tema atual: {self.theme_name}   •   Bichos: {self.animal_pack_name}",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(8, 0))

        guide_box = ttk.Frame(base_body, style="Card.TFrame", padding=10)
        guide_box.pack(fill="x", pady=(0, 7))
        guide_head = ttk.Frame(guide_box, style="Card.TFrame")
        guide_head.pack(fill="x")
        ttk.Label(
            guide_head,
            text="Como funcionam os métodos",
            style="Section.TLabel",
        ).pack(side="left")
        ttk.Button(
            guide_head,
            text="ABRIR GUIA COMPLETO",
            style="Accent.TButton",
            command=self._show_method_guide,
        ).pack(side="right")
        ttk.Label(
            guide_box,
            text=(
                "Reset Cobertura • Puxada Combinada • Reset + Histórica • Reset + 3+1 • "
                "Reset combinações • Similaridade • Seca do Dia • Manual. "
                "O guia mostra a base usada, janela histórica, cálculo e saída de cada modelo."
            ),
            style="CardMuted.TLabel",
            wraplength=940,
        ).pack(anchor="w", pady=(3, 0))

        health = self.db.base_health()
        audit = health["audit"]
        latest = self.db.latest_draw()
        result_count = self.db.count()
        game_count = self.db.game_count()

        if latest:
            latest_txt = (
                datetime.strptime(
                    latest["data"], "%Y-%m-%d"
                ).strftime("%d/%m/%Y")
                + f" • {latest['sorteio']} {latest['hora']}"
            )
        else:
            latest_txt = "Base vazia"

        health_box = ttk.Frame(
            base_body,
            style="Card.TFrame",
            padding=10,
        )
        health_box.pack(fill="x", pady=(0, 7))

        ttk.Label(
            health_box,
            text=f"Saúde da base: {health['state']}",
            style="Card.TLabel",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")

        ttk.Label(
            health_box,
            text=(
                f"{result_count:,} prêmio(s) • "
                f"{audit['draws']:,} extração(ões) • "
                f"{game_count} jogo(s) congelado(s) • "
                f"{health['pending_games']} pendente(s) • "
                f"último: {latest_txt}"
            ).replace(",", "."),
            style="Card.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        ttk.Label(
            health_box,
            text=(
                f"Incompletas: {len(audit['incomplete'])} • "
                f"Possíveis lacunas operacionais: "
                f"{health['possible_gap_count']} • "
                f"Problemas estruturais: {len(audit['problems'])}"
            ),
            style="Card.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        if health["last_network_check"]:
            try:
                check_dt = datetime.fromisoformat(
                    health["last_network_check"]
                ).strftime("%d/%m/%Y %H:%M")
            except Exception:
                check_dt = health["last_network_check"]

            ttk.Label(
                health_box,
                text=(
                    f"Última consulta: {check_dt} • "
                    f"{health['last_network_check_type'] or '—'} • "
                    f"{health['last_network_errors']} falha(s) de acesso. "
                    "Falha de acesso não significa resultado ausente."
                ),
                style="Card.TLabel",
                wraplength=950,
            ).pack(anchor="w", pady=(2, 0))

        info = ttk.Frame(
            base_body,
            style="Card.TFrame",
            padding=10,
        )
        info.pack(fill="x", pady=(0, 7))

        ttk.Label(
            info,
            text="Base compartilhada",
            style="Card.TLabel",
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w")

        ttk.Label(
            info,
            text=str(DB_PATH),
            style="Card.TLabel",
            wraplength=950,
        ).pack(anchor="w", pady=(2, 0))

        if self.startup_migration_report.get("mensagem"):
            ttk.Label(
                info,
                text=self.startup_migration_report["mensagem"],
                style="Card.TLabel",
                wraplength=950,
            ).pack(anchor="w", pady=(4, 0))

        # Diagnóstico pré-EXE: caminhos e persistência ficam visíveis para facilitar suporte e atualização.
        latest_backup = self._latest_auto_backup()
        latest_backup_txt = "Nenhum backup automático encontrado"
        if latest_backup:
            try:
                latest_backup_txt = (
                    datetime.fromtimestamp(latest_backup.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                    + f" • {latest_backup.name}"
                )
            except Exception:
                latest_backup_txt = latest_backup.name

        diag_box = ttk.Frame(base_body, style="Card.TFrame", padding=10)
        diag_box.pack(fill="x", pady=(0, 7))
        ttk.Label(diag_box, text="Diagnóstico / Pré-EXE", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            diag_box,
            text=(
                f"Versão {APP_VERSION} • Banco: {DB_PATH}\n"
                f"Dados persistentes: {DATA_DIR}\n"
                f"Último backup automático: {latest_backup_txt}"
            ),
            style="CardMuted.TLabel",
            wraplength=980,
            justify="left",
        ).pack(anchor="w", pady=(3, 7))
        diag_actions = ttk.Frame(diag_box, style="Card.TFrame")
        diag_actions.pack(fill="x")
        diag_specs = [
            ("Abrir pasta de dados", self.base_open_data_folder),
            ("Abrir logs", self.base_open_log_folder),
            ("Copiar diagnóstico", self.base_copy_diagnostics),
            ("Sobre a Central", self._show_about),
        ]
        for idx, (text, command) in enumerate(diag_specs):
            row, col = divmod(idx, 2)
            ttk.Button(diag_actions, text=text, command=command).grid(
                row=row, column=col, sticky="ew", padx=(0 if col == 0 else 4, 4 if col == 0 else 0),
                pady=(0 if row == 0 else 4, 0),
            )
        diag_actions.grid_columnconfigure(0, weight=1, uniform="diagact")
        diag_actions.grid_columnconfigure(1, weight=1, uniform="diagact")

        actions = ttk.Frame(
            base_body,
            style="Card.TFrame",
            padding=10,
        )
        actions.pack(fill="x", pady=(0, 7))

        action_specs = [
            ("Revisar base", self.show_audit),
            ("Verificar lacunas", self.base_verify_gaps),
            ("Sincronizar 2026 inteiro", self.start_sync),
            ("Fazer backup", self.base_backup),
            ("Tabela de prêmios", lambda: PayoutConfigDialog(self, self.db)),
            ("Importar / mesclar banco", self.base_import_database),
        ]
        for idx, (text, command) in enumerate(action_specs):
            row, col = divmod(idx, 3)
            btn = ttk.Button(actions, text=text, command=command)
            btn.grid(
                row=row, column=col, sticky="ew",
                padx=(0 if col == 0 else 4, 4 if col < 2 else 0),
                pady=(0 if row == 0 else 5, 0),
            )
            if text == "Sincronizar 2026 inteiro":
                self.sync_btn = btn
        for col in range(3):
            actions.grid_columnconfigure(col, weight=1, uniform="baseact")

        ttk.Label(
            base_body,
            text=(
                "“Possível lacuna” é um horário esperado pelo calendário "
                "operacional que não apareceu na base. Feriados ou mudanças "
                "excepcionais podem explicar alguns casos; por isso a Central "
                "não transforma isso automaticamente em erro."
            ),
            wraplength=930,
            padding=(0, 6, 0, 0),
        ).pack(anchor="w")

    def _auto_decision_cycle(self):
        try:
            if self.db.count() == 0:
                return
            self.db.audit_decision_snapshots()
            target = self.db.next_operational_target()
            if target and not self.db.get_draw(target["data"], target["sorteio"], target["hora"]):
                self.db.freeze_decision_snapshot(force=False)
        except Exception:
            # Falta de amostra não deve interromper a abertura da Central.
            return

    @staticmethod
    def _decision_target_text(snapshot):
        if not snapshot:
            return "—"
        try:
            d = datetime.strptime(snapshot["target_data"], "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            d = snapshot.get("target_data") or "—"
        return f"{snapshot.get('target_sorteio','—')} {snapshot.get('target_hora','—')} • {d}"

    @staticmethod
    def _shadow_lab_target_label(target):
        if not target:
            return "—"
        try:
            d = datetime.strptime(str(target.get("data") or ""), "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            d = str(target.get("data") or "—")
        return f"{d} • {target.get('sorteio','—')} {target.get('hora','—')}"

    def _build_shadow_lab_section(self, body):
        """Laboratório Sombra incorporado à Central de Decisão."""
        try:
            self.db.audit_shadow_snapshots()
            self.db.ensure_shadow_snapshot(trigger="ABRIR_DECISAO")
        except Exception:
            pass

        lab_intro = ttk.Frame(body, style="Card.TFrame", padding=11)
        lab_intro.pack(fill="x", pady=(4, 8))
        ttk.Label(lab_intro, text="LABORATÓRIO SOMBRA", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            lab_intro,
            text=(
                "Área experimental da própria Decisão: leituras congeladas antes do resultado, "
                "comparação prospectiva de Centenas/Puxadas e Seca exclusiva do 1º prêmio. "
                "Nada aqui promove método automaticamente."
            ),
            style="CardMuted.TLabel", wraplength=1080, justify="left",
        ).pack(anchor="w", pady=(3, 0))


        controls = ttk.Frame(body, style="Card.TFrame", padding=10)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(controls, text="RODADA ANALISADA", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(controls, text="ESCOPO", style="CardMuted.TLabel").grid(row=0, column=1, sticky="w", padx=(10,0))
        ttk.Label(controls, text="JANELA", style="CardMuted.TLabel").grid(row=0, column=2, sticky="w", padx=(10,0))

        self.shadow_lab_target_var = tk.StringVar()
        self.shadow_lab_scope_var = tk.StringVar(value="1º")
        self.shadow_lab_window_var = tk.StringVar(value="120")
        self.shadow_lab_target_map = {}
        targets = self.db.future_operational_targets(14)
        target_values = []
        for target in targets:
            label = self._shadow_lab_target_label(target)
            self.shadow_lab_target_map[label] = dict(target)
            target_values.append(label)
        cb_target = ttk.Combobox(
            controls, textvariable=self.shadow_lab_target_var,
            values=target_values, state="readonly", width=34,
        )
        cb_target.grid(row=1, column=0, sticky="ew", pady=(3,0))
        cb_scope = ttk.Combobox(
            controls, textvariable=self.shadow_lab_scope_var,
            values=["1º", "1º–5º"], state="readonly", width=10,
        )
        cb_scope.grid(row=1, column=1, sticky="w", padx=(10,0), pady=(3,0))
        cb_window = ttk.Combobox(
            controls, textvariable=self.shadow_lab_window_var,
            values=["30", "60", "120"], state="readonly", width=8,
        )
        cb_window.grid(row=1, column=2, sticky="w", padx=(10,0), pady=(3,0))
        ttk.Button(
            controls, text="ATUALIZAR", style="Accent.TButton",
            command=self._shadow_lab_refresh,
        ).grid(row=1, column=3, sticky="e", padx=(12,0), pady=(3,0))
        controls.columnconfigure(0, weight=1)

        next_target = self.db.next_operational_target() or {}
        next_label = self._shadow_lab_target_label(next_target)
        if next_label in self.shadow_lab_target_map:
            self.shadow_lab_target_var.set(next_label)
        elif target_values:
            self.shadow_lab_target_var.set(target_values[0])

        for cb in (cb_target, cb_scope, cb_window):
            cb.bind("<<ComboboxSelected>>", lambda _e: self._shadow_lab_refresh())

        info = ttk.Frame(body, style="Card.TFrame", padding=10)
        info.pack(fill="x", pady=(0,8))
        ttk.Label(info, text="Como esta camada é tratada", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            info,
            text=(
                "Puxadas de Bicho e Seca do Dia entram como leituras experimentais. "
                "A Puxada é comparada prospectivamente com Reset e Similaridade; a Seca é medida somente no 1º prêmio. "
                "Nada aqui altera automaticamente o método oficial nem cria mensagens retrospectivas de arrependimento."
            ),
            style="CardMuted.TLabel", wraplength=1080, justify="left",
        ).pack(anchor="w", pady=(4,0))

        self.shadow_lab_results = ttk.Frame(body)
        self.shadow_lab_results.pack(fill="both", expand=True)
        self._shadow_lab_refresh()

    def show_shadow_lab_page(self):
        """Compatibilidade: o antigo Laboratório agora abre a tela única de Decisão."""
        self.show_decision_page(open_lab=True)

    def _shadow_lab_selected_target(self):
        return dict(self.shadow_lab_target_map.get(self.shadow_lab_target_var.get()) or {})

    def _shadow_lab_refresh(self):
        host = getattr(self, "shadow_lab_results", None)
        if host is None or not host.winfo_exists():
            return
        for child in host.winfo_children():
            child.destroy()

        target = self._shadow_lab_selected_target()
        if not target:
            ttk.Label(host, text="Não há rodada operacional disponível para análise.", style="Sub.TLabel").pack(anchor="w")
            return
        try:
            self.db.audit_shadow_snapshots()
            # Só a próxima rodada pode ser congelada; chamadas para alvos posteriores são ignoradas pelo banco.
            self.db.ensure_shadow_snapshot(target=target, trigger="LABORATORIO")
            window = int(self.shadow_lab_window_var.get() or 120)
            scope = self.shadow_lab_scope_var.get() or "1º"
            rec = self.db.shadow_recommendation(target, window=window, scope=scope)
            status = self.db.shadow_lab_status(target)
        except Exception as exc:
            ttk.Label(host, text=f"Não foi possível montar o laboratório: {exc}", style="Sub.TLabel", wraplength=1000).pack(anchor="w")
            return

        current = status.get("current") or {}
        state = current.get("status") or "AINDA NÃO CONGELADA"
        summary = ttk.Frame(host, style="Card.TFrame", padding=11)
        summary.pack(fill="x", pady=(0,8))
        summary.columnconfigure(0, weight=1)
        ttk.Label(summary, text="LEITURA PROSPECTIVA", style="CardMuted.TLabel").grid(row=0,column=0,sticky="w")
        ttk.Label(
            summary, text=self._shadow_lab_target_label(target), style="Card.TLabel",
            font=("Segoe UI Semibold", 15),
        ).grid(row=1,column=0,sticky="w",pady=(2,2))
        ttk.Label(
            summary,
            text=f"Estado da rodada: {state} • {int(status.get('audited') or 0)} leitura(s) auditada(s) deste horário • {int(status.get('pending') or 0)} pendente(s)",
            style="CardMuted.TLabel", wraplength=860,
        ).grid(row=2,column=0,sticky="w")
        ttk.Label(summary, text=f"Escopo {scope} • janela até {window} rodadas", style="CardMuted.TLabel").grid(row=0,column=1,sticky="e",padx=(15,0))

        # v0.35.2 — leitura atual congelada para a próxima rodada.
        # Apenas apresenta os sinais já gravados prospectivamente; não altera métodos.
        payload_now = current.get("payload") or {}
        current_box = ttk.Frame(host, style="Card.TFrame", padding=10)
        current_box.pack(fill="x", pady=(0,8))
        ttk.Label(current_box, text="LEITURA ATUAL CONGELADA", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            current_box,
            text="Sinais que já estavam congelados para esta rodada antes do resultado. A convergência abaixo é somente contagem transparente entre métodos disponíveis.",
            style="CardMuted.TLabel", wraplength=1050,
        ).pack(anchor="w", pady=(2,6))

        def _shadow_fmt_groups(values):
            out=[]
            for raw in values or []:
                try:
                    g=int(raw)
                except Exception:
                    continue
                if 1 <= g <= 25:
                    out.append(f"{g:02d} {BICHOS.get(g, str(g)).title()}")
            return " • ".join(out) if out else "Sem leitura disponível"

        bichos_now = payload_now.get("bichos") or {}
        method_sets = []
        for method_name in ("Reset Cobertura", "Puxada Combinada", "Similaridade"):
            method_payload = bichos_now.get(method_name) or {}
            groups_now = []
            for raw in method_payload.get("groups") or []:
                try:
                    g=int(raw)
                except Exception:
                    continue
                if 1 <= g <= 25 and g not in groups_now:
                    groups_now.append(g)
            groups_now = groups_now[:5]
            if groups_now:
                method_sets.append((method_name, set(groups_now)))
                ttk.Label(
                    current_box,
                    text=f"{method_name}: {_shadow_fmt_groups(groups_now)}",
                    style="Card.TLabel", wraplength=1050, justify="left",
                ).pack(anchor="w", pady=(1,0))
            else:
                ttk.Label(
                    current_box,
                    text=f"{method_name}: Sem leitura disponível",
                    style="CardMuted.TLabel", wraplength=1050, justify="left",
                ).pack(anchor="w", pady=(1,0))

        convergence = Counter()
        for _method_name, group_set in method_sets:
            convergence.update(group_set)
        shared = sorted(
            ((g,c) for g,c in convergence.items() if c >= 2),
            key=lambda item: (-item[1], item[0]),
        )
        available_methods = len(method_sets)
        if shared:
            conv_text = " • ".join(
                f"{g:02d} {BICHOS.get(g, str(g)).title()} ({count}/{available_methods})"
                for g,count in shared
            )
        elif available_methods >= 2:
            conv_text = "Nenhum bicho apareceu em pelo menos 2 métodos nesta leitura."
        else:
            conv_text = "Ainda não há métodos suficientes disponíveis para medir convergência."
        ttk.Label(
            current_box,
            text=f"Convergência: {conv_text}",
            style="CardMuted.TLabel", wraplength=1050, justify="left",
        ).pack(anchor="w", pady=(5,0))

        dry_now = ((payload_now.get("seca_1p") or {}).get("Seca do Dia 1º") or {})
        dry_groups_now = []
        for raw in dry_now.get("groups") or []:
            try:
                g=int(raw)
            except Exception:
                continue
            if 1 <= g <= 25 and g not in dry_groups_now:
                dry_groups_now.append(g)
        ttk.Label(
            current_box,
            text=f"Seca do Dia • 1º prêmio: {_shadow_fmt_groups(dry_groups_now[:5])}",
            style="Card.TLabel" if dry_groups_now else "CardMuted.TLabel",
            wraplength=1050, justify="left",
        ).pack(anchor="w", pady=(5,0))

        # Três blocos principais: Centenas, Puxadas/Bichos e Seca 1º.
        cards = ttk.Frame(host)
        cards.pack(fill="x", pady=(0,8))
        for i in range(3):
            cards.columnconfigure(i, weight=1, uniform="shadowcards")

        cent = rec.get("centena") or {}
        cent_best = cent.get("best") or {}
        c1 = ttk.Frame(cards, style="Card.TFrame", padding=10)
        c1.grid(row=0,column=0,sticky="nsew",padx=(0,4))
        ttk.Label(c1,text="CENTENAS",style="CardMuted.TLabel").pack(anchor="w")
        ttk.Label(c1,text=cent_best.get("name") or "Sem evidência suficiente",style="Card.TLabel",font=("Segoe UI Semibold",11),wraplength=310).pack(anchor="w",pady=(3,1))
        ttk.Label(c1,text=f"Evidência: {cent.get('status','SEM DADOS')}",style="CardMuted.TLabel").pack(anchor="w")
        if cent_best:
            ttk.Label(c1,text=f"{int(cent_best.get('rounds') or 0)} rodadas • {float(cent_best.get('win_rate') or 0):.1f}% com acerto",style="CardMuted.TLabel",wraplength=310).pack(anchor="w",pady=(2,0))

        bichos = rec.get("bichos") or {}
        bbest = bichos.get("best") or {}
        c2 = ttk.Frame(cards, style="Card.TFrame", padding=10)
        c2.grid(row=0,column=1,sticky="nsew",padx=4)
        ttk.Label(c2,text="PUXADAS / BICHOS",style="CardMuted.TLabel").pack(anchor="w")
        ttk.Label(c2,text=bbest.get("name") or "Sem evidência suficiente",style="Card.TLabel",font=("Segoe UI Semibold",11),wraplength=310).pack(anchor="w",pady=(3,1))
        ttk.Label(c2,text=f"Evidência: {bichos.get('status','SEM DADOS')}",style="CardMuted.TLabel").pack(anchor="w")
        if bbest:
            if scope == "1º":
                metric = f"{float(bbest.get('avg_coverage') or 0)*100:.1f}% de acerto do 1º"
            else:
                metric = f"cobertura média {float(bbest.get('avg_coverage') or 0):.2f}/5"
            ttk.Label(c2,text=f"{int(bbest.get('rounds') or 0)} rodadas • {metric}",style="CardMuted.TLabel",wraplength=310).pack(anchor="w",pady=(2,0))

        dry = rec.get("seca_1p") or {}
        c3 = ttk.Frame(cards, style="Card.TFrame", padding=10)
        c3.grid(row=0,column=2,sticky="nsew",padx=(4,0))
        ttk.Label(c3,text="SECA DO DIA • 1º",style="CardMuted.TLabel").pack(anchor="w")
        ttk.Label(c3,text="Seca do Dia 1º",style="Card.TLabel",font=("Segoe UI Semibold",11)).pack(anchor="w",pady=(3,1))
        ttk.Label(c3,text=f"Evidência: {dry.get('status','SEM DADOS')}",style="CardMuted.TLabel").pack(anchor="w")
        if int(dry.get("rounds") or 0):
            ttk.Label(c3,text=f"{int(dry.get('rounds') or 0)} rodadas • {float(dry.get('hit_rate') or 0):.1f}% de acerto do 1º",style="CardMuted.TLabel",wraplength=310).pack(anchor="w",pady=(2,0))
        else:
            ttk.Label(c3,text="Amostra ainda em formação.",style="CardMuted.TLabel").pack(anchor="w",pady=(2,0))

        # Ranking transparente dos seletores de bicho.
        rank = ttk.Frame(host, style="Card.TFrame", padding=10)
        rank.pack(fill="x", pady=(0,8))
        ttk.Label(rank,text="Ranking prospectivo dos seletores de bicho",style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(rank,text="Reset, Puxada Combinada e Similaridade são comparados nas mesmas leituras sombra disponíveis para este horário.",style="CardMuted.TLabel",wraplength=1050).pack(anchor="w",pady=(2,5))
        cols=("method","rounds","main","recent")
        tv=ttk.Treeview(rank,columns=cols,show="headings",height=max(3,min(5,len(bichos.get('rows') or []))))
        heads={"method":"Método","rounds":"Rodadas","main":"Métrica geral","recent":"Recente"}
        widths={"method":250,"rounds":80,"main":160,"recent":160}
        for cc in cols:
            tv.heading(cc,text=heads[cc]); tv.column(cc,width=widths[cc],anchor="w" if cc=="method" else "center")
        for row in bichos.get("rows") or []:
            if scope == "1º":
                main=f"{float(row.get('avg_coverage') or 0)*100:.1f}% 1º"
                recent=f"{float(row.get('recent_avg') or 0)*100:.1f}% 1º"
            else:
                main=f"{float(row.get('avg_coverage') or 0):.2f}/5"
                recent=f"{float(row.get('recent_avg') or 0):.2f}/5"
            tv.insert("","end",values=(row.get("name"),int(row.get("rounds") or 0),main,recent))
        tv.pack(fill="x")

        cent_rank = ttk.Frame(host, style="Card.TFrame", padding=10)
        cent_rank.pack(fill="x", pady=(0,8))
        ttk.Label(cent_rank,text="Ranking prospectivo das Centenas",style="CardTitle.TLabel").pack(anchor="w")
        ccols=("method","rounds","rate","recent","avg")
        ctv=ttk.Treeview(cent_rank,columns=ccols,show="headings",height=max(4,min(6,len(cent.get('rows') or []))))
        cheads={"method":"Construção","rounds":"Rodadas","rate":"Acerto","recent":"Recente","avg":"Média de acertos"}
        cwidths={"method":260,"rounds":80,"rate":120,"recent":120,"avg":130}
        for cc in ccols:
            ctv.heading(cc,text=cheads[cc]); ctv.column(cc,width=cwidths[cc],anchor="w" if cc=="method" else "center")
        for row in cent.get("rows") or []:
            ctv.insert("","end",values=(
                row.get("name"), int(row.get("rounds") or 0),
                f"{float(row.get('win_rate') or 0):.1f}%", f"{float(row.get('recent_rate') or 0):.1f}%",
                f"{float(row.get('avg_hits') or 0):.2f}",
            ))
        ctv.pack(fill="x")

        ttk.Label(
            host,
            text="O laboratório mede evidência prospectiva e estabilidade. Ele não transforma desempenho histórico em garantia de prêmio e não promove método automaticamente.",
            style="Sub.TLabel", wraplength=1080,
        ).pack(anchor="w", pady=(0,10))

    def show_decision_page(self, open_lab=False):
        self._set_active_nav("Decisão")
        self._clear_content()
        self._page = "decision"
        try:
            self.db.audit_decision_snapshots()
            snapshot, _created = self.db.freeze_decision_snapshot(force=False)
        except Exception as exc:
            snapshot = self.db.latest_decision_snapshot()
            error = str(exc)
        else:
            error = ""

        self._page_title(
            "Central de Decisão",
            "Visão da rodada, convergência, desempenho prospectivo e Laboratório Sombra em uma única tela. O índice não é probabilidade de prêmio.",
        )
        body = self._make_scrollable_page_body(self.content, "decision")

        hero = ttk.Frame(body, style="Card.TFrame", padding=12)
        hero.pack(fill="x", pady=(0, 8))
        hero.columnconfigure(0, weight=1)
        ttk.Label(hero, text="PRÓXIMA RODADA", style="CardMuted.TLabel").grid(row=0,column=0,sticky="w")
        ttk.Label(
            hero, text=self._decision_target_text(snapshot), style="Card.TLabel",
            font=("Segoe UI Semibold", 16),
        ).grid(row=1,column=0,sticky="w",pady=(2,4))

        if snapshot:
            score = float(snapshot.get("confidence_score") or 0)
            conf = f"{score:.0f}/100 • {snapshot.get('confidence_label') or '—'}"
            rec = snapshot.get("recommendation") or "—"
        else:
            conf, rec = "—", "Sem leitura congelada"
        ttk.Label(hero, text="ÍNDICE DE CONSISTÊNCIA", style="CardMuted.TLabel").grid(row=0,column=1,sticky="e",padx=(16,0))
        ttk.Label(hero, text=conf, style="Card.TLabel", font=("Segoe UI Semibold", 18)).grid(row=1,column=1,sticky="e",padx=(16,0))
        ttk.Label(hero, text=rec, style="CardMuted.TLabel").grid(row=2,column=1,sticky="e",padx=(16,0))
        if error:
            ttk.Label(hero, text=f"Observação: {error}", style="CardMuted.TLabel", wraplength=900).grid(row=3,column=0,columnspan=2,sticky="w",pady=(7,0))

        if not snapshot:
            return

        # Componentes transparentes do índice.
        components = snapshot.get("components") or {}
        comp_card = ttk.Frame(body, style="Card.TFrame", padding=10)
        comp_card.pack(fill="x", pady=(0,8))
        ttk.Label(comp_card, text="Por que esse índice?", style="CardTitle.TLabel").pack(anchor="w")
        comp_row = ttk.Frame(comp_card, style="Card.TFrame")
        comp_row.pack(fill="x", pady=(7,0))
        comp_defs = [
            ("Convergência", components.get("convergence", 0), "acordo entre fontes diferentes"),
            ("Força do Reset", components.get("reset_strength", 0), "força + separação do ranking oficial"),
            ("Suporte", components.get("context_support", 0), "janela e contexto histórico"),
            ("Evidência", components.get("prospective_evidence", 0), f"{int(components.get('prospective_rounds') or 0)} rodada(s) congelada(s)"),
        ]
        for i,(title,value,sub) in enumerate(comp_defs):
            card = ttk.Frame(comp_row, style="Card2.TFrame", padding=8)
            card.pack(side="left", fill="x", expand=True, padx=(0,6 if i<3 else 0))
            ttk.Label(card,text=title,style="CardMuted.TLabel").pack(anchor="w")
            ttk.Label(card,text=f"{float(value):.0f}/100",style="Card.TLabel",font=("Segoe UI Semibold",13)).pack(anchor="w")
            ttk.Label(card,text=sub,style="CardMuted.TLabel",wraplength=210).pack(anchor="w")

        # Sinais lado a lado.
        signals = snapshot.get("signals") or {}
        sig_card = ttk.Frame(body, style="Card.TFrame", padding=10)
        sig_card.pack(fill="x", pady=(0,8))
        ttk.Label(sig_card,text="O que cada método está dizendo",style="CardTitle.TLabel").pack(anchor="w")
        sig_row = ttk.Frame(sig_card, style="Card.TFrame")
        sig_row.pack(fill="x",pady=(7,0))
        for i,name in enumerate(("Reset Cobertura","Puxada Combinada","Similaridade")):
            sig = signals.get(name) or {}
            card = ttk.Frame(sig_row,style="Card2.TFrame",padding=8)
            card.pack(side="left",fill="both",expand=True,padx=(0,6 if i<2 else 0))
            ttk.Label(card,text=name,style="Card.TLabel",font=("Segoe UI Semibold",10)).pack(anchor="w")
            if sig.get("available"):
                groups = sig.get("groups") or []
                animals = sig.get("animals") or []
                lines = [f"{rank}. {animal} ({int(group):02d})" for rank,(group,animal) in enumerate(zip(groups,animals),start=1)]
                ttk.Label(card,text="\n".join(lines),style="Card.TLabel",justify="left").pack(anchor="w",pady=(5,0))
            else:
                ttk.Label(card,text="Sem sinal suficiente nesta base.",style="CardMuted.TLabel",wraplength=280).pack(anchor="w",pady=(5,0))

        reset_sig = signals.get("Reset Cobertura") or {}
        why = ttk.Frame(body,style="Card.TFrame",padding=10)
        why.pack(fill="x",pady=(0,8))
        topbar = ttk.Frame(why,style="Card.TFrame")
        topbar.pack(fill="x")
        ttk.Label(topbar,text="Por que estes 5?",style="CardTitle.TLabel").pack(side="left")
        ttk.Label(topbar,text="Clique num bicho para ver onde ele aparece nos métodos.",style="CardMuted.TLabel").pack(side="left",padx=(10,0))
        chips = ttk.Frame(why,style="Card.TFrame")
        chips.pack(fill="x",pady=(7,0))
        for g,a in zip(reset_sig.get("groups") or [], reset_sig.get("animals") or []):
            ttk.Button(
                chips,text=f"{a} ({int(g):02d})",
                command=lambda gg=int(g), aa=a, ss=snapshot: self._decision_explain_dialog(ss,gg,aa),
            ).pack(side="left",padx=(0,6))

        perf_card = ttk.Frame(body,style="Card.TFrame",padding=10)
        perf_card.pack(fill="both",expand=True,pady=(0,8))
        perf_head = ttk.Frame(perf_card,style="Card.TFrame")
        perf_head.pack(fill="x")
        ttk.Label(perf_head,text="Comparação prospectiva dos métodos",style="CardTitle.TLabel").pack(side="left")
        self.decision_window = tk.StringVar(value="30")
        ttk.Label(perf_head,text="Janela",style="CardMuted.TLabel").pack(side="right",padx=(8,4))
        cb=ttk.Combobox(perf_head,textvariable=self.decision_window,values=["30","60","120","Todos"],width=7,state="readonly")
        cb.pack(side="right")
        cb.bind("<<ComboboxSelected>>",lambda _e:self._decision_refresh_perf())
        cols=("method","rounds","avg","p2","p3","pos")
        self.decision_perf_tree=ttk.Treeview(perf_card,columns=cols,show="headings",height=5)
        heads={"method":"Método","rounds":"Rodadas","avg":"Cobertura média","p2":"2+ bichos","p3":"3+ bichos","pos":"Acerto posicional"}
        widths={"method":220,"rounds":80,"avg":120,"p2":100,"p3":100,"pos":120}
        for c in cols:
            self.decision_perf_tree.heading(c,text=heads[c])
            self.decision_perf_tree.column(c,width=widths[c],anchor="center" if c!="method" else "w")
        self.decision_perf_tree.pack(fill="x",pady=(8,3))
        self.decision_perf_note=ttk.Label(perf_card,text="",style="CardMuted.TLabel",wraplength=980)
        self.decision_perf_note.pack(anchor="w")
        self._decision_refresh_perf()

        # v0.28.0 — Etapa 2: campeão × desafiante, contexto, tendência e concentração.
        self._decision_build_stage2(body, snapshot)

        # v0.29.0 — Etapa 3: simulador histórico walk-forward sem look-ahead.
        self._decision_build_stage3(body)

        # v0.36.0 — Laboratório deixa de ser página paralela e vira seção da Decisão.
        self._build_shadow_lab_section(body)
        if open_lab:
            canvas = getattr(self, "_smart_scroll_canvases", {}).get("decision")
            if canvas is not None:
                self.after_idle(lambda c=canvas: c.yview_moveto(1.0))

        hist = ttk.Frame(body,style="Card.TFrame",padding=10)
        hist.pack(fill="x",pady=(0,8))
        ttk.Label(hist,text="Congelamento da rodada",style="CardTitle.TLabel").pack(anchor="w")
        created = str(snapshot.get("created_at") or "—").replace("T"," ")
        status = snapshot.get("status") or "PENDENTE"
        ttk.Label(
            hist,
            text=f"Leitura salva em {created} • Status: {status}. Depois de congelada, a previsão não é reescrita com o resultado.",
            style="CardMuted.TLabel",wraplength=1000,
        ).pack(anchor="w",pady=(4,0))

    def _decision_build_stage2(self, body, snapshot):
        # Campeão × desafiante: sempre pareado nas mesmas rodadas e sem promoção automática.
        cc = self.db.decision_champion_challenger(window=60, min_rounds=12)
        champ = ttk.Frame(body, style="Card.TFrame", padding=10)
        champ.pack(fill="x", pady=(0,8))
        head = ttk.Frame(champ, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="Campeão × Desafiante", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(head, text="Janela: até 60 rodadas pareadas • promoção nunca é automática", style="CardMuted.TLabel").pack(side="right")
        best=cc.get("best")
        if best:
            cm=best.get("champion") or {}
            dm=best.get("challenger_metrics") or {}
            line=(
                f"Oficial: {cc['official_champion']}  {cm.get('avg_coverage',0):.2f}/5   •   "
                f"Desafiante: {best.get('challenger')}  {dm.get('avg_coverage',0):.2f}/5   •   "
                f"Diferença: {best.get('avg_diff',0):+.2f}   •   "
                f"2+ bichos: {best.get('p2_diff',0):+.0f} pp   •   "
                f"{best.get('paired_rounds',0)} confronto(s)"
            )
        else:
            line="Ainda não há confrontos pareados suficientes."
        ttk.Label(champ,text=line,style="Card.TLabel",font=("Segoe UI Semibold",10),wraplength=1080).pack(anchor="w",pady=(6,2))
        ttk.Label(champ,text=f"{cc.get('status','—')} — {cc.get('recommendation','—')}",style="CardMuted.TLabel",wraplength=1080).pack(anchor="w")

        # Detector de mudança de comportamento.
        trend = self.db.decision_change_detection(recent_window=12, baseline_window=30)
        trend_card=ttk.Frame(body,style="Card.TFrame",padding=10)
        trend_card.pack(fill="x",pady=(0,8))
        t_head=ttk.Frame(trend_card,style="Card.TFrame")
        t_head.pack(fill="x")
        ttk.Label(t_head,text="Mudança de comportamento",style="CardTitle.TLabel").pack(side="left")
        ttk.Label(t_head,text="12 recentes × 30 anteriores",style="CardMuted.TLabel").pack(side="right")
        tcols=("method","status","recent","base","delta","p2")
        tree=ttk.Treeview(trend_card,columns=tcols,show="headings",height=3)
        heads={"method":"Método","status":"Sinal","recent":"Recente","base":"Base anterior","delta":"Δ cobertura","p2":"Δ 2+"}
        widths={"method":220,"status":150,"recent":105,"base":105,"delta":100,"p2":90}
        for c in tcols:
            tree.heading(c,text=heads[c]); tree.column(c,width=widths[c],anchor="w" if c in ("method","status") else "center")
        for r in trend.get("rows") or []:
            tree.insert("","end",values=(
                r["method"],r["status"],f"{r['recent_avg']:.2f}/5 ({r['recent_rounds']})",
                f"{r['baseline_avg']:.2f}/5 ({r['baseline_rounds']})",f"{r['avg_delta']:+.2f}",f"{r['p2_delta']:+.0f} pp",
            ))
        tree.pack(fill="x",pady=(7,3))
        ttk.Label(trend_card,text="Este alerta identifica desvio recente; não prova que o sorteio mudou nem prevê o próximo resultado.",style="CardMuted.TLabel",wraplength=1050).pack(anchor="w")

        # Desempenho por horário e dia da semana.
        context=ttk.Frame(body,style="Card.TFrame",padding=10)
        context.pack(fill="x",pady=(0,8))
        c_head=ttk.Frame(context,style="Card.TFrame"); c_head.pack(fill="x")
        ttk.Label(c_head,text="Onde cada método funciona melhor?",style="CardTitle.TLabel").pack(side="left")
        ttk.Label(c_head,text="Até 120 leituras prospectivas auditadas",style="CardMuted.TLabel").pack(side="right")
        grids=ttk.Frame(context,style="Card.TFrame"); grids.pack(fill="x",pady=(7,0))
        grids.columnconfigure(0,weight=1); grids.columnconfigure(1,weight=1)
        methods=("Reset Cobertura","Puxada Combinada","Similaridade")
        short={"Reset Cobertura":"Reset","Puxada Combinada":"Puxada","Similaridade":"Similar."}
        def make_context_table(parent,title,data,col):
            box=ttk.Frame(parent,style="Card2.TFrame",padding=7); box.grid(row=0,column=col,sticky="nsew",padx=(0,4) if col==0 else (4,0))
            ttk.Label(box,text=title,style="Card.TLabel",font=("Segoe UI Semibold",10)).pack(anchor="w")
            cols=("label","rounds","reset","pull","sim")
            tv=ttk.Treeview(box,columns=cols,show="headings",height=min(7,max(3,len(data.get('rows') or []))))
            labels={"label":title.replace("Por ","").replace("dia da semana","Dia"),"rounds":"N","reset":"Reset","pull":"Puxada","sim":"Similar."}
            widths={"label":92,"rounds":42,"reset":88,"pull":88,"sim":88}
            for cc2 in cols:
                tv.heading(cc2,text=labels[cc2]); tv.column(cc2,width=widths[cc2],anchor="w" if cc2=="label" else "center")
            for row in data.get("rows") or []:
                perf=row.get("methods") or {}
                def cell(m):
                    r=perf.get(m)
                    return "—" if not r else f"{r['avg_coverage']:.2f} ({r['rounds']})"
                tv.insert("","end",values=(row.get("label"),row.get("rounds"),cell(methods[0]),cell(methods[1]),cell(methods[2])))
            tv.pack(fill="x",pady=(5,0))
        make_context_table(grids,"Por horário",self.db.decision_performance_by_hour(window=120),0)
        make_context_table(grids,"Por dia da semana",self.db.decision_performance_by_weekday(window=120),1)

        # Concentração dos jogos congelados para o alvo atual.
        conc=self.db.decision_bet_concentration(snapshot.get("target_data"),snapshot.get("target_sorteio"),snapshot.get("target_hora"))
        conc_card=ttk.Frame(body,style="Card.TFrame",padding=10)
        conc_card.pack(fill="x",pady=(0,8))
        con_head=ttk.Frame(conc_card,style="Card.TFrame"); con_head.pack(fill="x")
        ttk.Label(con_head,text="Concentração dos jogos desta rodada",style="CardTitle.TLabel").pack(side="left")
        ttk.Label(con_head,text=f"{conc.get('games',0)} jogo(s) congelado(s) • {conc.get('items',0)} palpite(s)",style="CardMuted.TLabel").pack(side="right")
        if conc.get("group_mentions"):
            top=conc.get("top") or []
            top_txt="   •   ".join(f"{r['bicho']} {r['share']:.0f}%" for r in top[:5])
            ttk.Label(conc_card,text=f"Índice {conc.get('score',0):.0f}/100 • {conc.get('label')}  |  Dois bichos líderes concentram {conc.get('top2_share',0):.0f}% das dependências.",style="Card.TLabel",font=("Segoe UI Semibold",10),wraplength=1080).pack(anchor="w",pady=(6,2))
            ttk.Label(conc_card,text=top_txt,style="CardMuted.TLabel",wraplength=1080).pack(anchor="w")
            if conc.get("label") == "ALTA":
                ttk.Label(conc_card,text="Atenção: muitos palpites dependem dos mesmos bichos. Isso reduz a cobertura real mesmo quando os números parecem diferentes.",style="CardMuted.TLabel",wraplength=1080).pack(anchor="w",pady=(3,0))
        else:
            ttk.Label(conc_card,text="Ainda não há jogos congelados suficientes para medir concentração nesta rodada.",style="CardMuted.TLabel").pack(anchor="w",pady=(6,0))

    def _decision_build_stage3(self, body):
        card=ttk.Frame(body,style="Card.TFrame",padding=10)
        card.pack(fill="x",pady=(0,8))
        head=ttk.Frame(card,style="Card.TFrame"); head.pack(fill="x")
        ttk.Label(head,text="Simulador Walk-Forward",style="CardTitle.TLabel").pack(side="left")
        ttk.Label(head,text="Etapa 3 • sem olhar o futuro",style="CardMuted.TLabel").pack(side="right")
        ttk.Label(
            card,
            text="Refaz cada rodada usando exatamente os métodos atuais e somente os dados que já existiam antes daquela extração-base. O resultado seguinte entra apenas para medir o acerto.",
            style="CardMuted.TLabel",wraplength=1080,
        ).pack(anchor="w",pady=(4,7))

        controls=ttk.Frame(card,style="Card.TFrame"); controls.pack(fill="x")
        ttk.Label(controls,text="Janela",style="CardMuted.TLabel").pack(side="left")
        if not hasattr(self,"decision_wf_window"):
            self.decision_wf_window=tk.StringVar(value="120")
        cb=ttk.Combobox(controls,textvariable=self.decision_wf_window,values=["30","60","120","240"],width=7,state="readonly")
        cb.pack(side="left",padx=(5,8))
        self.decision_wf_run_btn=ttk.Button(controls,text="SIMULAR",command=self._decision_walk_forward_start)
        self.decision_wf_run_btn.pack(side="left")
        self.decision_wf_cancel_btn=ttk.Button(controls,text="Cancelar",command=self._decision_walk_forward_cancel)
        self.decision_wf_cancel_btn.pack(side="left",padx=(6,0))
        self.decision_wf_export_btn=ttk.Button(controls,text="Exportar CSV",command=self._decision_walk_forward_export)
        self.decision_wf_export_btn.pack(side="right")

        self.decision_wf_progress=ttk.Progressbar(card,mode="determinate",maximum=100)
        self.decision_wf_progress.pack(fill="x",pady=(8,3))
        self.decision_wf_status=ttk.Label(card,text="Escolha a janela e clique em SIMULAR.",style="CardMuted.TLabel",wraplength=1080)
        self.decision_wf_status.pack(anchor="w")

        cols=("method","rounds","avg","p2","p3","p4","p5","uplift","pos")
        self.decision_wf_tree=ttk.Treeview(card,columns=cols,show="headings",height=3)
        heads={"method":"Método","rounds":"N","avg":"Cobertura","p2":"2+","p3":"3+","p4":"4+","p5":"5/5","uplift":"vs. acaso","pos":"Posicional"}
        widths={"method":190,"rounds":48,"avg":85,"p2":62,"p3":62,"p4":62,"p5":62,"uplift":82,"pos":82}
        for c in cols:
            self.decision_wf_tree.heading(c,text=heads[c])
            self.decision_wf_tree.column(c,width=widths[c],anchor="w" if c=="method" else "center")
        self.decision_wf_tree.pack(fill="x",pady=(7,3))
        self.decision_wf_note=ttk.Label(card,text="",style="CardMuted.TLabel",wraplength=1080)
        self.decision_wf_note.pack(anchor="w")

        ttk.Label(card,text="Robustez do recorte • primeira metade × segunda metade",style="Card.TLabel",font=("Segoe UI Semibold",9)).pack(anchor="w",pady=(8,2))
        rcols=("method","first","second","delta","p2")
        self.decision_wf_robust_tree=ttk.Treeview(card,columns=rcols,show="headings",height=3)
        rheads={"method":"Método","first":"1ª metade","second":"2ª metade","delta":"Δ cobertura","p2":"Δ 2+"}
        rwidths={"method":190,"first":130,"second":130,"delta":110,"p2":90}
        for c in rcols:
            self.decision_wf_robust_tree.heading(c,text=rheads[c])
            self.decision_wf_robust_tree.column(c,width=rwidths[c],anchor="w" if c=="method" else "center")
        self.decision_wf_robust_tree.pack(fill="x",pady=(0,2))
        ttk.Label(card,text="A divisão em metades é apenas diagnóstico de estabilidade; não é prova estatística nem critério automático para trocar método.",style="CardMuted.TLabel",wraplength=1080).pack(anchor="w")

        running=bool(getattr(self,"_walk_forward_running",False))
        if running:
            self.decision_wf_run_btn.configure(state="disabled")
            self.decision_wf_cancel_btn.configure(state="normal")
            st=getattr(self,"_walk_forward_progress_state",None) or (0,1,"Preparando…")
            done,total,label=st
            self.decision_wf_progress.configure(value=(done/max(1,total))*100.0)
            self.decision_wf_status.configure(text=label)
        else:
            self.decision_wf_cancel_btn.configure(state="disabled")
        result=getattr(self,"walk_forward_last_result",None)
        if result:
            self._decision_walk_forward_render(result)
        else:
            self.decision_wf_export_btn.configure(state="disabled")

    def _decision_walk_forward_ui_alive(self):
        try:
            return self._page=="decision" and self.decision_wf_tree.winfo_exists()
        except Exception:
            return False

    def _decision_walk_forward_start(self):
        if getattr(self,"_walk_forward_running",False):
            return
        try:
            window=int(self.decision_wf_window.get())
        except Exception:
            window=120
        self._walk_forward_running=True
        self._walk_forward_cancel_event=threading.Event()
        self._walk_forward_queue=queue.Queue()
        self._walk_forward_progress_state=(0,max(1,window),"Preparando o walk-forward…")
        if self._decision_walk_forward_ui_alive():
            self.decision_wf_run_btn.configure(state="disabled")
            self.decision_wf_cancel_btn.configure(state="normal")
            self.decision_wf_export_btn.configure(state="disabled")
            self.decision_wf_progress.configure(value=0)
            self.decision_wf_status.configure(text="Preparando as rodadas históricas…")

        q=self._walk_forward_queue
        cancel_event=self._walk_forward_cancel_event
        def progress(done,total,base):
            label=f"{done}/{total} • {base.get('data','—')} {base.get('sorteio','—')} {base.get('hora','—')}"
            q.put(("progress",done,total,label))
        def worker():
            try:
                result=self.db.decision_walk_forward(window=window,progress_callback=progress,cancel_event=cancel_event)
                q.put(("done",result))
            except Exception as exc:
                q.put(("error",str(exc)))
        threading.Thread(target=worker,daemon=True,name="GPH-WalkForward").start()
        self.after(100,self._decision_walk_forward_poll)

    def _decision_walk_forward_cancel(self):
        event=getattr(self,"_walk_forward_cancel_event",None)
        if event is not None:
            event.set()
            if self._decision_walk_forward_ui_alive():
                self.decision_wf_status.configure(text="Cancelando após a rodada atual…")
                self.decision_wf_cancel_btn.configure(state="disabled")

    def _decision_walk_forward_poll(self):
        q=getattr(self,"_walk_forward_queue",None)
        if q is None:
            return
        terminal=False
        while True:
            try:
                msg=q.get_nowait()
            except queue.Empty:
                break
            kind=msg[0]
            if kind=="progress":
                _,done,total,label=msg
                self._walk_forward_progress_state=(done,total,label)
                if self._decision_walk_forward_ui_alive():
                    self.decision_wf_progress.configure(value=(done/max(1,total))*100.0)
                    self.decision_wf_status.configure(text=label)
            elif kind=="done":
                terminal=True
                self._walk_forward_running=False
                self.walk_forward_last_result=msg[1]
                if self._decision_walk_forward_ui_alive():
                    self.decision_wf_run_btn.configure(state="normal")
                    self.decision_wf_cancel_btn.configure(state="disabled")
                    self._decision_walk_forward_render(msg[1])
            elif kind=="error":
                terminal=True
                self._walk_forward_running=False
                if self._decision_walk_forward_ui_alive():
                    self.decision_wf_run_btn.configure(state="normal")
                    self.decision_wf_cancel_btn.configure(state="disabled")
                    self.decision_wf_status.configure(text=f"Falha na simulação: {msg[1]}")
        if getattr(self,"_walk_forward_running",False) and not terminal:
            self.after(120,self._decision_walk_forward_poll)

    def _decision_walk_forward_render(self,result):
        if not self._decision_walk_forward_ui_alive():
            return
        tree=self.decision_wf_tree
        for item in tree.get_children():
            tree.delete(item)
        for r in result.get("summary") or []:
            pos="—" if r.get("avg_position") is None else f"{r['avg_position']:.2f}/5"
            uplift=float(r.get("uplift_vs_random") or 0.0)
            tree.insert("","end",values=(
                r.get("method"),r.get("rounds",0),f"{r.get('avg_coverage',0):.2f}/5",
                f"{r.get('pct_2plus',0):.0f}%",f"{r.get('pct_3plus',0):.0f}%",
                f"{r.get('pct_4plus',0):.0f}%",f"{r.get('pct_5',0):.0f}%",
                f"{uplift:+.2f}",pos,
            ))
        robust=getattr(self,"decision_wf_robust_tree",None)
        if robust is not None:
            for item in robust.get_children():
                robust.delete(item)
            for r in result.get("robustness") or []:
                robust.insert("","end",values=(
                    r.get("method"),f"{r.get('first_avg',0):.2f}/5 ({r.get('first_rounds',0)})",
                    f"{r.get('second_avg',0):.2f}/5 ({r.get('second_rounds',0)})",
                    f"{r.get('delta',0):+.2f}",f"{(r.get('second_p2',0)-r.get('first_p2',0)):+.0f} pp",
                ))
        simulated=int(result.get("simulated_rounds") or 0)
        requested=int(result.get("requested_rounds") or 0)
        paired=int(result.get("paired_rounds") or 0)
        best=result.get("best_paired") or {}
        if result.get("cancelled"):
            status=f"Simulação cancelada • {simulated}/{requested} rodada(s) processada(s)."
        else:
            status=f"Concluído • {simulated} rodada(s) processada(s) • {paired} rodada(s) comparáveis entre os três métodos."
        self.decision_wf_status.configure(text=status)
        self.decision_wf_progress.configure(value=100 if simulated else 0)
        if best:
            note=(
                f"Melhor no recorte pareado: {best.get('method')} ({best.get('avg_coverage',0):.2f}/5). "
                f"Período dos alvos: {result.get('date_from') or '—'} a {result.get('date_to') or '—'}. "
                "'vs. acaso' é a diferença para a sobreposição esperada de uma seleção aleatória com o mesmo nº de grupos únicos. "
                "Resultado histórico não garante desempenho futuro."
            )
        else:
            note="Ainda não houve rodadas comparáveis suficientes."
        self.decision_wf_note.configure(text=note)
        self.decision_wf_export_btn.configure(state="normal" if simulated else "disabled")

    def _decision_walk_forward_export(self):
        result=getattr(self,"walk_forward_last_result",None)
        if not result:
            messagebox.showinfo("Walk-Forward","Execute uma simulação antes de exportar.",parent=self)
            return
        default=f"GP-H_walk_forward_{int(result.get('window') or 0)}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
        path=filedialog.asksaveasfilename(
            parent=self,title="Exportar Walk-Forward",initialdir=str(EXPORT_DIR),initialfile=default,
            defaultextension=".csv",filetypes=[("CSV","*.csv")],
        )
        if not path:
            return
        with open(path,"w",encoding="utf-8-sig",newline="") as fh:
            w=csv.writer(fh,delimiter=";")
            w.writerow(["GP-H Walk-Forward",f"janela={result.get('window')}",f"lookahead_safe={result.get('lookahead_safe')}"])
            w.writerow([])
            w.writerow(["Método","Rodadas","Cobertura média","2+ %","3+ %","4+ %","5/5 %","Esperado acaso","Diferença vs acaso","Posicional"])
            for r in result.get("summary") or []:
                w.writerow([
                    r.get("method"),r.get("rounds"),f"{r.get('avg_coverage',0):.4f}",f"{r.get('pct_2plus',0):.2f}",
                    f"{r.get('pct_3plus',0):.2f}",f"{r.get('pct_4plus',0):.2f}",f"{r.get('pct_5',0):.2f}",
                    f"{r.get('avg_random_expected',0):.4f}",f"{r.get('uplift_vs_random',0):+.4f}",
                    "" if r.get("avg_position") is None else f"{r.get('avg_position'):.4f}",
                ])
            w.writerow([])
            w.writerow(["Robustez","Método","1ª metade N","1ª metade cobertura","2ª metade N","2ª metade cobertura","Delta cobertura","Delta 2+ pp"])
            for r in result.get("robustness") or []:
                w.writerow(["metades",r.get("method"),r.get("first_rounds"),f"{r.get('first_avg',0):.4f}",r.get("second_rounds"),f"{r.get('second_avg',0):.4f}",f"{r.get('delta',0):+.4f}",f"{(r.get('second_p2',0)-r.get('first_p2',0)):+.2f}"])
            w.writerow([])
            w.writerow(["Base data","Base sorteio","Base hora","Alvo data","Alvo sorteio","Alvo hora","Resultado grupos","Método","Palpite grupos","Cobertura","Posicional"])
            for row in result.get("details") or []:
                target_groups=" ".join(f"{int(g):02d}" for g in row.get("target_groups") or [])
                for method,sig in (row.get("methods") or {}).items():
                    w.writerow([
                        row["base"].get("data"),row["base"].get("sorteio"),row["base"].get("hora"),
                        row["target"].get("data"),row["target"].get("sorteio"),row["target"].get("hora"),target_groups,
                        method," ".join(f"{int(g):02d}" for g in sig.get("groups") or []),
                        "" if sig.get("coverage_hits") is None else sig.get("coverage_hits"),
                        "" if sig.get("position_hits") is None else sig.get("position_hits"),
                    ])
        messagebox.showinfo("Walk-Forward",f"Relatório exportado em:\n{path}",parent=self)

    def _decision_refresh_perf(self):
        tree = getattr(self,"decision_perf_tree",None)
        if tree is None:
            return
        for item in tree.get_children():
            tree.delete(item)
        window = getattr(self,"decision_window",tk.StringVar(value="30")).get()
        perf = self.db.decision_method_performance(window=window)
        for row in perf["rows"]:
            pos = "—" if row.get("avg_position") is None else f"{row['avg_position']:.2f}/5"
            tree.insert("","end",values=(
                row["method"],row["rounds"],f"{row['avg_coverage']:.2f}/5",
                f"{row['pct_2plus']:.0f}%",f"{row['pct_3plus']:.0f}%",pos,
            ))
        n=perf["audited_snapshots"]
        if n < 10:
            note=f"Amostra prospectiva ainda pequena ({n} rodada(s)). A Central limita automaticamente o índice de confiança até acumular evidência suficiente."
        else:
            note=f"{n} rodadas congeladas e auditadas nesta janela. Comparação feita somente com previsões registradas antes do resultado."
        self.decision_perf_note.configure(text=note)

    def _decision_explain_dialog(self,snapshot,group,animal):
        lines=self.db.decision_explain_group(snapshot,group)
        comp=snapshot.get("components") or {}
        overlap=(comp.get("overlap_detail") or {})
        extra=[]
        for name,data in overlap.items():
            extra.append(f"{name} × Reset: {int(data.get('overlap') or 0)} bicho(s) em comum")
        messagebox.showinfo(
            f"Por que {animal}?",
            f"{animal} • Grupo {int(group):02d}\n\n" + "\n".join(lines) + ("\n\nConvergência geral:\n"+"\n".join(extra) if extra else ""),
            parent=self,
        )

    def show_statistics_page(self):
        self._set_active_nav("Estatísticas")
        self._clear_content()
        self._page = "statistics"

        self.stat_from = tk.StringVar()
        self.stat_to = tk.StringVar()
        self.stat_draw = tk.StringVar(value="Todos")
        self.stat_prize = tk.StringVar(value="Todos")
        self.stat_current = None

        self._page_title(
            "Estatísticas",
            "Frequência histórica dos 25 bichos no recorte escolhido.",
        )
        body = self._make_scrollable_page_body(self.content, "statistics")

        filt = ttk.Frame(body, style="Card.TFrame", padding=8)
        filt.pack(fill="x", pady=(0, 7))

        ttk.Label(filt, text="De", style="Card.TLabel").grid(row=0,column=0,sticky="w",padx=(0,7))
        CalendarField(
            filt, self.stat_from, width=10,
            on_change=self.statistics_date_changed
        ).grid(row=1,column=0,sticky="w",padx=(0,7),pady=(2,0))

        ttk.Label(filt, text="Até", style="Card.TLabel").grid(row=0,column=1,sticky="w",padx=(0,7))
        CalendarField(
            filt, self.stat_to, width=10,
            on_change=self.statistics_date_changed
        ).grid(row=1,column=1,sticky="w",padx=(0,7),pady=(2,0))

        ttk.Label(filt, text="Sorteio / Hora", style="Card.TLabel").grid(row=0,column=2,sticky="w",padx=(0,7))
        self.stat_cb_draw = ttk.Combobox(
            filt, textvariable=self.stat_draw,
            width=18, state="readonly"
        )
        self.stat_cb_draw.grid(row=1,column=2,sticky="w",padx=(0,7),pady=(2,0))

        ttk.Label(filt, text="Prêmio", style="Card.TLabel").grid(row=0,column=3,sticky="w",padx=(0,7))
        ttk.Combobox(
            filt, textvariable=self.stat_prize,
            values=["Todos","1","2","3","4","5"],
            width=7, state="readonly"
        ).grid(row=1,column=3,sticky="w",padx=(0,7),pady=(2,0))

        ttk.Button(
            filt, text="Atualizar", style="Accent.TButton",
            command=self.statistics_refresh,
        ).grid(row=1,column=4,padx=(4,0),pady=(2,0))

        ttk.Button(
            filt, text="Limpar", command=self.statistics_clear,
        ).grid(row=1,column=5,padx=(5,0),pady=(2,0))

        top_line = ttk.Frame(body)
        top_line.pack(fill="x", pady=(0, 5))
        self.stat_summary = ttk.Label(top_line, text="")
        self.stat_summary.pack(side="left", fill="x", expand=True)
        ttk.Button(
            top_line, text="Detalhes do selecionado",
            command=self.statistics_open_details,
        ).pack(side="right")
        ttk.Button(
            top_line, text="Exportar CSV",
            command=self.statistics_export_csv,
        ).pack(side="right", padx=(0, 6))

        table = ttk.Frame(body)
        table.pack(fill="both", expand=True)

        cols = (
            "rank","grupo","bicho","ocorrencias","pctpremios","draws","pctdraws",
            "p1","p2","p3","p4","p5","ultima"
        )
        self.stat_tree = ttk.Treeview(
            table, columns=cols, show="headings", selectmode="browse"
        )
        labels = {
            "rank":"#","grupo":"G","bicho":"Bicho","ocorrencias":"Ocorr.",
            "pctpremios":"% prêmios","draws":"Extrações","pctdraws":"% extr.",
            "p1":"1º","p2":"2º","p3":"3º","p4":"4º","p5":"5º","ultima":"Última"
        }
        widths = {
            "rank":38,"grupo":42,"bicho":95,"ocorrencias":68,"pctpremios":70,
            "draws":70,"pctdraws":68,"p1":38,"p2":38,"p3":38,"p4":38,"p5":38,
            "ultima":165
        }
        for c in cols:
            self.stat_tree.heading(c, text=labels[c])
            self.stat_tree.column(
                c, width=widths[c],
                anchor="w" if c in ("bicho","ultima") else "center"
            )

        y = ttk.Scrollbar(table, orient="vertical", command=self.stat_tree.yview)
        x = ttk.Scrollbar(table, orient="horizontal", command=self.stat_tree.xview)
        self.stat_tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.stat_tree.grid(row=0,column=0,sticky="nsew")
        y.grid(row=0,column=1,sticky="ns")
        x.grid(row=1,column=0,sticky="ew")
        table.rowconfigure(0,weight=1)
        table.columnconfigure(0,weight=1)

        self.stat_tree.bind("<Double-1>", self.statistics_open_details)
        self.statistics_date_changed()
        self.statistics_refresh()

    def statistics_clear(self):
        self.stat_from.set("")
        self.stat_to.set("")
        self.stat_draw.set("Todos")
        self.stat_prize.set("Todos")
        self.statistics_date_changed()
        self.statistics_refresh()

    def statistics_date_changed(self):
        try:
            d1 = parse_br_date(self.stat_from.get())
            d2 = parse_br_date(self.stat_to.get())
        except ValueError:
            return
        values = self._draw_combo_values(d1, d2)
        if self.stat_draw.get() not in values:
            self.stat_draw.set("Todos")
        self.stat_cb_draw["values"] = values

    def statistics_refresh(self):
        try:
            d1 = parse_br_date(self.stat_from.get())
            d2 = parse_br_date(self.stat_to.get())
            if d1 and d2 and d1 > d2:
                raise ValueError("A data inicial não pode ser maior que a final.")

            sorteio, hora = self._split_draw_combo(self.stat_draw.get())

            stats = self.db.stats_by_animal(
                date_from=d1, date_to=d2,
                sorteio=sorteio, hora=hora,
                premio=self.stat_prize.get(),
            )
            self.stat_current = stats

            for item in self.stat_tree.get_children():
                self.stat_tree.delete(item)

            for rank, r in enumerate(stats["rows"], start=1):
                last_txt = "—"
                if r["ultima"]:
                    d = datetime.strptime(
                        r["ultima"]["data"], "%Y-%m-%d"
                    ).strftime("%d/%m/%Y")
                    last_txt = (
                        f"{d} {r['ultima']['hora']} • "
                        f"{r['ultima']['premio']}º • {r['ultima']['milhar']}"
                    )

                self.stat_tree.insert(
                    "", "end", iid=str(r["grupo"]),
                    values=(
                        rank, f'{r["grupo"]:02d}', r["bicho"], r["ocorrencias"],
                        f'{r["pct_premios"]:.2f}%', r["extracoes_com_bicho"],
                        f'{r["pct_extracoes"]:.2f}%',
                        r["p1"], r["p2"], r["p3"], r["p4"], r["p5"], last_txt,
                    ),
                )

            self.stat_summary.configure(
                text=(
                    f"{stats['total_prizes']:,} prêmio(s) • "
                    f"{stats['total_draws']:,} extração(ões)"
                ).replace(",", ".")
            )
        except Exception as e:
            messagebox.showerror("Estatísticas", str(e), parent=self)

    def statistics_export_csv(self):
        stats = self.stat_current
        if not stats or not stats.get("rows"):
            messagebox.showwarning(
                "Exportar",
                "Não há estatísticas no recorte atual.",
                parent=self,
            )
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialdir=str(EXPORT_DIR),
            initialfile="gph_estatisticas.csv",
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([
                "Rank","Grupo","Bicho","Ocorrências","% prêmios",
                "Extrações com o bicho","% extrações","1º","2º","3º","4º","5º",
                "Última data","Último sorteio","Última hora","Último prêmio","Última milhar",
            ])
            for rank, r in enumerate(stats["rows"], start=1):
                last = r.get("ultima") or {}
                values = [
                    rank, f"{int(r['grupo']):02d}", r["bicho"], r["ocorrencias"],
                    f"{r['pct_premios']:.2f}%", r["extracoes_com_bicho"],
                    f"{r['pct_extracoes']:.2f}%", r["p1"], r["p2"], r["p3"], r["p4"], r["p5"],
                    last.get("data", ""), last.get("sorteio", ""), last.get("hora", ""),
                    last.get("premio", ""), str(last.get("milhar", "")).zfill(4) if last.get("milhar") not in (None, "") else "",
                ]
                w.writerow([self._csv_text(v) for v in values])

        messagebox.showinfo(
            "Exportar",
            f"Arquivo criado com campos em formato de texto e zeros preservados:\n{path}",
            parent=self,
        )

    def statistics_open_details(self, _event=None):
        sel = self.stat_tree.selection()
        if not sel:
            messagebox.showinfo(
                "Estatísticas", "Selecione um bicho primeiro.", parent=self
            )
            return

        grupo = int(sel[0])
        d1 = parse_br_date(self.stat_from.get())
        d2 = parse_br_date(self.stat_to.get())
        AnimalDetailsDialog(self, self.db, grupo, d1, d2)

    # ========================================================
    # PUXADAS — painel central
    # ========================================================
    def show_pulls_page(self):
        self._set_active_nav("Puxadas")
        self._clear_content()
        self._page = "pulls"

        animal_values = [f"{g:02d} - {BICHOS[g]}" for g in range(1, 26)]

        self.pull_animal = tk.StringVar(value=animal_values[0])
        self.pull_state = tk.StringVar(value="Geral")
        self.pull_from = tk.StringVar()
        self.pull_to = tk.StringVar()
        self.pull_draw = tk.StringVar(value="Todos")
        self.pull_current = None

        self._page_title(
            "Puxadas",
            "Quando o bicho-base aparece, o que costuma vir na extração seguinte?",
        )
        body = self._make_scrollable_page_body(self.content, "pulls")

        filt = ttk.Frame(body, style="Card.TFrame", padding=8)
        filt.pack(fill="x", pady=(0, 7))

        controls = [
            ("Bicho-base", ttk.Combobox(
                filt, textvariable=self.pull_animal,
                values=animal_values, width=18, state="readonly"
            )),
            ("Estado", ttk.Combobox(
                filt, textvariable=self.pull_state,
                values=["Geral","×1","×2","×3+"], width=7, state="readonly"
            )),
            ("De", CalendarField(
                filt, self.pull_from, width=9,
                on_change=self.pulls_date_changed
            )),
            ("Até", CalendarField(
                filt, self.pull_to, width=9,
                on_change=self.pulls_date_changed
            )),
        ]
        for col, (label, widget) in enumerate(controls):
            ttk.Label(filt, text=label, style="Card.TLabel").grid(
                row=0,column=col,sticky="w",padx=(0,6)
            )
            widget.grid(row=1,column=col,sticky="w",padx=(0,6),pady=(2,0))

        ttk.Label(filt, text="Origem / Hora", style="Card.TLabel").grid(
            row=0,column=4,sticky="w",padx=(0,6)
        )
        self.pull_cb_draw = ttk.Combobox(
            filt, textvariable=self.pull_draw,
            width=18, state="readonly"
        )
        self.pull_cb_draw.grid(row=1,column=4,sticky="w",padx=(0,6),pady=(2,0))

        ttk.Button(
            filt, text="Calcular", style="Accent.TButton",
            command=self.pulls_refresh,
        ).grid(row=1,column=5,padx=(4,0),pady=(2,0))

        info = ttk.Frame(body)
        info.pack(fill="x", pady=(0, 5))
        self.pull_summary = ttk.Label(info, text="")
        self.pull_summary.pack(side="left", fill="x", expand=True)
        ttk.Button(
            info, text="Exemplos do selecionado",
            command=self.pulls_open_examples,
        ).pack(side="right")

        table = ttk.Frame(body)
        table.pack(fill="both", expand=True)
        cols = (
            "rank","grupo","bicho","hits","prob","baseline","lift","ocorr",
            "p1","p2","p3","p4","p5"
        )
        self.pull_tree = ttk.Treeview(
            table, columns=cols, show="headings", selectmode="browse"
        )
        labels = {
            "rank":"#","grupo":"G","bicho":"Bicho","hits":"Próx. c/ bicho",
            "prob":"Cobertura","baseline":"Base","lift":"Lift",
            "ocorr":"Ocorr.","p1":"1º","p2":"2º","p3":"3º","p4":"4º","p5":"5º"
        }
        widths = {
            "rank":38,"grupo":42,"bicho":95,"hits":86,"prob":72,"baseline":65,
            "lift":55,"ocorr":60,"p1":38,"p2":38,"p3":38,"p4":38,"p5":38
        }
        for c in cols:
            self.pull_tree.heading(c, text=labels[c])
            self.pull_tree.column(
                c, width=widths[c],
                anchor="w" if c == "bicho" else "center"
            )

        y = ttk.Scrollbar(table, orient="vertical", command=self.pull_tree.yview)
        x = ttk.Scrollbar(table, orient="horizontal", command=self.pull_tree.xview)
        self.pull_tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.pull_tree.grid(row=0,column=0,sticky="nsew")
        y.grid(row=0,column=1,sticky="ns")
        x.grid(row=1,column=0,sticky="ew")
        table.rowconfigure(0,weight=1)
        table.columnconfigure(0,weight=1)

        self.pull_tree.bind("<Double-1>", self.pulls_open_examples)

        self.pull_transitions = ttk.Label(
            body, text="Transições: —", wraplength=950
        )
        self.pull_transitions.pack(anchor="w", pady=(5, 0))

        self.pulls_date_changed()
        self.pulls_refresh()

    def pulls_selected_group(self):
        value = self.pull_animal.get().strip()
        m = re.match(r"(\d{1,2})", value)
        if not m:
            raise ValueError("Selecione um bicho-base.")
        return int(m.group(1))

    def pulls_date_changed(self):
        try:
            d1 = parse_br_date(self.pull_from.get())
            d2 = parse_br_date(self.pull_to.get())
        except ValueError:
            return

        values = self._draw_combo_values(d1, d2)
        if self.pull_draw.get() not in values:
            self.pull_draw.set("Todos")
        self.pull_cb_draw["values"] = values


    def pulls_refresh(self):
        try:
            d1 = parse_br_date(self.pull_from.get())
            d2 = parse_br_date(self.pull_to.get())
            if d1 and d2 and d1 > d2:
                raise ValueError("A data inicial não pode ser maior que a final.")

            source_sort, source_hour = self._split_draw_combo(self.pull_draw.get())

            result = self.db.historical_pulls(
                base_group=self.pulls_selected_group(),
                state=self.pull_state.get(),
                date_from=d1,
                date_to=d2,
                source_sort=source_sort,
                source_hour=source_hour,
            )
            self.pull_current = result

            for item in self.pull_tree.get_children():
                self.pull_tree.delete(item)

            for rank, r in enumerate(result["ranking"], start=1):
                self.pull_tree.insert(
                    "", "end", iid=str(r["grupo"]),
                    values=(
                        rank, f'{r["grupo"]:02d}', r["bicho"], r["hit_draws"],
                        f'{r["prob"]:.2f}%', f'{r["baseline_prob"]:.2f}%',
                        f'{r["lift"]:.2f}x', r["total_occ"],
                        r["p1"], r["p2"], r["p3"], r["p4"], r["p5"],
                    ),
                )

            self.pull_summary.configure(
                text=(
                    f"{result['base_bicho']} ({result['base_group']:02d}) • "
                    f"{result['state']} • suporte {result['support']} • "
                    f"baseline {result['baseline_support']}"
                )
            )

            trans = result["transitions"][:4]
            if trans:
                self.pull_transitions.configure(
                    text="Transições: " + " | ".join(
                        f"{t['source_sort']} {t['source_hour']} → "
                        f"{t['target_sort']} {t['target_hour']}: {t['count']}"
                        for t in trans
                    )
                )
            else:
                self.pull_transitions.configure(text="Transições: nenhuma.")
        except Exception as e:
            messagebox.showerror("Puxadas", str(e), parent=self)

    def pulls_open_examples(self, _event=None):
        if not self.pull_current:
            return

        sel = self.pull_tree.selection()
        if not sel:
            messagebox.showinfo(
                "Puxadas", "Selecione um bicho-alvo primeiro.", parent=self
            )
            return

        target_group = int(sel[0])
        target = next(
            (
                r for r in self.pull_current["ranking"]
                if r["grupo"] == target_group
            ),
            None,
        )
        if target:
            PullExamplesDialog(
                self,
                base_group=self.pull_current["base_group"],
                state=self.pull_current["state"],
                target_row=target,
            )

    # ========================================================
    # MÉTODOS — painel central
    # ========================================================
    def show_methods_page(self):
        self._set_active_nav("Métodos")
        self._clear_content()
        self._page = "methods"

        self.method_name = tk.StringVar(value="GP-H Reset Cobertura v1 (Oficial)")
        self.method_date = tk.StringVar()
        self.method_draw = tk.StringVar(value="Todos")
        self.method_topn = tk.StringVar(value="5")
        self.method_min_support = tk.StringVar(value="5")
        self.method_choose_old = tk.BooleanVar(value=False)
        self.method_advanced = tk.BooleanVar(value=False)
        self.method_current_result = None
        self.method_current_draw = None

        self._page_title(
            "Métodos",
            "Escolha o resultado-base, a quantidade e gere os bichos.",
        )
        body = self._make_scrollable_page_body(self.content, "methods")

        base = ttk.Frame(body, style="Card.TFrame", padding=8)
        base.pack(fill="x", pady=(0, 6))

        head = ttk.Frame(base, style="Card.TFrame")
        head.pack(fill="x")

        ttk.Label(
            head,
            text="Resultado-base:",
            style="Card.TLabel",
            font=("Segoe UI Semibold", 9),
        ).pack(side="left")

        self.method_base_label = ttk.Label(
            head,
            text="Carregando…",
            style="Card.TLabel",
            wraplength=730,
        )
        self.method_base_label.pack(side="left", padx=(6, 0), fill="x", expand=True)

        ttk.Button(
            head,
            text="Último",
            command=self.methods_load_latest,
        ).pack(side="right")

        ttk.Checkbutton(
            head,
            text="Escolher outro",
            variable=self.method_choose_old,
            command=self.methods_toggle_base,
        ).pack(side="right", padx=(0, 7))

        self.method_selector = ttk.Frame(base, style="Card.TFrame")

        ttk.Label(self.method_selector, text="Data", style="Card.TLabel").grid(row=0,column=0,sticky="w",padx=(0,6))
        CalendarField(
            self.method_selector,
            self.method_date,
            width=9,
            on_change=self.methods_date_changed,
        ).grid(row=1,column=0,sticky="w",padx=(0,6),pady=(2,0))

        ttk.Label(
            self.method_selector,
            text="Sorteio / Hora",
            style="Card.TLabel",
        ).grid(row=0,column=1,sticky="w",padx=(0,6))

        self.method_cb_draw = ttk.Combobox(
            self.method_selector,
            textvariable=self.method_draw,
            values=["Todos"],
            width=18,
            state="readonly",
        )
        self.method_cb_draw.grid(
            row=1,column=1,sticky="w",padx=(0,6),pady=(2,0)
        )

        ttk.Button(
            self.method_selector,
            text="Usar este resultado",
            command=self.methods_use_selected_draw,
        ).grid(row=1,column=2,padx=(4,0),pady=(2,0))

        controls = ttk.Frame(body, style="Card.TFrame", padding=8)
        controls.pack(fill="x", pady=(0, 6))

        ttk.Label(
            controls, text="Método", style="Card.TLabel"
        ).pack(side="left")

        method_cb = ttk.Combobox(
            controls,
            textvariable=self.method_name,
            values=["GP-H Reset Cobertura v1 (Oficial)","Puxada Combinada","Sombra Similaridade"],
            width=20,
            state="readonly",
        )
        method_cb.pack(side="left", padx=(5, 10))
        method_cb.bind("<<ComboboxSelected>>", self.methods_method_changed)

        ttk.Label(
            controls, text="Qtd. bichos", style="Card.TLabel"
        ).pack(side="left")

        self.method_topn_cb = ttk.Combobox(
            controls,
            textvariable=self.method_topn,
            values=["1","2","3","4","5","6","7","8","9","10"],
            width=5,
            state="readonly",
        )
        self.method_topn_cb.pack(side="left", padx=(5, 10))

        ttk.Button(
            controls,
            text="GERAR BICHOS",
            style="Accent.TButton",
            command=self.methods_calculate,
        ).pack(side="left")

        self.method_advanced_check = ttk.Checkbutton(
            controls,
            text="Opções técnicas",
            variable=self.method_advanced,
            command=self.methods_toggle_advanced,
        )
        self.method_advanced_check.pack(side="right")

        self.method_advanced_frame = ttk.Frame(
            body, style="Card.TFrame", padding=7
        )

        ttk.Label(
            self.method_advanced_frame,
            text="Suporte mínimo ×1/×2/×3+:",
            style="Card.TLabel",
        ).pack(side="left")

        ttk.Combobox(
            self.method_advanced_frame,
            textvariable=self.method_min_support,
            values=["3","5","8","10"],
            width=5,
            state="readonly",
        ).pack(side="left", padx=(5, 8))

        ttk.Label(
            self.method_advanced_frame,
            text="Padrão 5; pouca amostra cai para Geral.",
            style="Card.TLabel",
        ).pack(side="left")

        result_head = ttk.Frame(body)
        result_head.pack(fill="x", pady=(0, 4))

        ttk.Label(
            result_head,
            text="Bichos indicados",
            font=("Segoe UI Semibold", 12),
        ).pack(side="left")

        self.method_result_note = ttk.Label(
            result_head, text="Clique em GERAR BICHOS."
        )
        self.method_result_note.pack(side="left", padx=(8, 0))

        ttk.Button(
            result_head,
            text="Detalhes técnicos",
            command=self.methods_open_technical,
        ).pack(side="right")

        table = ttk.Frame(body)
        table.pack(fill="both", expand=True)

        cols = ("rank","bicho","grupo","sinal")
        self.method_tree = ttk.Treeview(
            table, columns=cols, show="headings", selectmode="browse"
        )

        for c, label, width, anchor in [
            ("rank","#",45,"center"),
            ("bicho","Bicho",180,"w"),
            ("grupo","Grupo",70,"center"),
            ("sinal","Sinal do método",250,"center"),
        ]:
            self.method_tree.heading(c, text=label)
            self.method_tree.column(c, width=width, anchor=anchor)

        y = ttk.Scrollbar(table, orient="vertical", command=self.method_tree.yview)
        self.method_tree.configure(yscrollcommand=y.set)
        self.method_tree.grid(row=0,column=0,sticky="nsew")
        y.grid(row=0,column=1,sticky="ns")
        table.rowconfigure(0,weight=1)
        table.columnconfigure(0,weight=1)

        self.methods_load_latest()
        self.methods_method_changed()

    def methods_method_changed(self, _event=None):
        name = self.method_name.get()
        is_shadow = name == "Sombra Similaridade"
        is_reset = name == "GP-H Reset Cobertura v1 (Oficial)"

        if is_shadow:
            self.method_topn.set("5")
            self.method_topn_cb.configure(state="disabled")
            self.method_advanced.set(False)
            self.method_advanced_frame.pack_forget()
            self.method_advanced_check.configure(state="disabled")
            self.method_result_note.configure(
                text="Sombra separada: 5 slots, repetição permitida."
            )
        elif is_reset:
            self.method_topn.set("5")
            self.method_topn_cb.configure(state="disabled")
            self.method_advanced.set(False)
            self.method_advanced_frame.pack_forget()
            self.method_advanced_check.configure(state="disabled")
            self.method_result_note.configure(
                text="OFICIAL • last240 • pull • pair3 • probability"
            )
        else:
            self.method_topn_cb.configure(state="readonly")
            self.method_advanced_check.configure(state="normal")
            self.method_result_note.configure(
                text="Método experimental de convergência."
            )

    def methods_date_iso(self):
        txt = self.method_date.get().strip()
        return parse_br_date(txt) if txt else None

    def methods_toggle_base(self):
        if self.method_choose_old.get():
            self.method_selector.pack(fill="x", pady=(0, 6))
            self.methods_refresh_draw_options()
        else:
            self.method_selector.pack_forget()

    def methods_toggle_advanced(self):
        if self.method_advanced.get():
            self.method_advanced_frame.pack(fill="x", pady=(0, 6))
        else:
            self.method_advanced_frame.pack_forget()

    def methods_refresh_draw_options(self):
        d = self.methods_date_iso()
        values = self._draw_combo_values(d, d)
        if self.method_draw.get() not in values:
            self.method_draw.set("Todos")
        self.method_cb_draw["values"] = values

    def methods_date_changed(self):
        self.method_draw.set("Todos")
        self.methods_refresh_draw_options()

    def methods_sort_changed(self, _event=None):
        self.methods_refresh_draw_options()

    def methods_hour_changed(self, _event=None):
        self.methods_refresh_draw_options()

    def methods_load_latest(self):
        latest = self.db.latest_operational_draw()
        if not latest:
            self.method_current_draw = None
            self.method_base_label.configure(text="Base operacional vazia.")
            return

        self.method_current_draw = latest
        d = datetime.strptime(latest["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
        self.method_date.set(d)
        self.methods_refresh_draw_options()
        self.method_draw.set(
            self._draw_combo_label(latest["sorteio"], latest["hora"])
        )
        self.methods_show_base(latest)

    def methods_use_selected_draw(self):
        try:
            d = self.methods_date_iso()
            if not d:
                raise ValueError("Escolha uma data.")

            sorteio, hora = self._split_draw_combo(self.method_draw.get())
            if sorteio == "Todos" or hora == "Todos":
                raise ValueError("Escolha Sorteio / Hora.")

            draw = self.db.get_draw(d, sorteio, hora)
            if not draw:
                raise ValueError("Resultado não encontrado.")

            self.method_current_draw = draw
            self.methods_show_base(draw)
            self.method_choose_old.set(False)
            self.methods_toggle_base()
        except Exception as e:
            messagebox.showerror("Métodos", str(e), parent=self)

    def methods_show_base(self, draw):
        d = datetime.strptime(draw["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
        animals = " • ".join(
            f"{p['bicho']} ({p['grupo']:02d})"
            for p in draw["prizes"]
        )
        self.method_base_label.configure(
            text=f"{d} • {draw['sorteio']} {draw['hora']} → {animals}"
        )

    def methods_calculate(self):
        try:
            if not self.method_current_draw:
                raise ValueError("Escolha um resultado-base primeiro.")

            draw = self.method_current_draw
            name = self.method_name.get()

            for item in self.method_tree.get_children():
                self.method_tree.delete(item)

            if name == "Sombra Similaridade":
                result = self.db.method_similarity_day(
                    draw["data"],
                    draw["sorteio"],
                    draw["hora"],
                    top_days=12,
                )
                self.method_current_result = result

                for rank, r in enumerate(result["selected"], start=1):
                    self.method_tree.insert(
                        "", "end", iid=f"slot-{rank}",
                        values=(
                            rank,
                            r["bicho"],
                            f'{r["grupo"]:02d}',
                            f'{r["weighted_share"]:.1f}% dos votos ponderados',
                        ),
                    )

                self.method_result_note.configure(
                    text=" • ".join(
                        f"{r['bicho']} ({r['grupo']:02d})"
                        for r in result["selected"]
                    )
                )

            elif name == "GP-H Reset Cobertura v1 (Oficial)":
                result = self.db.method_reset_coverage_v1(
                    draw["data"],
                    draw["sorteio"],
                    draw["hora"],
                    top_n=5,
                )
                self.method_current_result = result

                for rank, r in enumerate(result["selected"], start=1):
                    signal = f'{r["score_pct"]:.2f}%'
                    if result["context_mode"] == "pair3":
                        signal += f' • pair3 {result["pair3_matches"]} am.'
                    else:
                        signal += " • contexto neutro"

                    self.method_tree.insert(
                        "", "end",
                        iid=f"reset-{rank}-{r['grupo']}",
                        values=(
                            rank,
                            r["bicho"],
                            f'{r["grupo"]:02d}',
                            signal,
                        ),
                    )

                target = result["target"]
                ctx = (
                    "pair3"
                    if result["context_mode"] == "pair3"
                    else "pull estrutural (domingo)"
                )

                self.method_result_note.configure(
                    text=(
                        "OFICIAL → "
                        + " • ".join(
                            f"{r['bicho']} ({r['grupo']:02d})"
                            for r in result["selected"]
                        )
                        + f"  | alvo {target['sorteio']} {target['hora']} | {ctx}"
                    )
                )

            else:
                result = self.db.method_convergencia_g5(
                    draw["data"],
                    draw["sorteio"],
                    draw["hora"],
                    top_n=int(self.method_topn.get()),
                    min_state_support=int(self.method_min_support.get()),
                )
                self.method_current_result = result

                for rank, r in enumerate(result["selected"], start=1):
                    self.method_tree.insert(
                        "", "end", iid=f"pull-{rank}-{r['grupo']}",
                        values=(
                            rank,
                            r["bicho"],
                            f'{r["grupo"]:02d}',
                            f'{r["source_count"]} fonte(s)',
                        ),
                    )

                self.method_result_note.configure(
                    text=" • ".join(
                        f"{r['bicho']} ({r['grupo']:02d})"
                        for r in result["selected"]
                    )
                )

        except Exception as e:
            messagebox.showerror("Métodos", str(e), parent=self)

    def methods_open_technical(self):
        if not self.method_current_result:
            messagebox.showinfo(
                "Métodos", "Primeiro gere os bichos.", parent=self
            )
            return

        method = self.method_current_result.get("method")

        if method == "Sombra Similaridade do Dia":
            SimilarityTechnicalDialog(self, self.method_current_result)
        elif method == "GP-H Reset Cobertura v1":
            ResetCoverageTechnicalDialog(self, self.method_current_result)
        else:
            MethodsTechnicalDialog(self, self.method_current_result)

    def show_generator_page(self):
        self._set_active_nav("Gerador")
        self._clear_content()
        self._page = "generator"

        self.gen_source = tk.StringVar(value="Método oficial — Reset")
        self.gen_num_animals = tk.StringVar(value="5")
        self.gen_kind = tk.StringVar(value="Centena")
        self.gen_strategy = tk.StringVar(value="Histórica simples")
        self.gen_scope = tk.StringVar(value="1º–5º")
        self.gen_total = tk.StringVar(value="20")

        self.gen_manual_groups = []
        self.gen_current_groups = []
        self.gen_current_generation = None

        # Opções da Seca do Dia.
        self.gen_dry_date = tk.StringVar()
        self.gen_dry_targets_per_source = tk.StringVar(value="3")
        self.gen_dry_min_support = tk.StringVar(value="3")
        self.gen_dry_repeats = tk.StringVar(value="Contar repetições")

        latest = self.db.latest_draw()
        if latest:
            self.gen_dry_date.set(
                datetime.strptime(
                    latest["data"], "%Y-%m-%d"
                ).strftime("%d/%m/%Y")
            )

        self._page_title(
            "Gerador",
            "Escolha a estratégia, o tipo e exatamente quantos números quer.",
        )
        body = self._make_scrollable_page_body(self.content, "generator")

        controls = ttk.Frame(
            body, style="Card.TFrame", padding=8
        )
        controls.pack(fill="x", pady=(0, 6))

        # Origem
        ttk.Label(
            controls, text="Origem", style="Card.TLabel"
        ).grid(row=0,column=0,sticky="w",padx=(0,6))

        self.gen_cb_source = ttk.Combobox(
            controls,
            textvariable=self.gen_source,
            values=[
                "Método oficial — Reset",
                "Escolher manualmente",
            ],
            width=23,
            state="readonly",
        )
        self.gen_cb_source.grid(
            row=1,column=0,sticky="w",padx=(0,7),pady=(2,0)
        )
        self.gen_cb_source.bind(
            "<<ComboboxSelected>>",
            self.generator_source_changed,
        )

        ttk.Label(
            controls, text="Qtd. bichos", style="Card.TLabel"
        ).grid(row=0,column=1,sticky="w",padx=(0,6))

        self.gen_cb_animals = ttk.Combobox(
            controls,
            textvariable=self.gen_num_animals,
            values=["1","2","3","4","5","6","7","8","9","10"],
            width=6,
            state="readonly",
        )
        self.gen_cb_animals.grid(
            row=1,column=1,sticky="w",padx=(0,7),pady=(2,0)
        )

        self.gen_manual_btn = ttk.Button(
            controls,
            text="Selecionar bichos",
            command=self.generator_choose_manual,
            state="disabled",
        )
        self.gen_manual_btn.grid(
            row=1,column=2,sticky="w",padx=(0,10),pady=(2,0)
        )

        # Tipo
        ttk.Label(
            controls, text="Tipo", style="Card.TLabel"
        ).grid(row=2,column=0,sticky="w",padx=(0,6),pady=(9,0))

        self.gen_cb_kind = ttk.Combobox(
            controls,
            textvariable=self.gen_kind,
            values=["Grupo","Dezena","Centena","Milhar"],
            width=9,
            state="readonly",
        )
        self.gen_cb_kind.grid(
            row=3,column=0,sticky="w",padx=(0,7),pady=(2,0)
        )
        self.gen_cb_kind.bind(
            "<<ComboboxSelected>>",
            self.generator_kind_changed,
        )

        ttk.Label(
            controls, text="Estratégia", style="Card.TLabel"
        ).grid(row=2,column=1,sticky="w",padx=(0,6),pady=(9,0))

        self.gen_cb_strategy = ttk.Combobox(
            controls,
            textvariable=self.gen_strategy,
            values=[
                "Histórica simples",
                "Oficial 3+1",
                "Seca do Dia 1º",
            ],
            width=15,
            state="readonly",
        )
        self.gen_cb_strategy.grid(
            row=3,column=1,sticky="w",padx=(0,7),pady=(2,0)
        )
        self.gen_cb_strategy.bind(
            "<<ComboboxSelected>>",
            self.generator_strategy_changed,
        )

        ttk.Label(
            controls, text="Histórico", style="Card.TLabel"
        ).grid(row=2,column=2,sticky="w",padx=(0,6),pady=(9,0))

        self.gen_cb_scope = ttk.Combobox(
            controls,
            textvariable=self.gen_scope,
            values=["1º–5º","1º"],
            width=8,
            state="readonly",
        )
        self.gen_cb_scope.grid(
            row=3,column=2,sticky="w",padx=(0,7),pady=(2,0)
        )

        ttk.Label(
            controls, text="Quantidade", style="Card.TLabel"
        ).grid(row=2,column=3,sticky="w",padx=(0,6),pady=(9,0))

        # Quantidade livre: 1 a 100.
        self.gen_cb_total = ttk.Spinbox(
            controls,
            textvariable=self.gen_total,
            from_=1,
            to=100,
            width=7,
        )
        self.gen_cb_total.grid(
            row=3,column=3,sticky="w",padx=(0,7),pady=(2,0)
        )

        ttk.Button(
            controls,
            text="GERAR",
            style="Accent.TButton",
            command=self.generator_generate,
        ).grid(row=3,column=4,sticky="w",pady=(2,0))

        # ----------------------------------------------------
        # Opções recolhíveis da Seca do Dia
        # ----------------------------------------------------
        self.gen_dry_frame = ttk.Frame(
            body, style="Card.TFrame", padding=7
        )

        ttk.Label(
            self.gen_dry_frame,
            text="Dia-base fechado",
            style="Card.TLabel",
        ).grid(row=0,column=0,sticky="w",padx=(0,6))

        CalendarField(
            self.gen_dry_frame,
            self.gen_dry_date,
            width=10,
        ).grid(row=1,column=0,sticky="w",padx=(0,10),pady=(2,0))

        ttk.Label(
            self.gen_dry_frame,
            text="Alvos/fonte",
            style="Card.TLabel",
        ).grid(row=0,column=1,sticky="w",padx=(0,6))

        ttk.Combobox(
            self.gen_dry_frame,
            textvariable=self.gen_dry_targets_per_source,
            values=["1","2","3","4","5","6"],
            width=6,
            state="readonly",
        ).grid(row=1,column=1,sticky="w",padx=(0,10),pady=(2,0))

        ttk.Label(
            self.gen_dry_frame,
            text="Suporte mín.",
            style="Card.TLabel",
        ).grid(row=0,column=2,sticky="w",padx=(0,6))

        ttk.Combobox(
            self.gen_dry_frame,
            textvariable=self.gen_dry_min_support,
            values=["1","2","3","5","8","10"],
            width=6,
            state="readonly",
        ).grid(row=1,column=2,sticky="w",padx=(0,10),pady=(2,0))

        ttk.Label(
            self.gen_dry_frame,
            text="Repetição",
            style="Card.TLabel",
        ).grid(row=0,column=3,sticky="w",padx=(0,6))

        ttk.Combobox(
            self.gen_dry_frame,
            textvariable=self.gen_dry_repeats,
            values=[
                "Contar repetições",
                "Uma vez por bicho",
            ],
            width=18,
            state="readonly",
        ).grid(row=1,column=3,sticky="w",padx=(0,10),pady=(2,0))

        ttk.Button(
            self.gen_dry_frame,
            text="Detalhes da Seca",
            command=self.generator_open_dry_details,
        ).grid(row=1,column=4,sticky="w",pady=(2,0))

        # ----------------------------------------------------
        # Resumo e tabela
        # ----------------------------------------------------
        info = ttk.Frame(body)
        info.pack(fill="x", pady=(0, 5))

        self.gen_animals_label = ttk.Label(
            info,
            text="Os bichos serão calculados pelo GP-H Reset Cobertura v1.",
            wraplength=650,
        )
        self.gen_animals_label.pack(
            side="left", fill="x", expand=True
        )

        self.gen_summary_label = ttk.Label(
            info, text="Clique em GERAR."
        )
        self.gen_summary_label.pack(
            side="right", padx=(8, 0)
        )

        table = ttk.Frame(body)
        table.pack(fill="both", expand=True)

        cols = (
            "jogo","bicho","grupo","numero",
            "dezena","regra","freq","ultima",
        )
        self.gen_tree = ttk.Treeview(
            table,
            columns=cols,
            show="headings",
            selectmode="browse",
        )

        for c, label, width, anchor in [
            ("jogo","#",38,"center"),
            ("bicho","Bicho",105,"w"),
            ("grupo","G",40,"center"),
            ("numero","Número",80,"center"),
            ("dezena","Dz.",48,"center"),
            ("regra","Regra",125,"w"),
            ("freq","Ocorr.",65,"center"),
            ("ultima","Última ocorrência",175,"w"),
        ]:
            self.gen_tree.heading(c, text=label)
            self.gen_tree.column(
                c, width=width, anchor=anchor
            )

        y = ttk.Scrollbar(
            table,
            orient="vertical",
            command=self.gen_tree.yview,
        )
        x = ttk.Scrollbar(
            table,
            orient="horizontal",
            command=self.gen_tree.xview,
        )
        self.gen_tree.configure(
            yscrollcommand=y.set,
            xscrollcommand=x.set,
        )
        self.gen_tree.grid(
            row=0,column=0,sticky="nsew"
        )
        y.grid(row=0,column=1,sticky="ns")
        x.grid(row=1,column=0,sticky="ew")
        table.rowconfigure(0,weight=1)
        table.columnconfigure(0,weight=1)

        footer = ttk.Frame(
            body, padding=(0,5,0,0)
        )
        footer.pack(fill="x")

        self.gen_rule_label = ttk.Label(
            footer,
            text="Centena histórica simples.",
            wraplength=760,
        )
        self.gen_rule_label.pack(
            side="left", fill="x", expand=True
        )

        ttk.Button(
            footer,
            text="Congelar jogo",
            command=self.generator_freeze_game,
        ).pack(side="right", padx=(0, 6))

        ttk.Button(
            footer,
            text="Copiar números",
            command=self.generator_copy_numbers,
        ).pack(side="right")

        self.generator_refresh_control_states()

    def generator_source_changed(self, _event=None):
        self.generator_refresh_control_states()

        manual = (
            self.gen_source.get()
            == "Escolher manualmente"
        )
        if manual:
            if self.gen_manual_groups:
                self.generator_update_animals_label(
                    self.gen_manual_groups
                )
            else:
                self.gen_animals_label.configure(
                    text="Clique em Selecionar bichos."
                )
        else:
            self.gen_animals_label.configure(
                text=(
                    "Os bichos serão calculados pelo método "
                    "usando o último resultado."
                )
            )

    def generator_kind_changed(self, _event=None):
        kind = self.gen_kind.get()
        strategy = self.gen_strategy.get()

        if kind not in ("Centena", "Milhar"):
            self.gen_strategy.set(
                "Histórica simples"
            )
        elif (
            kind == "Milhar"
            and strategy == "Oficial 3+1"
        ):
            self.gen_strategy.set(
                "Histórica simples"
            )

        self.generator_refresh_control_states()

    def generator_strategy_changed(self, _event=None):
        # Ao entrar na Seca, mantém como padrão o formato antigo:
        # 2 bichos / 2 números, mas o usuário pode alterar livremente.
        if self.gen_strategy.get() == "Seca do Dia 1º":
            self.gen_num_animals.set("2")
            self.gen_total.set("2")

        self.generator_refresh_control_states()

    def generator_refresh_control_states(self):
        kind = self.gen_kind.get()
        strategy = self.gen_strategy.get()
        manual = (
            self.gen_source.get()
            == "Escolher manualmente"
        )

        official = (
            kind == "Centena"
            and strategy == "Oficial 3+1"
        )
        dry = (
            kind in ("Centena", "Milhar")
            and strategy == "Seca do Dia 1º"
        )

        # Estratégias válidas por tipo.
        if kind == "Centena":
            self.gen_cb_strategy.configure(
                values=[
                    "Histórica simples",
                    "Oficial 3+1",
                    "Seca do Dia 1º",
                ],
                state="readonly",
            )
        elif kind == "Milhar":
            if strategy == "Oficial 3+1":
                self.gen_strategy.set(
                    "Histórica simples"
                )
                strategy = "Histórica simples"

            self.gen_cb_strategy.configure(
                values=[
                    "Histórica simples",
                    "Seca do Dia 1º",
                ],
                state="readonly",
            )
            dry = (
                self.gen_strategy.get()
                == "Seca do Dia 1º"
            )
        else:
            self.gen_strategy.set(
                "Histórica simples"
            )
            self.gen_cb_strategy.configure(
                values=["Histórica simples"],
                state="disabled",
            )
            dry = False

        # Seca: origem e escopo são internos/fixos.
        if dry:
            self.gen_cb_source.configure(
                state="disabled"
            )
            self.gen_manual_btn.configure(
                state="disabled"
            )
            self.gen_cb_animals.configure(
                state="readonly"
            )

            self.gen_scope.set("1º")
            self.gen_cb_scope.configure(
                state="disabled"
            )
            self.gen_cb_total.configure(
                state="normal"
            )

            self.gen_dry_frame.pack(
                fill="x", pady=(0, 5)
            )

            self.gen_rule_label.configure(
                text=(
                    "Seca do Dia 1º: escolhe os bichos pelo histórico "
                    "dia→dia dos 1º prêmios. Depois gera Centena/Milhar "
                    "pela frequência exata de 1º prêmio. "
                    "Quantidade de bichos e números é livre."
                )
            )
            self.gen_animals_label.configure(
                text=(
                    "Os bichos serão escolhidos automaticamente "
                    "pela Seca do Dia."
                )
            )
            return

        self.gen_dry_frame.pack_forget()
        self.gen_cb_source.configure(
            state="readonly"
        )

        self.gen_manual_btn.configure(
            state="normal" if manual else "disabled"
        )
        self.gen_cb_animals.configure(
            state="disabled" if manual else "readonly"
        )

        if kind == "Grupo":
            self.gen_cb_scope.configure(
                state="disabled"
            )
            self.gen_cb_total.configure(
                state="disabled"
            )
            self.gen_rule_label.configure(
                text=(
                    "Grupo: mostra diretamente os bichos selecionados."
                )
            )
            return

        if official:
            self.gen_num_animals.set("5")
            self.gen_total.set("20")
            self.gen_scope.set("1º–5º")

            if not manual:
                self.gen_cb_animals.configure(
                    state="disabled"
                )

            self.gen_cb_scope.configure(
                state="disabled"
            )
            self.gen_cb_total.configure(
                state="disabled"
            )
            self.gen_rule_label.configure(
                text=(
                    "Oficial 3+1: 5 bichos × 4 Centenas. "
                    "3 na principal + 1 na segunda; "
                    "com congelamento da principal por 1 rodada."
                )
            )
            return

        self.gen_cb_scope.configure(
            state="readonly"
        )
        self.gen_cb_total.configure(
            state="normal"
        )

        texts = {
            "Dezena": (
                "Dezena: ordena as 4 dezenas do grupo "
                "pela frequência histórica."
            ),
            "Centena": (
                "Centena histórica simples: ordena as "
                "40 Centenas pela frequência."
            ),
            "Milhar": (
                "Milhar: ordena as 400 Milhares do grupo "
                "pela frequência histórica."
            ),
        }
        self.gen_rule_label.configure(
            text=texts.get(kind, "")
        )

    def generator_choose_manual(self):
        ManualGroupSelectorDialog(
            self,
            self.gen_manual_groups,
            self.generator_manual_selected,
        )

    def generator_manual_selected(self, groups):
        self.gen_manual_groups = groups
        self.generator_update_animals_label(
            groups
        )

    def generator_update_animals_label(self, groups):
        if not groups:
            self.gen_animals_label.configure(
                text="Nenhum bicho selecionado."
            )
            return

        self.gen_animals_label.configure(
            text=" • ".join(
                f"{BICHOS[g]} ({g:02d})"
                for g in groups
            )
        )

    def generator_resolve_groups(self):
        if self.gen_source.get() == "Escolher manualmente":
            if not self.gen_manual_groups:
                raise ValueError("Selecione pelo menos um bicho.")
            return list(self.gen_manual_groups)

        latest = self.db.latest_operational_draw()
        if not latest:
            raise ValueError(
                "A base não possui resultado operacional para usar no Reset."
            )

        result = self.db.method_reset_coverage_v1(
            latest["data"],
            latest["sorteio"],
            latest["hora"],
            top_n=int(self.gen_num_animals.get()),
        )

        groups = [r["grupo"] for r in result["selected"]]
        self.generator_update_animals_label(groups)
        return groups

    def generator_format_last(self, raw):
        if not raw:
            return "Nunca apareceu"

        parts = raw.split("|")
        if len(parts) >= 4:
            d = datetime.strptime(
                parts[0], "%Y-%m-%d"
            ).strftime("%d/%m/%Y")
            return (
                f"{d} {parts[1]} • "
                f"{parts[2]} • {parts[3]}º"
            )

        return raw

    def generator_generate(self):
        try:
            kind = self.gen_kind.get()
            strategy = self.gen_strategy.get()

            dry = (
                kind in ("Centena", "Milhar")
                and strategy == "Seca do Dia 1º"
            )

            for item in self.gen_tree.get_children():
                self.gen_tree.delete(item)

            if dry:
                base_date = parse_br_date(
                    self.gen_dry_date.get()
                )
                if not base_date:
                    raise ValueError(
                        "Escolha o dia-base da Seca do Dia."
                    )

                self.gen_current_generation = (
                    self.db.generate_dry_day_numbers(
                        base_date=base_date,
                        kind=kind,
                        total=int(
                            self.gen_total.get()
                        ),
                        top_animals=int(
                            self.gen_num_animals.get()
                        ),
                        targets_per_source=int(
                            self.gen_dry_targets_per_source.get()
                        ),
                        min_support=int(
                            self.gen_dry_min_support.get()
                        ),
                        count_repeats=(
                            self.gen_dry_repeats.get()
                            == "Contar repetições"
                        ),
                    )
                )

                groups = list(
                    self.gen_current_generation["groups"]
                )
                self.gen_current_groups = groups
                self.generator_update_animals_label(
                    groups
                )

            else:
                groups = self.generator_resolve_groups()
                self.gen_current_groups = groups

                if kind == "Grupo":
                    self.gen_current_generation = {
                        "kind":"Grupo",
                        "strategy":"Direto",
                        "groups":groups,
                        "rows":[
                            {
                                "grupo":g,
                                "bicho":BICHOS[g],
                                "numero":f"{g:02d}",
                                "dezena_base":"—",
                                "regra":"Grupo",
                                "ocorrencias":"",
                                "ultima":"",
                            }
                            for g in groups
                        ],
                    }

                elif (
                    kind == "Centena"
                    and strategy == "Oficial 3+1"
                ):
                    self.gen_current_generation = (
                        self.db.generate_centenas_3plus1(
                            groups=groups,
                            previous_draw=self.db.latest_operational_draw(),
                        )
                    )

                else:
                    self.gen_current_generation = (
                        self.db.generate_historical_numbers(
                            groups=groups,
                            kind=kind,
                            total=int(
                                self.gen_total.get()
                            ),
                            scope=self.gen_scope.get(),
                        )
                    )

            # Registra a origem dos bichos para que o desempenho futuro
            # compare o conjunto completo: seletor + estratégia numérica.
            if dry:
                self.gen_current_generation["selector"] = "Seca do Dia 1º"
            elif self.gen_source.get() == "Escolher manualmente":
                self.gen_current_generation["selector"] = "Manual"
            else:
                self.gen_current_generation["selector"] = "GP-H Reset Cobertura v1"

            rows = self.gen_current_generation["rows"]

            for i, r in enumerate(
                rows, start=1
            ):
                self.gen_tree.insert(
                    "", "end",
                    values=(
                        i,
                        r["bicho"],
                        f'{r["grupo"]:02d}',
                        r["numero"],
                        r.get(
                            "dezena_base", "—"
                        ),
                        r.get(
                            "regra", "Histórica"
                        ),
                        r.get(
                            "ocorrencias", ""
                        ),
                        self.generator_format_last(
                            r.get("ultima", "")
                        )
                        if kind != "Grupo"
                        else "—",
                    ),
                )

            if dry:
                method = (
                    self.gen_current_generation["method"]
                )
                date_txt = datetime.strptime(
                    self.gen_current_generation["base_date"],
                    "%Y-%m-%d",
                ).strftime("%d/%m/%Y")

                self.gen_summary_label.configure(
                    text=(
                        f"{len(rows)} {kind.lower()}(s) • "
                        f"{len(groups)} bicho(s) • "
                        f"base {date_txt} • "
                        f"{len(method['base_first_prizes'])} "
                        f"1º prêmio(s)"
                    )
                )

            elif kind == "Grupo":
                self.gen_summary_label.configure(
                    text=f"{len(rows)} grupo(s)."
                )

            elif (
                kind == "Centena"
                and strategy == "Oficial 3+1"
            ):
                frozen = [
                    a
                    for a in self.gen_current_generation["animals"]
                    if a["frozen"]
                ]
                ties = [
                    a
                    for a in self.gen_current_generation["animals"]
                    if a["principal_tied"]
                ]

                prev_draw = self.gen_current_generation.get("previous_draw")
                if prev_draw:
                    prev_date = datetime.strptime(
                        prev_draw["data"], "%Y-%m-%d"
                    ).strftime("%d/%m/%Y")
                    base_txt = (
                        f"{prev_draw['sorteio']} {prev_draw['hora']} "
                        f"de {prev_date}"
                    )
                else:
                    base_txt = "base operacional não identificada"

                summary = (
                    f"20 Centenas • regra 3+1 • base {base_txt}"
                )

                if frozen:
                    summary += (
                        " • congelada(s): "
                        + ", ".join(
                            f"{a['bicho']}({a['principal']})"
                            for a in frozen
                        )
                    )
                else:
                    summary += (
                        " • sem congelamento"
                    )

                if ties:
                    summary += (
                        " • empate técnico em: "
                        + ", ".join(
                            a["bicho"]
                            for a in ties
                        )
                    )

                self.gen_summary_label.configure(
                    text=summary
                )

            else:
                counts = (
                    self.gen_current_generation["counts"]
                )
                self.gen_summary_label.configure(
                    text=" | ".join(
                        f"{BICHOS[g]}:{counts[g]}"
                        for g in groups
                    )
                )

        except Exception as e:
            messagebox.showerror(
                "Gerador", str(e), parent=self
            )

    def generator_open_dry_details(self):
        generation = self.gen_current_generation

        if (
            not generation
            or generation.get("strategy")
            != "Seca do Dia 1º"
        ):
            messagebox.showinfo(
                "Seca do Dia",
                "Gere primeiro uma Seca do Dia.",
                parent=self,
            )
            return

        DryDayTechnicalDialog(
            self,
            generation["method"],
        )

    def generator_freeze_game(self):
        generation = self.gen_current_generation

        if not generation or not generation.get("rows"):
            messagebox.showinfo(
                "Congelar jogo",
                "Gere o jogo primeiro.",
                parent=self,
            )
            return

        selector = generation.get("selector", "Não registrado")
        strategy = generation.get("strategy", "Histórica simples")
        kind = generation.get("kind", self.gen_kind.get())
        qty = len(generation["rows"])

        if strategy == "Seca do Dia 1º":
            target_text = "próximo dia disponível • somente 1º prêmio"
            base_draw = None
        else:
            target = self.db.next_operational_target()
            target_text = (
                "próxima rodada operacional • "
                + generation.get("scope", "1º–5º")
            )
            base_draw = self.db.latest_operational_draw()

            already = self.db.pending_operational_games_for_target(target)
            if already:
                if target:
                    td = datetime.strptime(
                        target["data"], "%Y-%m-%d"
                    ).strftime("%d/%m/%Y")
                    target_name = (
                        f"{target['sorteio']} {target['hora']} • {td}"
                    )
                else:
                    target_name = "próxima rodada"

                continue_anyway = messagebox.askyesno(
                    "Jogo já congelado para esta rodada",
                    (
                        f"Já existe(m) {len(already)} jogo(s) congelado(s) "
                        f"aguardando {target_name}.\n\n"
                        "Você pode criar outro para testar uma variação, "
                        "mas isso pode duplicar uma aposta sem querer.\n\n"
                        "Deseja congelar outro mesmo assim?"
                    ),
                    parent=self,
                )
                if not continue_anyway:
                    return

        ok = messagebox.askyesno(
            "Congelar jogo",
            (
                f"Seletor: {selector}\n"
                f"Estratégia: {strategy}\n"
                f"Tipo: {kind}\n"
                f"Quantidade: {qty}\n"
                f"Alvo de auditoria: {target_text}\n\n"
                "Congelar exatamente este jogo?"
            ),
            parent=self,
        )
        if not ok:
            return

        game_id = self.db.freeze_generated_game(
            generation,
            base_draw=base_draw,
        )

        self._update_results_nav_badge()

        messagebox.showinfo(
            "Jogo congelado",
            (
                f"Jogo #{game_id} congelado.\n\n"
                "Ele ficará em Resultados e entrará no painel de desempenho "
                "quando for auditado."
            ),
            parent=self,
        )

    def generator_copy_numbers(self):
        if (
            not self.gen_current_generation
            or not self.gen_current_generation.get("rows")
        ):
            messagebox.showinfo(
                "Gerador",
                "Gere os jogos primeiro.",
                parent=self,
            )
            return

        numbers = [
            r["numero"]
            for r in self.gen_current_generation["rows"]
        ]

        self.clipboard_clear()
        self.clipboard_append(
            ", ".join(numbers)
        )
        self.update()

        messagebox.showinfo(
            "Gerador",
            "Números copiados.",
            parent=self,
        )

    def first_run_prompt(self):
        if messagebox.askyesno(
            "Primeiro uso",
            "A base está vazia.\n\nDeseja baixar agora o histórico de 02/01/2026 até hoje?\n"
            "Na primeira vez isso pode levar alguns minutos."
        ):
            self.start_sync()

    def _current_search_date_scope(self):
        """Resolve Data específica ou De/Até para o formato ISO do banco."""
        exact = parse_br_date(self.var_date.get())
        d1 = parse_br_date(self.var_from.get())
        d2 = parse_br_date(self.var_to.get())

        if exact:
            return exact, exact
        return d1, d2

    def refresh_search_filter_options(self, prefer=None):
        try:
            d1, d2 = self._current_search_date_scope()
        except ValueError:
            return

        values = self._draw_combo_values(d1, d2)
        if self.var_draw.get() not in values:
            self.var_draw.set("Todos")
        self.cb_draw["values"] = values

    def _draw_combo_label(self, sorteio, hora):
        if not sorteio or not hora:
            return "Todos"
        return f"{sorteio} • {hora}"

    def _split_draw_combo(self, value):
        value = (value or "Todos").strip()
        if value == "Todos" or " • " not in value:
            return "Todos", "Todos"
        sorteio, hora = value.split(" • ", 1)
        return sorteio.strip(), hora.strip()

    def _draw_combo_values(self, date_from=None, date_to=None):
        return ["Todos"] + [
            self._draw_combo_label(s, h)
            for s, h in self.db.draw_combo_options(
                date_from=date_from,
                date_to=date_to,
            )
        ]


    def refresh_filters(self):
        self.refresh_search_filter_options(prefer=None)

    def on_search_sort_changed(self, _event=None):
        self.refresh_search_filter_options()

    def on_search_hour_changed(self, _event=None):
        self.refresh_search_filter_options()

    def on_exact_date_changed(self):
        if self.var_date.get().strip():
            self.var_from.set("")
            self.var_to.set("")
        if hasattr(self, "cb_draw"):
            self.refresh_search_filter_options()

    def on_range_date_changed(self):
        if self.var_from.get().strip() or self.var_to.get().strip():
            self.var_date.set("")
        if hasattr(self, "cb_draw"):
            self.refresh_search_filter_options()

    def clear_filters(self):
        self.var_type.set("Todos")
        self.var_value.set("")
        self.var_date.set("")
        self.var_from.set("")
        self.var_to.set("")
        self.var_draw.set("Todos")
        self.var_prize.set("Todos")
        self.refresh_search_filter_options()
        self.search()

    def search(self):
        try:
            exact = parse_br_date(self.var_date.get())
            d1 = parse_br_date(self.var_from.get())
            d2 = parse_br_date(self.var_to.get())

            if exact:
                d1 = exact
                d2 = exact

            if d1 and d2 and d1 > d2:
                raise ValueError("A data inicial não pode ser maior que a final.")

            sorteio, hora = self._split_draw_combo(self.var_draw.get())

            rows = self.db.search(
                tipo=self.var_type.get(),
                valor=self.var_value.get(),
                date_from=d1,
                date_to=d2,
                sorteio=sorteio,
                hora=hora,
                premio=self.var_prize.get(),
            )
            self.last_rows = rows

            for item in self.tree.get_children():
                self.tree.delete(item)

            for r in rows:
                d = datetime.strptime(r["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
                self.tree.insert("", "end", values=(
                    d, r["sorteio"], r["hora"], f'{r["premio"]}º',
                    r["milhar"], r["centena"], r["dezena"],
                    f'{r["grupo"]:02d}', r["bicho"]
                ))

            self.update_summary(rows)
            self.status.configure(
                text=f"{len(rows):,}".replace(",", ".") + " prêmio(s) na pesquisa."
            )
        except Exception as e:
            messagebox.showerror("Pesquisa", str(e))

    def update_summary(self, rows):
        total = len(rows)
        draws = len({(r["data"], r["sorteio"], r["hora"]) for r in rows})
        days = len({r["data"] for r in rows})
        by_draw = Counter((r["sorteio"], r["hora"]) for r in rows)

        lines = [f"Encontrados: {total} prêmio(s) • {draws} extração(ões) • {days} dia(s)."]
        if rows:
            latest = max(rows, key=lambda r: (r["data"], r["hora"], -r["premio"]))
            ld = datetime.strptime(latest["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            lines.append(
                f"Ocorrência mais recente na pesquisa: {ld} • {latest['sorteio']} {latest['hora']} • "
                f"{latest['premio']}º • {latest['milhar']} • {latest['bicho']}."
            )
        if by_draw:
            ranked = sorted(by_draw.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
            lines.append("Por horário: " + " | ".join(f"{s} {h}: {n}" for (s,h), n in ranked))

        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", "\n".join(lines))
        self.summary.configure(state="disabled")


    def _widget_alive(self, name):
        widget = getattr(self, name, None)
        try:
            return widget is not None and bool(widget.winfo_exists())
        except Exception:
            return False

    def _set_action_buttons(self, enabled=True):
        state = "normal" if enabled else "disabled"
        for name in ("update_btn", "sync_btn"):
            if self._widget_alive(name):
                getattr(self, name).configure(state=state)

    def base_verify_gaps(self):
        gaps = self.db.possible_operational_gaps(limit=1000)

        if not gaps:
            messagebox.showinfo(
                "Verificar lacunas",
                "Nenhuma possível lacuna operacional foi encontrada.",
                parent=self,
            )
            return

        text = (
            f"Foram encontrados {len(gaps)} horário(s) operacional(is) "
            "sem resultado na base.\n\n"
            "É uma lista de verificação, não uma confirmação de erro: "
            "feriados ou mudanças excepcionais podem explicar alguns casos.\n\n"
            "Primeiros registros:"
        )

        for gap in gaps[:20]:
            d = datetime.strptime(
                gap["data"], "%Y-%m-%d"
            ).strftime("%d/%m/%Y")
            text += (
                f"\n- {d} • {gap['sorteio']} {gap['hora']}"
            )

        if len(gaps) > 20:
            text += f"\n- ... e mais {len(gaps) - 20}."

        messagebox.showinfo(
            "Possíveis lacunas",
            text,
            parent=self,
        )

    def create_auto_backup(self, reason):
        if self.db.count() == 0 and self.db.game_count() == 0:
            return None
        return self.db.auto_backup(
            reason=reason,
            keep=5,
        )

    def base_backup(self):
        try:
            default_name = (
                "GP-H_backup_"
                + datetime.now().strftime("%Y-%m-%d_%H-%M")
                + ".db"
            )

            path = filedialog.asksaveasfilename(
                parent=self,
                title="Salvar backup da base GP-H",
                defaultextension=".db",
                initialfile=default_name,
                filetypes=[
                    ("Banco SQLite", "*.db"),
                    ("Todos os arquivos", "*.*"),
                ],
            )
            if not path:
                return

            saved = self.db.backup_to(path)
            messagebox.showinfo(
                "Backup",
                f"Backup criado com sucesso:\n{saved}",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror(
                "Backup",
                str(exc),
                parent=self,
            )

    def base_import_database(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Selecionar banco GP-H anterior",
            filetypes=[
                ("Banco SQLite", "*.db"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if not path:
            return

        try:
            info = self.db.inspect_external_database(path)
            if info["error"]:
                raise ValueError(info["error"])

            ok = messagebox.askyesno(
                "Importar / mesclar banco",
                (
                    f"Arquivo:\n{path}\n\n"
                    f"Prêmios encontrados: {info['resultados']}\n"
                    f"Jogos congelados: {info['jogos']}\n"
                    f"Última data: {info['latest_date'] or '—'}\n\n"
                    "A base atual NÃO será substituída. "
                    "Somente lacunas e jogos ausentes serão incorporados.\n\n"
                    "Continuar?"
                ),
                parent=self,
            )
            if not ok:
                return

            self.create_auto_backup("antes_importacao")
            report = self.db.merge_external_database(path)

            messagebox.showinfo(
                "Importação concluída",
                (
                    f"{report['resultados_adicionados']} prêmio(s) novo(s).\n"
                    f"{report['jogos_adicionados']} jogo(s) congelado(s) novo(s)."
                ),
                parent=self,
            )
            self.show_base_config()

        except Exception as exc:
            messagebox.showerror(
                "Importar banco",
                str(exc),
                parent=self,
            )

    def base_open_data_folder(self):
        self._open_folder(DATA_DIR, "Pasta da base")


    def refresh_current_page(self):
        if self._page == "search":
            self.refresh_filters()
            self.search()
        elif self._page == "home":
            self.show_home()
        elif self._page == "statistics":
            self.show_statistics_page()
        elif self._page == "decision":
            self.show_decision_page()
        elif self._page == "pulls":
            self.show_pulls_page()
        elif self._page == "shadow_lab":
            self.show_shadow_lab_page()
        elif self._page == "methods":
            self.show_methods_page()
        elif self._page == "generator":
            self.show_generator_page()
        elif self._page == "play":
            # Nunca destruir uma montagem em andamento só para refletir dados externos.
            if getattr(self, "play_generation", None) or getattr(self, "play_ticket_draft", None):
                try:
                    self.status.configure(
                        text="Dados atualizados; a montagem atual foi preservada."
                    )
                except Exception:
                    pass
                return
            self.show_play_page()
        elif self._page == "results":
            self.show_results()
        elif self._page == "base":
            self.show_base_config()

    def open_statistics(self):
        self.show_statistics_page()

    def open_pulls(self):
        self.show_pulls_page()

    def open_methods_lab(self):
        self.show_methods_page()

    def open_game_generator(self):
        self.show_generator_page()

    def open_manual(self):
        ManualDialog(self, self.db, self.after_manual_saved)

    def after_manual_saved(self):
        self.db.audit_frozen_games()
        self._update_results_nav_badge()
        self.refresh_current_page()
        self.show_audit()


    def start_update_search(self):
        if self.sync_running or self.update_running:
            return
        self.update_running = True
        self._set_action_buttons(False)
        self.status.configure(text="Procurando resultados que faltam na internet…")
        threading.Thread(target=self.update_search_worker, daemon=True).start()

    def update_search_worker(self):
        """
        Busca somente o período necessário:
        - base vazia: 02/01/2026 até hoje;
        - base existente: último dia armazenado - 30 dias até hoje.
        A janela mensal ajuda a recuperar resultados ausentes e correções tardias
        sem precisar baixar novamente todo o histórico.
        """
        try:
            today = date.today()
            latest = self.db.latest_date()
            if latest is None:
                start = START_DATE
            else:
                start = max(START_DATE, latest - timedelta(days=WEB_RESULT_RECHECK_DAYS))

            total_days = (today - start).days + 1
            all_rows = []
            errors = []

            for idx in range(total_days):
                day = start + timedelta(days=idx)
                try:
                    _, rows = fetch_day(day)
                    all_rows.extend(rows)
                    state = f"{len(rows)} prêmio(s) encontrados" if rows else "sem resultados"
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        state = "página ainda não disponível"
                    else:
                        state = f"erro HTTP {e.code}"
                        errors.append(f"{day.strftime('%d/%m/%Y')}: HTTP {e.code}")
                except Exception as e:
                    state = "erro"
                    errors.append(f"{day.strftime('%d/%m/%Y')}: {e}")

                self.sync_queue.put(("update_progress", idx + 1, total_days, day, state))
                time.sleep(0.08)

            novos, alterados, iguais = self.db.compare_web_rows(all_rows)
            self.sync_queue.put(("update_done", {
                "start": start,
                "end": today,
                "novos": novos,
                "alterados": alterados,
                "iguais": iguais,
                "errors": errors,
            }))
        except Exception as e:
            self.sync_queue.put(("update_fatal", str(e)))

    def show_update_preview(self, report):
        novos = report["novos"]
        alterados = report["alterados"]
        erros = report["errors"]

        if not novos and not alterados:
            msg = (
                "Não encontrei resultados novos para adicionar.\n\n"
                f"Período verificado: {report['start'].strftime('%d/%m/%Y')} "
                f"até {report['end'].strftime('%d/%m/%Y')}."
            )
            if erros:
                msg += f"\n\nHouve {len(erros)} erro(s) de acesso durante a busca."
            messagebox.showinfo("GP-H — Atualizações", msg)
            return

        UpdatePreviewDialog(
            self,
            self.db,
            novos=novos,
            alterados=alterados,
            iguais=report["iguais"],
            on_apply=self.after_web_update,
        )

    def after_web_update(self):
        self.db.audit_frozen_games()
        self._update_results_nav_badge()
        self.refresh_current_page()
        # Revisão já foi executada no momento da gravação.
        audit = self.db.audit()
        self.status.configure(
            text=(
                f"Atualização aplicada e revisada: {audit['total']:,} prêmios • "
                f"{audit['draws']:,} extrações."
            ).replace(",", ".")
        )

    def start_sync(self):
        if self.sync_running:
            return

        try:
            backup = self.create_auto_backup(
                "antes_sincronizacao"
            )
        except Exception as exc:
            messagebox.showerror(
                "Sincronização",
                (
                    "Não consegui criar o backup automático.\n\n"
                    f"{exc}\n\n"
                    "A sincronização não foi iniciada."
                ),
                parent=self,
            )
            return

        self.sync_running = True
        self._set_action_buttons(False)

        self.status.configure(
            text=(
                "Backup automático criado. Preparando sincronização…"
                if backup
                else "Preparando sincronização…"
            )
        )

        threading.Thread(
            target=self.sync_worker,
            daemon=True,
        ).start()

    def sync_worker(self):
        try:
            today = date.today()
            total_days = (today - START_DATE).days + 1
            fetched = 0
            skipped = 0
            errors = []
            inserted = 0

            for idx in range(total_days):
                day = START_DATE + timedelta(days=idx)

                # Em atualizações futuras, datas antigas já presentes são puladas.
                # Os últimos 7 dias são sempre relidos para absorver resultados ausentes e
                # correções recentes do site. Datas mais antigas já presentes são puladas.
                if day < today - timedelta(days=WEB_RESULT_RECHECK_DAYS) and self.db.has_date(day):
                    skipped += 1
                    self.sync_queue.put(("progress", idx + 1, total_days, day, "já existente"))
                    continue

                try:
                    _, rows = fetch_day(day)
                    if rows:
                        self.db.upsert_rows(rows)
                        inserted += len(rows)
                        fetched += 1
                        state = f"{len(rows)} prêmios"
                    else:
                        state = "sem 1º–5º publicado"
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        state = "página não encontrada"
                    else:
                        errors.append(f"{day.strftime('%d/%m/%Y')}: HTTP {e.code}")
                        state = f"erro HTTP {e.code}"
                except Exception as e:
                    errors.append(f"{day.strftime('%d/%m/%Y')}: {e}")
                    state = "erro"

                self.sync_queue.put(("progress", idx + 1, total_days, day, state))
                time.sleep(0.08)

            audit = self.db.audit()
            self.sync_queue.put(("done", {
                "fetched_days": fetched,
                "skipped_days": skipped,
                "processed_rows": inserted,
                "errors": errors,
                "audit": audit,
            }))
        except Exception as e:
            self.sync_queue.put(("fatal", str(e)))

    def poll_queue(self):
        try:
            while True:
                item = self.sync_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, current, total, day, state = item
                    pct = current / max(total, 1) * 100
                    self.status.configure(
                        text=f"Sincronizando {day.strftime('%d/%m/%Y')} — {state} — {pct:.0f}%"
                    )
                elif kind == "done":
                    self.sync_running = False
                    self._set_action_buttons(True)
                    report = item[1]
                    self.db.record_network_check(
                        "Sincronização completa",
                        len(report.get("errors", [])),
                    )
                    self.db.audit_frozen_games()
                    self._update_results_nav_badge()
                    self.refresh_current_page()
                    self.show_audit(report=report)
                elif kind == "fatal":
                    self.sync_running = False
                    self._set_action_buttons(True)
                    self.status.configure(text="Falha na sincronização.")
                    messagebox.showerror("Sincronização", item[1])
                elif kind == "account_sync_done":
                    _, report, silent = item
                    self.account_sync_running = False
                    profile = dict(self.account_profile or {})
                    profile["sync_status"] = "ok"
                    profile["last_sync_at"] = report.get("last_sync_at") or datetime.now().isoformat(timespec="seconds")
                    profile["sync_last_error"] = None
                    self.account_profile = save_account_profile(profile)

                    # v0.27.1: NUNCA reconstruir a página ativa ao concluir sync multi-PC.
                    # show_play_page()/show_* destroem os widgets, resetam o scroll e
                    # podem apagar uma geração ainda não adicionada ao bilhete. Os dados
                    # recebidos já estão no banco e aparecerão naturalmente ao navegar
                    # ou atualizar a tela de propósito.
                    try:
                        self.db.audit_frozen_games()
                    except Exception:
                        pass
                    try:
                        self._update_results_nav_badge()
                    except Exception:
                        pass

                    if not silent:
                        self._refresh_account_status()
                        self.status.configure(text="Sincronização entre PCs concluída.")
                        messagebox.showinfo(
                            "Sincronização entre PCs",
                            self._account_sync_report_text(report),
                            parent=self,
                        )
                elif kind == "account_sync_error":
                    _, error, silent = item
                    self.account_sync_running = False
                    profile = dict(self.account_profile or {})
                    profile["sync_status"] = "error"
                    profile["sync_last_error"] = str(error)
                    self.account_profile = save_account_profile(profile)
                    self._refresh_account_status()
                    self.status.configure(text="Falha na sincronização entre PCs.")
                    if not silent:
                        messagebox.showerror(
                            "Sincronização entre PCs",
                            str(error),
                            parent=self,
                        )
                elif kind == "update_progress":
                    _, current, total, day, state = item
                    pct = current / max(total, 1) * 100
                    self.status.configure(
                        text=f"Buscando {day.strftime('%d/%m/%Y')} — {state} — {pct:.0f}%"
                    )
                elif kind == "update_done":
                    self.update_running = False
                    self._set_action_buttons(True)
                    report = item[1]
                    self.db.record_network_check(
                        "Buscar atualizações",
                        len(report.get("errors", [])),
                    )
                    self.status.configure(text="Busca de atualizações concluída.")
                    self.show_update_preview(report)
                elif kind == "update_fatal":
                    self.update_running = False
                    self._set_action_buttons(True)
                    self.status.configure(text="Falha na busca de atualizações.")
                    messagebox.showerror("Buscar atualizações", item[1])
                elif kind == "program_update_check_done":
                    _, result, manual = item
                    self._program_update_check_done(result, manual)
                elif kind == "program_update_download_done":
                    _, result, release = item
                    self._program_update_download_done(result, release)
        except queue.Empty:
            pass
        self.after(150, self.poll_queue)

    def show_audit(self, report=None):
        audit = report["audit"] if report else self.db.audit()
        problems = audit["problems"]
        inc = audit["incomplete"]

        min_d = audit["min_date"] or "—"
        max_d = audit["max_date"] or "—"
        if min_d != "—":
            min_d = datetime.strptime(min_d, "%Y-%m-%d").strftime("%d/%m/%Y")
        if max_d != "—":
            max_d = datetime.strptime(max_d, "%Y-%m-%d").strftime("%d/%m/%Y")

        text = (
            f"REVISÃO DA BASE — {APP_NAME} v{APP_VERSION}\n\n"
            f"Período: {min_d} a {max_d}\n"
            f"Prêmios armazenados: {audit['total']:,}\n"
            f"Extrações: {audit['draws']:,}\n"
        ).replace(",", ".")

        if problems:
            text += "\nProblemas encontrados:\n- " + "\n- ".join(problems)
        else:
            text += "\n✓ Nenhuma inconsistência estrutural encontrada."

        if inc:
            # Uma extração do dia atual pode estar incompleta enquanto o site atualiza.
            text += f"\n\nAtenção: {len(inc)} extração(ões) com quantidade diferente de 5 prêmios."
            for d, s, h, c in inc[:8]:
                text += f"\n- {d} • {s} {h}: {c} prêmio(s)"
            if len(inc) > 8:
                text += f"\n- ... e mais {len(inc)-8}."

        if report:
            text += (
                f"\n\nSincronização:\n"
                f"Dias baixados/relidos: {report['fetched_days']}\n"
                f"Dias antigos já existentes e pulados: {report['skipped_days']}\n"
                f"Linhas processadas: {report['processed_rows']}\n"
                f"Falhas de acesso à página: {len(report['errors'])}"
            )
            if report["errors"]:
                text += (
                    "\n\nEssas falhas indicam dias que não puderam ser "
                    "verificados nessa tentativa; não significam, sozinhas, "
                    "que o resultado esteja ausente da base."
                )
                text += "\n\nPrimeiras falhas:\n- " + "\n- ".join(report["errors"][:8])

        self.status.configure(
            text=f"Base revisada: {audit['total']:,} prêmios • {audit['draws']:,} extrações.".replace(",", ".")
        )
        messagebox.showinfo("Revisão concluída", text)

    def export_csv(self):
        if not self.last_rows:
            messagebox.showwarning("Exportar", "Não há resultados na pesquisa atual.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialdir=str(EXPORT_DIR),
            initialfile="gph_pesquisa.csv",
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Data","Sorteio","Hora","Prêmio","Milhar","Centena","Dezena","Grupo","Bicho","Fonte"])
            for r in self.last_rows:
                values = [
                    r["data"], r["sorteio"], r["hora"],
                    str(r["premio"]), str(r["milhar"]).zfill(4),
                    str(r["centena"]).zfill(3), str(r["dezena"]).zfill(2),
                    str(r["grupo"]).zfill(2), r["bicho"], r["fonte"],
                ]
                w.writerow([self._csv_text(v) for v in values])
        messagebox.showinfo(
            "Exportar",
            f"Arquivo criado com campos em formato de texto e zeros preservados:\n{path}"
        )


if __name__ == "__main__":
    try:
        app = App()
        if not getattr(app, "_startup_cancelled", False):
            app.mainloop()
    except BaseException as exc:
        log_path = write_crash_log(exc)
        try:
            # Cria uma raiz mínima só para mostrar o erro, caso a janela principal tenha falhado.
            err_root = tk.Tk()
            err_root.withdraw()
            msg = "O GP-H encontrou um erro ao abrir."
            if log_path:
                msg += f"\n\nFoi criado o arquivo:\n{log_path}\n\nEnvie esse arquivo ou uma foto para o ChatGPT."
            else:
                msg += "\n\nNão foi possível criar o relatório de erro."
            messagebox.showerror("GP-H Central - erro ao abrir", msg)
            err_root.destroy()
        except Exception:
            pass
        raise
