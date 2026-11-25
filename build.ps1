<#
.SYNOPSIS
  Construit LiveClipper-Setup.exe : interface React -> PyInstaller (onedir) -> installeur Inno Setup.

.EXAMPLE
  .\build.ps1                      # tout construire
  .\build.ps1 -Version 1.2.0       # numéro de version de l'installeur
  .\build.ps1 -SkipFrontend        # réutiliser frontend\dist
  .\build.ps1 -SkipInstaller       # s'arrêter après PyInstaller (dist\LiveClipper)
  .\build.ps1 -PrebuiltBootloader  # ne pas recompiler le lanceur PyInstaller (pas de compilateur C)

  Prérequis : Python 3.11 (py -3.11), Node.js 20+, Inno Setup 6 (ISCC.exe).
#>
param(
    [string]$Version = "",
    [switch]$SkipFrontend,
    [switch]$SkipInstaller,
    [switch]$SkipTools,
    [switch]$PrebuiltBootloader,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest beaucoup plus rapide
Set-Location -Path $PSScriptRoot
$Root = $PSScriptRoot

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Magenta }
function Fail($msg) { Write-Host "ERREUR : $msg" -ForegroundColor Red; exit 1 }

if (-not $Version) {
    $m = Select-String -Path "$Root\pyproject.toml" -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
    $Version = if ($m) { $m.Matches[0].Groups[1].Value } else { "1.0.0" }
}
Write-Host "Live Clipper $Version" -ForegroundColor Cyan

