# Projet : Live Clipper

Pipeline : `clipper.py` (lis README.md pour l'installation et les commandes).

## Quand l'utilisateur donne un lien de live
1. `python clipper.py clip "<URL>"` (si le live dure plus de 3 h, propose `--section`).
2. Ouvre `manifest.json` et résume les nouveaux clips : horodatage, titre, score, accroche, auteur/source.
3. Propose d'améliorer les accroches et les légendes, puis édite `manifest.json` si l'utilisateur est d'accord.
   Si une accroche change, relance seulement le montage de ce clip.
4. Ne lance jamais `approve` ni `post --publish` sans un accord explicite de l'utilisateur.

## Règles
- Chaque légende doit créditer l'auteur et le lien source (fait automatiquement par `build_caption`).
- En cas d'erreur de publication : lis `clips/<id>/erreur_<plateforme>.png`, puis corrige les sélecteurs
  dans `post_tiktok` / `post_instagram`. Teste sans `--publish`.
- Ne contourne pas les captchas ni les vérifications de sécurité : demande à l'utilisateur de les faire.
- Garde les délais entre publications (`delay_between_posts_sec`).
