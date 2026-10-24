# Docker

Éléments propres à l'image SARCADE Server.

- `fetch_web_client.py` : intègre le client Web à l'image pendant la construction (voir `docs/web-client-v0.1.md`).

Le déploiement local de développement est piloté par le fichier Compose à la racine.
- `caddy/` : proxy inverse HTTPS (profil Compose `https`), option A Let's Encrypt par défi DNS ou option B autorité locale (voir `docs/https-v0.1.md`).
