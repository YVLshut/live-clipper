# Tests manuels à faire sur ton PC Windows

Tout le reste a été testé automatiquement sous Linux (`pytest` : pipeline réel sur CPU avec une vidéo générée
par ffmpeg, API, file de jobs, WebSocket, OAuth et publication simulés, planification, garde-fou captcha dans un
vrai Chromium, exécutable PyInstaller Linux lancé de bout en bout). Les points ci-dessous demandent Windows,
un GPU, un écran ou tes vrais comptes. Coche-les au fur et à mesure.

Les journaux sont dans `%APPDATA%\LiveClipper\logs\liveclipper.log` (Paramètres → Système → Journaux).
En cas de problème, envoie-moi ce fichier.

---

## 1. Installation

- [ ] Télécharge `LiveClipper-Setup.exe` (artefact du workflow GitHub Actions, voir BUILD.md).
- [ ] Lance-le. Si Windows SmartScreen affiche « Windows a protégé votre ordinateur », clique sur
      **Informations complémentaires → Exécuter quand même** (l'exe n'est pas signé).
- [ ] L'installeur est en français, propose « Créer un raccourci sur le Bureau » et s'installe dans
      `C:\Program Files\Live Clipper`.
- [ ] Les raccourcis **Bureau** et **menu Démarrer → Live Clipper** existent, avec l'icône violette.
- [ ] « Lancer Live Clipper » à la fin de l'installation ouvre l'application.

### Si Windows bloque l'application (« Une stratégie de contrôle d'application a bloqué ce fichier »)
C'est le **Contrôle intelligent des applications** (Smart App Control) de Windows 11 : il refuse les DLL non
signées numériquement, et celles de Live Clipper (Python, Whisper, numpy…) ne le sont pas.
- [ ] Vérifie son état : **Sécurité Windows → Contrôle des applications et du navigateur → Paramètres du contrôle
      intelligent des applications**. S'il est sur « Activé » ou « Évaluation », c'est lui.
- [ ] Pour lister tous les fichiers bloqués (utile pour moi), dans PowerShell après une tentative de lancement :

```powershell
Get-WinEvent -LogName 'Microsoft-Windows-CodeIntegrity/Operational' -MaxEvents 300 | Where-Object { $_.Id -in 3033,3034,3076,3077 } | Format-List TimeCreated, Id, Message | Out-File "$env:USERPROFILE\Desktop\blocages-liveclipper.txt"
```

- [ ] Solutions : soit le passer sur **Désactivé** (attention : selon ta version de Windows, le réactiver peut
      demander de réinstaller Windows), soit signer l'application avec un certificat de signature de code (voir BUILD.md).

## 2. Fenêtre native (pywebview)

- [ ] L'application s'ouvre dans **sa propre fenêtre** (titre « Live Clipper », thème sombre), sans navigateur visible
      ni console noire.
- [ ] La fenêtre se redimensionne, ne descend pas sous ~1100×700, et le texte est net (écran HiDPI).
- [ ] En bas à gauche : « Moteur connecté » (pastille verte).
- [ ] Ferme la fenêtre : le processus `LiveClipper.exe` disparaît du Gestionnaire des tâches en quelques secondes.
- [ ] Relance-la : les données sont toujours là.
- [ ] Lance l'app deux fois de suite : la 2e fenêtre fonctionne aussi (même moteur), sans erreur.
- [ ] Un lien externe (ex. « console.anthropic.com » dans Paramètres) s'ouvre dans **ton navigateur habituel**.
- [ ] Paramètres → Dossier de sortie → **Parcourir…** ouvre le sélecteur de dossier Windows.

## 3. Assistant de premier lancement

- [ ] Au 1er lancement, l'assistant s'affiche (Bienvenue → Transcription → Carte graphique → IA).
- [ ] Étape « Carte graphique » : ta **RTX 3080** est détectée (« Carte NVIDIA détectée : NVIDIA GeForce RTX 3080 »).
- [ ] Télécharge les **bibliothèques GPU** : la barre progresse (environ 1 Go), puis « Bibliothèques GPU installées ».
      Vérifie que `%APPDATA%\LiveClipper\cuda` contient `cublas64_12.dll` et `cudnn*.dll`.
