"""Catalogue informatif autonome. Python 3.10+, bibliothèque standard uniquement."""
import json
import os
import time
import sqlite3
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CATEGORIES = ("Perte de poids", "Anti-Age/Peau/Cheveux", "Nootropique", "Récupération/Régénération")

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
        if not isinstance(item, dict) or not {"title", "description"}.issubset(item) or set(item) - {"title", "description", "category"}:
            raise ValueError("Chaque fiche contient title, description et éventuellement category.")
        if "category" in item and item["category"] not in CATEGORIES:
            raise ValueError("Catégorie inconnue.")
        for key, limit in (("title", 50), ("description", 3000)):
            if not isinstance(item[key], str) or not 0 < len(item[key]) <= limit:
                raise ValueError("Texte de fiche invalide.")
    return data


def button(label, action):
    return {"text": label, "callback_data": action}


def menu(catalog):
    return {"inline_keyboard": [
        [button("🛍 Boutique", "catalog")],
        [button("👤 Mon profil", "profile"), button("🛒 Mon panier", "basket")],
    ]}


class SelectionStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        setup_products(self)
        self.db.execute("CREATE TABLE IF NOT EXISTS selections (user_id INTEGER, title TEXT, PRIMARY KEY(user_id, title))")

    def titles(self, user_id):
        return {row[0] for row in self.db.execute("SELECT title FROM selections WHERE user_id = ?", (user_id,))}

    def add(self, user_id, title):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO selections VALUES (?, ?)", (user_id, title))

    def clear(self, user_id):
        with self.db:
            self.db.execute("DELETE FROM selections WHERE user_id = ?", (user_id,))


import json
import re
from decimal import Decimal

ADMIN_ID = 8843973247


def setup_products(store):
    store.db.execute("CREATE TABLE IF NOT EXISTS cosmetic_products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, cents INTEGER NOT NULL, category TEXT NOT NULL)")
    store.db.execute("CREATE TABLE IF NOT EXISTS admin_drafts (user_id INTEGER PRIMARY KEY, content TEXT NOT NULL)")
    store.db.commit()


def products(store):
    return store.db.execute("SELECT id,name,cents,category FROM cosmetic_products ORDER BY id").fetchall()


def money(cents):
    return f"{cents // 100},{cents % 100:02d} €"


def draft(store, value=None):
    if value is None:
        row = store.db.execute("SELECT content FROM admin_drafts WHERE user_id=?", (ADMIN_ID,)).fetchone()
        return json.loads(row[0]) if row else {}
    with store.db:
        store.db.execute("INSERT OR REPLACE INTO admin_drafts VALUES (?,?)", (ADMIN_ID, json.dumps(value)))


