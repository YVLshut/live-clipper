"""Paramètres, informations système, ouverture de liens/dossiers."""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from .. import __version__, config, paths, secrets
from ..errors import UserError
from ..pipeline.utils import NO_WINDOW, tool

router = APIRouter(prefix="/api")

PUBLIC_KEYS = ["whisper_model", "device", "language", "min_len", "max_len", "max_clips", "layout", "font",
               "words_per_line", "encoder", "default_hashtags", "output_dir", "ai_model", "browser_channel",
               "meta_app_id", "tiktok_client_key", "setup_done"]
SECRET_FIELDS = {"anthropic_api_key": secrets.ANTHROPIC_KEY, "meta_app_secret": secrets.META_APP_SECRET,
                 "tiktok_client_secret": secrets.TIKTOK_CLIENT_SECRET}
LANGUAGES = [("fr", "Français"), ("en", "Anglais"), ("es", "Espagnol"), ("de", "Allemand"),
             ("it", "Italien"), ("pt", "Portugais"), ("auto", "Détection automatique")]


def settings_out() -> dict:
    cfg = config.get_all()
    out: dict[str, Any] = {k: cfg.get(k) for k in PUBLIC_KEYS}
    out["output_dir_effective"] = str(config.clips_dir(cfg))
    out["secrets"] = {k: secrets.has(v) for k, v in SECRET_FIELDS.items()}
    out["choices"] = {
        "whisper_model": config.WHISPER_MODELS, "ai_model": config.AI_MODELS,
        "encoder": config.ENCODERS, "layout": config.LAYOUTS, "device": ["auto", "cuda", "cpu"],
        "language": [{"value": v, "label": l} for v, l in LANGUAGES],
    }
    out["oauth_redirects"] = {
        "instagram": f"http://localhost:{cfg['oauth_port']}/oauth/instagram/callback",
        "tiktok": f"http://localhost:{cfg['oauth_port']}/oauth/tiktok/callback",
    }
    out["data_dir"] = str(paths.home())
    return out


@router.get("/settings")
def get_settings():
    return settings_out()


class SettingsPatch(BaseModel):
    model_config = {"extra": "allow"}


def _validate(k: str, v: Any) -> Any:
    if k in ("min_len", "max_len"):
        v = float(v)
        if not 3 <= v <= 180:
            raise UserError("Les durées doivent être comprises entre 3 et 180 secondes.")
    if k == "max_clips":
        v = int(v)
        if not 1 <= v <= 30:
            raise UserError("Nombre de clips : entre 1 et 30.")
    if k == "words_per_line":
        v = max(1, min(6, int(v)))
    if k == "whisper_model" and v not in config.WHISPER_MODELS:
        raise UserError("Modèle Whisper inconnu.")
    if k == "encoder" and v not in config.ENCODERS:
        raise UserError("Encodeur inconnu.")
    if k == "layout" and v not in config.LAYOUTS:
        raise UserError("Mise en page inconnue.")
    if k == "device" and v not in ("auto", "cuda", "cpu"):
        raise UserError("Appareil inconnu.")
    if k == "default_hashtags":
        tags = v.split() if isinstance(v, str) else list(v or [])
        v = [t if t.startswith("#") else f"#{t}" for t in (x.strip() for x in tags) if t]
    if k == "output_dir" and v:
        p = Path(v).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
            (p / ".lc_write_test").write_text("ok")
            (p / ".lc_write_test").unlink()
        except OSError:
            raise UserError(f"Impossible d'écrire dans le dossier {p}.")
        v = str(p)
    if k in ("meta_app_id", "tiktok_client_key", "font"):
        v = str(v or "").strip()
    return v


