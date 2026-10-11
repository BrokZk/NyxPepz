# NyxPepz — stocks des cosmétiques et suivi Mondial Relay

## Fonctionnement du stock

Dans NyxPepzShopBot : /start → Admin → Gérer les stocks.
Sélectionnez un produit, envoyez le nombre disponible, puis confirmez.
Le même accès est présent dans la fiche Admin de chaque produit.

Un stock de 0 affiche RUPTURE DE STOCK. Le produit reste dans sa catégorie
et sa fiche peut être consultée ; il ne peut plus être ajouté au panier.
Un nouveau produit démarre à 0 jusqu'à votre première saisie du stock.
Les stocks sont enregistrés dans la base PostgreSQL commune, jamais
remplacés par la synchronisation du catalogue du bot.

Ajouter au panier ne réserve rien. Les unités sont retirées du stock
disponible quand le client enregistre sa commande dans le formulaire de
coordonnées. Elles restent réservées pendant le paiement.
Une annulation ou expiration d'une commande en attente remet les unités
en stock une seule fois. Un paiement validé ne retire pas une deuxième fois
les mêmes unités.

Si un paiement arrive après expiration, la validation tente de réserver à
nouveau les unités. Si elles ne sont plus disponibles, l'admin affiche un
message de stock insuffisant ; les points ne sont pas crédités et le
paiement doit être traité manuellement.
Un paiement reçu à vérifier garde sa réservation jusqu'à son traitement.
Les remboursements et retours physiques ne sont pas automatisés par ce patch.

Le nombre saisi correspond à la quantité DISPONIBLE À LA VENTE, hors
commandes déjà réservées. Exemple : 3 disponibles et 2 réservés ; si vous
fixez le disponible à 4 puis annulez la réservation de 2, le disponible
devient 6. Pour réapprovisionner, ajoutez les nouvelles unités au disponible
affiché et saisissez le nouveau disponible.
Limites conservées : 99 unités d'un même produit par panier, 40 produits.
Le stock disponible peut aller de 0 à 1 000 000.

## Initialisation des anciens produits

Les anciens produits démarrent eux aussi à 0 : aucune quantité fictive
n'est inventée. Avant de rouvrir les commandes, renseignez vos stocks.
Déduisez de votre comptage les unités destinées aux commandes déjà
enregistrées avant cette installation, y compris celles en attente que
vous souhaitez honorer.

Les anciennes commandes n'ont jamais été retirées de ce nouveau compteur :
leur annulation ne rajoute donc pas artificiellement des unités.
Les réservations automatiques concernent les commandes créées après ce patch.
Ne supprimez pas le disque du bot ou les bases existantes.

## Mondial Relay

Dans NyxPepzShopBot : Mon profil → Mondial Relay.
Le bot affiche les commandes du compte connecté pour lesquelles un numéro
de suivi a été renseigné dans l'administration de la Mini App NyxBot.
Le numéro et le code postal proviennent de la même commande, dans la base
commune. Un utilisateur ne voit pas les suivis d'un autre utilisateur.

Saisissez le NUMÉRO D'EXPÉDITION de Mondial Relay dans le champ de suivi
de la commande dans NyxBot, puis enregistrez l'envoi. Ce n'est pas le nom
du PDF du bordereau, ni une référence interne différente.
Le numéro apparaît ensuite dans le bot à la prochaine ouverture du suivi.

Le bouton ouvre le site officiel Mondial Relay. Les messages d'expédition
envoyés par le bot des cosmétiques disposent aussi d'un bouton Mondial Relay.
Le lien contient le numéro et le code postal lorsque leur format convient.
Le site peut demander de les saisir : le bot offre des boutons Copier le
suivi et Copier le code postal. Le préremplissage du site n'a pas pu être
confirmé, car le site bloque l'accès automatisé.
L'ouverture de l'application native dépend du téléphone et des associations
de liens ; ce paquet ne la garantit pas.
Avec votre compte particulier, aucune clé API ou référence enseigne n'est
nécessaire. Ce patch ne consulte pas automatiquement les étapes du transporteur :
le site officiel fournit le suivi, et les statuts enregistrés dans NyxBot
restent ceux que vous y renseignez.

## Fichiers à uploader

Le dossier upload représente la racine de BrokZk/NyxPepz :

