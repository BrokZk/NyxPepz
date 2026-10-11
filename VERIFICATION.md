# Vérifications

Base : BrokZk/NyxPepz/main, commit e507a424437f1cba008befb337316ef4eb9ab6c5.

45 tests exécutés et réussis localement :

- 37 tests Flask/SQLAlchemy sur une copie complète des sources et une base
  SQLite temporaire : réservation, restauration, paiement tardif, dernière
  unité demandée par deux clients, modifications de stock idempotentes,
  suivi privé, commandes, alertes et parrainage 10 % / 5 %.
- 8 tests du bot et de personnalisation : droits Admin, stock à zéro,
  quantités limitées au disponible, anciennes confirmations refusées,
  bouton Mondial Relay et données copiables, catégories et persistance.

Les paiements et Telegram étaient simulés. Aucun paiement réel, appel
Telegram d'envoi, modification GitHub ou déploiement Render n'a été effectué.
Les fichiers Python sont contrôlés syntaxiquement et l'archive vérifiée.

Limites :
- Concurrence testée sur SQLite, pas sur PostgreSQL réel.
- Pas de test sur un téléphone réel.
- Le lien reste sur le domaine officiel Mondial Relay. Le numéro et le
  code postal sont également affichés et copiables. Le site a bloqué
  l'accès automatisé, donc son préremplissage n'est pas certifié.
- Aucune garantie d'ouverture de l'application native.
