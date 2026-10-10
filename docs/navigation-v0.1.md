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

## Navigation on the device (level 3, variant B)
Decision of 10 Oct 2026. The server builds a **compact road graph** from the
same OSM extract as Valhalla (`SARCADE_OSM_PBF`, department + 10 km), at
start and whenever the extract is newer (weekly refresh), and serves it:

- `GET /api/v0.1/routing/graph/info`: availability, version, date, size,
  SHA-256, bounding box, number of vertices and edges;
- `GET /api/v0.1/routing/graph`: the package (ETag = SHA-256, `304` when the
  app already has it).

Format « SRG1 » (gzip, little-endian, see `src/sarcade/routing/graph.py`):
vertices at junctions and ends of ways, edges with length, modes allowed in
each direction (car, foot, off-road; one-way streets for vehicles), road
class, name and intermediate points; the header carries the speeds per
mode and class so that the app uses the same values as the server.
Tracks are open to off-road and foot, not to cars; private roads are left
out. `python -m sarcade.routing.graph extract.osm.pbf graph.srg.gz` builds it
by hand.

## Navigation app of the organisation (level 1)
Administration setting `navigation`: `app` (`operator` by default,
`organic_maps`, `osmand`, `apple_maps`, `google_maps`, `waze`) and
`hide_tracking_apps` (hide Google Maps and Waze). Sent to the clients by
`GET /api/v0.1/clients/config`, `/clients/check` and each heartbeat.