```text
upload/
├── cosmetic_inventory.py             AJOUTER à la racine
├── mondial_tracking.py               AJOUTER à la racine
├── cosmetics_checkout.py             REMPLACER à la racine
├── shop.py                           REMPLACER à la racine
├── shop_delivery.py                  REMPLACER à la racine
├── catalog_bot/
│   └── bot.py                       REMPLACER catalog_bot/bot.py
└── tests/
    ├── test_cosmetics_checkout.py    REMPLACER
    ├── test_bot_personnalisation.py  REMPLACER
    ├── test_cosmetic_stock.py        AJOUTER
    └── test_stock_bot.py             AJOUTER
```

Ne créez pas de dossier upload sur GitHub.
Gardez app.py, referral_rewards.py, shop_packs.py, catalog.json, les fichiers
HTML et les autres tests en place. Les boutons personnalisés, les catégories,
les points 10 % / 5 % et le retrait des anciens blocs d'accueil sont conservés.
Le diff et les documents du ZIP sont à conserver sur votre PC.
Si les fichiers ont changé depuis le commit indiqué dans VERIFICATION.md,
comparez le diff avant de remplacer les versions récentes.

## Installation GitHub et Render

1. Sauvegardez la base et le disque du bot avant mise à jour.
2. Préparez une branche GitHub depuis main, par exemple stock-et-suivi.
3. Envoyez le contenu de upload aux dix chemins indiqués et vérifiez le diff.
4. Avant fusion, sur Render nyxpepz, mettez COSMETICS_CHECKOUT_ENABLED à 0
   et appliquez ce réglage. Cela ferme les nouvelles commandes le temps
   de mettre tous les services à la même version.
5. Fusionnez la branche dans main.
6. Déployez nyxpepz, puis nyxpepz-notifications et nyxpepzshopbot. Attendez
   Live sur les trois services avant de rouvrir les commandes.
   Si les déploiements partent automatiquement, vérifiez qu'ils utilisent
   le même dernier commit.
7. Aucune nouvelle variable Render ou dépendance n'est nécessaire. Gardez
   le token du bot boutique sur nyxpepz-notifications, comme précédemment.
8. Depuis le compte 8843973247, /start → Admin → Gérer les stocks :
   renseignez le disponible de chaque produit.
9. Lancez les tests ci-dessous. Puis remettez COSMETICS_CHECKOUT_ENABLED à 1
   sur nyxpepz avec Save and deploy pour rouvrir les commandes.

Le démarrage crée trois tables supplémentaires (stock, réservations,
modifications idempotentes) ; aucune ancienne table n'est supprimée.

## Tests dans Render → nyxpepz → Shell

```bash
PYTHONPATH=tests python -m unittest test_cosmetic_stock.StockTrackingTests -v
```

Puis :

```bash
PYTHONPATH=tests python -m unittest test_stock_bot.StockBotTests test_bot_personnalisation.PersonnalisationTests -v
```

Enfin :

```bash
PYTHONPATH=tests python -m unittest test_cosmetic_alerts.AdminAlertTests test_referral_percentage.ReferralPercentageTests -v
```

Ces tests utilisent des bases temporaires et des paiements simulés, sans
modifier les commandes ou points de production.

## Vérification dans Telegram

- Stock initial 2 : ajoutez deux unités. Le bot ne doit pas permettre
  d'ajouter une troisième.
- Enregistrez la commande sans payer : le disponible doit devenir 0.
- Depuis un autre compte, le produit affiche RUPTURE DE STOCK.
- Annulez la commande en attente dans Mes commandes de la Mini App :
  le disponible doit revenir à 2.
- Sur une commande déjà payée, renseignez le numéro d'expédition dans
  l'admin de NyxBot. Dans le profil du client sur NyxPepzShopBot, ouvrez
  Mondial Relay et vérifiez le numéro, le code postal et le lien.

## Précautions pour une marche arrière

Ne remettez pas un ancien worker ou shop.py qui ignorerait les réservations
après création de commandes avec stock : leur expiration ne restituerait
plus les unités correctement. Fermez d'abord les nouvelles commandes et
conservez les helpers de réservation/restauration pour les commandes existantes.
Ne restaurez pas une ancienne base par-dessus des commandes payées.

Sources officielles :
https://www.mondialrelay.fr/faq/recevoir-un-colis/comment-suivre-l-acheminement-de-mon-colis/
https://www.mondialrelay.fr/suivi-de-colis/
