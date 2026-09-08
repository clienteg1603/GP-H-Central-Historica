# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
root = Path(SPECPATH)
a = Analysis(
    ["gph_updater.py"],
    pathex=[str(root)],
    binaries=[], datas=[], hiddenimports=[], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="GP-H_Updater",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=False,
    icon=str(root / "assets" / "logo" / "gph_icon.ico"),
)
