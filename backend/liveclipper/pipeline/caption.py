"""Légende finale avec crédit de la source (repris de clipper.build_caption)."""
from __future__ import annotations


def credit_line(source: dict) -> str:
    url = source.get("url") or ""
    return f"🎥 Source : {source.get('author') or 'inconnu'}" + (
        f" — {url}" if url.startswith(("http://", "https://")) else "")


def build_caption(clip: dict, source: dict, default_hashtags: list[str] | None = None,
                  max_len: int = 2150) -> str:
    tags = " ".join(dict.fromkeys(
        [t if t.startswith("#") else f"#{t}" for t in (clip.get("hashtags") or []) + (default_hashtags or [])
         if t and t.strip()]))
    body = clip.get("caption") or clip.get("title", "")
    return f"{body}\n\n{credit_line(source)}\n\n{tags}".strip()[:max_len]
