# -*- coding: utf-8 -*-
"""GP-H Updater v1.0

Atualizador externo da GP-H Central Histórica.
Somente biblioteca padrão do Python.

Ele é executado fora da Central para conseguir substituir o executável principal
após o fechamento do aplicativo. Os dados do usuário ficam fora da instalação e
nunca são copiados/removidos por este módulo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

UPDATER_VERSION = "1.0"
PACKAGE_META_NAME = "update_package.json"
DEFAULT_MAIN_EXE = "GP-H Central Historica.exe"
DEFAULT_UPDATER_EXE = "GP-H_Updater.exe"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def _safe_relpath(value: str) -> Path:
    rel = Path(str(value).replace("\\", "/"))
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Caminho inválido no pacote: {value}")
    return rel


def read_package_meta(package_path: Path) -> dict:
    with zipfile.ZipFile(package_path, "r") as zf:
        try:
            raw = zf.read(PACKAGE_META_NAME)
        except KeyError as exc:
            raise ValueError(f"Pacote sem {PACKAGE_META_NAME}") from exc
    meta = json.loads(raw.decode("utf-8"))
    if int(meta.get("schema") or 0) != 1:
        raise ValueError("Versão de pacote de atualização não suportada.")
    files = meta.get("files") or []
    if not isinstance(files, list) or not files:
        raise ValueError("Pacote sem lista de arquivos gerenciados.")
    for item in files:
        _safe_relpath(item)
    return meta


def _wait_for_pid(pid: int, timeout: int = 45):
    if not pid or pid <= 0:
        return
    deadline = time.time() + max(1, timeout)
    if os.name == "nt":
        try:
            import ctypes
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
            if handle:
                remain = max(0, int((deadline - time.time()) * 1000))
                ctypes.windll.kernel32.WaitForSingleObject(handle, remain)
                ctypes.windll.kernel32.CloseHandle(handle)
                return
        except Exception:
            pass
    while time.time() < deadline:
        try:
            os.kill(int(pid), 0)
        except (ProcessLookupError, OSError):
            return
        time.sleep(0.25)


def _zip_existing_files(install_dir: Path, files: list[str], backup_zip: Path):
    backup_zip.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    with zipfile.ZipFile(backup_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in files:
            rel = _safe_relpath(item)
            if rel.as_posix().lower() in seen:
                continue
            seen.add(rel.as_posix().lower())
            src = install_dir / rel
            if not src.exists() or not src.is_file():
                continue
            zf.write(src, rel.as_posix())
        backup_meta = {
            "schema": 1,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "install_dir": str(install_dir),
            "files": sorted(seen),
        }
        zf.writestr("backup_meta.json", json.dumps(backup_meta, ensure_ascii=False, indent=2))


def _extract_payload(package_path: Path, meta: dict, stage_dir: Path):
    stage_dir.mkdir(parents=True, exist_ok=True)
    wanted = {_safe_relpath(v).as_posix() for v in meta.get("files") or []}
    with zipfile.ZipFile(package_path, "r") as zf:
        names = set(zf.namelist())
        for rel in wanted:
            member = f"payload/{rel}"
            if member not in names:
                raise ValueError(f"Arquivo ausente no pacote: {rel}")
            target = stage_dir / _safe_relpath(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _copy_with_retries(src: Path, dst: Path, retries: int = 20):
    dst.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for _ in range(retries):
        try:
            tmp = dst.with_name(dst.name + ".gph-new")
            if tmp.exists():
                tmp.unlink()
            shutil.copy2(src, tmp)
            os.replace(tmp, dst)
            return
        except (PermissionError, OSError) as exc:
            last = exc
            time.sleep(0.35)
    raise last or OSError(f"Não foi possível substituir {dst}")


def install_package(
    package_path: Path,
    install_dir: Path,
    backup_dir: Path,
    expected_sha256: str = "",
    current_version: str = "",
) -> dict:
    """Instala um pacote já baixado. Não toca na pasta de dados do usuário."""
    package_path = Path(package_path).resolve()
    install_dir = Path(install_dir).resolve()
    backup_dir = Path(backup_dir).resolve()
    if not package_path.is_file():
        raise FileNotFoundError(package_path)
    if expected_sha256:
        actual = sha256_file(package_path)
        if actual != expected_sha256.strip().lower():
            raise ValueError("SHA-256 do pacote não confere.")
    meta = read_package_meta(package_path)
    new_version = str(meta.get("version") or "").strip()
    if not new_version:
        raise ValueError("Pacote sem versão.")

    managed = [str(v) for v in meta.get("files") or []]
    # O atualizador não substitui a si mesmo enquanto está rodando.
    updater_name = str(meta.get("updater_executable") or DEFAULT_UPDATER_EXE)
    managed_without_updater = [v for v in managed if Path(v).name.lower() != updater_name.lower()]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    previous = current_version or "anterior"
    backup_zip = backup_dir / f"GP-H_backup_programa_v{previous}_{stamp}.zip"
    _zip_existing_files(install_dir, managed_without_updater, backup_zip)

    with tempfile.TemporaryDirectory(prefix="gph_update_") as td:
        stage = Path(td) / "payload"
        _extract_payload(package_path, meta, stage)
        try:
            for item in managed_without_updater:
                rel = _safe_relpath(item)
                src = stage / rel
                dst = install_dir / rel
                _copy_with_retries(src, dst)
        except Exception:
            # Rollback automático daquilo que existia antes.
            restore_backup(backup_zip, install_dir)
            raise

    return {
        "ok": True,
        "version": new_version,
        "backup": str(backup_zip),
        "main_executable": str(meta.get("main_executable") or DEFAULT_MAIN_EXE),
        "files": managed_without_updater,
    }


def restore_backup(backup_zip: Path, install_dir: Path) -> dict:
    backup_zip = Path(backup_zip).resolve()
    install_dir = Path(install_dir).resolve()
    if not backup_zip.is_file():
        raise FileNotFoundError(backup_zip)
    restored = []
    with zipfile.ZipFile(backup_zip, "r") as zf:
        for name in zf.namelist():
            if name.endswith("/") or name == "backup_meta.json":
                continue
            rel = _safe_relpath(name)
            target = install_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src:
                with tempfile.NamedTemporaryFile(delete=False, dir=str(target.parent), prefix="gph_rb_", suffix=".tmp") as tmp:
                    shutil.copyfileobj(src, tmp)
                    tmp_path = Path(tmp.name)
            os.replace(tmp_path, target)
            restored.append(rel.as_posix())
    return {"ok": True, "restored": restored}


def _launch(path: Path):
    path = Path(path)
    if not path.exists():
        return False
    try:
        if os.name == "nt":
            subprocess.Popen([str(path)], cwd=str(path.parent), close_fds=True)
        else:
            subprocess.Popen([str(path)], cwd=str(path.parent), close_fds=True)
        return True
    except Exception:
        return False


def _write_log(log_path: Path | None, lines: list[str]):
    if not log_path:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="GP-H Updater")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    parser.add_argument("--package")
    parser.add_argument("--backup")
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--backup-dir")
    parser.add_argument("--expected-sha256", default="")
    parser.add_argument("--current-version", default="")
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--main-exe", default=DEFAULT_MAIN_EXE)
    parser.add_argument("--log")
    args = parser.parse_args(argv)

    log_path = Path(args.log) if args.log else None
    lines = [
        "GP-H UPDATER",
        f"Updater: {UPDATER_VERSION}",
        f"Início: {datetime.now().isoformat(timespec='seconds')}",
        f"Instalação: {args.install_dir}",
    ]
    try:
        _wait_for_pid(args.pid)
        if args.install:
            if not args.package or not args.backup_dir:
                raise ValueError("--package e --backup-dir são obrigatórios na instalação.")
            result = install_package(
                Path(args.package), Path(args.install_dir), Path(args.backup_dir),
                expected_sha256=args.expected_sha256,
                current_version=args.current_version,
            )
            main_name = result.get("main_executable") or args.main_exe
            lines.append(f"Atualizado para: {result['version']}")
            lines.append(f"Backup: {result['backup']}")
        else:
            if not args.backup:
                raise ValueError("--backup é obrigatório no rollback.")
            restore_backup(Path(args.backup), Path(args.install_dir))
            main_name = args.main_exe
            lines.append(f"Rollback aplicado: {args.backup}")
        lines.append("Status: OK")
        _write_log(log_path, lines)
        _launch(Path(args.install_dir) / main_name)
        return 0
    except Exception as exc:
        lines.append(f"Status: ERRO - {type(exc).__name__}: {exc}")
        _write_log(log_path, lines)
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk(); root.withdraw()
            messagebox.showerror(
                "GP-H Updater",
                f"A atualização não pôde ser concluída.\n\n{exc}\n\nLog:\n{log_path or 'não disponível'}",
                parent=root,
            )
            root.destroy()
        except Exception:
            pass
        # Se a instalação falhou e o rollback automático restaurou a versão anterior,
        # tenta reabrir a Central para o usuário não ficar sem aplicação.
        try:
            _launch(Path(args.install_dir) / args.main_exe)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