@router.put("/settings")
def put_settings(body: dict[str, Any]):
    values = {}
    for k, v in body.items():
        if k in SECRET_FIELDS:
            if v:  # vide = inchangé
                secrets.set(SECRET_FIELDS[k], str(v).strip())
            continue
        if k in PUBLIC_KEYS:
            values[k] = _validate(k, v)
    if "min_len" in values or "max_len" in values:
        cfg = {**config.get_all(), **values}
        if float(cfg["min_len"]) >= float(cfg["max_len"]):
            raise UserError("La durée min doit être inférieure à la durée max.")
    if values.get("device") == "cuda" or values.get("encoder") == "h264_nvenc":
        pass  # vérifié à l'exécution (repli automatique)
    config.update(values)
    if "device" in values or "whisper_model" in values:
        from ..pipeline import transcribe
        transcribe._cache.clear()
    return settings_out()


@router.delete("/settings/secret/{name}")
def delete_secret(name: str):
    if name not in SECRET_FIELDS:
        raise UserError("Secret inconnu.", status=404)
    secrets.set(SECRET_FIELDS[name], None)
    return settings_out()


@router.post("/settings/test-anthropic")
def test_anthropic():
    key = secrets.get(secrets.ANTHROPIC_KEY)
    if not key:
        raise UserError("Aucune clé API Anthropic enregistrée.")
    import anthropic
    try:
        anthropic.Anthropic(api_key=key, max_retries=1, timeout=20).models.retrieve(
            config.get("ai_model") or "claude-sonnet-5-5")
    except anthropic.AuthenticationError:
        raise UserError("Clé API invalide.")
    except anthropic.NotFoundError:
        raise UserError("Clé valide, mais le modèle choisi n'est pas accessible avec ce compte.")
    except anthropic.APIConnectionError:
        raise UserError("Impossible de joindre l'API Anthropic (connexion Internet ?).")
    except anthropic.APIStatusError as e:
        raise UserError(f"Erreur de l'API Anthropic ({e.status_code}).")
    return {"ok": True, "message": "Clé API valide ✔"}


def _version(cmd: list[str]) -> Optional[str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, **NO_WINDOW)
        return (r.stdout or r.stderr).splitlines()[0].strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


@router.get("/system")
def system_info():
    from ..pipeline.transcribe import cuda_available
    ok, why = cuda_available()
    ff = _version([tool("ffmpeg"), "-version"])
    return {
        "version": __version__,
        "gpu": {"available": ok, "detail": why},
        "ffmpeg": ff.split(" Copyright")[0] if ff else None,
        "yt_dlp": _version([tool("yt-dlp"), "--version"]),
        "data_dir": str(paths.home()),
        "logs_dir": str(paths.logs_dir()),
        "platform": sys.platform,
    }


class OpenBody(BaseModel):
    url: Optional[str] = None
    path: Optional[str] = None


def open_path(p: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(p))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])


@router.post("/open")
def open_external(body: OpenBody):
    """Ouvre un lien dans le navigateur du système, ou un dossier de l'application dans l'Explorateur."""
    if body.url:
        if not body.url.startswith(("https://", "http://")):
            raise UserError("Lien non autorisé.")
        webbrowser.open(body.url)
        return {"ok": True}
    if body.path:
        p = Path(body.path)
        allowed = [paths.home(), config.clips_dir()]
        if not any(p.resolve().is_relative_to(a.resolve()) for a in allowed):
            raise UserError("Dossier non autorisé.")
        if p.is_file():
            p = p.parent
        open_path(p)
        return {"ok": True}
    raise UserError("Rien à ouvrir.")


@router.post("/system/update-ytdlp")
def update_ytdlp():
    """Met à jour yt-dlp (les plateformes changent souvent, une version récente évite les échecs)."""
    exe = tool("yt-dlp")
    try:
        r = subprocess.run([exe, "-U"], capture_output=True, text=True, timeout=180, **NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise UserError(f"Mise à jour de yt-dlp impossible : {e}")
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0 or "error" in out.lower():
        raise UserError("Mise à jour de yt-dlp impossible : " + (out.splitlines()[-1] if out else "erreur inconnue"))
    return {"ok": True, "message": out.splitlines()[-1] if out else "yt-dlp est à jour.",
            "version": _version([exe, "--version"])}
