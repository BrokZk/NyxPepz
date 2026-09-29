# Mise à jour NyxPepz

## Changements prêts

- Les deux packs existants sont reliés à leur composition : Retatrutide 10 mg + GHK-Cu 50 mg, et Retatrutide 15 mg + Cagrilintide 10 mg. Les prix restent ceux enregistrés dans l’administration (110 € et 200 € dans les offres initiales).
- L’accueil ouvre le pack correspondant dans « Packs & promos ». Le panier facture le prix du pack ; le stock est réservé sur chaque produit inclus, en tenant compte des produits achetés séparément. Une annulation ou expiration restitue ces quantités.
- Les commandes administrateur sont séparées en « À traiter », « En livraison » et « Historique », avec chargement par pages de 50. Aucune commande n’est supprimée. Les clients conservent leur suivi, et Sheets continue de recevoir les mises à jour.
- Le calculateur convertit les quantités saisies (mg/mcg, mL et échelles U-100/U-50/U-40). Il ne propose pas de protocole ou de dose. Il demande le volume final, distingue échelle et capacité, et bloque les valeurs incohérentes.
- « Encyclopédie peptides » propose recherche, catégories et lecture avec agrandissement des 21 fiches originales reçues. Les doublons exacts d’ipamorelin et de cagrilintide n’apparaissent qu’une fois. Les images sont conservées sans modification et leur contenu n’est pas présenté comme médicalement validé.
- Le worker peut remplacer l’ancien bot par un menu unique « 🌙 Ouvrir NyxPepz », en conservant les notifications de commandes. Les anciens boutons ne déclenchent plus les anciennes opérations lorsqu’ils sont reçus par ce nouveau gestionnaire.

## Mise en ligne

Les fichiers de ce dossier sont une mise à jour du dépôt existant : conserver les images et les autres fichiers déjà présents. Ne pas remplacer le dépôt entier par ce dossier.

1. Déployer le nouveau code du worker `nyxpepz-notifications`, puis le service web `nyxpepz`. Le worker doit connaître les lignes de commande des packs avant que les clients commencent à en commander.
2. Pour le bouton Telegram unique : arrêter le programme de l’ancien bot, puis ajouter **sur le worker uniquement** `TELEGRAM_LAUNCHER_ENABLED=1` et `SHOP_PUBLIC_URL=https://nyxpepz.onrender.com`.
3. Conserver `TELEGRAM_BOT_TOKEN` et toutes les variables existantes. La commande du worker reste `flask --app app shop-dispatch --loop`. Aucun troisième service payant n’est nécessaire.
4. Envoyer `/start` au bot : le nouveau message contient uniquement « 🌙 Ouvrir NyxPepz ». Les anciens messages Telegram restent dans l’historique ; un clic sur un ancien bouton remplace son clavier par le bouton unique.

Le gestionnaire Telegram est désactivé tant que la variable vaut autre chose que `1`. Ne pas l’activer en même temps qu’un autre programme reçoit les messages du même bot. En présence d’un webhook existant, le nouveau gestionnaire ne le supprime pas et signale le conflit dans les logs.

Ne pas relancer l’import initial des stocks. Les tables supplémentaires se créent au démarrage. Les compositions initiales ne sont configurées qu’une seule fois, et uniquement si les titres et sous-titres des offres initiales sont encore inchangés. Une offre personnalisée doit être configurée via le bouton « Composition » de l’administration.

## Documents de l’encyclopédie

Les fichiers reçus sont placés dans `static/encyclopedia/`, puis référencés dans `static/encyclopedia.json`. Inclure ce dossier d’images dans la mise en ligne. La lecture accepte des documents PDF ou images, ainsi que des sections textuelles, sans exécuter le contenu des fiches. Les originaux ne sont chargés qu’à l’ouverture de la fiche : la liste n’oblige pas à télécharger les 21 images. Aucun texte médical ou protocole n’a été ajouté aux documents.

## Validation

Tests locaux : commande, prix, stocks partagés, annulation, paiement tardif, fidélité, parrainage, filtrage des commandes, menu Telegram simulé, conversions et affichage sur cinq largeurs mobiles. Les notifications Telegram, paiements et données de production ne sont pas utilisés pour ces tests. Les transactions ont été vérifiées sur SQLite ; la vérification après déploiement sur PostgreSQL reste nécessaire.

Références du calculateur : [unités SI — NIST](https://www.nist.gov/pml/owm/metric-si-prefixes), [erreurs de conversion et de seringue — FDA](https://www.fda.gov/drugs/human-drug-compounding/fda-alerts-health-care-providers-compounders-and-patients-dosing-errors-associated-compounded).

Tests reproductibles depuis le dépôt, après installation des dépendances : `python -m unittest discover -s tests -p test_app_updates.py` et `node tests/test_calculator.cjs`. Les tests Python utilisent une base temporaire et des appels Telegram simulés.
