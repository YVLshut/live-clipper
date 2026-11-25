# Live Clipper

Application de bureau Windows pour clipper automatiquement des lives :
**lien de live → repérage des moments forts par l'IA → clips 9:16 sous-titrés → publication Instagram / TikTok**,
avec l'auteur et la source crédités dans chaque légende.

## Installation

Télécharge `LiveClipper-Setup.exe` (onglet **Releases** du dépôt, ou artefact du workflow **Actions → Build Windows**)
et lance-le. Au premier démarrage, un assistant télécharge le modèle de transcription Whisper (et, si tu as une carte
NVIDIA, les bibliothèques GPU), puis te demande ta clé API Anthropic.

Toutes les données (base, clips, profils de comptes, modèles, logs) sont dans `%APPDATA%\LiveClipper`.
Les clés et jetons sont dans le Gestionnaire d'identification Windows.

## Fonctionnalités

**Lives**
- Un ou plusieurs liens Twitch, YouTube ou Kick, en direct ou terminés. Un live en direct est enregistré par
  tranches de 30 min, clippées au fur et à mesure. Chaque lien devient un job suivi
  en direct : téléchargement (yt-dlp) → transcription (faster-whisper, GPU NVIDIA ou CPU int8) → repérage IA
  (Claude, à partir de la transcription horodatée et des pics de volume) → montage ffmpeg 9:16 (fond flou ou recadrage,
  sous-titres karaoké, accroche).
- Pour chaque clip : score /10, titre, accroche, légende, hashtags. L'accroche est modifiable : seul ce clip est remonté.
- La source est enregistrée (auteur, chaîne, live, titre, plateforme, date) et ajoutée à chaque légende :
  « 🎥 Source : auteur — lien ».

**Comptes**
- Plusieurs comptes Instagram et TikTok, avec nom, avatar et statut de connexion.
- API officielles : Instagram Graph API (Reels, compte pro relié à une Page Facebook) et TikTok Content Posting API,
  connexion OAuth, jetons rafraîchis automatiquement. Un guide intégré explique comment créer tes apps développeur.
- Mode de secours « navigateur » : un profil Edge/Chromium séparé par compte, où tu te connectes toi-même.
  **Aucun contournement de captcha ou de vérification** : la publication est mise en pause et tu es prévenu.
- Règles par compte : publication automatique (désactivée par défaut), approbation manuelle obligatoire par défaut,
  score minimal, posts max par jour, plages horaires, délai aléatoire entre deux posts.

**Publier**
- Clique sur 10, 50 ou 100 clips : chaque compte coché publie ce nombre de clips, 1 par heure, automatiquement
  (les meilleurs d'abord, différents d'un compte à l'autre tant que possible). Une fenêtre montre l'avancée
  compte par compte.
- File et calendrier des posts programmés, statut (en attente, publié + lien, échec + raison, pause), capture d'écran
  et bouton Réessayer en cas d'échec.

## Pour les développeurs

- Reconstruire l'installeur : [BUILD.md](BUILD.md) (`build.ps1` ou GitHub Actions).
- Points à vérifier sur un vrai PC Windows : [TESTS_MANUELS.md](TESTS_MANUELS.md).
- CLI (même base que l'application) :

```bash
python clipper.py clip "https://www.twitch.tv/videos/123456" --section 01:00:00-01:30:00 --max-clips 5
```

```bash
python clipper.py list
```

## À savoir

- Publier via un navigateur automatisé (mode secours) est contraire aux conditions d'utilisation d'Instagram et de
  TikTok. Préfère les API officielles ; les délais entre posts limitent le risque sans l'annuler.
- Tant que ton app TikTok n'a pas passé l'audit de TikTok, les vidéos publiées via l'API sont privées.
- Ne clippe que des créateurs qui t'ont donné leur accord : le crédit en légende ne suffit pas en cas de réclamation.
