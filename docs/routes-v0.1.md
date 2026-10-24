# Routes avec points de passage (V0.1)

Spécification : note « Route avec points de passage » du vault (décisions du 10 octobre 2026).

## Objets synchronisés (ADR-001)
| `object_type` | Contenu |
|---|---|
| `route` | nom, couleur, mode de tracé par défaut (`straight` ou `paths`), profil (`foot` ou `vehicle`), statut, **ordre des points** (`point_order`), affectation (`assigned_team_id` ou `assigned_group_id`) |
| `route_waypoint` | **un objet par point** : nom, type (départ, passage, point de contrôle, ravitaillement, arrivée), position, commentaire, heure prévue, **rayon d'approche (50 m par défaut)**, mode du tronçon qui y arrive et son tracé calculé (`leg_geometry`, `leg_needs_routing`) |
| `route_passage` | passage d'une équipe à un point, `auto` ou `manual`, annulable |

Chaque point étant un objet distinct, deux personnes qui modifient deux points différents ne s'écrasent pas.

## Règles
- **Route affectée** : modifiable (route et points) seulement par son auteur et le PCO ; sinon `rejected`.
- **Équipe prévenue** : toute modification d'une route affectée (affectation, point ajouté, déplacé, modifié, supprimé, ordre changé) envoie **un message urgent** au groupe de l'équipe, un seul par lot de synchronisation, avec demande d'accusé de réception.
- **Ordre modifié en même temps** : le client envoie l'ordre sur lequel il a travaillé (`base_point_order`) ; la dernière version gagne, et si l'ordre avait changé entre-temps, le PCO est prévenu (main courante et `route.order_conflict`).
- Main courante : création, affectation, suppression de route, passages et annulations, signalements.

## API
| Point d'accès | Rôle |
|---|---|
| `GET /api/v0.1/events/{id}/routes` | routes avec points ordonnés, longueur de chaque tronçon (le long du tracé calculé s'il existe), longueur cumulée et totale, passages |
| `GET /api/v0.1/events/{id}/routes/{route_id}.gpx` | export GPX : route (points nommés) et trace pour les tronçons par les chemins |
| `POST /api/v0.1/events/{id}/routes/{route_id}/reports` | l'équipe signale un point impraticable (main courante, `route.report`) ; le PCO décide |

Le calcul des tronçons par les chemins (Valhalla) arrive avec la navigation niveau 2.

Vérification : `tests/test_routes.py`, `demo/verify_routes.py` (CI).
