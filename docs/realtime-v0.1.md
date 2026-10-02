# Temps réel et lecture des positions — v0.1

## REST
- GET /api/v0.1/events/{event_id}/positions/latest
- GET /api/v0.1/events/{event_id}/devices/{device_id}/positions
- GET /api/v0.1/events/{event_id}/pois
- POST /api/v0.1/events/{event_id}/pois

L'historique d'une trace est paginé/limité par le paramètre limit.

## WebSocket
Connexion : /api/v0.1/events/{event_id}/ws

Événements initiaux :
- position.updated
- poi.created

Le flux est strictement isolé par event_id. À ce stade, l'authentification WebSocket sera ajoutée avec la couche IAM.

## Objectif
Un client abonné à un événement reçoit immédiatement une nouvelle position ou un nouveau POI après validation et persistance en base.
