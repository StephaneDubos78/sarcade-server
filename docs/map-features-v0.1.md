# Objets cartographiques v0.1

Objets dessinés sur la carte par les opérateurs : point, ligne, flèche, cercle, rectangle, zone, texte, tracé libre, mesure.

## Synchronisation
Type d'objet `map_feature` dans `POST /api/v0.1/sync`, actions `create`, `update` et `delete`.

- `create` et `update` portent l'état complet de l'objet : `id`, `event_id`, `kind`, `points` (liste de `[lat, lon]`), `radius_m` (cercle), `color` (ARGB), `stroke_width`, `label`, `created_by`, `updated_by`, `updated_at`.
- `delete` porte `id`, `event_id`, `updated_by`, `updated_at`.

## Règle de conflit (ADR-001)
Dernier écrivain gagnant par objet, sur le couple (`updated_at`, `updated_by`).

| Statut | Signification |
|---|---|
| `accepted` | appliqué, diffusé en temps réel et dans le flux de changements |
| `conflict` | plus ancien que l'état connu, ignoré. Le client retire l'opération de son Outbox et reçoit l'état gagnant par le flux |
| `duplicate` | `operation_id` déjà reçu |
| `rejected` | données invalides ou événement inconnu, jamais applicable |

La suppression pose une pierre tombale. Une modification plus récente fait réapparaître l'objet, ce qui permet d'annuler une suppression. Un horodatage plus de 5 minutes dans le futur est ramené à l'heure du serveur.

Le flux `GET /events/{id}/sync/changes` ne contient que les opérations acceptées, avec l'état résultant (dont `revision` et `deleted`).

## Lecture
- `GET /api/v0.1/events/{id}/map-features` : objets actifs (`include_deleted=true` pour les pierres tombales)
- `GET /api/v0.1/events/{id}/map-features.geojson` : FeatureCollection GeoJSON

## Temps réel
`map_feature.upserted` et `map_feature.deleted`, avec l'état résultant.

## Main courante
Création, suppression et restauration sont journalisées. Les modifications ne le sont pas, pour ne pas noyer la main courante.

## Vérification
`demo/verify_map_features.py`, exécuté par la CI contre PostgreSQL/PostGIS.
