# Client Web (PWA) servi par le serveur

Le serveur SARCADE sert lui-même le client Web : accès depuis n'importe quel navigateur du réseau, et application installable (PWA), canal principal sur ChromeOS. Le client partage alors l'origine de l'API : pas de CORS, et il fonctionne sur un réseau local sans Internet.

## Activation
**Avec Docker (cas normal)** : l'image du serveur contient déjà le client Web, téléchargé à la construction depuis la pré-version `web-dev` de `sarcade-app` (mise à jour par sa CI). Après `docker compose up -d --build`, le client s'ouvre à l'adresse du serveur, par exemple `http://serveur:8000/`, dans Chrome, Edge, Firefox ou Safari.

- Récupérer un client plus récent : `docker compose build --build-arg SARCADE_WEB_CACHEBUST=$(date +%s) server`.
- Image sans client Web (API seule) : `--build-arg SARCADE_WEB_URL=`.
- Construction sans Internet : le téléchargement échoue sans bloquer, l'image est construite sans client Web.

**Sans Docker** : extraire l'artefact `sarcade-web.tar.gz` dans un dossier, par exemple `/opt/sarcade/web`, puis définir `SARCADE_WEB_ROOT=/opt/sarcade/web` et redémarrer le serveur.

Sans client Web (variable absente ou dossier sans `index.html`), rien n'est servi à `/` et l'API fonctionne comme avant.

## Comportement
- Monté en dernier, à `/` : les routes `/health` et `/api/...` restent prioritaires.
- `index.html`, `manifest.json`, `flutter_bootstrap.js`, `version.json` et le service worker sont envoyés avec `Cache-Control: no-cache`, pour qu'une nouvelle version du client soit prise en compte au démarrage suivant.

## Limite actuelle : HTTPS
Chrome n'autorise l'installation de la PWA et la géolocalisation que sur HTTPS (ou `localhost`). En HTTP sur le réseau, le client s'ouvre dans un onglet mais ne s'installe pas et ne partage pas la position. Le passage en HTTPS est une étape à part.
