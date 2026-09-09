from __future__ import annotations

import base64
import gzip
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED_GZIP_SHA256 = "0253f530852c31b3a614ee6c079ee5e375e424176ac75c6c952de438fde3e2bd"
EXPECTED_SOURCE_SHA256 = "b0071e1cafce199e57a08170c17d91d117611551f64fd271c1e412ca4a6a2caa"

parts = []
for idx in range(10):
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
