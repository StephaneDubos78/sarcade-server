# Opérations d'événement (V0.1)

Réglages décidés par le PCO, dernier contact des appareils et fin d'événement.
Spécifications : notes « Synchronisation client-serveur » et « Suivi de position » du vault.

## Réglages de l'événement

`GET /api/v0.1/events/{event_id}` renvoie l'événement avec ses réglages (valeurs par défaut pour les événements existants).

`PATCH /api/v0.1/events/{event_id}/settings` (corps : `actor_id`, `settings`) modifie un ou plusieurs réglages :

| Réglage | Défaut | Valeurs |
|---|---|---|
| `low_bandwidth` | `false` | mode liaison faible imposé par le PCO |
| `low_bandwidth_interval_s` | 60 | envoi groupé, 15 à 3600 s |
| `sync_alert_minutes` | 5 | alerte des éléments non partis et appareils en retard, 1 à 120 min |
| `tracking_required` | `false` | suivi de position imposé par le PCO |
| `tracking_default_interval_s` | 30 | 10, 30, 60, 120, 300 ou 600 s |
| `tracking_min_interval_s` / `tracking_max_interval_s` | 10 / 600 | bornes fixées par le PCO |

Chaque changement est inscrit dans la main courante et diffusé (`event.settings.updated`). Les réglages sont figés après la fin de l'événement (409).

## Dernier contact des appareils

`POST /api/v0.1/events/{event_id}/devices/{device_id}/heartbeat` : contact périodique du client (libellé, plateforme, version, batterie, éléments en attente, suivi actif et fréquence souhaitée). La réponse indique ce que l'appareil doit appliquer : réglages, fréquence de suivi ramenée dans les bornes du PCO, suivi imposé, fin d'événement.

Chaque position reçue (API ou synchronisation) met aussi à jour le dernier contact, la dernière position et la batterie.

`GET /api/v0.1/events/{event_id}/devices` : vue PCO, appareils en retard d'abord (`late` au-delà de `sync_alert_minutes`, `unknown`, `ok`).

## Positions

Les positions acceptent `battery_pct` (0 à 100) et portent une `source` (`device` pour l'instant, `aprs` ensuite).

## Fin de l'événement

`POST /api/v0.1/events/{event_id}/close` (corps : `actor_id`) : statut `closed`, heure de fin, entrée de main courante, diffusion `event.closed`. Les clients arrêtent alors le suivi de position. Idempotent.

## Limite

L'authentification (ADR-002) n'est pas encore en place : `actor_id` et `device_id` sont déclarés par le client.

Vérification : `demo/verify_event_operations.py`, exécuté par la CI.