def admin_screen(action, user, store):
    if user["id"] != ADMIN_ID:
        return "Accès réservé à l'administrateur.", {"inline_keyboard": [[button("‹ Retour", "menu")]]}
    cancel = {"inline_keyboard": [[button("Annuler", "admin")]]}
    if action == "admin":
        draft(store, {})
        return "⚙️ Admin — catalogue de cosmétiques", {"inline_keyboard": [
            [button("＋ Ajouter un produit", "admin:new")],
            [button("Modifier / supprimer", "admin:list")],
            [button("‹ Retour", "menu")],
        ]}
    if action == "admin:new" or action.startswith("admin:edit:"):
        value = {"step": "name"}
        if action.startswith("admin:edit:"):
            number = action.rsplit(":", 1)[1]
            if not number.isdigit() or not any(p[0] == int(number) for p in products(store)):
                return "Produit introuvable.", cancel
            value["id"] = int(number)
        draft(store, value)
        return "1/3 — Envoie le nom du produit cosmétique (80 caractères maximum).", cancel
    if action == "admin:list":
        rows = [[button(f"{p[1]} · {money(p[2])}", f"admin:product:{p[0]}")] for p in products(store)]
        return "Choisis un produit." if rows else "Aucun produit ajouté.", {"inline_keyboard": rows + [[button("‹ Admin", "admin")]]}
    if action.startswith(("admin:product:", "admin:delete:", "admin:remove:")):
        number = action.rsplit(":", 1)[1]
        item = next((p for p in products(store) if number.isdigit() and p[0] == int(number)), None)
        if not item:
            return "Produit introuvable.", cancel
        if action.startswith("admin:remove:"):
            with store.db:
                store.db.execute("DELETE FROM cosmetic_products WHERE id=?", (item[0],))
                store.db.execute("DELETE FROM selections WHERE title=?", (f"cosmetic:{item[0]}",))
            return "Produit supprimé.", {"inline_keyboard": [[button("‹ Admin", "admin")]]}
        if action.startswith("admin:delete:"):
            return "Supprimer " + item[1] + " ?", {"inline_keyboard": [[button("Confirmer la suppression", f"admin:remove:{item[0]}")], [button("Annuler", "admin:list")]]}
        return f"{item[1]}\n{money(item[2])}\n{item[3]}", {"inline_keyboard": [
            [button("Modifier", f"admin:edit:{item[0]}"), button("Supprimer", f"admin:delete:{item[0]}")],
            [button("‹ Admin", "admin")],
        ]}
    value = draft(store)
    if action.startswith("admin:category:") and value.get("step") == "category":
        number = action.rsplit(":", 1)[1]
        if not number.isdigit() or int(number) >= len(CATEGORIES):
            return None
        value.update(category=CATEGORIES[int(number)], step="confirm")
        draft(store, value)
        return f"Confirmer ce produit ?\n\n{value['name']}\n{money(value['cents'])}\n{value['category']}", {"inline_keyboard": [[button("✓ Enregistrer", "admin:confirm")], [button("Annuler", "admin")]]}
    if action == "admin:confirm" and value.get("step") == "confirm":
        with store.db:
            if "id" in value:
                store.db.execute("UPDATE cosmetic_products SET name=?,cents=?,category=? WHERE id=?", (value["name"],value["cents"],value["category"],value["id"]))
            else:
                if len(products(store)) >= 40:
                    return "Limite de 40 produits atteinte.", cancel
                store.db.execute("INSERT INTO cosmetic_products (name,cents,category) VALUES (?,?,?)", (value["name"],value["cents"],value["category"]))
            store.db.execute("DELETE FROM admin_drafts WHERE user_id=?", (ADMIN_ID,))
        return "✓ Produit enregistré dans la boutique.", {"inline_keyboard": [[button("＋ Ajouter un produit", "admin:new")], [button("🛍 Boutique", "catalog")], [button("‹ Admin", "admin")]]}
    return "Cette étape a expiré. Recommence depuis Admin.", cancel


def admin_text(text, user, store):
    if user["id"] != ADMIN_ID:
        return None
    if text.startswith("/"):
        draft(store, {})
        return None
    value = draft(store)
    cancel = {"inline_keyboard": [[button("Annuler", "admin")]]}
    if value.get("step") == "name":
        name = text.strip()
        if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
            return "Envoie un nom sur une ligne, de 1 à 80 caractères.", cancel
        value.update(name=name, step="price")
        draft(store, value)
        return "2/3 — Envoie le prix en euros : par exemple 10 ou 10,50.", cancel
    if value.get("step") == "price":
        price = text.strip().replace(",", ".")
        if not re.fullmatch(r"\d{1,6}(?:\.\d{1,2})?", price):
            return "Prix invalide. Envoie uniquement un nombre, par exemple 10,50.", cancel
        cents = int(Decimal(price) * 100)
        if not 1 <= cents <= 99999999:
            return "Le prix doit être compris entre 0,01 et 999 999,99 euros.", cancel
        value.update(cents=cents, step="category")
        draft(store, value)
        return "3/3 — Choisis la catégorie.", {"inline_keyboard": [
            [button(CATEGORIES[0], "admin:category:0"), button(CATEGORIES[1], "admin:category:1")],
            [button(CATEGORIES[2], "admin:category:2"), button(CATEGORIES[3], "admin:category:3")],
            [button("Annuler", "admin")],
        ]}
    if value:
        return "Utilise les boutons pour terminer ou annuler.", cancel
    return None


