# Construire LiveClipper-Setup.exe

Le résultat : `packaging\Output\LiveClipper-Setup.exe`, un installeur Windows (Inno Setup) qui pose
l'application dans `Program Files\Live Clipper`, crée les raccourcis Bureau et menu Démarrer, et un désinstalleur.
Les données utilisateur restent dans `%APPDATA%\LiveClipper`.

## Méthode 1 — GitHub Actions (rien à installer)

Le workflow `.github/workflows/build.yml` tourne sur `windows-latest` à chaque push sur `main`, à chaque pull request
et à la main (onglet **Actions → Build Windows → Run workflow**).

1. Ouvre l'onglet **Actions** du dépôt, puis le dernier run « Build Windows ».
2. En bas de la page, dans **Artifacts**, télécharge `LiveClipper-Setup-<version>` (un zip qui contient l'exe).

Pour publier une version (Release GitHub avec l'exe en pièce jointe) :

```bash
git tag v1.0.0
```

```bash
git push origin v1.0.0
```

Le numéro du tag (sans le `v`) devient la version de l'installeur.

## Méthode 2 — sur ton PC Windows avec `build.ps1`

### Prérequis (une seule fois)

| Outil | Installation |
|---|---|
| Python **3.11** | `winget install Python.Python.3.11` |
| Node.js 20+ | `winget install OpenJS.NodeJS.LTS` |
| Inno Setup 6 | `winget install JRSoftware.InnoSetup` |
| Git | `winget install Git.Git` |

### Construire

Dans PowerShell, à la racine du dépôt :

```powershell
.\build.ps1
```

Si PowerShell refuse d'exécuter le script :

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Le script enchaîne :

1. **Python** : crée `.venv-build` et installe `requirements-dev.txt` (FastAPI, faster-whisper, PyInstaller…).
2. **Interface** : `npm ci` puis `npm run build` dans `frontend\` → `frontend\dist`.
3. **Outils embarqués** : télécharge dans `packaging\bin` le build GPL de ffmpeg de BtbN (avec libx264 et h264_nvenc),
   ffprobe et `yt-dlp.exe` (une seule fois, ensuite ils sont réutilisés).
4. **PyInstaller** (mode onedir) avec `packaging\liveclipper.spec` → `dist\LiveClipper\LiveClipper.exe`.
5. **Test de démarrage** : lance `LiveClipper.exe --headless` et vérifie que le moteur répond.
6. **Inno Setup** : compile `packaging\installer.iss` → `packaging\Output\LiveClipper-Setup.exe`.

Options :

| Option | Effet |
|---|---|
| `-Version 1.2.0` | numéro de version (par défaut celui de `pyproject.toml`) |
| `-SkipFrontend` | réutilise `frontend\dist` |
| `-SkipTools` | ne retélécharge pas ffmpeg / yt-dlp |
| `-SkipInstaller` | s'arrête après PyInstaller (pratique pour tester `dist\LiveClipper\LiveClipper.exe`) |
| `-Python "C:\chemin\python.exe"` | interpréteur à utiliser |

Pour forcer la mise à jour de ffmpeg ou de yt-dlp, supprime `packaging\bin` avant de relancer le script.

## Ce qui n'est PAS dans l'installeur (et pourquoi)

- **Modèles Whisper** (75 Mo à 3 Go) : téléchargés au premier lancement par l'assistant, avec une barre de progression,
  dans `%APPDATA%\LiveClipper\models`.
- **Bibliothèques CUDA** (cuBLAS + cuDNN, environ 1 Go) : proposées par l'assistant si une carte NVIDIA est détectée,
  installées dans `%APPDATA%\LiveClipper\cuda`. Sans elles, l'app tourne sur le CPU (int8).
- **Navigateur du mode secours** : Microsoft Edge (installé sur tous les Windows) est utilisé via Playwright.
- **WebView2** (moteur d'affichage de la fenêtre) : présent sur Windows 10/11 à jour. L'installeur vérifie et propose
  le téléchargement s'il manque.

## Développement (Linux, macOS ou Windows)

```bash
python3.11 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements-dev.txt
```

```bash
cd frontend && npm ci && npm run build && cd ..
```

Moteur seul, interface sur http://127.0.0.1:47615 :

```bash
.venv/bin/python desktop/launcher.py --headless
```

Interface avec rechargement à chaud (dans un 2e terminal, ouvre ensuite http://localhost:5173) :

```bash
cd frontend && npm run dev
```

Tests (pipeline réel sur une vidéo générée par ffmpeg, Whisper `tiny` sur CPU, API, publication simulée) :

```bash
HF_HUB_DISABLE_XET=1 .venv/bin/python -m pytest -q
```

## Structure

```
backend/liveclipper/        moteur Python (FastAPI)
  pipeline/                 code repris de clipper.py : download, transcribe, peaks, highlights, render, caption
  jobs/                     file de jobs SQLite (clipping, remontage)
  publish/                  comptes, OAuth, Instagram Graph API, TikTok Content Posting API, mode navigateur,
                            garde-fou captcha, planificateur, worker de publication
  api/                      routes REST + WebSocket
desktop/launcher.py         point d'entrée : moteur + fenêtre pywebview
frontend/                   interface React + Vite + Tailwind
packaging/                  liveclipper.spec (PyInstaller), installer.iss (Inno Setup), icône
tests/                      pytest
clipper.py                  CLI (même base que l'application)
```

## Signature de code (Smart App Control)

Sous Windows 11, le « Contrôle intelligent des applications » bloque les DLL non signées dont il ne connaît pas
la réputation. Le build limite déjà le nombre de DLL natives (extensions Cython de SQLAlchemy remplacées par leur
version Python pur, modules natifs optionnels exclus), mais les bibliothèques indispensables (Python, numpy,
pydantic, ctranslate2/Whisper, PyAV, onnxruntime) restent natives et non signées.

La solution durable est de **signer** `LiveClipper.exe`, toutes les `.dll`/`.pyd` de `dist\LiveClipper` et
l'installeur avec un certificat de signature de code reconnu (par exemple Azure Trusted Signing, environ 10 $/mois,
ou un certificat OV/EV d'une autorité de certification), avec `signtool sign /fd SHA256 /tr <horodatage> /td SHA256`
entre l'étape PyInstaller et l'étape Inno Setup de `build.ps1`.