# ---------------------------------------------------------------- Python
Step "Environnement Python"
if (-not $Python) {
    if (Get-Command py -ErrorAction SilentlyContinue) { $Python = "py -3.11" }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { $Python = "python" }
    else { Fail "Python 3.11 introuvable (https://www.python.org/downloads/)." }
}
$venv = "$Root\.venv-build"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Invoke-Expression "$Python -m venv `"$venv`""
    if ($LASTEXITCODE -ne 0) { Fail "Création de l'environnement virtuel impossible." }
}
$py = "$venv\Scripts\python.exe"
& $py -c "import sys; assert sys.version_info[:2] == (3, 11), sys.version" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "Attention : Python 3.11 recommandé." -ForegroundColor Yellow }
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r "$Root\requirements-dev.txt" --quiet
if ($LASTEXITCODE -ne 0) { Fail "Installation des dépendances Python impossible." }

if (-not $PrebuiltBootloader) {
    # Le lanceur (bootloader) précompilé de PyInstaller est partagé par de nombreux logiciels, y compris
    # malveillants : les antivirus le signalent souvent par simple ressemblance (faux positifs « !ml »).
    # On le recompile à partir des sources (compilateur MSVC requis, présent sur le runner GitHub).
    Step "Recompilation du lanceur PyInstaller (réduit les faux positifs antivirus)"
    $pyiVersion = (& $py -c "import PyInstaller; print(PyInstaller.__version__)").Trim()
    $env:PYINSTALLER_COMPILE_BOOTLOADER = "1"
    & $py -m pip install --force-reinstall --no-deps --no-binary pyinstaller "pyinstaller==$pyiVersion"
    $build = $LASTEXITCODE
    Remove-Item Env:\PYINSTALLER_COMPILE_BOOTLOADER
    if ($build -ne 0) { Fail "Recompilation du lanceur PyInstaller impossible (Visual Studio Build Tools requis, ou -PrebuiltBootloader)." }
    Write-Host "Lanceur PyInstaller $pyiVersion recompilé." -ForegroundColor Green
}

# ---------------------------------------------------------------- Interface
if (-not $SkipFrontend) {
    Step "Interface React (npm ci + build)"
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "Node.js introuvable (https://nodejs.org)." }
    Push-Location "$Root\frontend"
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "npm ci a échoué." }
    npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "La construction de l'interface a échoué." }
    Pop-Location
}
if (-not (Test-Path "$Root\frontend\dist\index.html")) { Fail "frontend\dist absent." }

# ---------------------------------------------------------------- ffmpeg / ffprobe / yt-dlp
$bin = "$Root\packaging\bin"
if (-not $SkipTools) {
    Step "Outils embarqués (ffmpeg, ffprobe, yt-dlp)"
    New-Item -ItemType Directory -Force -Path $bin | Out-Null
    if (-not (Test-Path "$bin\ffmpeg.exe") -or -not (Test-Path "$bin\ffprobe.exe")) {
        # Build GPL de BtbN : libx264 + h264_nvenc
        $url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        $zip = "$env:TEMP\lc-ffmpeg.zip"; $tmp = "$env:TEMP\lc-ffmpeg"
        Write-Host "Téléchargement de ffmpeg…"
        Invoke-WebRequest -Uri $url -OutFile $zip
        if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
        Expand-Archive -Path $zip -DestinationPath $tmp
        $ff = Get-ChildItem -Path $tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1
        Copy-Item $ff.FullName "$bin\ffmpeg.exe" -Force
        Copy-Item (Join-Path $ff.DirectoryName "ffprobe.exe") "$bin\ffprobe.exe" -Force
        Remove-Item -Recurse -Force $tmp, $zip
    }
    if (-not (Test-Path "$bin\yt-dlp.exe")) {
        Write-Host "Téléchargement de yt-dlp…"
        Invoke-WebRequest -Uri "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -OutFile "$bin\yt-dlp.exe"
    }
    & "$bin\ffmpeg.exe" -hide_banner -version | Select-Object -First 1
    & "$bin\yt-dlp.exe" --version
}

# ---------------------------------------------------------------- PyInstaller
Step "PyInstaller (onedir)"
$parts = ($Version -replace '[^0-9.]', '').Split('.') + @('0', '0', '0', '0')
$v4 = ($parts[0..3] | ForEach-Object { if ($_ -eq '') { '0' } else { $_ } }) -join ', '
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($v4), prodvers=($v4)),
  kids=[StringFileInfo([StringTable('040C04B0', [
    StringStruct('CompanyName', 'Live Clipper'),
    StringStruct('FileDescription', 'Live Clipper'),
    StringStruct('FileVersion', '$Version'),
    StringStruct('ProductName', 'Live Clipper'),
    StringStruct('ProductVersion', '$Version')])]),
    VarFileInfo([VarStruct('Translation', [1036, 1200])])]
)
"@ | Set-Content -Encoding UTF8 "$Root\packaging\version_info.txt"

& $py -m PyInstaller "$Root\packaging\liveclipper.spec" --noconfirm --clean --distpath "$Root\dist" --workpath "$Root\build"
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller a échoué." }
if (-not (Test-Path "$Root\dist\LiveClipper\LiveClipper.exe")) { Fail "dist\LiveClipper\LiveClipper.exe absent." }

# Vérification rapide : le moteur démarre-t-il ?
Step "Test de démarrage (moteur seul)"
$env:LIVECLIPPER_HOME = "$env:TEMP\lc-smoke-test"
$p = Start-Process -FilePath "$Root\dist\LiveClipper\LiveClipper.exe" -ArgumentList "--headless", "--port", "47699" -PassThru
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:47699/api/health" -TimeoutSec 2
        if ($r.app -eq "LiveClipper") { $ok = $true; break }
    } catch { }
}
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Remove-Item Env:\LIVECLIPPER_HOME
if (-not $ok) { Fail "Le moteur ne répond pas (voir $env:TEMP\lc-smoke-test\logs)." }
Write-Host "Moteur OK" -ForegroundColor Green

if ($SkipInstaller) { Write-Host "`nTerminé : dist\LiveClipper\LiveClipper.exe" -ForegroundColor Green; exit 0 }

# ---------------------------------------------------------------- Inno Setup
Step "Installeur Inno Setup"
$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    foreach ($c in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
                     "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $c) { $iscc = $c; break }
    }
}
if (-not $iscc) { Fail "Inno Setup 6 introuvable (winget install JRSoftware.InnoSetup)." }
& $iscc "/DAppVersion=$Version" "$Root\packaging\installer.iss"
if ($LASTEXITCODE -ne 0) { Fail "La compilation de l'installeur a échoué." }

$out = "$Root\packaging\Output\LiveClipper-Setup.exe"
$size = [math]::Round((Get-Item $out).Length / 1MB, 1)
Write-Host "`nTerminé : $out ($size Mo)" -ForegroundColor Green
