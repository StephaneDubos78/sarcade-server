# Outils du NAS de test

`sarcade-switch.sh` : bascule le serveur du NAS sur une branche en une commande (sauvegarde de la base si la branche ajoute des migrations, refus de revenir sur une branche plus ancienne que la base, reconstruction, attente de `/health`).

Installation (une fois, en root) :
```
curl -fsSL https://raw.githubusercontent.com/StephaneDubos78/sarcade-server/main/tool/nas/sarcade-switch.sh -o /usr/local/bin/sarcade-switch && chmod +x /usr/local/bin/sarcade-switch
```

Utilisation : `sarcade-switch main`, `sarcade-switch feat/aprs`, `sarcade-switch --status`, `sarcade-switch --list`.

Sauvegardes : `/volume1/docker/sarcade/sauvegardes/`. Réglages par variables d'environnement (`SARCADE_ROOT`, `SARCADE_DB_SERVICE`…), valeurs par défaut adaptées au DS1825+.
