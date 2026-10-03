# NyxPepz — Admin CA réel

Base : dépôt BrokZk/NyxPepz, révision 4218297, récupérée le 3 octobre 2026.
Remplacer app.py, shop.py, templates/index.html et static/admin-sales.js aux mêmes
emplacements. Ajouter real_sales.py et tests/test_real_sales.py. Conserver tous les
autres fichiers, notamment la clé publique paygate_callback_public.pem existante.

## Render
Conserver DATABASE_URL, SECRET_KEY, ADMIN_TELEGRAM_IDS, SHOP_ENABLED=1,
PAYGATE_ENABLED=1, PAYGATE_WALLET et SHOP_PUBLIC_URL (URL publique HTTPS exacte,
sans chemin ni paramètres). Aucune nouvelle variable ni clé API PayGate nécessaire.
Conserver les autres variables déjà utilisées par l'application. Aucun secret inclus.

Sauvegarder la base avant déploiement. Au démarrage, migration additive : création
de payment_record, payment_receipt et payment_accounting_audit, sans altérer les
tables existantes. Création PostgreSQL protégée par verrou transactionnel entre
workers. Les erreurs de migration arrêtent le démarrage au lieu d'être masquées.

## Comportement
Admin > Mes ventes : CA brut, frais connus, net vérifié, couverture des montants,
Crypto / autres / non renseigné, prestataires traçables et commandes paginées.
Autres moyens renseignés hors PayGate : brut = net, frais = 0 automatiquement,
selon votre règle, sans justificatif ni confirmation supplémentaire. Cela reste
une règle de gestion, pas une vérification bancaire indépendante.
Les corrections de moyen de paiement sont prises en compte et journalisées.
Cadeaux et commandes non payées exclus ; périodes selon validation, heure de Paris.

PayGate : signature RSA/SHA-256 sur l'URL publique constante + query brute,
clé v1 locale, nonce et adresse liés à la commande, unicité de txid_in et transaction
atomique. Les callbacks restent en vérification manuelle du montant EUR avant
confirmation comme dans le dépôt actuel ; stock, fidélité et notifications conservés.
Chaque callback signé conserve les montants réels, parts des wallets et transactions.
Les champs crypto de PaymentRecord décrivent le dernier callback ; PaymentReceipt
conserve tous les callbacks, notamment lors de règlements multiples.

Limite officielle : ni callback ni payment-status ne donnent un net EUR ou le taux
EUR de règlement. Le net PayGate en euros et les frais en euros restent donc NULL,
jamais estimés depuis USDC, un ratio ou un taux actuel. Les règlements crypto et la
différence entre crypto reçue et part réellement transférée au marchand sont
consultables par commande. Cette différence n'est pas présentée comme des frais EUR.
Le prestataire PayGate est traçable ; son sous-prestataire et le moyen réellement
choisi dans le checkout multi-provider ne sont pas divulgués par ces callbacks.
La ventilation des moyens suit les informations Admin actuelles, y compris
l'inférence crypto déjà présente pour les anciennes preuves PayGate.
Les anciens montants sans net vérifiable affichent « Net historique indisponible ».

## Backfill facultatif (Render Shell)
`flask --app app payments-backfill` : crée les lignes comptables des commandes
payées historiques sans modifier leur statut, stock, fidélité ou date de validation.
`flask --app app payments-backfill --recover-status` : lecture ponctuelle du statut
officiel uniquement pour les commandes ayant déjà un ipn_token exploitable.
Conserve coin/value_coin/txid_out retournés ; aucun net historique n'est inventé.
Ne pas programmer cette récupération en boucle : endpoint prévu pour usage ponctuel.

## Vérifications
7 nouveaux tests réussis : montants inconnus, brut=net automatique, corrections,
callbacks et doublons, vraie signature RSA et altération de query, migration SQLite
répétée sans perte et backfill par token. Syntaxes Python/JavaScript vérifiées ;
test calculateur JavaScript réussi. Suite existante : 8/10 réussis, les mêmes deux
échecs reproduits sur le dépôt original (groupes Admin et mock du bot Telegram).
Pas de nouveau défaut détecté par ces contrôles. Migration PostgreSQL et application
sur Render non exécutées ici ; aucune promesse de vérification en production.

Documentation officielle consultée :
https://paygate.to/docs/payment-gateway-api/index.html
