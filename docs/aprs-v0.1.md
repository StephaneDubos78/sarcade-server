# APRS (V0.1)

Spécification : note « APRS » du vault (décisions du 10 octobre 2026).

## Principe
Le **serveur** est le seul à parler à APRS ; il redistribue les positions aux clients par le flux temps réel habituel (`position.updated`, `source: "aprs"`). Seules les stations des **groupes d'indicatifs sélectionnés** sont affichées et enregistrées : les autres ne sont ni affichées, ni enregistrées.

## Entrées
| Entrée | Activation | Comportement |
|---|---|---|
| APRS-IS (Internet) | `SARCADE_APRS_IS=1` (`SARCADE_APRS_IS_HOST`, `SARCADE_APRS_IS_PORT`, défaut `rotate.aprs2.net:14580`) | connexion en lecture seule (code d'accès -1), filtre `b/` limité aux indicatifs suivis, mis à jour à chaud ; le serveur n'envoie jamais rien vers APRS-IS |
| Radio par le Gateway | `SARCADE_KISS_HOST`, `SARCADE_KISS_PORT` (défaut 8001) | modem logiciel KISS TCP (Dire Wolf) ; toutes les trames sont reçues, seules celles des indicatifs suivis sont gardées |
| Lignes poussées par le Gateway | `POST /api/v0.1/aprs/frames` (`via`: `rf` ou `is`, `lines`) | pour un modem sans KISS TCP |

Les deux entrées sont **fusionnées et dédoublonnées** : un même paquet (émetteur et contenu) entendu par radio et sur APRS-IS dans les 30 s n'est gardé qu'une fois.

Décodage : positions non compressées et compressées (avec ou sans horodatage), **Mic-E** (la plupart des postes mobiles), objets, trafic tiers. Vérifié contre la bibliothèque aprslib sur près de 3 000 trames.

## Groupes d'indicatifs
- `GET/POST /api/v0.1/aprs/groups`, `PUT/DELETE /api/v0.1/aprs/groups/{id}` (nom, indicatifs) : créés par l'administrateur de l'organisation.
- Un indicatif sans SSID couvre **tous ses SSID** (F4JPO couvre F4JPO-7, F4JPO-9…) ; avec SSID, seulement cette station.
- Un événement suit des groupes et le PCO peut ajouter des indicatifs : réglages `aprs_groups` et `aprs_callsigns` (`PATCH /events/{id}/settings`). `GET /events/{id}/aprs/callsigns` donne la liste effective. Un événement terminé ne suit plus rien.

## Rattachement aux opérateurs
Un opérateur déclare son indicatif dans le heartbeat (`callsign`) : ses positions APRS se rattachent à son appareil. Sinon, la station apparaît sous `aprs:<indicatif>`.

## Émission radio locale (désactivée par défaut)
Réglage `aprs_tx_rf` du PCO, consentement de l'opérateur (`aprs_tx_consent` dans le heartbeat), indicatif de l'ADRASEC (`SARCADE_APRS_CALLSIGN`) et liaison radio active : la position de l'opérateur est émise **en radio seulement**, comme objet portant son indicatif, sous l'indicatif de l'ADRASEC, au plus toutes les 2 minutes. Jamais vers APRS-IS.

## État
`GET /api/v0.1/aprs/status` : état des deux liaisons, filtre APRS-IS courant, paquets reçus, positions enregistrées.

Vérifications : `tests/test_aprs.py`, `tests/test_aprs_links.py` (faux serveurs APRS-IS et KISS), `demo/verify_aprs.py` (CI).
