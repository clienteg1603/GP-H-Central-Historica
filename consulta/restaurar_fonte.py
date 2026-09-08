from __future__ import annotations

import base64
import gzip
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED_GZIP_SHA256 = "0749b490776074bd87e504734954e7f72b0875a141d1be4f29970def38e0847d"
EXPECTED_SOURCE_SHA256 = "b22b7f073cd4c9749b6abdaeeeed483486fbe75e78af3a3c0427ec9b4ca8b99d"

parts = []
for idx in range(9):
    path = ROOT / f"src_{idx}.b64"
    parts.append(path.read_text(encoding="ascii").strip())

raw = base64.b64decode("".join(parts), validate=True)
raw_sha = hashlib.sha256(raw).hexdigest()
if raw_sha != EXPECTED_GZIP_SHA256:
    raise RuntimeError(f"SHA-256 do pacote-fonte inválido: {raw_sha}")

source = gzip.decompress(raw)
source_sha = hashlib.sha256(source).hexdigest()
if source_sha != EXPECTED_SOURCE_SHA256:
    raise RuntimeError(f"SHA-256 do fonte restaurado inválido: {source_sha}")

out = ROOT / "gph_consulta.py"
out.write_bytes(source)
print(f"Fonte restaurado: {out} ({len(source)} bytes)")
print(f"SHA-256: {source_sha}")
