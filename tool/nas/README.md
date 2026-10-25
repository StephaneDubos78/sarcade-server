# Outils du NAS de test

## sarcade-switch
Bascule le serveur du NAS sur une branche en une commande : sauvegarde de la base si la branche ajoute des migrations, refus de revenir sur une branche plus ancienne que la base, reconstruction (avec le dernier client web), attente de `/health`.

Utilisation : `sarcade-switch main`, `sarcade-switch feat/aprs`, `sarcade-switch --status`, `sarcade-switch --list`.

Sauvegardes : `/volume1/docker/sarcade/sauvegardes/`. Réglages par variables d'environnement (`SARCADE_ROOT`, `SARCADE_DB_SERVICE`…), valeurs par défaut adaptées au DS1825+.

## sarcade-autoupdate
Met le NAS à jour tout seul depuis GitHub, toutes les 5 minutes (Planificateur de tâches de DSM) :
- **nouveau commit sur `main`** dont la CI est au vert → `sarcade-switch main` (sauvegarde, migrations, reconstruction) ;
- **nouveau client web** publié (`web-dev`) → reconstruction du serveur seul ;
- **NAS basculé à la main** sur une autre branche (recette d'une PR) → rien, jusqu'au retour sur `main` (`sarcade-switch main`) ;
- **CI en échec** → rien, le NAS reste sur la dernière version verte ;
- **échec d'une mise à jour** → pause automatique (fichier `autoupdate.off`) et message dans le journal.

Commandes : `sarcade-autoupdate --status` (état et derniers passages), `sarcade-autoupdate --dry-run` (dit ce qu'il ferait).
Pause : `touch /volume1/docker/sarcade/autoupdate.off` ; reprise : `rm /volume1/docker/sarcade/autoupdate.off`.
Journal : `/volume1/docker/sarcade/autoupdate.log`.

Les outils se réinstallent eux-mêmes depuis le dépôt après chaque mise à jour du serveur.

## Installation (une fois, en root)
```
cd /volume1/docker/sarcade && git -C sarcade-server remote set-url origin https://github.com/sdubos-consulting/sarcade-server.git && for t in sarcade-switch sarcade-autoupdate; do curl -fsSL https://raw.githubusercontent.com/sdubos-consulting/sarcade-server/main/tool/nas/$t.sh -o /usr/local/bin/$t && chmod +x /usr/local/bin/$t; done && sarcade-autoupdate --dry-run
```

Puis dans DSM : **Panneau de configuration → Planificateur de tâches → Créer → Tâche planifiée → Script défini par l'utilisateur** :
- Général : nom `SARCADE mise à jour automatique`, utilisateur **root** ;
- Programmer : **tous les jours**, fréquence **toutes les 5 minutes**, de 00:00 à 23:55 ;
- Paramètres de tâche : `/usr/local/bin/sarcade-autoupdate`.
