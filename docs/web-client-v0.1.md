# Client Web (PWA) servi par le serveur

Le serveur SARCADE peut servir lui-même le client Web installable (canal principal sur ChromeOS). Le client partage alors l'origine de l'API : pas de CORS, et il fonctionne sur un réseau local sans Internet.

## Activation
1. Récupérer l'artefact `sarcade-web.tar.gz` du job `web-build` de `sarcade-app`.
2. L'extraire dans un dossier du serveur, par exemple `/opt/sarcade/web`.
3. Définir `SARCADE_WEB_ROOT=/opt/sarcade/web` et redémarrer le serveur.

Le client s'ouvre à l'adresse du serveur (`http://serveur:8000/`). Sans `SARCADE_WEB_ROOT`, ou si le dossier ne contient pas `index.html`, rien n'est servi à `/` et l'API fonctionne comme avant.

## Comportement
- Monté en dernier, à `/` : les routes `/health` et `/api/...` restent prioritaires.
- `index.html`, `manifest.json`, `flutter_bootstrap.js`, `version.json` et le service worker sont envoyés avec `Cache-Control: no-cache`, pour qu'une nouvelle version du client soit prise en compte au démarrage suivant.

## Limite actuelle : HTTPS
Chrome n'autorise l'installation de la PWA et la géolocalisation que sur HTTPS (ou `localhost`). En HTTP sur le réseau, le client s'ouvre dans un onglet mais ne s'installe pas et ne partage pas la position. Le passage en HTTPS est une étape à part.
