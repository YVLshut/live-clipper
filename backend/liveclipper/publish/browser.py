"""Mode de secours « navigateur » : un profil Chromium persistant et séparé par compte.

- Connexion : une fenêtre s'ouvre, l'utilisateur se connecte lui-même (une seule fois).
- Publication : reprise de post_tiktok / post_instagram (clipper.py), avec un contrôle anti-captcha
  à chaque étape. Si une vérification apparaît : VerificationRequired -> pause + notification,
  la fenêtre reste ouverte pour que l'utilisateur la traite. Aucun contournement.

Toutes les fonctions de ce module doivent être appelées depuis le même thread (API sync de Playwright).
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Callable

from .. import config, paths
from ..errors import PublishError, VerificationRequired
from . import guard

log = logging.getLogger("liveclipper.browser")

LOGIN_URLS = {"instagram": "https://www.instagram.com/accounts/login/",
              "tiktok": "https://www.tiktok.com/login"}
SESSION_COOKIES = {"instagram": ("sessionid", "instagram.com"), "tiktok": ("sessionid", "tiktok.com")}


def _browsers_path() -> str:
    """Navigateurs téléchargés par Live Clipper (repli si Edge / Chrome sont introuvables)."""
    d = paths.home() / "ms-playwright"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def install_chromium() -> None:
    """Télécharge Chromium pour Playwright (environ 150 Mo) dans %APPDATA%\\LiveClipper\\ms-playwright."""
    import os
    import subprocess
    from playwright._impl._driver import compute_driver_executable
    from ..events import bus
    from ..pipeline.utils import NO_WINDOW
    bus.notify("Téléchargement d'un navigateur Chromium pour le mode navigateur (environ 150 Mo)…", "info")
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": _browsers_path()}
    r = subprocess.run([*compute_driver_executable(), "install", "chromium"], env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=1800, **NO_WINDOW)
    if r.returncode:
        raise PublishError("Téléchargement du navigateur Chromium impossible : "
                           + ((r.stderr or r.stdout or "").strip().splitlines() or ["erreur inconnue"])[-1])


class Browsers:
    """Contextes persistants ouverts, par compte (vivent dans le thread du worker de publication)."""

    def __init__(self) -> None:
        self._pw = None
        self.contexts: dict[int, object] = {}

    def _playwright(self):
        if self._pw is None:
            import os
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _browsers_path())
            try:
                from playwright.sync_api import sync_playwright
                self._pw = sync_playwright().start()
            except Exception as e:
                log.exception("Démarrage de Playwright")
                raise PublishError("Le pilote du navigateur (Playwright) n'a pas pu démarrer : "
                                   f"{str(e).splitlines()[0][:300] if str(e) else type(e).__name__}") from e
        return self._pw

    def open(self, account_id: int, headless: bool = False, profile_dir: str | None = None):
        ctx = self.contexts.get(account_id)
        if ctx is not None:
            try:
                _ = ctx.pages  # contexte toujours vivant ?
                return ctx
            except Exception:
                self.contexts.pop(account_id, None)
        kw = dict(user_data_dir=profile_dir or str(paths.profiles_dir() / str(account_id)), headless=headless,
                  viewport={"width": 1280, "height": 860}, locale="fr-FR")
        pw = self._playwright()
        wanted = config.get("browser_channel") or "msedge"
        # ordre d'essai : navigateur choisi, puis Edge, Chrome, et enfin Chromium (téléchargé si besoin)
        channels = list(dict.fromkeys([wanted, "msedge", "chrome", "chromium"]))
        errors = []
        ctx = None
        for ch in channels:
            try:
                ctx = pw.chromium.launch_persistent_context(channel=None if ch == "chromium" else ch, **kw)
                break
            except Exception as e:
                msg = str(e).splitlines()[0] if str(e) else type(e).__name__
                log.warning("Navigateur %s indisponible : %s", ch, msg)
                errors.append(f"{ch} : {msg[:150]}")
                if ch == "chromium" and ("Executable doesn't exist" in str(e) or "playwright install" in str(e)):
                    try:
                        install_chromium()
                        ctx = pw.chromium.launch_persistent_context(**kw)
                        break
                    except Exception as e2:
                        errors.append(f"chromium (téléchargé) : {str(e2).splitlines()[0][:150]}")
        if ctx is None:
            raise PublishError("Impossible d'ouvrir un navigateur (Edge, Chrome ou Chromium). " + " | ".join(errors))
        self.contexts[account_id] = ctx
        return ctx

    def close(self, account_id: int) -> None:
        ctx = self.contexts.pop(account_id, None)
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass

    def shutdown(self) -> None:
        for aid in list(self.contexts):
            self.close(aid)
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None


def is_logged_in(ctx, platform: str) -> bool:
    name, domain = SESSION_COOKIES[platform]
    try:
        return any(c["name"] == name and domain in c["domain"] and c.get("value") for c in ctx.cookies())
    except Exception:
        return False


def _page(ctx):
    pages = [p for p in ctx.pages if not p.is_closed()]
    return pages[0] if pages else ctx.new_page()


def login(browsers: Browsers, account_id: int, platform: str, done: Callable[[], bool],
          timeout: float = 900, on_open: Callable[[], None] = lambda: None) -> bool:
    """Ouvre la page de connexion et attend que l'utilisateur ait fini (bouton « J'ai terminé »,
    fenêtre fermée, ou session détectée puis 5 s de calme). Renvoie True si connecté."""
    ctx = browsers.open(account_id, headless=False)
    page = _page(ctx)
    try:
        page.bring_to_front()
    except Exception:
        pass
    on_open()
    try:
        page.goto(LOGIN_URLS[platform], wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        log.warning("Chargement de la page de connexion : %s", e)
    t0, seen_at = time.time(), None
    while time.time() - t0 < timeout and not done():
        try:
            if not [p for p in ctx.pages if not p.is_closed()]:
                break  # fenêtre fermée par l'utilisateur
            if is_logged_in(ctx, platform):
                seen_at = seen_at or time.time()
                if time.time() - seen_at > 8:
                    break
            ctx.pages[0].wait_for_timeout(1000)
        except Exception:
            break
    ok = is_logged_in(ctx, platform)
    browsers.close(account_id)
    return ok


def check_login(browsers: Browsers, account_id: int, platform: str) -> bool:
    ctx = browsers.open(account_id, headless=True)
    try:
        return is_logged_in(ctx, platform)
    finally:
        browsers.close(account_id)


# ------------------------------------------------------------------ publication (reprise de clipper.py)
def _guard(page, account_id: int, where: str) -> None:
    reason = guard.detect(page)
    if reason:
        shot = _screenshot(page, account_id, "verification")
        raise VerificationRequired(f"Vérification de sécurité requise ({where}) : {reason}. "
                                   "Traite-la dans la fenêtre ouverte, puis clique sur « Reprendre ».", shot)


def _screenshot(page, account_id: int, tag: str) -> str | None:
    f = paths.screenshots_dir() / f"{tag}_{account_id}_{int(time.time())}.png"
    try:
        page.screenshot(path=str(f), full_page=False)
        return str(f)
    except Exception:
        return None


def click_text(page, pattern, timeout=4000) -> bool:
    try:
        page.get_by_role("button", name=re.compile(pattern, re.I)).first.click(timeout=timeout)
        return True
    except Exception:
        return False


def post_tiktok(page, video: str, caption: str, account_id: int) -> str | None:
    from playwright.sync_api import expect
    page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    _guard(page, account_id, "ouverture de TikTok Studio")
    if "login" in page.url:
        raise PublishError("Session TikTok expirée : reconnecte le compte.", reconnect=True)
    page.locator('input[type="file"]').first.set_input_files(video, timeout=60000)
    editor = page.locator('div[contenteditable="true"]').first
    editor.wait_for(timeout=120000)
    _guard(page, account_id, "après l'envoi du fichier")
    editor.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    page.keyboard.insert_text(caption)
    page.keyboard.press("Escape")  # ferme le menu de suggestions de hashtags
    btn = page.locator('button[data-e2e="post_video_button"]')
    expect(btn).to_be_enabled(timeout=600000)  # attend la fin de l'upload
    _guard(page, account_id, "avant publication")
    btn.click()
    page.wait_for_timeout(10000)
    _guard(page, account_id, "après publication")
    return None


def post_instagram(page, video: str, caption: str, account_id: int) -> str | None:
    page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    _guard(page, account_id, "ouverture d'Instagram")
    if "/accounts/login" in page.url:
        raise PublishError("Session Instagram expirée : reconnecte le compte.", reconnect=True)
    page.locator('svg[aria-label="Nouvelle publication"], svg[aria-label="New post"], '
                 'svg[aria-label="Créer"], svg[aria-label="Create"]').first.click(timeout=20000)
    try:
        page.get_by_text(re.compile(r"^(Publication|Post)$")).first.click(timeout=3000)
    except Exception:
        pass
    page.locator('input[type="file"]').first.set_input_files(video, timeout=30000)
    click_text(page, r"^OK$", 6000)  # « Les vidéos sont désormais partagées en reels »
    try:  # recadrage -> format original (garde le 9:16)
        page.locator('svg[aria-label="Sélectionner le recadrage"], svg[aria-label="Select crop"]').first.click(timeout=6000)
        page.get_by_text(re.compile(r"^(Original|D’origine|D'origine)$")).first.click(timeout=4000)
    except Exception:
        pass
    for _ in range(2):
        if not click_text(page, r"^(Suivant|Next)$", 20000):
            _guard(page, account_id, "étape suivante")
            raise PublishError("Bouton « Suivant » introuvable : l'interface d'Instagram a peut-être changé.")
        page.wait_for_timeout(1500)
    box = page.locator('div[aria-label^="Écrivez une légende"], div[aria-label^="Write a caption"]').first
    box.click(timeout=20000)
    page.keyboard.insert_text(caption)
    _guard(page, account_id, "avant publication")
    if not click_text(page, r"^(Partager|Share)$", 20000):
        raise PublishError("Bouton « Partager » introuvable : l'interface d'Instagram a peut-être changé.")
    page.get_by_text(re.compile(r"(a été partagé|has been shared)", re.I)).first.wait_for(timeout=600000)
    return None


def publish(browsers: Browsers, account_id: int, platform: str, video: Path, caption: str,
            username: str | None = None) -> str | None:
    """Publie via le profil du compte. Lève VerificationRequired (fenêtre laissée ouverte) ou PublishError."""
    ctx = browsers.open(account_id, headless=False)
    if not is_logged_in(ctx, platform):
        browsers.close(account_id)
        raise PublishError("Le compte n'est pas connecté dans son navigateur : clique sur « Se connecter ».",
                           reconnect=True)
    page = ctx.new_page()
    try:
        fn = post_tiktok if platform == "tiktok" else post_instagram
        url = fn(page, str(Path(video).resolve()), caption, account_id)
    except VerificationRequired:
        raise  # on garde la fenêtre ouverte pour l'utilisateur
    except PublishError as e:
        e.screenshot = e.screenshot or _screenshot(page, account_id, "erreur")
        browsers.close(account_id)
        raise
    except Exception as e:
        shot = _screenshot(page, account_id, "erreur")
        browsers.close(account_id)
        raise PublishError(f"Échec de la publication dans le navigateur : {str(e).splitlines()[0][:300]}",
                           screenshot=shot) from e
    browsers.close(account_id)
    if url:
        return url
    if username:
        return (f"https://www.tiktok.com/@{username}" if platform == "tiktok"
                else f"https://www.instagram.com/{username}/")
    return None


def selftest(profile_dir: str) -> str:
    """Vérifie que le navigateur du mode secours s'ouvre (utilisé par le build Windows)."""
    b = Browsers()
    try:
        ctx = b.open(0, headless=True, profile_dir=profile_dir)
        page = _page(ctx)
        page.set_content("<title>ok</title>")
        title = page.title()
        name = ctx.browser.browser_type.name if getattr(ctx, "browser", None) else "chromium"
        return f"OK ({name}, page « {title} »)"
    finally:
        b.shutdown()
