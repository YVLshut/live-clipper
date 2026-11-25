"""Détection des captchas / vérifications de sécurité.

Live Clipper ne tente JAMAIS de les contourner : dès qu'une vérification apparaît,
la publication est mise en pause et l'utilisateur est prévenu pour agir lui-même.
"""
from __future__ import annotations

import re

URL_PATTERNS = [
    r"/challenge", r"/checkpoint", r"captcha", r"/two_factor", r"/accounts/suspended",
    r"/verify", r"/auth_platform/", r"security[-_]check",
]
TEXT_PATTERNS = [
    r"v[ée]rifi(?:ez|e|cation)\s+(?:que|de s[ée]curit[ée]|votre identit[ée])",
    r"confirm (?:that )?(?:it'?s you|you'?re (?:a )?human)", r"verify (?:it'?s you|you are human|to continue)",
    r"security check", r"suspicious (?:login|activity)", r"activit[ée] suspecte",
    r"faites glisser|drag the (?:slider|puzzle)", r"select all images", r"captcha",
    r"entrez le code|enter (?:the|your) (?:security |confirmation )?code",
    r"we detected an unusual", r"nous avons d[ée]tect[ée]",
]
SELECTORS = [
    'iframe[src*="captcha"]', 'iframe[title*="captcha" i]', '[id*="captcha" i]', '[class*="captcha" i]',
    'div[class*="secsdk"]', '#arkose', 'iframe[src*="arkoselabs"]', 'iframe[src*="recaptcha"]',
    'input[name="verificationCode"]', 'input[name="security_code"]',
]


def detect_in(url: str, text: str) -> str | None:
    """Version pure (testable) : renvoie la raison si une vérification est détectée."""
    for p in URL_PATTERNS:
        if re.search(p, url or "", re.I):
            return f"page de vérification ({url})"
    low = (text or "")[:20000]
    for p in TEXT_PATTERNS:
        m = re.search(p, low, re.I)
        if m:
            return f"vérification demandée (« {m.group(0)} »)"
    return None


def detect(page) -> str | None:
    """Inspecte une page Playwright (et ses iframes de captcha)."""
    try:
        for sel in SELECTORS:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                return f"captcha détecté ({sel})"
        text = page.evaluate("() => document.body ? document.body.innerText : ''")
        return detect_in(page.url, text)
    except Exception:
        return None
