"""Secrets (clé Anthropic, secrets d'app, jetons OAuth) via le Gestionnaire d'identification Windows.

On passe par `keyring` (backend Windows Credential Manager sous Windows).
Si aucun trousseau n'est disponible (Linux sans Secret Service, tests), repli sur un fichier
local protégé dans le dossier de données, avec un avertissement dans les logs.
"""
from __future__ import annotations

import json
import logging
import os
import threading

from . import paths

log = logging.getLogger(__name__)
SERVICE = "LiveClipper"
_lock = threading.Lock()
_use_file: bool | None = None


def _file_store() -> dict:
    f = paths.home() / "secrets.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _file_save(data: dict) -> None:
    f = paths.home() / "secrets.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def _backend_ok() -> bool:
    global _use_file
    if _use_file is None:
        if os.environ.get("LIVECLIPPER_KEYRING") == "file":
            _use_file = True
        else:
            try:
                import keyring
                kr = keyring.get_keyring()
                # fail.Keyring et un Chainer vide ont une priorité nulle
                _use_file = float(getattr(kr, "priority", 0) or 0) <= 0
            except Exception:  # pragma: no cover
                _use_file = True
            if _use_file:
                log.warning("Aucun trousseau système disponible : secrets stockés dans %s",
                            paths.home() / "secrets.json")
    return not _use_file


def get(name: str) -> str | None:
    with _lock:
        if _backend_ok():
            import keyring
            try:
                return keyring.get_password(SERVICE, name)
            except Exception as e:
                log.error("Lecture du secret %s impossible : %s", name, e)
                return None
        return _file_store().get(name)


def set(name: str, value: str | None) -> None:  # noqa: A001
    with _lock:
        if _backend_ok():
            import keyring
            if value:
                keyring.set_password(SERVICE, name, value)
            else:
                try:
                    keyring.delete_password(SERVICE, name)
                except Exception:
                    pass
            return
        data = _file_store()
        if value:
            data[name] = value
        else:
            data.pop(name, None)
        _file_save(data)


def get_json(name: str) -> dict | None:
    raw = get(name)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def set_json(name: str, value: dict | None) -> None:
    set(name, json.dumps(value) if value else None)


def has(name: str) -> bool:
    return bool(get(name))


# Noms utilisés
ANTHROPIC_KEY = "anthropic_api_key"
META_APP_SECRET = "meta_app_secret"
TIKTOK_CLIENT_SECRET = "tiktok_client_secret"


def account_tokens_key(account_id: int) -> str:
    return f"account_tokens:{account_id}"
