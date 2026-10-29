# Affichage sur Smart TV : état et vue (v0.1)

## Vue envoyée par un téléphone

`PUT /api/v0.1/events/{event_id}/displays/{display_id}/view` `{"view": {...} | null}` (`null` = cadrage automatique, options par défaut). Clés gardées (les autres sont ignorées) :

- `lat`, `lon`, `zoom`, `basemap`, `tile_url` (https seulement), `attribution` ;
- `layers` : `operators`, `aprs`, `offline`, `drawings`, `bearings` (vrai par défaut), `highpoints`, `relays` (faux par défaut) ;
- `opacity` : `ops`, `draw`, `brg`, `ref`, de 0,1 à 1 (1 par défaut) ;
- `messages` : panneau des messages affiché (vrai par défaut ; le bandeau des messages immédiats reste).

Type invalide : 422 (`invalid_layers`, `invalid_opacity`, `invalid_messages`…).

## État lu par la TV

`GET /api/v0.1/tv/state[?fr=…&rr=…]` (en-tête `Authorization: Display <jeton>`) :

- `positions` filtrées selon `layers` (`offline` faux : opérateurs sans position depuis plus de 10 min masqués) ;
- `options` : `layers`, `opacity`, `messages` appliqués ;
- `weather` : `{"temp_c", "icon", "vigilance"}` de l'heure en cours (`icon` parmi `sun`, `sun_cloud`, `cloud`, `rain`, `storm`, `snow`, `fog`, `moon`, `moon_cloud` — lune la nuit, entre coucher et lever du soleil ; `vigilance` `null`, `yellow`, `orange`, `red`), tiré du cache météo de l'événement, recalculé au plus toutes les 10 min ; `null` sans point météo ;
- `drawings` (objets cartographiques hors relevés : `kind`, `points`, `radius_m`, `color`, `stroke_width`, `label`, `opacity`), `bearings` (`lat`, `lon`, `azimuth_deg`, `length_m`, `search`, `label`, `exercise`, `color` stable par recherche) et `references` (points hauts `HIGH_POINT`, relais `RELAY` : `name`, `callsign`, `lat`, `lon`) ;
- `features_rev`, `references_rev` : la TV les renvoie en `fr` / `rr` ; tant qu'ils n'ont pas changé, `drawings`, `bearings` et `references` ne sont pas renvoyés.

- `messages` : messages généraux seulement (la main courante n'est plus envoyée ni affichée, 29 octobre 2026) ;
- `alert` : bandeau rouge (`sender_id`, `body`, `created_at`) = dernier message immédiat général des 10 dernières minutes, sauf s'il a été retiré sur cet écran ou si c'est une détresse (« 🆘 … ») close par un message « Fin de détresse — <même expéditeur> » (ou « End of distress ») ; `null` sinon ;
- `sos` : expéditeurs dont la détresse n'est pas close (pastille « SOS » clignotante de l'en-tête, qui reste après retrait du bandeau).

## Retirer le bandeau SOS d'un écran

`POST /api/v0.1/events/{event_id}/displays/{display_id}/alert/clear` : les messages reçus jusque-là n'affichent plus le bandeau sur cet écran ; un nouveau message immédiat le rallume. Droits : la personne qui a appairé l'écran (e-mail vérifié par Cloudflare Access, champ `owner`) ou un administrateur (`admin`) ; sinon 403 `owner_or_admin_required`. Sans e-mail vérifié (réseau local sans Access) : permis. Ligne « Bandeau SOS retiré de l'écran » en main courante.

`GET /api/v0.1/events/{event_id}/displays` donne en plus `owner`, `alert` (bandeau affiché) et `can_clear_alert` (pour l'appelant).

Vérification : `tests/test_tv.py`, `demo/verify_map_features.py`.
