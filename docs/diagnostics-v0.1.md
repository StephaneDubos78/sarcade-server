# Diagnostic du serveur (V0.1)

Carte « Paramètres › Diagnostic étoffé », validée par le porteur le 30 octobre 2026 (2 h 58), lot 5.

- `GET /api/v0.1/diagnostics/server` — **PCO et administrateurs** (`require_pco` ; sur une adresse publique protégée par Cloudflare Access, un appelant sans e-mail vérifié est refusé, `403 pco_required`).
- Réponse : `status` (`ok` / `degraded` / `down`), `version`, `started_at`, `uptime_s`, `components` (`database`, `realtime`, `tunnel`, `wakeup`, `aprs`, `weather` : `green` / `orange` / `red` / `off`), `detail`, `resources` (`cpu_pct`, `cpu_count`, `load`, `memory{used_mb,total_mb,pct}`, `disk{path,used_gb,total_gb,pct}`, `alert` au-delà de 80 %), `alert_pct`, `last_update`, `last_backup`, `update_status`.
- Ressources lues dans `/proc` et `os.statvfs` (vues depuis le conteneur, aucune dépendance) ; disque : dossier des fichiers (`SARCADE_FILE_ROOT`) ou `/`.
- Tunnel : vert si une requête est passée par Cloudflare (en-tête `cf-ray`) dans les 15 dernières minutes ; orange sinon (Access actif) ; `off` sans Access ni passage par Cloudflare.
- Dernière sauvegarde : déduite du dernier rapport de l'outil de mise à jour (`backup …`), `null` sinon.

Vérification : `tests/test_diagnostics.py`, `demo/verify_diagnostics.py`.
