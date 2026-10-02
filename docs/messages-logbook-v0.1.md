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
