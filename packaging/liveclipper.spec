# -*- mode: python ; coding: utf-8 -*-
# PyInstaller (mode onedir) : pyinstaller packaging/liveclipper.spec --noconfirm
# Produit dist/LiveClipper/LiveClipper.exe (+ dossier _internal).
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
IS_WIN = sys.platform.startswith("win")

datas = []
binaries = []
hiddenimports = []

# Interface React construite (npm run build)
dist = os.path.join(ROOT, "frontend", "dist")
if not os.path.isfile(os.path.join(dist, "index.html")):
    raise SystemExit("frontend/dist absent : lance d'abord `npm run build` dans frontend/.")
datas.append((dist, os.path.join("frontend", "dist")))

# ffmpeg / ffprobe / yt-dlp (téléchargés par build.ps1 dans packaging/bin)
bin_dir = os.path.join(SPECPATH, "bin")
if os.path.isdir(bin_dir):
    for f in os.listdir(bin_dir):
        binaries.append((os.path.join(bin_dir, f), "bin"))
elif IS_WIN:
    raise SystemExit("packaging/bin absent : build.ps1 télécharge ffmpeg, ffprobe et yt-dlp.")

for pkg in ["faster_whisper", "ctranslate2", "tokenizers", "onnxruntime", "av", "webview", "playwright",
            "uvicorn", "websockets", "sqlmodel", "anthropic", "huggingface_hub", "keyring", "certifi"]:
    try:
        d, b, h = collect_all(pkg)
    except Exception as e:  # paquet absent sur cette plateforme
        print(f"[spec] {pkg} ignoré : {e}")
        continue
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules("liveclipper")
hiddenimports += ["keyring.backends.Windows", "keyring.backends.fail", "multipart", "python_multipart"]
if IS_WIN:
    hiddenimports += ["webview.platforms.edgechromium", "webview.platforms.winforms", "clr", "clr_loader"]

a = Analysis(
    [os.path.join(ROOT, "desktop", "launcher.py")],
    pathex=[os.path.join(ROOT, "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "torch", "tensorflow"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LiveClipper",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # pas de console : logs dans %APPDATA%\LiveClipper\logs
    icon=os.path.join(SPECPATH, "icon.ico"),
    version=os.path.join(SPECPATH, "version_info.txt") if os.path.exists(os.path.join(SPECPATH, "version_info.txt")) else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LiveClipper")