def cosmetic_screen(action, user, store):
    number = action.rsplit(":", 1)[-1]
    item = next((p for p in products(store) if number.isdigit() and p[0] == int(number)), None)
    if not item:
        return "Ce produit n'est plus disponible dans le catalogue.", {"inline_keyboard": [[button("‹ Boutique", "catalog")]]}
    key = f"cosmetic:{item[0]}"
    if action.startswith("cosave:"):
        store.add(user["id"], key)
    selected = key in store.titles(user["id"])
    text = f"{item[1]}\n\nPrix : {money(item[2])}\nCatégorie : {item[3]}"
    rows = [] if selected else [[button("📌 Conserver dans mon panier", f"cosave:{item[0]}")]]
    if selected:
        text += "\n\n✓ Produit conservé dans votre sélection."
    rows += [[button("🛒 Mon panier", "basket")], [button("‹ Boutique", "catalog")]]
    return text, {"inline_keyboard": rows}


def screen(action, catalog, user, store):
    if action.startswith("admin"):
        return admin_screen(action, user, store)
    if action.startswith(("cosmetic:", "cosave:")):
        return cosmetic_screen(action, user, store)
    user_id = user["id"]
    selected = store.titles(user_id)
    back = [button("‹ Retour", "menu")]
    if action == "menu":
        keyboard = menu(catalog)
        if user_id == ADMIN_ID:
            keyboard["inline_keyboard"].append([button("⚙️ Admin", "admin")])
        return "🌙 Bienvenue chez NyxPepz !\n\nRetrouvez ici notre catalogue et découvrez les fiches de nos produits.\n\n🛍 Boutique\n👤 Consulter mon profil\n🛒 Mon Panier", keyboard
    if action == "catalog":
        rows = [
            [button(CATEGORIES[0], "category:0"), button(CATEGORIES[1], "category:1")],
            [button(CATEGORIES[2], "category:2"), button(CATEGORIES[3], "category:3")],
        ]
        return "🛍 Boutique\n\nChoisissez une catégorie.", {"inline_keyboard": rows + [back]}
    if action.startswith("category:"):
        number = action.partition(":")[2]
        if not number.isdigit() or int(number) >= len(CATEGORIES):
            return None
        category = CATEGORIES[int(number)]
        rows = [[button(item["title"], f"info:{i}")] for i, item in enumerate(catalog) if item.get("category") == category]
        rows += [[button(f"{p[1]} · {money(p[2])}", f"cosmetic:{p[0]}")] for p in products(store) if p[3] == category]
        text = category + "\n\n" + ("Choisissez un produit ou une fiche." if rows else "Aucune fiche disponible dans cette catégorie pour le moment.")
        return text, {"inline_keyboard": rows + [[button("‹ Boutique", "catalog")]]}
    if action == "profile":
        name = str(user.get("first_name") or "Membre")[:100]
        username = user.get("username")
        text = "👤 Mon profil\n\nBonjour " + name + " !"
        if username:
            text += "\nPseudo : @" + str(username)[:64]
        count = sum(item["title"] in selected for item in catalog) + sum(f"cosmetic:{p[0]}" in selected for p in products(store))
        text += f"\nFiches enregistrées : {count}\n\nCe profil utilise votre compte Telegram.\n" + NOTICE
        return text, {"inline_keyboard": [[button("🛒 Mon panier", "basket")], back]}
    if action == "clear":
        store.clear(user_id)
        selected = set()
        action = "basket"
    if action == "basket":
        rows = [[button(item["title"], f"info:{i}")] for i, item in enumerate(catalog) if item["title"] in selected]
        rows += [[button(f"{p[1]} · {money(p[2])}", f"cosmetic:{p[0]}")] for p in products(store) if f"cosmetic:{p[0]}" in selected]
        text = "🛒 Mon panier\n\n" + (f"{len(rows)} fiche(s) enregistrée(s)." if rows else "Votre panier documentaire est vide.")
        text += "\n\nSélection de fiches uniquement, sans commande ni paiement."
        if rows:
            rows.append([button("🗑 Vider mon panier", "clear")])
        return text, {"inline_keyboard": rows + [[button("🛍 Boutique", "catalog")], back]}
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
    result = admin_text(message.get("text", ""), user, store) if not query else None
    if result is None:
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


