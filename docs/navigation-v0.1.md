# Navigation, niveau 2 (V0.1)

Spécification : note « Navigation vers un point désigné » du vault (fonction renommée **Navigation** le 10 octobre 2026).

## Moteur
- **Valhalla** sur le serveur (`SARCADE_VALHALLA_URL`), avec les données OpenStreetMap du **département de l'ADRASEC et une marge de 10 km**.
- Démarrage : `docker compose --profile routing up -d`. Le service `osm-extract` télécharge l'extrait régional (`SARCADE_OSM_PBF_URL`, Île-de-France par défaut) et le découpe au cadre `SARCADE_ROUTING_BBOX` (Yvelines et environ 10 km par défaut, **valeurs approximatives à vérifier**) ; puis Valhalla construit ses tuiles. Rafraîchi au plus une fois par semaine.
- Mention obligatoire : « © OpenStreetMap contributors » (ODbL).

## Calcul d'itinéraire
`POST /api/v0.1/routing` (`event_id`, `points` dont la position actuelle en premier, `mode`) :

| Mode | Valhalla |
|---|---|
| `car` | voiture (`auto`) |
| `foot` | à pied (`pedestrian`), sentiers compris |
| `offroad` | tout-terrain : voiture avec pistes et chemins forestiers (`use_tracks`) |

Réponse : longueur, durée, tracé (`[[lat, lon]]`), instructions en français. 422 sans itinéraire possible, 503 si le moteur est indisponible. `GET /api/v0.1/routing/status` indique s'il répond.

## Routes coupées
Objet synchronisé `road_closure` (ligne et libellé, actif ou non), **créé et levé par le PCO seulement**. Chaque itinéraire de l'événement l'évite (`exclude_polygons`, bande de 15 m autour de la ligne). Main courante : « Route coupée », « Route rouverte ». `GET /events/{id}/road-closures`.

## Tronçons des routes « par les chemins »
`POST /api/v0.1/events/{id}/routes/{route_id}/legs` calcule les tronçons en attente (posés hors connexion, `leg_needs_routing`), selon le profil de la route (à pied ou véhicule). Le serveur le fait aussi seul toutes les deux minutes quand `SARCADE_VALHALLA_URL` est défini. Le tracé est enregistré dans le point et publié dans le flux de changements ; sans chemin possible, le tronçon reste droit (`leg_routing_failed`).

## Itinéraire partagé avec le PCO
Objet synchronisé `itinerary` (appareil, équipe, destination, mode, tracé, longueur restante, heure d'arrivée estimée, statut). Le PCO le voit (`GET /events/{id}/itineraries`). Main courante : départ et arrivée.

Vérification : `tests/test_navigation.py`, `demo/verify_navigation.py` (CI, avec `demo/services_stub.py` à la place de Valhalla).
