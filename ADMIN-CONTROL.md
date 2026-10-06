# Dashboard et Protocoles Admin

## Comportement

L’Admin est organisé en Dashboard, Boutique, Commandes, Marketing, Communauté et Réglages. Les écrans existants restent accessibles : produits/stock, packs/composition, nouveautés, ventes, commandes/bordereaux, utilisateurs/points, cadeaux, concours et ambassadeurs. Les Réglages expliquent la configuration actuelle sans exposer ni modifier les secrets.

Le Dashboard appelle `/api/admin/dashboard?period=today|7d|30d|all`. Le CA brut provient exclusivement des commandes payées, expédiées, disponibles ou livrées, hors cadeaux. Les périodes suivent les dates de confirmation `ConfirmedOrderEvent` et le calendrier Europe/Paris. Les périodes 7/30 jours incluent le jour courant et les 6/29 jours précédents. Les anciennes commandes sans date de confirmation restent incluses dans Tout et sont signalées comme historique non vérifié ; elles sont exclues des périodes datées.

Frais et net restent `null` et sont affichés indisponibles : les preuves PayGate existantes enregistrent des montants crypto, sans règlement net vérifié en euros. Aucun taux de change ni frais supposés. La ventilation utilise la dernière révision du moyen de paiement enregistré ; à défaut une preuve PayGate indique Crypto, sinon le moyen reste non renseigné.

Les commandes sur la période et les nouveaux clients utilisent leur date de création. Les alertes représentent toujours l’état actuel : paiements `payment_review`, commandes payées/offertes sans préparation enregistrée, produits actifs avec stock <= 5, commandes expédiées/disponibles/livrées sans numéro de suivi. L’interface distingue ces périmètres.

Les Protocoles sont des fiches éditoriales informatives. Pas de génération de posologie personnalisée. Le formulaire gère titre, catégorie, description, contenu, étapes, photo, visibilité, ordre, modification et suppression. L’image utilise `uploadPhoto` et `/api/admin/upload` existants. Les textes sont rendus sans interprétation HTML.

## Migration et déploiement

- Ajout de la seule table `protocol` via le mécanisme `db.create_all()` existant. Aucun changement destructif des tables existantes.
- Import transactionnel des fiches `static/protocols.json` au premier démarrage, protégé par le marqueur unique `protocols-editorial-import-v1` dans `catalog_update`. Les redémarrages ne réimportent pas les fiches supprimées et ne réécrivent pas les modifications.
- Sources, références, notes et anciens blocs sont conservés. Lorsqu’un Admin enregistre des étapes éditoriales, elles remplacent les anciens blocs ; les sources restent accessibles.
- Commande idempotente disponible : `flask --app app protocols-migrate`. Le démarrage applique déjà l’import.
- Avant déploiement, utiliser la procédure habituelle de sauvegarde PostgreSQL. Le compte DB doit pouvoir créer la table et insérer le marqueur. Aucun nouveau secret ni dépendance d’exécution n’est nécessaire. Cloudinary conserve sa configuration actuelle.
- Brancher/déployer la branche après revue. Cette livraison ne fusionne pas main et ne déclenche aucune modification Render.
- Pour afficher un net vérifié ultérieurement, il faudra une source comptable des frais et règlements en EUR. Les données actuelles ne le permettent pas.
- La migration est testée sur SQLite et le DDL est compilé pour PostgreSQL. Son exécution sur une vraie base PostgreSQL et la vérification dans Telegram/iPhone restent à faire au déploiement.

## Fichiers

- `app.py` : installation des modules et import initial.
- `admin_dashboard.py` : métriques réelles, filtres, ventilation et indisponibilité explicite du net.
- `protocols.py` : modèle, migration et endpoints publics/Admin CRUD avec validation et contrôle d’accès.
- `static/admin-control.js` : six rubriques, Dashboard et formulaires Protocoles réutilisant les fonctions actuelles.
- `static/admin-control.css` : mise en page mobile/bureau et champs tactiles.
- `static/protocols.js` : consultation via l’API, contenus éditoriaux/images et rafraîchissement après modification.
- `templates/index.html` : chargement des deux nouveaux assets.
- `tests/test_admin_control.py` : 8 tests d’accès, CRUD, validation, ordre/visibilité, import atomique/idempotent, données financières, alertes et changements d’heure.
- `ADMIN-CONTROL.md` : comportement, déploiement et résultats de validation.

## Validation

- Les 8 nouveaux tests Python passent.
- Syntaxe des modules Python modifiés et de tous les fichiers JavaScript de `static/` vérifiée.
- Test JavaScript existant du calculateur réussi (mg/mcg, virgules, capacités et unités).
- Navigateur Edge : Dashboard/filtres en viewport 390 x 844, création/modification/masquage/suppression d’un protocole, consultation publique, texte contenant des balises traité comme texte, navigation existante et viewport bureau 1280 x 900. Aucune erreur JavaScript relevée.
- Suite Python existante : 8 tests réussis, 2 échecs reproduits sur le commit initial `1e248493b3c85f04ee2a8befb04045401485f7e3`. `test_admin_groups_and_cursor` attend uniquement une commande là où le filtre historique retourne plusieurs états existants ; `test_launcher_one_button_and_old_callback` attend un offset 3 mais obtient 0 avec un avertissement AttributeError du lanceur. Ces problèmes préexistants ne sont pas modifiés par cette livraison.
- Aucun secret Render modifié ; tests locaux avec base isolée et configuration fictive. Aucun paiement réel ni message Telegram envoyé.

## Mise à jour : cartes interactives

Toutes les cartes du Dashboard ouvrent maintenant un détail. Les commandes montrent le client, la référence, le montant, le statut et la date ; les clients montrent le nom, le compte Telegram, la date d'inscription et les points. Les liens ouvrent les fiches Admin existantes. Les stocks faibles ouvrent la liste des produits et permettent d'ouvrir leur éditeur de stock existant. Frais/net expliquent leur indisponibilité sans chiffres inventés.

Endpoint Admin supplémentaire : `/api/admin/dashboard/details?metric=gross|orders_today|orders_in_period|preparing|clients|clients_in_period|payment_review|low_stock|missing_tracking&period=today|7d|30d|all&page=1`. Pagination de 20 éléments, tri stable, aucune modification de données. Les filtres suivent exactement les compteurs : commandes du jour à Paris même si une autre période est sélectionnée, nouveaux clients selon la période, alertes selon l'état actuel. Les requêtes obsolètes ne remplacent pas une liste plus récente dans l'interface.

Cette mise à jour fournit 8 fichiers : `admin_dashboard.py`, `static/admin-control.js`, `static/admin-control.css`, `static/admin-orders.js`, `static/admin-users.js`, `templates/index.html`, `tests/test_admin_control.py`, `ADMIN-CONTROL.md`. Elle inclut la correction précédente du bouton À préparer. Aucun changement de migration, dépendance ou secret.

Validation supplémentaire : 11 tests du module Admin réussis, dont 3 nouveaux couvrant accès, pagination, concordance de chaque liste avec son compteur et filtres de dates. Syntaxe Python/JS vérifiée. La vérification navigateur de cette extension n'a pas pu être exécutée : le lancement d'Edge est bloqué par les permissions de l'environnement. Les parcours interactifs nouveaux restent à vérifier après déploiement ; la validation navigateur décrite plus haut concerne la livraison initiale.
