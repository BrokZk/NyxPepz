"""Catalogue informatif autonome. Python 3.10+, bibliothèque standard uniquement."""
import json
import os
import time
import sqlite3
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

NOTICE = "Catalogue informatif uniquement. Aucune commande, aucun paiement."


class ApiError(Exception):
    def __init__(self, code, retry_after=0):
        self.code = code
        self.retry_after = retry_after


def load_catalog():
    data = json.loads(Path(__file__).with_name("catalog.json").read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) > 40:
        raise ValueError("Le catalogue doit contenir au maximum 40 fiches.")
    for item in data:
        if not isinstance(item, dict) or set(item) != {"title", "description"}:
            raise ValueError("Chaque fiche contient uniquement title et description.")
        for key, limit in (("title", 50), ("description", 3000)):
            if not isinstance(item[key], str) or not 0 < len(item[key]) <= limit:
                raise ValueError("Texte de fiche invalide.")
    return data


def button(label, action):
    return {"text": label, "callback_data": action}


def menu(catalog):
    return {"inline_keyboard": [
        [button("🛍 Voir les produits", "catalog")],
        [button("👤 Mon profil", "profile"), button("🛒 Mon panier", "basket")],
    ]}


class SelectionStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS selections (user_id INTEGER, title TEXT, PRIMARY KEY(user_id, title))")

    def titles(self, user_id):
        return {row[0] for row in self.db.execute("SELECT title FROM selections WHERE user_id = ?", (user_id,))}

    def add(self, user_id, title):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO selections VALUES (?, ?)", (user_id, title))

    def clear(self, user_id):
        with self.db:
            self.db.execute("DELETE FROM selections WHERE user_id = ?", (user_id,))


def screen(action, catalog, user, store):
    user_id = user["id"]
    selected = store.titles(user_id)
    back = [button("‹ Retour", "menu")]
    if action == "menu":
        return "🌙 Bienvenue chez NyxPepz !\n\nRetrouvez ici notre catalogue et découvrez les fiches de nos produits.\n\n🛍 Voir les produits\n👤 Consulter mon profil\n🛒 Mon Panier", menu(catalog)
    if action == "catalog":
        rows = [[button(item["title"], f"info:{i}")] for i, item in enumerate(catalog)]
        return "🛍 Voir les produits\n\nChoisissez une fiche informative.", {"inline_keyboard": rows + [back]}
    if action == "profile":
        name = str(user.get("first_name") or "Membre")[:100]
        username = user.get("username")
        text = "👤 Mon profil\n\nBonjour " + name + " !"
        if username:
            text += "\nPseudo : @" + str(username)[:64]
        count = sum(item["title"] in selected for item in catalog)
        text += f"\nFiches enregistrées : {count}\n\nCe profil utilise votre compte Telegram.\n" + NOTICE
        return text, {"inline_keyboard": [[button("🛒 Mon panier", "basket")], back]}
    if action == "clear":
        store.clear(user_id)
        selected = set()
        action = "basket"
    if action == "basket":
        rows = [[button(item["title"], f"info:{i}")] for i, item in enumerate(catalog) if item["title"] in selected]
        text = "🛒 Mon panier\n\n" + (f"{len(rows)} fiche(s) enregistrée(s)." if rows else "Votre panier documentaire est vide.")
        text += "\n\nSélection de fiches uniquement, sans commande ni paiement."
        if rows:
            rows.append([button("🗑 Vider mon panier", "clear")])
        return text, {"inline_keyboard": rows + [[button("🛍 Voir les produits", "catalog")], back]}
    if action.startswith(("info:", "save:")):
        prefix, _, number = action.partition(":")
        if not number.isdigit() or int(number) >= len(catalog):
            return None
        index = int(number)
        item = catalog[index]
        if prefix == "save":
            store.add(user_id, item["title"])
            selected.add(item["title"])
        text = item["title"] + "\n\n" + item["description"] + "\n\n" + NOTICE
        rows = []
        if item["title"] not in selected:
            rows.append([button("📌 Conserver dans mon panier", f"save:{index}")])
        else:
            text += "\n\n✓ Fiche conservée dans votre panier documentaire."
        rows += [[button("🛒 Mon panier", "basket")], [button("‹ Catalogue", "catalog")]]
        return text, {"inline_keyboard": rows}
    return None


def handle(update, catalog, api, store):
    query = update.get("callback_query")
    message = (query.get("message") if query else update.get("message")) or {}
    chat = message.get("chat") or {}
    if query:
        api("answerCallbackQuery", {"callback_query_id": query["id"]})
    if chat.get("type") != "private":
        return
    user = (query.get("from") if query else message.get("from")) or {}
    if user.get("id") != chat.get("id"):
        return
    if not query and not isinstance(message.get("text"), str):
        return
    action = query.get("data", "") if query else "menu"
    result = screen(action, catalog, user, store)
    if result is None:
        return
    text, keyboard = result
    payload = {"chat_id": chat["id"], "text": text, "reply_markup": keyboard}
    if query:
        payload["message_id"] = message["message_id"]
        api("editMessageText", payload)
    else:
        api("sendMessage", payload)


def make_api(token):
    def api(method, payload):
        request = Request(
            "https://api.telegram.org/bot" + token + "/" + method,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=45) as response:
                result = json.load(response)
        except HTTPError as error:
            try:
                data = json.load(error)
                delay = data.get("parameters", {}).get("retry_after", 0)
            except (ValueError, OSError):
                delay = 0
            raise ApiError(error.code, delay) from None
        except (URLError, TimeoutError, OSError):
            raise ApiError(0) from None
        if not result.get("ok"):
            raise ApiError(result.get("error_code", 0),
                           result.get("parameters", {}).get("retry_after", 0))
        return result["result"]
    return api


def main():
    token = os.environ.get("NYXPEPZ_CATALOG_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Définissez NYXPEPZ_CATALOG_BOT_TOKEN dans votre environnement.")
    catalog = load_catalog()
    api = make_api(token)
    try:
        if api("getMe", {}).get("username", "").lower() != "nyxpepzshopbot":
            raise SystemExit("Le token doit appartenir à @NyxPepzShopBot.")
        if api("getWebhookInfo", {}).get("url"):
            raise SystemExit("Un webhook est actif. Arrêtez l'ancien service avant configuration.")
    except ApiError as error:
        raise SystemExit(f"Vérification Telegram impossible (code {error.code}).") from None
    store = SelectionStore(os.environ.get("NYXPEPZ_CATALOG_STATE_PATH") or str(Path(__file__).with_name("catalog-state.sqlite3")))
    offset = 0
    print("Catalogue informatif démarré. Ctrl+C pour arrêter.")
    while True:
        try:
            updates = api("getUpdates", {
                "offset": offset, "timeout": 30,
                "allowed_updates": ["message", "callback_query"],
            })
            for update in updates:
                try:
                    handle(update, catalog, api, store)
                except ApiError as error:
                    if error.code not in (400, 403):
                        raise
                    print(f"Message ignoré (code {error.code}).")
                offset = update["update_id"] + 1
        except ApiError as error:
            if error.code in (401, 404, 409):
                raise SystemExit(f"Bot arrêté (code {error.code}) : vérifiez le token et les autres instances.") from None
            print(f"Connexion temporairement indisponible (code {error.code}).")
            time.sleep(max(3, error.retry_after))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Catalogue arrêté.")

