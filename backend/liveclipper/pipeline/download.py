"""1. Source + téléchargement (repris de clipper.download)."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from ..errors import UserError
from .utils import (NO_WINDOW, CancelCheck, Progress, Throttle, check, never_cancel, noop_progress,
                    run, safe, tool)

PLATFORMS = {"twitch": "Twitch", "youtube": "YouTube", "kick": "Kick"}


def _platform(info: dict) -> str:
    key = (info.get("extractor_key") or info.get("extractor") or "").lower()
    for k, v in PLATFORMS.items():
        if k in key:
            return v
    return info.get("extractor_key") or "Autre"


def _date(info: dict) -> str | None:
    d = info.get("upload_date") or info.get("release_date")
    if d and re.fullmatch(r"\d{8}", d):
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    ts = info.get("timestamp") or info.get("release_timestamp")
    if ts:
        return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
    return d


def source_from_info(info: dict, url: str) -> dict:
    platform = _platform(info)
    vid = safe(f"{platform.lower()}_{info.get('id') or 'live'}")
    author_url = info.get("uploader_url") or info.get("channel_url")
    if not author_url and platform == "Twitch" and info.get("uploader_id"):
        author_url = f"https://www.twitch.tv/{info['uploader_id']}"
    if not author_url and platform == "Kick" and (info.get("channel") or info.get("uploader_id")):
        author_url = f"https://kick.com/{info.get('channel') or info.get('uploader_id')}"
    return {
        "id": vid,
        "url": info.get("webpage_url") or url,
        "author": info.get("uploader") or info.get("channel") or info.get("uploader_id") or "inconnu",
        "author_url": author_url,
        "title": info.get("title"),
        "platform": platform,
        "date": _date(info),
        "was_live": bool(info.get("is_live") or info.get("was_live")),
        "is_live": bool(info.get("is_live")),
    }


def probe(url: str) -> dict:
    """Métadonnées yt-dlp (-J)."""
    r = subprocess.run([tool("yt-dlp"), "-J", "--no-warnings", "--no-playlist", url],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", **NO_WINDOW)
    if r.returncode:
        raise subprocess.CalledProcessError(r.returncode, [tool("yt-dlp"), url], r.stdout, r.stderr)
    return json.loads(r.stdout)


def local_source(path: Path) -> dict:
    st = path.stat()
    return {
        "id": safe(f"local_{path.stem}"),
        "url": path.resolve().as_uri(),
        "author": "Fichier local",
        "author_url": None,
        "title": path.stem,
        "platform": "Fichier local",
        "date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"),
        "was_live": False,
        "is_live": False,
    }


_PCT = re.compile(r"LCPROG\s+([\d.]+)%")


def download(url: str, work: Path, section: str | None = None,
             progress: Progress = noop_progress, cancel: CancelCheck = never_cancel) -> tuple[Path, dict]:
    """Télécharge la vidéo, extrait l'audio 16 kHz mono. Renvoie (dossier de travail, source)."""
    url = url.strip()
    if not url:
        raise UserError("Lien vide.")
    p = progress if isinstance(progress, Throttle) else Throttle(progress)
    local = Path(url)
    if local.is_file():
        src = local_source(local)
    else:
        if not re.match(r"https?://", url):
            raise UserError(f"Ce n'est pas un lien valide : {url}")
        p(0.01, "Lecture des informations du live…", force=True)
        src = source_from_info(probe(url), url)
    check(cancel)
    if section:
        src["id"] = safe(f"{src['id']}_{section.replace(':', '').replace('-', '_')}")
    d = work / src["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "source.json").write_text(json.dumps(src, ensure_ascii=False, indent=2), encoding="utf-8")

    video = d / "video.mp4"
    if not video.exists():
        if local.is_file():
            cmd = [tool("ffmpeg"), "-y", "-v", "error"]
            if section:
                a, b = section.split("-", 1)
                cmd += ["-ss", a, "-to", b]
            run(cmd + ["-i", str(local), "-c", "copy", str(video)], cancel=cancel)
        else:
            tmp = d / "video.part.mp4"
            cmd = [tool("yt-dlp"), "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
                   "--merge-output-format", "mp4", "--no-playlist", "--newline",
                   "--progress-template", "download:LCPROG %(progress._percent_str)s",
                   "--ffmpeg-location", tool("ffmpeg"), "-o", str(tmp)]
            if section:
                cmd += ["--download-sections", f"*{section}"]
            if src.get("is_live"):
                cmd += ["--live-from-start"]

            def on_line(line: str) -> None:
                m = _PCT.search(line)
                if m:
                    p(min(0.95, float(m.group(1)) / 100), f"Téléchargement {float(m.group(1)):.0f} %")

            run(cmd + [url], cancel=cancel, on_line=on_line)
            if not tmp.exists():
                cands = sorted(d.glob("video.part*"))
                if not cands:
                    raise UserError("Le téléchargement n'a produit aucun fichier vidéo.")
                tmp = cands[0]
            tmp.rename(video)
    check(cancel)
    audio = d / "audio.wav"
    if not audio.exists():
        p(0.97, "Extraction de l'audio…", force=True)
        run([tool("ffmpeg"), "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
             "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact", str(audio)],
            cancel=cancel)
    p(1.0, "Téléchargement terminé", force=True)
    return d, src
