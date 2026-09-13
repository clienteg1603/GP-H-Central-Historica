from pathlib import Path

path = Path("tmp_patch_v04820.py")
text = path.read_text(encoding="utf-8")
old = '''    "                box.pack(side=\\"left\\", fill=\\"x\\", expand=True, padx=(0, 4 if idx < 2 else 0))\\n",
    "                box.pack(\\n"
    "                    side=\\"left\\", fill=\\"x\\", expand=True,\\n"
    "                    padx=(0, 4 if idx < len(delay_fields) - 1 else 0),\\n"
    "                )\\n",
'''
new = '''    "            box.pack(side=\\"left\\", fill=\\"x\\", expand=True, padx=(0, 4 if idx < 2 else 0))\\n",
    "            box.pack(\\n"
    "                side=\\"left\\", fill=\\"x\\", expand=True,\\n"
    "                padx=(0, 4 if idx < len(delay_fields) - 1 else 0),\\n"
    "            )\\n",
'''
if old not in text:
    raise SystemExit("bloco de espaçamento antigo não encontrado no patch")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Patch temporário corrigido.")
