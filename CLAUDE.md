# Projet : Live Clipper

Application de bureau Windows (FastAPI + React dans une fenêtre pywebview, empaquetée avec PyInstaller + Inno Setup).
Lis BUILD.md pour l'architecture, le développement et la construction de l'installeur.

- Moteur : `backend/liveclipper/` (pipeline repris de l'ancien clipper.py dans `pipeline/`).
- Interface : `frontend/` (tout en français, thème sombre).
- Données : `%APPDATA%\LiveClipper` (surcharge : `LIVECLIPPER_HOME`). Secrets : keyring, jamais en clair.
- Tests : `HF_HUB_DISABLE_XET=1 .venv/bin/python -m pytest -q` ; tout ce qui n'est pas testable sous Linux va dans TESTS_MANUELS.md.

## Quand l'utilisateur donne un lien de live (CLI)
1. `python clipper.py clip "<URL>"` (si le live dure plus de 3 h, propose `--section`).
2. `python clipper.py list`, puis résume les nouveaux clips : horodatage, titre, score, accroche, auteur/source.
3. Ne lance jamais `approve` ni de publication sans un accord explicite de l'utilisateur.

## Règles
- Chaque légende doit créditer l'auteur et le lien source (`pipeline/caption.py`, `build_caption`).
- Messages d'erreur destinés à l'utilisateur : en français (`errors.UserError`, `errors.humanize`).
- En cas d'erreur de publication en mode navigateur : regarde la capture enregistrée (`%APPDATA%\LiveClipper\screenshots`)
  puis corrige les sélecteurs dans `publish/browser.py` (`post_tiktok` / `post_instagram`).
- Ne contourne jamais les captchas ni les vérifications de sécurité (`publish/guard.py` met en pause et prévient).
- Garde les délais aléatoires entre publications (règles par compte, `publish/scheduler.py`).
