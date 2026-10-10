# Messages, ACK et main courante — v0.1

Les messages et ACK sont append-only et passent par le mécanisme Offline First.

## Message
Priorités initiales : routine, urgent, immediate. Les destinataires sont des identifiants d'utilisateurs/équipes. La V0.1 limite le texte à 2048 caractères côté protocole.

## ACK
États : received, read, accepted, rejected. Un ACK applicatif est distinct d'un acquittement de transport radio.

## Main courante
Le serveur produit une chronologie immuable des événements opérationnels significatifs. La V0.1 journalise au minimum les messages et ACK. Les positions ne sont pas inscrites une à une afin d'éviter le bruit.

## Temps réel
Événements WebSocket : message.created et ack.created.

## Photos et pièces jointes
Un message peut référencer jusqu'à 4 fichiers dans `attachments` : `file_id`, `name`, `mime_type`, `size_bytes`. Le message ne transporte pas les octets.

1. Le client choisit l'identifiant du fichier (UUID) et envoie la photo par `POST /events/{id}/files` avec les champs `file_id` et `mime_type`.
2. L'envoi est idempotent : un nouvel essai avec le même `file_id` et le même contenu renvoie le fichier existant (200) ; un contenu différent renvoie 409.
3. Le message est ensuite synchronisé normalement. Hors connexion, le client garde la photo et le message, et envoie la photo d'abord au retour du réseau.

Des pièces jointes mal formées font rejeter le message. La main courante indique le nombre de photos, par exemple « Véhicule repéré [1 photo] ». Les fichiers téléchargés portent `X-Content-Type-Options: nosniff`, car le client Web partage l'origine du serveur.
