"""Worker de publication : un thread unique qui publie (API ou navigateur) et gère les connexions navigateur."""
from __future__ import annotations

import logging
import queue
import threading
import traceback
from pathlib import Path

from .. import config, db
from ..errors import PublishError, UserError, VerificationRequired, humanize
from ..events import bus
from ..models import Clip, Publication, Source, now
from ..pipeline.caption import build_caption
from . import accounts, browser, instagram_api, tiktok_api

log = logging.getLogger("liveclipper.publish")


def update_pub(pub_id: int, **fields) -> Publication:
    with db.session() as s:
        p = s.get(Publication, pub_id)
        for k, v in fields.items():
            setattr(p, k, v)
        s.add(p)
        s.commit()
        s.refresh(p)
    bus.publish("publication.updated", p)
    return p


class PublishWorker:
    def __init__(self) -> None:
        self.tasks: queue.Queue = queue.Queue()
        self.browsers = browser.Browsers()
        self.login_done: set[int] = set()
        self.queued: set[int] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        # surchargeables (tests)
        self.api_publishers = {"instagram": self._api_instagram, "tiktok": self._api_tiktok}
        self.browser_publish = browser.publish

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="publisher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.tasks.put(("stop", None))
        if self._thread:
            self._thread.join(5)

    # ------------------------------------------------------------ API publique (thread-safe)
    def enqueue_publication(self, pub_id: int) -> None:
        with self._lock:
            if pub_id in self.queued:
                return
            self.queued.add(pub_id)
        self.tasks.put(("publish", pub_id))

    def enqueue_login(self, account_id: int) -> None:
        self.login_done.discard(account_id)
        self.tasks.put(("login", account_id))

    def finish_login(self, account_id: int) -> None:
        self.login_done.add(account_id)

    def enqueue_check(self, account_id: int) -> None:
        self.tasks.put(("check", account_id))

    def enqueue_close(self, account_id: int) -> None:
        self.tasks.put(("close", account_id))

    # ------------------------------------------------------------ boucle
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                kind, arg = self.tasks.get(timeout=1)
            except queue.Empty:
                continue
            if kind == "stop":
                break
            try:
                {"publish": self.publish, "login": self._login, "check": self._check,
                 "close": self.browsers.close}[kind](arg)
            except Exception:
                log.error("Tâche %s(%s) : %s", kind, arg, traceback.format_exc())
        self.browsers.shutdown()

    def _login(self, account_id: int) -> None:
        acc = accounts.get_account(account_id)
        accounts.update_account(account_id, status_message="Ouverture du navigateur…")
        try:
            ok = browser.login(
                self.browsers, account_id, acc.platform, lambda: account_id in self.login_done,
                on_open=lambda: accounts.update_account(
                    account_id, status_message="Fenêtre de connexion ouverte : connecte-toi…"))
        except Exception as e:  # toute erreur doit être visible dans l'interface
            log.error("Connexion navigateur du compte %s : %s", account_id, traceback.format_exc())
            msg = e.message if isinstance(e, PublishError) else humanize(e)
            accounts.update_account(account_id, status="disconnected",
                                    status_message=f"Le navigateur ne s'est pas ouvert : {msg}")
            bus.notify(f"Le navigateur ne s'est pas ouvert : {msg}", "error", account_id=account_id)
            self.browsers.close(account_id)
            return
        if ok:
            accounts.update_account(account_id, status="connected", status_message=None)
            bus.notify(f"Compte « {acc.name} » connecté.", "success")
        else:
            accounts.update_account(account_id, status="disconnected",
                                    status_message="Connexion non détectée : réessaie.")
            bus.notify(f"Connexion du compte « {acc.name} » non détectée.", "warning")

    def _check(self, account_id: int) -> None:
        acc = accounts.get_account(account_id)
        try:
            if acc.mode == "api":
                token = accounts.valid_token(acc)
                if acc.platform == "tiktok":
                    tiktok_api.user_info(token)
                else:
                    instagram_api.list_accounts(token)
                ok = True
            else:
                ok = browser.check_login(self.browsers, account_id, acc.platform)
        except PublishError as e:
            accounts.mark_reconnect(account_id, e.message) if e.reconnect else bus.notify(e.message, "error")
            return
        except Exception as e:
            bus.notify(f"Vérification impossible : {humanize(e)}", "error")
            return
        if ok:
            accounts.update_account(account_id, status="connected", status_message=None)
            bus.notify(f"« {acc.name} » est bien connecté.", "success")
        else:
            accounts.mark_reconnect(account_id, "Session expirée.")

    # ------------------------------------------------------------ publication
    def _api_instagram(self, acc, video: Path, caption: str, progress) -> str:
        if not acc.external_id:
            raise PublishError("Compte Instagram non lié : reconnecte-le.", reconnect=True)
        return instagram_api.publish_reel(acc.external_id, accounts.valid_token(acc), video, caption, progress)

    def _api_tiktok(self, acc, video: Path, caption: str, progress) -> str:
        return tiktok_api.publish_video(accounts.valid_token(acc), video, caption, acc.privacy_level, progress)

    def publish(self, pub_id: int) -> None:
        try:
            self._publish(pub_id)
        finally:
            with self._lock:
                self.queued.discard(pub_id)

    def _publish(self, pub_id: int) -> None:
        with db.session() as s:
            pub = s.get(Publication, pub_id)
            if pub is None or pub.status not in ("scheduled", "paused"):
                return
            clip = s.get(Clip, pub.clip_id)
            source = s.get(Source, clip.source_id) if clip else None
        try:
            acc = accounts.get_account(pub.account_id)
        except UserError:
            update_pub(pub_id, status="failed", error="Compte supprimé.")
            return
        if clip is None or not Path(clip.file).exists():
            update_pub(pub_id, status="failed", error="Fichier du clip introuvable.")
            return
        cfg = config.get_all()
        caption = pub.caption or build_caption(clip.model_dump(), (source.model_dump() if source else {}),
                                               cfg.get("default_hashtags") or [])
        update_pub(pub_id, status="running", error=None, attempts=pub.attempts + 1, caption=caption)
        log.info("Publication %s : clip %s -> %s (%s, %s)", pub_id, clip.id, acc.name, acc.platform, acc.mode)
        progress = lambda m: bus.publish("publication.progress", {"id": pub_id, "message": m})  # noqa: E731
        try:
            if acc.mode == "api":
                url = self.api_publishers[acc.platform](acc, Path(clip.file), caption, progress)
            else:
                url = self.browser_publish(self.browsers, acc.id, acc.platform, Path(clip.file), caption,
                                           acc.username)
        except VerificationRequired as e:
            update_pub(pub_id, status="paused", error=e.message, screenshot=e.screenshot)
            bus.notify(f"⏸ Publication en pause sur « {acc.name} » : une vérification de sécurité est demandée. "
                       "Traite-la dans la fenêtre ouverte puis clique sur « Reprendre ».", "warning",
                       publication_id=pub_id)
            return
        except PublishError as e:
            update_pub(pub_id, status="failed", error=e.message, screenshot=e.screenshot)
            if e.reconnect:
                accounts.mark_reconnect(acc.id, e.message)
            bus.notify(f"Échec de la publication sur « {acc.name} » : {e.message}", "error", publication_id=pub_id)
            return
        except Exception as e:
            log.error("Publication %s : %s", pub_id, traceback.format_exc())
            update_pub(pub_id, status="failed", error=humanize(e))
            bus.notify(f"Échec de la publication sur « {acc.name} » : {humanize(e)}", "error")
            return
        update_pub(pub_id, status="published", published_at=now(), post_url=url, error=None)
        bus.notify(f"✔ Clip publié sur « {acc.name} »", "success", publication_id=pub_id, url=url)