- [ ] Étape « Transcription » : choisis **large-v3-turbo** (recommandé avec GPU) → la barre progresse jusqu'à 100 %.
      Le dossier `%APPDATA%\LiveClipper\models\large-v3-turbo` contient `model.bin`.
- [ ] Clique sur **Annuler** pendant un téléchargement : il s'arrête proprement, et le relancer reprend.
- [ ] Étape IA : colle ta clé `sk-ant-…`, puis **Terminer**.
- [ ] Ouvre le **Gestionnaire d'identification Windows** (Panneau de configuration → Gestionnaire d'identification →
      Informations d'identification Windows) : une entrée `anthropic_api_key@LiveClipper` existe.
      La clé n'apparaît **nulle part en clair** dans `%APPDATA%\LiveClipper`.
- [ ] Paramètres → Intelligence artificielle → **Tester** → « Clé API valide ✔ ».

## 4. GPU / CPU

- [ ] Paramètres → Système : la ligne GPU indique « 1 GPU CUDA détecté(s) ».
- [ ] Lance un clipping (section 5) : pendant la transcription, le message indique « Transcription sur GPU… »
      et le Gestionnaire des tâches → Performances → GPU montre l'activité « Cuda » (ou « Compute »).
- [ ] Mets « Processeur de calcul » sur **CPU**, relance un court clipping : « Transcription sur CPU… » (plus lent mais OK).
- [ ] Repli automatique : renomme temporairement `%APPDATA%\LiveClipper\cuda` en `cuda_off`, remets « Automatique »,
      relance l'app et un clipping : il doit passer en CPU sans planter (les logs mentionnent le repli). Renomme ensuite
      le dossier en `cuda`.
- [ ] Encodeur **h264_nvenc** (Paramètres → Montage) : un clip se monte nettement plus vite ; le fichier se lit bien.
      Si NVENC échoue, le log indique « repli sur libx264 » et le clip est quand même créé.

## 5. Clipping (Onglet 1)

Utilise des lives de créateurs qui t'ont donné leur accord.

- [ ] Colle un lien **Twitch** (VOD), lance avec « Passage précis » 00:10:00 → 00:30:00 et 3 clips max.
      Le job affiche en direct Téléchargement → Transcription → Repérage IA → Montage, avec le pourcentage.
- [ ] Colle **plusieurs liens** (YouTube + Kick) d'un coup : un job par lien, traités l'un après l'autre.
- [ ] La carte du job affiche l'auteur (lien vers la chaîne), la plateforme, la date et un lien « live ».
- [ ] **Annuler** un job en cours : il s'arrête et passe en « Annulé » ; **Réessayer** le relance.
- [ ] Lien invalide ou vidéo privée : message d'erreur clair en français, pas de plantage.
- [ ] Galerie : chaque clip se lit dans le lecteur, en 9:16, avec les sous-titres karaoké et l'accroche en haut
      pendant 3 s. Score /10, titre, légende et hashtags proposés par l'IA.
- [ ] Teste les deux mises en page : **Fond flou** et **Recadrage**.
- [ ] Modifie l'**accroche** → « Enregistrer et remonter » : un voile « Remontage… » s'affiche, puis le lecteur montre
      la nouvelle accroche. Les autres clips ne sont pas remontés.
- [ ] Modifie la **légende** et les **hashtags** : la « Légende publiée » se met à jour et contient toujours
      « 🎥 Source : auteur — lien ».
- [ ] **Approuver / Rejeter / Supprimer** fonctionnent ; « Supprimer » efface le dossier du clip sur le disque.
- [ ] « Ouvrir le dossier » ouvre l'Explorateur sur les clips.
- [ ] Paramètres → yt-dlp → **Mettre à jour** : message de succès (ou « déjà à jour »).

## 6. Comptes — API officielles (Onglet 2)

### Instagram (Graph API)
- [ ] Suis le guide intégré (Paramètres → Applications développeur → Meta → **Guide pas à pas**) pour créer l'app Meta,
      déclarer l'URL de redirection `http://localhost:47615/oauth/instagram/callback` et copier l'ID et la clé secrète.
- [ ] Comptes → Ajouter un compte → Instagram → API officielle → **Se connecter** : ton navigateur s'ouvre sur Facebook.
      Accepte les autorisations : la page « Compte connecté ! » s'affiche, et dans l'app le compte passe à « Connecté »
      avec le nom @ et l'avatar.
