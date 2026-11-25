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
    # modules natifs optionnels non utilisés (moins de DLL à faire accepter par Windows)
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "torch", "tensorflow", "PIL", "uvloop",
              "watchfiles", "httptools", "yaml", "_yaml", "hf_xet", "greenlet"],
    noarchive=False,
)
# --- Smart App Control / stratégies de contrôle d'application Windows -----------------------------
# Windows peut bloquer le chargement de DLL natives non signées (.pyd). SQLAlchemy livre des
# extensions Cython OPTIONNELLES (*_cy.pyd) dont le code Python pur est fourni à côté (*_cy.py) :
# on retire les .pyd et on embarque les .py, qui sont chargés à la place (perte de vitesse négligeable).
import sqlalchemy as _sa

_sa_dir = os.path.dirname(_sa.__file__)


def _is_sa_cython(dest: str) -> bool:
    d = dest.replace("\\", "/")
    return d.startswith("sqlalchemy/") and "_cy." in d and d.endswith((".pyd", ".so"))


_dropped = [b[0] for b in a.binaries if _is_sa_cython(b[0])]
a.binaries = [b for b in a.binaries if not _is_sa_cython(b[0])]
for _root, _dirs, _files in os.walk(_sa_dir):
    for _f in _files:
        if _f.endswith("_cy.py"):
            _src = os.path.join(_root, _f)
            _rel = os.path.relpath(_src, os.path.dirname(_sa_dir))
            a.datas.append((_rel.replace("\\", "/"), _src, "DATA"))
print(f"[spec] extensions Cython SQLAlchemy remplacées par du Python pur : {len(_dropped)}")

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
