"""4. Repérage des moments forts (repris de clipper.find_highlights).

`ask_claude` passe désormais par le SDK Anthropic (sortie JSON structurée) au lieu du CLI `claude -p`.
Repli sur les pics de volume si aucune clé n'est configurée ou si l'API échoue.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from pydantic import BaseModel

from .utils import CancelCheck, Progress, check, hms, never_cancel, noop_progress, to_sec

log = logging.getLogger("liveclipper.ai")

PROMPT = """Tu es monteur de clips viraux TikTok / Reels.
Voici la transcription horodatee d'un extrait du live de {author} ("{title}"), de {a} a {b}.
Pics de volume audio (rires, cris, reactions), z-score entre parentheses : {peaks}

Trouve jusqu'a {k} moments forts qui marchent SEULS, sans contexte : punchline, fou rire,
reaction forte, histoire courte avec une chute, clash, info surprenante.
Chaque clip dure entre {mn} et {mx} secondes, commence juste avant l'action (pas de blanc)
et se termine juste apres la chute. Sois exigeant : mieux vaut 1 excellent clip que 5 moyens.

Pour chaque clip, donne :
- start / end au format "HH:MM:SS" (horodatages de la transcription)
- score de 1 a 10 (potentiel viral)
- title : titre court
- hook : accroche affichee 3 s en haut de la video, 8 mots max
- caption : legende de 1-2 phrases
- hashtags : 3 a 6 hashtags pertinents commencant par #
Ecris en {lang_name}. Si rien n'est assez bon, renvoie une liste vide.
"""

LANG_NAMES = {"fr": "francais", "en": "anglais", "es": "espagnol", "de": "allemand", "it": "italien",
              "pt": "portugais"}


class Highlight(BaseModel):
    start: str
    end: str
    score: float
    title: str
    hook: str
    caption: str
    hashtags: list[str]


class HighlightList(BaseModel):
    clips: list[Highlight]


class AIError(Exception):
    pass


AskFn = Callable[[str, dict, str], Optional[list]]


def ask_claude(text: str, cfg: dict, api_key: str, client=None) -> list[dict]:
    """Envoie un extrait de transcription à Claude, renvoie la liste de moments forts."""
    import anthropic
    client = client or anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=600)
    model = cfg.get("ai_model") or "claude-sonnet-5-5"
    try:
        # Repli serveur en cas de refus (Sonnet/Opus) ; Haiku n'a pas de repli côté serveur.
        extra = {} if "haiku" in model else {"betas": ["server-side-fallback-2026-07-01"],
                                             "fallbacks": "default"}
        resp = client.beta.messages.parse(
            model=model,
            max_tokens=16000,
            output_config={"effort": "medium"},
            **extra,
            messages=[{"role": "user", "content": text}],
            output_format=HighlightList,
        )
    except anthropic.AuthenticationError as e:
        raise AIError("Clé API Anthropic invalide : vérifie-la dans les Paramètres.") from e
    except anthropic.PermissionDeniedError as e:
        raise AIError("La clé API Anthropic n'a pas accès à ce modèle.") from e
    except anthropic.NotFoundError as e:
        raise AIError(f"Modèle IA introuvable : {model}.") from e
    except anthropic.RateLimitError as e:
        raise AIError("Limite de requêtes Anthropic atteinte : réessaie dans quelques minutes.") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"Erreur de l'API Anthropic ({e.status_code}) : {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Impossible de joindre l'API Anthropic (connexion Internet ?).") from e
    if resp.stop_reason == "refusal":
        raise AIError("L'IA a refusé d'analyser cet extrait.")
    parsed = resp.parsed_output
    if parsed is None:
        raise AIError("Réponse de l'IA illisible.")
    return [h.model_dump() for h in parsed.clips]


def snap(h: dict, segs: list[dict], total: float, cfg: dict) -> dict:
    st, en = to_sec(h["start"]), to_sec(h["end"])
    for s in segs:
        if s["start"] <= st < s["end"]:
            st = s["start"]
            break
    for s in segs:
        if s["start"] < en <= s["end"]:
            en = s["end"]
            break
    st, en = max(0.0, st - 0.3), min(total, en + 0.4)
    en = min(en, st + cfg["max_len"])
    if en - st < cfg["min_len"]:
        en = min(total, st + cfg["min_len"])
    return {**h, "start": round(st, 2), "end": round(en, 2)}


def find_highlights(segs: list[dict], peaks: list[dict], src: dict, n: int, total: float, cfg: dict,
                    api_key: str | None, progress: Progress = noop_progress,
                    cancel: CancelCheck = never_cancel, ask: AskFn | None = None) -> tuple[list[dict], list[str]]:
    """Renvoie (moments forts triés par début, avertissements)."""
    ask = ask or ask_claude
    window = int(cfg.get("ai_window_sec") or 1500)
    cands: list[dict] = []
    warnings: list[str] = []
    use_ai = bool(api_key)
    if not use_ai:
        warnings.append("Aucune clé API Anthropic : repérage uniquement sur les pics de volume.")
    lang_name = LANG_NAMES.get(cfg.get("language") or "fr", cfg.get("language") or "francais")
    windows = [(a, a + window) for a in range(0, int(total) + 1, window)] if use_ai else []
    for i, (a, b) in enumerate(windows):
        check(cancel)
        lines = [f"[{hms(s['start'])}] {s['text']}" for s in segs if a <= s["start"] < b]
        progress(i / max(1, len(windows)), f"Analyse IA {hms(a)} → {hms(min(b, total))}")
        if len(lines) < 3:
            continue
        pk = ", ".join(f"{hms(p['t'])} ({p['z']})" for p in peaks if a <= p["t"] < b and p["z"] > 1.2) or "aucun"
        prompt = PROMPT.format(author=src["author"], title=src.get("title") or "", a=hms(a),
                               b=hms(min(b, total)), peaks=pk, k=max(2, n), mn=cfg["min_len"],
                               mx=cfg["max_len"], lang_name=lang_name)
        try:
            res = ask(prompt + "\nTRANSCRIPTION :\n" + "\n".join(lines), cfg, api_key)
        except AIError as e:
            log.warning("IA : %s", e)
            if str(e) not in warnings:
                warnings.append(str(e))
            if "Clé API" in str(e):
                break
            continue
        except Exception as e:  # pragma: no cover
            log.exception("IA : erreur inattendue")
            warnings.append(f"Erreur IA : {e}")
            continue
        for h in res or []:
            try:
                cands.append(snap(h, segs, total, cfg))
            except (KeyError, ValueError, TypeError):
                pass
    if not cands:  # secours : pics de volume
        if use_ai and not warnings:
            warnings.append("L'IA n'a trouvé aucun moment assez fort : clips proposés à partir des pics de volume.")
        elif use_ai:
            warnings.append("Repli sur les pics de volume.")
        for p in sorted(peaks, key=lambda p: -p["z"])[:n * 2]:
            cands.append(snap({"start": max(0, p["t"] - 20), "end": p["t"] + 12,
                               "score": round(min(10.0, max(1.0, 5 + p["z"])), 1),
                               "title": f"Moment {hms(p['t'])}", "hook": "", "caption": "",
                               "hashtags": []}, segs, total, cfg))
    out: list[dict] = []
    for c in sorted(cands, key=lambda x: -float(x.get("score") or 0)):
        if all(c["end"] <= o["start"] or c["start"] >= o["end"] for o in out):
            out.append(c)
        if len(out) >= n:
            break
    progress(1.0, f"{len(out)} moment(s) fort(s) trouvé(s)")
    return sorted(out, key=lambda x: x["start"]), warnings