- [ ] Si tu as plusieurs comptes Instagram pro : l'app te demande lequel utiliser.
- [ ] **Vérifier** → « est bien connecté ».

### TikTok (Content Posting API)
- [ ] Suis le guide TikTok, déclare `http://localhost:47615/oauth/tiktok/callback`.
      **Si TikTok refuse une adresse locale**, déclare une URL HTTPS quelconque, puis après l'autorisation copie l'adresse
      de la page d'erreur et utilise **« Coller l'adresse de retour »** sur la carte du compte.
- [ ] Le compte passe à « Connecté » avec le nom d'utilisateur.
- [ ] Note : tant que l'app n'est pas auditée par TikTok, choisis la visibilité « Moi uniquement » dans les règles.
      Si la connexion échoue sur l'étape PKCE (`code_challenge`), envoie-moi le message d'erreur exact.

### Jetons
- [ ] Les jetons sont dans le Gestionnaire d'identification Windows (`account_tokens:<n>@LiveClipper`).
- [ ] Le lendemain (le jeton TikTok dure 24 h), le compte est toujours « Connecté » : il a été rafraîchi automatiquement.

## 7. Comptes — mode navigateur (secours)

- [ ] Ajoute un compte TikTok en mode **Navigateur** → **Se connecter** : une fenêtre **Microsoft Edge** séparée s'ouvre
      sur la page de connexion. Connecte-toi toi-même, puis clique sur **J'ai terminé** dans l'app (ou ferme la fenêtre).
      Le compte passe à « Connecté ».
- [ ] Le profil est séparé : `%APPDATA%\LiveClipper\profiles\<n>` ; ta session Edge habituelle n'est pas touchée.
- [ ] Relance l'app puis **Vérifier** : toujours connecté (profil persistant).
- [ ] Ajoute un 2e compte du même réseau en mode navigateur : sessions indépendantes.

## 8. Publication (Onglet 3)

- [ ] Approuve un clip → **Programmer** → coche un compte → « Dès que possible » → **Publier**.
      Le post apparaît dans « Publication » en « En cours » puis « Publié », avec **Voir le post** qui ouvre le bon lien.
- [ ] Le post publié contient la légende avec « 🎥 Source : auteur — lien » et les hashtags.
- [ ] Instagram : le Reel est bien en 9:16 (pas recadré en carré).
- [ ] Programme un clip « À une date précise » dans 5 minutes : il part à l'heure prévue (l'app doit rester ouverte).
- [ ] **Calendrier** : le post apparaît le bon jour à la bonne heure ; navigation semaine précédente/suivante.
- [ ] Publication automatique : active-la sur un compte (score min 7, 2 posts/jour, plage 18:00-23:00, délai 45-120 min).
      Seuls les clips **approuvés** au-dessus du score sont programmés automatiquement, dans la plage, espacés
      d'un délai aléatoire, sans dépasser 2 par jour.
- [ ] Échec en mode navigateur (ex. coupe Internet pendant l'envoi) : statut « Échec » + raison, bouton **Capture**
      qui montre la capture d'écran, bouton **Réessayer** qui relance.
- [ ] **Captcha / vérification** : si TikTok ou Instagram affiche une vérification pendant une publication, le post passe
      en « En pause — vérification », une notification apparaît, la fenêtre Edge reste ouverte. Traite la vérification
      toi-même, puis clique sur **Reprendre** : la publication repart. L'app ne clique jamais à ta place sur un captcha.
- [ ] Session expirée : le compte passe à « À reconnecter » et la notification te le dit.

## 9. Désinstallation

- [ ] Paramètres Windows → Applications → Live Clipper → Désinstaller (ou menu Démarrer → Désinstaller Live Clipper).
- [ ] La question « Supprimer aussi tes données Live Clipper… ? » s'affiche. Avec **Non**, `%APPDATA%\LiveClipper` est
      conservé (réinstaller retrouve tout) ; avec **Oui**, il est supprimé.
- [ ] `C:\Program Files\Live Clipper` et les raccourcis ont disparu.
- [ ] (Optionnel) Les secrets restent dans le Gestionnaire d'identification : supprime à la main les entrées
      `…@LiveClipper` si tu veux tout effacer.

## 10. Release GitHub

- [ ] Pousse un tag `v1.0.0` : le workflow crée une Release avec `LiveClipper-Setup.exe` en pièce jointe.
