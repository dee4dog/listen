# PyInstaller spec for Listen. Build with:
#   .\.venv\Scripts\pyinstaller.exe scripts\listen.spec --noconfirm
# (see scripts\build_installer.ps1 for the full build + installer pipeline)
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
ROOT = Path(SPECPATH).resolve().parent

# These packages do their own dynamic/optional imports and ship non-Python
# data (model configs, compiled extensions) that PyInstaller's static
# analysis can't see, so pull each in wholesale rather than guessing hidden
# imports one at a time.
COLLECT_ALL = [
    "torch",
    "torchaudio",
    "speechbrain",
    "hyperpyyaml",
    "faster_whisper",
    "ctranslate2",
    "sklearn",
    "soundcard",
    "huggingface_hub",
    "tokenizers",
    "av",
]

datas = [(str(ROOT / "assets"), "assets")]
binaries = []
hiddenimports = []

for pkg in COLLECT_ALL:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Listen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "assets" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Listen",
)
