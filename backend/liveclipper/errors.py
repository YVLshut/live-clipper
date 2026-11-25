"""Erreurs avec un message clair en français pour l'interface."""
from __future__ import annotations

import subprocess


class UserError(Exception):
    """Erreur destinée à l'utilisateur : `message` est affiché tel quel."""

    def __init__(self, message: str, code: str = "erreur", status: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


class Cancelled(Exception):
    """Le job a été annulé par l'utilisateur."""


class VerificationRequired(Exception):
    """Un captcha ou une vérification de sécurité est apparu : intervention humaine requise."""

    def __init__(self, message: str, screenshot: str | None = None):
        super().__init__(message)
        self.message = message
        self.screenshot = screenshot


class PublishError(Exception):
    def __init__(self, message: str, screenshot: str | None = None, reconnect: bool = False):
        super().__init__(message)
        self.message = message
        self.screenshot = screenshot
        self.reconnect = reconnect


def _tail(text: str | bytes | None, n: int = 400) -> str:
    if not text:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return text.strip()[-n:]


def humanize(exc: BaseException) -> str:
    """Transforme n'importe quelle exception en message lisible en français."""
    if isinstance(exc, (UserError, PublishError, VerificationRequired)):
        return exc.message
    if isinstance(exc, Cancelled):
        return "Annulé."
    if isinstance(exc, FileNotFoundError):
        name = getattr(exc, "filename", None) or str(exc)
        if any(b in str(name) for b in ("ffmpeg", "ffprobe", "yt-dlp")):
            return f"Outil introuvable : {name}. Réinstalle Live Clipper."
        return f"Fichier introuvable : {name}"
    if isinstance(exc, subprocess.CalledProcessError):
        cmd = exc.cmd[0] if isinstance(exc.cmd, (list, tuple)) else str(exc.cmd)
        tail = _tail(exc.stderr) or _tail(exc.output)
        if "yt-dlp" in str(cmd):
            low = tail.lower()
            if "private" in low or "sign in" in low or "login" in low:
                return "Cette vidéo est privée ou réservée aux abonnés : impossible de la télécharger."
            if "unsupported url" in low:
                return "Lien non pris en charge. Utilise un lien Twitch, YouTube ou Kick."
            if "unable to download" in low or "http error" in low:
                return "Téléchargement impossible (réseau ou vidéo indisponible). " + tail[-200:]
            return "Échec du téléchargement : " + (tail or "erreur inconnue")
        if "ffmpeg" in str(cmd) or "ffprobe" in str(cmd):
            return "Échec du montage vidéo (ffmpeg) : " + (tail or "erreur inconnue")
        return f"La commande {cmd} a échoué : {tail}"
    if isinstance(exc, MemoryError):
        return "Mémoire insuffisante. Choisis un modèle Whisper plus petit dans les Paramètres."
    msg = str(exc) or exc.__class__.__name__
    low = msg.lower()
    if any(k in low for k in ("stratégie de contrôle d", "application control policy", "bloqué ce fichier",
                              "blocked this file")):
        return ("Windows a bloqué un composant de Live Clipper (Contrôle intelligent des applications) : "
                "les bibliothèques de l'application ne sont pas signées. Désactive-le dans Sécurité Windows > "
                "Contrôle des applications et du navigateur, puis redémarre Live Clipper. (" + msg[:160] + ")")
    if "CUDA" in msg or "cublas" in msg.lower() or "cudnn" in msg.lower():
        return ("Le GPU n'a pas pu être utilisé (" + msg[:200] + "). "
                "Passe l'appareil sur « CPU » dans les Paramètres ou installe les bibliothèques CUDA.")
    return f"Erreur inattendue : {msg[:500]}"
