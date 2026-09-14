from __future__ import annotations

import base64
import gzip
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED_GZIP_SHA256 = "0253f530852c31b3a614ee6c079ee5e375e424176ac75c6c952de438fde3e2bd"
EXPECTED_SOURCE_SHA256 = "b0071e1cafce199e57a08170c17d91d117611551f64fd271c1e412ca4a6a2caa"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Patch {label!r} esperava 1 ocorrência, encontrou {count}")
    return text.replace(old, new, 1)


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

text = source.decode("utf-8")

# v0.1.14: mantém a v0.1.13 como fonte-base verificada e aplica somente a
# extensão do atraso de bicho na cabeça (1º prêmio). O atraso geral de bicho
# continua considerando qualquer aparição do 1º ao 5º prêmio.
text = replace_once(
    text,
    'APP_VERSION = "0.1.13"',
    'APP_VERSION = "0.1.14"',
    "versão",
)
text = replace_once(
    text,
    '        empty = {"bicho": None, "centena": None, "dezena": None, "total_extracoes": 0}\n',
    '        empty = {"bicho": None, "bicho_cabeca": None, "centena": None, "dezena": None, "total_extracoes": 0}\n',
    "retorno vazio",
)
text = replace_once(
    text,
    '        last_seen = {"bicho": {}, "centena": {}, "dezena": {}}\n'
    '        last_row = {"bicho": {}, "centena": {}, "dezena": {}}\n',
    '        last_seen = {"bicho": {}, "bicho_cabeca": {}, "centena": {}, "dezena": {}}\n'
    '        last_row = {"bicho": {}, "bicho_cabeca": {}, "centena": {}, "dezena": {}}\n',
    "mapas de última ocorrência",
)
text = replace_once(
    text,
    '                if idx >= last_seen[field].get(value, -1):\n'
    '                    last_seen[field][value] = idx\n'
    '                    last_row[field][value] = dict(r)\n\n'
    '        # Bichos têm universo conhecido de 25 grupos. Em uma base histórica normal todos\n',
    '                if idx >= last_seen[field].get(value, -1):\n'
    '                    last_seen[field][value] = idx\n'
    '                    last_row[field][value] = dict(r)\n\n'
    '            # Cabeça: somente o 1º prêmio redefine a última ocorrência do bicho.\n'
    '            if int(r["premio"]) == 1:\n'
    '                head_group = int(r["grupo"])\n'
    '                if idx >= last_seen["bicho_cabeca"].get(head_group, -1):\n'
    '                    last_seen["bicho_cabeca"][head_group] = idx\n'
    '                    last_row["bicho_cabeca"][head_group] = dict(r)\n\n'
    '        # Bichos têm universo conhecido de 25 grupos. Em uma base histórica normal todos\n',
    "registro da cabeça",
)
text = replace_once(
    text,
    '        for field in ("bicho", "centena", "dezena"):\n',
    '        for field in ("bicho", "bicho_cabeca", "centena", "dezena"):\n',
    "cálculo dos líderes",
)
text = replace_once(
    text,
    '            if field == "bicho":\n'
    '                shown = BICHOS.get(int(raw), str(raw)).title()\n',
    '            if field in ("bicho", "bicho_cabeca"):\n'
    '                shown = BICHOS.get(int(raw), str(raw)).title()\n',
    "formatação do bicho",
)
text = replace_once(
    text,
    '                if field == "bicho":\n'
    '                    tied_values.append(BICHOS.get(int(v), str(v)).title())\n',
    '                if field in ("bicho", "bicho_cabeca"):\n'
    '                    tied_values.append(BICHOS.get(int(v), str(v)).title())\n',
    "formatação dos empates",
)
text = replace_once(
    text,
    '        for idx, (field, caption, search_type) in enumerate((\n'
    '            ("bicho", "Bicho", "Bicho"), ("centena", "Centena", "Centena"), ("dezena", "Dezena", "Dezena")\n'
    '        )):\n',
    '        for idx, (field, caption, search_type) in enumerate((\n'
    '            ("bicho", "Bicho 1º–5º", "Bicho"),\n'
    '            ("bicho_cabeca", "Cabeça 1º", "Bicho"),\n'
    '            ("centena", "Centena", "Centena"),\n'
    '            ("dezena", "Dezena", "Dezena"),\n'
    '        )):\n',
    "quatro cartões de atraso",
)
text = replace_once(
    text,
    '            box.pack(side="left", fill="x", expand=True, padx=(0, 4 if idx < 2 else 0))\n',
    '            box.pack(side="left", fill="x", expand=True, padx=(0, 4 if idx < 3 else 0))\n',
    "espaçamento dos cartões",
)

# Falha cedo se algum patch deixar o fonte sintaticamente inválido ou incompleto.
compile(text, "gph_consulta.py", "exec")
required = (
    'APP_VERSION = "0.1.14"',
    '"bicho_cabeca"',
    'if int(r["premio"]) == 1:',
    '("bicho_cabeca", "Cabeça 1º", "Bicho")',
)
for marker in required:
    if marker not in text:
        raise RuntimeError(f"Marcador obrigatório ausente após patch: {marker}")

patched = text.encode("utf-8")
patched_sha = hashlib.sha256(patched).hexdigest()
out = ROOT / "gph_consulta.py"
out.write_bytes(patched)
print(f"Fonte-base verificado: {source_sha}")
print(f"Fonte v0.1.14 restaurado: {out} ({len(patched)} bytes)")
print(f"SHA-256 v0.1.14: {patched_sha}")
