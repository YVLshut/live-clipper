# Live Clipper

Lien de live -> repérage des moments forts -> clips 9:16 sous-titrés -> publication TikTok / Instagram
depuis ton propre Chrome, avec l'auteur et la source crédités dans chaque légende.

## Installation (Windows, une seule fois)
1. Python 3.11+ et **ffmpeg** dans le PATH (`winget install Gyan.FFmpeg`)
2. `pip install -r requirements.txt`
3. GPU NVIDIA pour Whisper : `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`
   (sinon, dans config.json : `"device": "cpu", "compute_type": "int8"`, plus lent)
4. Claude Code installé (`claude` dans le PATH) : c'est lui qui repère les moments forts.

## Chrome pour la publication
Chrome refuse le pilotage sur ton profil principal, donc on utilise un profil dédié :
```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\chrome-clipper"
```
La première fois, connecte-toi à TikTok et Instagram dans cette fenêtre. Les connexions sont gardées pour la suite.
Garde cette fenêtre ouverte quand tu lances `post`.

## Utilisation
```
python clipper.py clip "https://www.twitch.tv/videos/123456"       # télécharge, transcrit, repère, monte
python clipper.py clip URL --section 01:00:00-03:00:00 --max-clips 8 --layout crop
python clipper.py list                                              # liste des clips + score + statut
python clipper.py approve <id> <id>      (ou --all)
python clipper.py post                                              # prépare les posts, TU cliques sur Publier
python clipper.py post --publish --platform tiktok --limit 2        # publie automatiquement
```
Les clips se trouvent dans `clips/<id>/clip.mp4`. Tout est noté dans `manifest.json`
(source, auteur, horodatage, légende, statut de publication).

## Layouts
- `blur` (par défaut) : la vidéo entière au centre, fond flou. Idéal pour les streams avec facecam + jeu.
- `crop` : recadrage plein écran au centre. Idéal pour les lives "talk" en face caméra.

## À savoir
- Les sélecteurs TikTok/Instagram changent régulièrement. En cas d'erreur, une capture `erreur_<plateforme>.png`
  est enregistrée : demande à Claude Code de corriger `post_tiktok` / `post_instagram`.
- Publier via un navigateur automatisé est contraire aux conditions d'utilisation des deux plateformes.
  Le mode par défaut (préparer, puis cliquer toi-même) et les délais entre posts limitent le risque, sans l'annuler.
- Ne clippe que des créateurs qui t'ont donné leur accord : le crédit en légende ne suffit pas en cas de réclamation.
