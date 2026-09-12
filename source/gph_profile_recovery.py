"""Recuperação resiliente do perfil local do GP-H — v0.48.3.

Corrige o caso em que account_profile.json some, fica truncado/corrompido ou
permanece em uma pasta antiga após atualização/extracão. A recuperação é
conservadora: só entra automaticamente quando existe um único código válido ou
quando a evidência aponta claramente para o computador atual.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

PROFILE_BACKUP_NAME = "account_profile.backup.json"
RECOVERY_LOG_NAME = "profile_recovery.log"
CODE_RE = re.compile(r"GPH-[A-Z0-9]{4}-[A-Z0-9]{4}")
MAX_TEXT_SCAN_FILES = 250
MAX_TEXT_SCAN_BYTES = 1024 * 1024


def _atomic_json(path: Path, data: dict):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _runtime_install_dir(central):
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(getattr(central, "ROOT", Path(__file__).resolve().parent)).resolve()


def _valid_profile(central, data):
    if not isinstance(data, dict):
        return False
    return bool(central.valid_profile_code(data.get("profile_code")))


def _normalize_profile(central, data, *, source="recovery", sync_folder=None):
    data = dict(data or {})
    code = central.normalize_profile_code(data.get("profile_code"))
    if not central.valid_profile_code(code):
        return None
    now = datetime.now().isoformat(timespec="seconds")
    out = dict(data)
    out["profile_code"] = code
    out["profile_name"] = str(out.get("profile_name") or "Perfil GP-H").strip() or "Perfil GP-H"
    out["remember_login"] = bool(out.get("remember_login", True))
    out["device_id"] = str(out.get("device_id") or uuid.uuid4())
    out["device_name"] = str(out.get("device_name") or central.default_device_name()).strip() or central.default_device_name()
    out["created_at"] = out.get("created_at") or now
    out["linked_at"] = out.get("linked_at") or now
    out.setdefault("last_login_at", None)
    if sync_folder:
        out["sync_folder"] = str(sync_folder)
        out["sync_enabled"] = True
    out["profile_recovered_at"] = now
    out["profile_recovered_from"] = source
    return out


def _read_json_candidate(central, path: Path, priority: int, source: str):
    path = Path(path)
    if not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    found = []
    try:
        data = json.loads(raw)
        if _valid_profile(central, data):
            found.append((priority, _normalize_profile(central, data, source=source), str(path)))
            return found
    except Exception:
        pass

    # Salvamento de JSON truncado: basta o código ainda estar presente.
    codes = sorted(set(CODE_RE.findall(raw.upper())))
    if len(codes) == 1 and central.valid_profile_code(codes[0]):
        name = "Perfil GP-H"
        m = re.search(r'"profile_name"\s*:\s*"([^"\\]{2,60})"', raw)
        if m:
            name = m.group(1).strip() or name
        partial = {"profile_code": codes[0], "profile_name": name, "remember_login": True}
        found.append((priority - 1, _normalize_profile(central, partial, source=source + " (salvado)"), str(path)))
    return found


def _nearby_profile_paths(central):
    seen = set()
    install = _runtime_install_dir(central)
    roots = [
        Path(central.DATA_DIR),
        install,
        install / "dados",
        install.parent,
    ]
    for env_name in ("LOCALAPPDATA", "APPDATA"):
        value = os.environ.get(env_name)
        if value:
            base = Path(value)
            roots.extend([
                base / "GP-H_Central_Historica",
                base / "GP-H_Central_Historica" / "dados",
                base / "GP-H Central Historica",
                base / "GP-H Central Historica" / "dados",
            ])
    user = os.environ.get("USERPROFILE")
    if user:
        home = Path(user)
        roots.extend([home / "Desktop", home / "Documents", home / "Downloads"])

    candidates = []
    for root in roots:
        try:
            root = root.resolve()
        except Exception:
            continue
        for path in (root / "account_profile.json", root / PROFILE_BACKUP_NAME, root / "dados" / "account_profile.json", root / "dados" / PROFILE_BACKUP_NAME):
            key = str(path).lower()
            if key not in seen:
                seen.add(key); candidates.append(path)

    # Versões extraídas lado a lado: limita a filhos imediatos para não varrer o disco.
    for parent in {install.parent, install.parent.parent if install.parent != install else install.parent}:
        try:
            children = list(parent.iterdir())[:200]
        except Exception:
            continue
        for child in children:
            if not child.is_dir():
                continue
            name = child.name.lower()
            if "gp-h" not in name and "gph" not in name:
                continue
            for path in (child / "account_profile.json", child / "dados" / "account_profile.json", child / "dados" / PROFILE_BACKUP_NAME):
                key = str(path).lower()
                if key not in seen:
                    seen.add(key); candidates.append(path)
    return candidates


def _sync_candidates(central):
    roots = []
    for env_name in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer", "Dropbox"):
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value))
    user = os.environ.get("USERPROFILE")
    if user:
        home = Path(user)
        roots.extend([home / "OneDrive", home / "Dropbox", home / "Google Drive"])

    out = []
    visited = set()
    for root in roots:
        try:
            root = root.resolve()
        except Exception:
            continue
        containers = [root / "GP-H_Central_Sync"]
        try:
            containers += [p / "GP-H_Central_Sync" for p in list(root.iterdir())[:100] if p.is_dir()]
        except Exception:
            pass
        for container in containers:
            key = str(container).lower()
            if key in visited or not container.is_dir():
                continue
            visited.add(key)
            try:
                profile_dirs = [p for p in container.iterdir() if p.is_dir()][:50]
            except Exception:
                continue
            for profile_dir in profile_dirs:
                manifest = profile_dir / "manifest.json"
                if not manifest.is_file():
                    continue
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                except Exception:
                    continue
                code = central.normalize_profile_code(data.get("profile_code") or profile_dir.name)
                if not central.valid_profile_code(code):
                    continue
                profile = {
                    "profile_code": code,
                    "profile_name": data.get("profile_name") or "Perfil GP-H",
                    "remember_login": True,
                }
                current_name = central.default_device_name().strip().lower()
                devices = profile_dir / "devices"
                if devices.is_dir():
                    try:
                        for dev_path in list(devices.glob("*.json"))[:100]:
                            try:
                                dev_data = json.loads(dev_path.read_text(encoding="utf-8"))
                                dev = dev_data.get("device") or {}
                                if str(dev.get("device_name") or "").strip().lower() == current_name:
                                    profile["device_id"] = dev.get("device_id")
                                    profile["device_name"] = dev.get("device_name")
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass
                normalized = _normalize_profile(central, profile, source="pasta de sincronização", sync_folder=container.parent)
                if normalized:
                    priority = 95 if normalized.get("device_id") else 75
                    out.append((priority, normalized, str(manifest)))
    return out


def _text_scan_candidates(central):
    base = Path(central.DATA_DIR)
    if not base.is_dir():
        return []
    by_code = {}
    count = 0
    try:
        iterator = base.rglob("*")
    except Exception:
        return []
    for path in iterator:
        if count >= MAX_TEXT_SCAN_FILES:
            break
        try:
            if not path.is_file() or path.suffix.lower() not in {".json", ".txt", ".log"}:
                continue
            if path.stat().st_size > MAX_TEXT_SCAN_BYTES:
                continue
            count += 1
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for code in set(CODE_RE.findall(raw.upper())):
            if central.valid_profile_code(code):
                by_code.setdefault(code, str(path))
    out = []
    for code, source in by_code.items():
        profile = _normalize_profile(central, {"profile_code": code, "profile_name": "Perfil GP-H", "remember_login": True}, source="vestígio local")
        if profile:
            out.append((40, profile, source))
    return out


def recover_profile(central):
    candidates = []
    current = Path(central.ACCOUNT_PROFILE_PATH)
    for path in _nearby_profile_paths(central):
        priority = 120 if path == current else (110 if path.name == PROFILE_BACKUP_NAME and path.parent == current.parent else 80)
        candidates.extend(_read_json_candidate(central, path, priority, "arquivo de perfil"))
    candidates.extend(_sync_candidates(central))
    candidates.extend(_text_scan_candidates(central))
    candidates = [item for item in candidates if item[1]]
    if not candidates:
        return None, None

    grouped = {}
    for priority, profile, source in candidates:
        code = profile["profile_code"]
        grouped.setdefault(code, []).append((priority, profile, source))

    if len(grouped) == 1:
        code = next(iter(grouped))
    else:
        # Só desempata entre códigos diferentes se exatamente um reconhecer este PC.
        machine = central.default_device_name().strip().lower()
        matching = [code for code, rows in grouped.items() if any(str(r[1].get("device_name") or "").strip().lower() == machine for r in rows)]
        if len(matching) != 1:
            return None, None
        code = matching[0]

    best = max(grouped[code], key=lambda item: item[0])
    return best[1], best[2]


def install_profile_recovery(central):
    if getattr(central, "_profile_recovery_v0483_installed", False):
        return
    original_load = central.load_account_profile

    def robust_save(data):
        clean = dict(data or {})
        clean["profile_code"] = central.normalize_profile_code(clean.get("profile_code"))
        if not central.valid_profile_code(clean.get("profile_code")):
            raise ValueError("Código de perfil inválido.")
        path = Path(central.ACCOUNT_PROFILE_PATH)
        _atomic_json(path, clean)
        try:
            _atomic_json(path.with_name(PROFILE_BACKUP_NAME), clean)
        except Exception:
            pass
        return clean

    def robust_load():
        profile = original_load()
        if profile:
            try:
                # Cria/renova um backup íntegro sem mudar identidade.
                robust_save(profile)
            except Exception:
                pass
            return profile
        recovered, source = recover_profile(central)
        if not recovered:
            return None
        try:
            saved = robust_save(recovered)
            log = Path(central.DATA_DIR) / "logs" / RECOVERY_LOG_NAME
            log.parent.mkdir(parents=True, exist_ok=True)
            masked = saved["profile_code"][:8] + "-****"
            log.write_text(
                f"{datetime.now().isoformat(timespec='seconds')} perfil recuperado {masked} de {source}\n",
                encoding="utf-8",
            )
            return saved
        except Exception:
            return recovered

    central.load_account_profile = robust_load
    central.save_account_profile = robust_save
    central._profile_recovery_v0483_installed = True
