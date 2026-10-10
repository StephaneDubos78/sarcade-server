# Prévisions météo (V0.1)

Spécification : note « Prévisions météo » du vault (décisions du 10 octobre 2026).

## Sources
- **Météo-France en premier** : modèles AROME et ARPEGE, par le point d'accès Météo-France d'Open-Meteo (`/v1/meteofrance`, modèle `meteofrance_seamless`, 4 jours).
- **Open-Meteo en repli** (`/v1/forecast`), qui ajoute la probabilité de pluie et la visibilité.
- **Vigilance Météo-France** du département : API du portail Météo-France (Licence Ouverte 2.0), clé `SARCADE_METEOFRANCE_API_KEY`. Le décodage suit la structure connue de la carte de vigilance, **à confirmer avec une vraie clé**.
- Usage commercial d'Open-Meteo (SARCADE Pro) : abonnement, `SARCADE_OPEN_METEO_URL` (URL client) et `SARCADE_OPEN_METEO_API_KEY`.

## Fonctionnement
- Le serveur rafraîchit **toutes les heures** la prévision de chaque événement actif (`SARCADE_WEATHER=1`, par défaut) et la garde en cache : les clients la reçoivent sur le réseau local, sans Internet.
- Point de prévision : réglage `weather_lat`/`weather_lon` du PCO, sinon le centre des positions de l'événement. Département de vigilance : réglage `department`, sinon `SARCADE_DEPARTMENT`.
- Passage en **vigilance orange ou rouge** : inscription dans la main courante et diffusion `weather.alert`, une seule fois par aggravation.

## API
| Point d'accès | Rôle |
|---|---|
| `GET /api/v0.1/events/{id}/weather` | dernière prévision (même sans Internet), `stale` au-delà de 6 h, vigilance ; `?compact=true` pour la liaison faible (toutes les 3 h sur 12 h) |
| `POST /api/v0.1/events/{id}/weather/refresh` | rafraîchissement immédiat (409 sans point, 503 sans source) |
| `GET /api/v0.1/events/{id}/weather/bulletin` | bulletin en français à publier dans « Diffusion PCO » |
| `GET /api/v0.1/weather?lat=&lon=` | prévision d'un point désigné, en cache une heure sur une grille d'environ 5 km |

Le lever et le coucher du soleil sont fournis dans la prévision ; le client les calcule aussi sans réseau.

Vérification : `tests/test_weather.py`, `demo/verify_weather.py` (CI, avec `demo/weather_stub.py` à la place d'Open-Meteo et de la vigilance).
