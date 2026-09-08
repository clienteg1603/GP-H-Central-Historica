# -*- coding: utf-8 -*-
r"""Cria um pacote de atualização online da GP-H Central Histórica.

Fluxo recomendado após compilar no Windows:
  py -3 CRIAR_PACOTE_ATUALIZACAO.py ^
      --version 0.35.1 ^
      --exe "dist\GP-H Central Historica.exe" ^
      --channel stable ^
      --notes "Resumo da versão" ^
      --out "release_server"

O script gera:
  release_server/update_manifest.json
  release_server/releases/GP-H_update_vX.Y.Z.zip

O manifesto usa URL relativa. Portanto, a pasta release_server pode ser enviada
para qualquer hospedagem HTTPS estática sem reescrever o pacote.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

APP_NAME = "GP-H Central Histórica"
MAIN_EXE = "GP-H Central Historica.exe"
UPDATER_EXE = "GP-H_Updater.exe"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def _read_manifest(path: Path) -> dict:
    if not path.is_file():
        return {"schema": 1, "app": APP_NAME, "server_name": "Servidor GP-H", "channels": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or int(data.get("schema") or 0) != 1:
        raise SystemExit("Manifesto existente incompatível.")
    if data.get("app") not in (None, "", APP_NAME):
        raise SystemExit("Manifesto existente pertence a outro aplicativo.")
    data.setdefault("channels", {})
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--exe", required=True)
    ap.add_argument("--channel", choices=["stable", "test"], default="stable")
    ap.add_argument("--notes", default="")
    ap.add_argument("--out", default="release_server")
    ap.add_argument("--server-name", default="Servidor GP-H")
    ap.add_argument("--url", default="", help="URL HTTPS absoluta opcional do pacote; se omitida usa releases/<arquivo>")
    ap.add_argument("--mirror", action="append", default=[], help="URL alternativa opcional do pacote")
    args = ap.parse_args()

    exe = Path(args.exe).resolve()
    if not exe.is_file():
        raise SystemExit(f"EXE não encontrado: {exe}")

    out = Path(args.out).resolve()
    releases = out / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    package_name = f"GP-H_update_v{args.version}.zip"
    package = releases / package_name

    package_meta = {
        "schema": 1,
        "app": APP_NAME,
        "version": args.version,
        "main_executable": MAIN_EXE,
        "updater_executable": UPDATER_EXE,
        "files": [MAIN_EXE],
    }
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("update_package.json", json.dumps(package_meta, ensure_ascii=False, indent=2))
        zf.write(exe, f"payload/{MAIN_EXE}")

    digest = sha256(package)
    manifest_path = out / "update_manifest.json"
    manifest = _read_manifest(manifest_path)
    manifest["schema"] = 1
    manifest["app"] = APP_NAME
    manifest["server_name"] = args.server_name
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest.setdefault("channels", {})[args.channel] = {
        "version": args.version,
        "url": args.url.strip() or f"releases/{package_name}",
        "sha256": digest,
        "notes": args.notes,
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mirrors": list(dict.fromkeys(v.strip() for v in args.mirror if v.strip())),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Cópia opcional do manifesto com nome humano para inspeção, sem ser usada pelo app.
    info = out / "LEIA-ME_PUBLICACAO.txt"
    info.write_text(
        "GP-H - PUBLICAÇÃO DE ATUALIZAÇÕES\n\n"
        "Envie TODO o conteúdo desta pasta para a raiz de uma hospedagem HTTPS estática.\n"
        "A Central precisa conhecer somente o endereço de update_manifest.json.\n\n"
        f"Canal atualizado: {args.channel}\nVersão: {args.version}\n"
        f"Pacote: releases/{package_name}\nSHA-256: {digest}\n",
        encoding="utf-8",
    )

    print(f"Pacote: {package}")
    print(f"Manifesto: {manifest_path}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
