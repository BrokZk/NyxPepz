# NyxPepz

Telegram Mini App — fondation fonctionnelle.

## Fonctions
- Authentification Telegram Mini Apps côté serveur
- Profil membre automatique
- Code de parrainage permanent unique à 5 caractères
- Points fidélité / parrainage et classement
- Catalogue NyxPepz
- Historique du poids + graphique
- Structure de suivi Mondial Relay via AfterShip
- Endpoint sécurisé pour créditer les commandes du bot

## Variables Render
`DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `AFTERSHIP_API_KEY`, `SECRET_KEY`, `ORDER_WEBHOOK_SECRET`.

Ne jamais placer les clés API ou le token Telegram dans le dépôt GitHub.

## Lancement local
`pip install -r requirements.txt`
puis `DEV_MODE=1 python app.py`

Avant production, vérifier la version courante de l'API AfterShip et renseigner `AFTERSHIP_BASE_URL` si nécessaire.
