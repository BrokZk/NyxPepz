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
    commerce = commerce_screen(action, catalog, user, store)
    if commerce is not None:
        return commerce
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
    if "update_id" in update:
        event_id = update["update_id"]
        if store.db.execute("SELECT id FROM bot_events WHERE id=?", (event_id,)).fetchone():
            return
        # Persist the receipt before any mutation: an uncertain Telegram reply
        # must not add another unit when the same update is redelivered.
        with store.db:
            store.db.execute("INSERT INTO bot_events VALUES (?)", (event_id,))
            store.db.execute("DELETE FROM bot_events WHERE id < ?", (event_id - 10000,))
    action = query.get("data", "") if query else "menu"
    try:
        result = admin_text(message.get("text", ""), user, store) if not query else None
        if result is None:
            result = screen(action, catalog, user, store)
        if action in ("admin:confirm",) or action.startswith("admin:remove:"):
            sync_cosmetics(store)
    except BridgeError as error:
        result = (str(error), {"inline_keyboard": [[button("Réessayer depuis le panier", "basket")], [button("‹ Retour", "menu")]]})
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


import hashlib
import hmac
import uuid
from urllib.parse import urlparse


class BridgeError(Exception):
    pass


def bridge(action, **payload):
    base = os.environ.get("NYXPEPZ_APP_URL", "").rstrip("/")
    secret = os.environ.get("NYXPEPZ_BRIDGE_SECRET", "")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or len(secret) < 32:
        raise BridgeError("La liaison Render n'est pas encore configurée.")
    body = json.dumps({"action": action, **payload}, separators=(",", ":")).encode()
    timestamp, nonce = str(int(time.time())), uuid.uuid4().hex
    signature = hmac.new(secret.encode(), timestamp.encode() + b"." + nonce.encode() + b"." + body, hashlib.sha256).hexdigest()
    req = Request(base + "/api/cosmetics/bridge", data=body, headers={
        "Content-Type": "application/json", "X-Nyx-Time": timestamp,
        "X-Nyx-Nonce": nonce, "X-Nyx-Signature": signature,
    })
    try:
        with urlopen(req, timeout=40) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            detail = json.load(error).get("error", "Liaison indisponible.")
        except (ValueError, OSError):
            detail = "Liaison indisponible."
        raise BridgeError(str(detail)[:200]) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise BridgeError("Connexion à l'application indisponible. Réessayez.") from None


def sync_cosmetics(store):
    return bridge("sync", products=[dict(id=p[0], name=p[1], cents=p[2], category=p[3]) for p in products(store)])


def setup_commerce(store):
    store.db.execute("CREATE TABLE IF NOT EXISTS cosmetic_cart (user_id INTEGER, product_id INTEGER, quantity INTEGER NOT NULL, PRIMARY KEY(user_id, product_id))")
    store.db.execute("CREATE TABLE IF NOT EXISTS cosmetic_checkout (user_id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL, checkout_key TEXT NOT NULL, draft_id TEXT)")
    store.db.execute("CREATE TABLE IF NOT EXISTS bot_cursor (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
    store.db.execute("CREATE TABLE IF NOT EXISTS bot_events (id INTEGER PRIMARY KEY)")
    store.db.commit()


def commerce_cart(store, user_id):
    return store.db.execute("SELECT p.id,p.name,p.cents,p.category,c.quantity FROM cosmetic_cart c JOIN cosmetic_products p ON p.id=c.product_id WHERE c.user_id=? ORDER BY p.id", (user_id,)).fetchall()


def cart_fingerprint(store, user_id):
    # Include prices/names: a changed catalogue needs a new reviewed checkout.
    return hashlib.sha256(json.dumps(commerce_cart(store, user_id)).encode()).hexdigest()


def change_cart(store, user_id, product_id, delta):
    row = store.db.execute("SELECT quantity FROM cosmetic_cart WHERE user_id=? AND product_id=?", (user_id, product_id)).fetchone()
    quantity = max(0, min(99, (row[0] if row else 0) + delta))
    with store.db:
        if quantity:
            store.db.execute("INSERT OR REPLACE INTO cosmetic_cart VALUES (?,?,?)", (user_id, product_id, quantity))
        else:
            store.db.execute("DELETE FROM cosmetic_cart WHERE user_id=? AND product_id=?", (user_id, product_id))


def commerce_screen(action, catalog, user, store):
    uid = user["id"]
    if action.startswith(("cosmetic:", "cosave:", "quantity:")):
        bits = action.split(":")
        number = bits[1] if len(bits) >= 2 else ""
        item = next((p for p in products(store) if number.isdigit() and p[0] == int(number)), None)
        if not item:
            return "Produit retiré du catalogue.", {"inline_keyboard": [[button("‹ Boutique", "catalog")]]}
        if action.startswith("cosave:"):
            change_cart(store, uid, item[0], 1)
        elif action.startswith("quantity:") and len(bits) == 3 and bits[2] in ("up", "down"):
            change_cart(store, uid, item[0], 1 if bits[2] == "up" else -1)
        row = next((r for r in commerce_cart(store, uid) if r[0] == item[0]), None)
        qty = row[4] if row else 0
        return f"{item[1]}\nPrix : {money(item[2])}\nDans votre panier : {qty}\nSous-total : {money(item[2] * qty)}", {"inline_keyboard": [
            [button("−", f"quantity:{item[0]}:down"), button(f"Qté : {qty}", f"cosmetic:{item[0]}"), button("＋", f"quantity:{item[0]}:up")],
            [button("🛒 Ajouter au panier", f"cosave:{item[0]}")],
            [button("‹ Boutique", "catalog"), button("🛒 Mon panier", "basket")],
        ]}
    if action == "clear":
        with store.db:
            store.db.execute("DELETE FROM cosmetic_cart WHERE user_id=?", (uid,))
            store.db.execute("DELETE FROM cosmetic_checkout WHERE user_id=?", (uid,))
        action = "basket"
    if action in ("basket", "checkout"):
        cart = commerce_cart(store, uid)
        subtotal = sum(row[2] * row[4] for row in cart)
        lines = [f"• {p[1]} × {p[4]} — {money(p[2] * p[4])}" for p in cart]
        text = ("📋 Récapitulatif" if action == "checkout" else "🛒 Mon panier") + "\n\n"
        text += "\n".join(lines) if lines else "Votre panier est vide."
        if lines:
            text += "\n\nProduits : " + money(subtotal) + "\nLivraison ajoutée selon le pays dans le formulaire."
        if action == "checkout" and cart:
            return text + "\n\nConfirmez ce panier avant de saisir vos coordonnées.", {"inline_keyboard": [
                [button("✓ Valider et saisir mes coordonnées", "address")],
                [button("‹ Mon panier", "basket")],
            ]}
        rows = [[button(f"{p[1]} ({p[4]})", f"cosmetic:{p[0]}")] for p in cart]
        if cart:
            rows += [[button("Vider le panier", "clear"), button("Valider mon panier", "checkout")]]
        rows += [[button("‹ Boutique", "catalog")]]
        saved = store.db.execute("SELECT draft_id FROM cosmetic_checkout WHERE user_id=?", (uid,)).fetchone()
        if saved and saved[0]:
            rows.append([button("Ma dernière commande", "order_status")])
        return text, {"inline_keyboard": rows}
    if action == "address":
        cart = commerce_cart(store, uid)
        if not cart:
            return commerce_screen("basket", catalog, user, store)
        fingerprint = cart_fingerprint(store, uid)
        existing = store.db.execute("SELECT fingerprint,checkout_key,draft_id FROM cosmetic_checkout WHERE user_id=?", (uid,)).fetchone()
        key = existing[1] if existing and existing[0] == fingerprint else uuid.uuid4().hex
        with store.db:
            store.db.execute("INSERT OR REPLACE INTO cosmetic_checkout VALUES (?,?,?,?)", (uid, fingerprint, key, existing[2] if existing and existing[0] == fingerprint else None))
        sync_cosmetics(store)
        result = bridge("draft", user=user, key=key, items=[dict(cosmetic_id=p[0], quantity=p[4]) for p in cart])
        with store.db:
            store.db.execute("UPDATE cosmetic_checkout SET draft_id=? WHERE user_id=?", (result["draft_id"], uid))
        return "📍 Coordonnées de livraison\n\nOuvrez le formulaire, vérifiez le total avec la livraison et enregistrez vos coordonnées.", {"inline_keyboard": [
            [{"text": "📍 Entrer mes coordonnées", "web_app": {"url": result["url"]}}],
            [button("Vérifier ma commande", "order_status")],
            [button("‹ Mon panier", "basket")],
        ]}
    if action in ("order_status", "retry_payment"):
        saved = store.db.execute("SELECT draft_id FROM cosmetic_checkout WHERE user_id=?", (uid,)).fetchone()
        if not saved or not saved[0]:
            return "Aucune commande en cours.", {"inline_keyboard": [[button("‹ Boutique", "catalog")]]}
        if action == "retry_payment":
            bridge("retry_payment", user=user, draft_id=saved[0])
        result = bridge("status", user=user, draft_id=saved[0])
        labels = {"coordonnees_attendues": "Coordonnées à renseigner", "awaiting_payment": "En attente de paiement",
                  "payment_review": "Paiement reçu — vérification", "paid": "Payée", "shipped": "Expédiée",
                  "available": "Au point de retrait", "delivered": "Livrée", "expired": "Expirée", "cancelled": "Annulée"}
        text = "Votre commande\n" + (result.get("reference") or "") + "\n" + labels.get(result["status"], result["status"])
        rows = []
        if result["status"] == "awaiting_payment":
            rows.append([button("Recevoir le lien de paiement", "retry_payment")])
        rows.append([button("‹ Boutique", "catalog")])
        return text, {"inline_keyboard": rows}
    if action == "profile":
        data = bridge("profile", user=user)
        return f"👤 Mon profil\n\nBonjour {str(user.get('first_name') or 'Membre')[:100]} !\nPoints fidélité : {data['points']}\nPoints parrainage : {data['referral_points']}\nCode parrainage : {data['referral_code']}", {"inline_keyboard": [
            [button("Ma dernière commande", "order_status")], [button("‹ Retour", "menu")],
        ]}
    return None


def deliver_payments(store, api):
    result = bridge("deliveries")
    for delivery in result["deliveries"]:
        try:
            api("sendMessage", {"chat_id": delivery["user_id"],
                "text": f"✓ Coordonnées enregistrées\nCommande {delivery['reference']}\nTotal : {money(delivery['total_cents'])}\n\nVoici votre lien de paiement. Les points seront crédités après validation du paiement.",
                "reply_markup": {"inline_keyboard": [[{"text": "💳 Payer ma commande", "url": delivery["payment_url"]}], [button("Vérifier ma commande", "order_status")]]}})
        except ApiError as error:
            if error.code not in (400, 403):
                raise
            bridge("ack", id=delivery["id"], lease=delivery["lease"])
            continue
        bridge("ack", id=delivery["id"], lease=delivery["lease"])
        uid = delivery["user_id"]
        saved = store.db.execute("SELECT fingerprint,draft_id FROM cosmetic_checkout WHERE user_id=?", (uid,)).fetchone()
        if saved and saved[1] == delivery["draft_id"] and saved[0] == cart_fingerprint(store, uid):
            with store.db:
                store.db.execute("DELETE FROM cosmetic_cart WHERE user_id=?", (uid,))


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
    setup_commerce(store)
    with store.db:
        store.db.execute("UPDATE cosmetic_products SET category=? WHERE category=?", (CATEGORIES[3], "Récupération"))
    cursor = store.db.execute("SELECT value FROM bot_cursor WHERE id=1").fetchone()
    offset = cursor[0] if cursor else 0
    last_sync = 0
    print("NyxPepzShopBot démarré : catalogue et commandes cosmétiques.")
    try:
        sync_cosmetics(store)
        last_sync = time.time()
    except BridgeError as error:
        print(str(error))
    while True:
        try:
            updates = api("getUpdates", {
                "offset": offset, "timeout": 10,
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
                with store.db:
                    store.db.execute("INSERT OR REPLACE INTO bot_cursor VALUES (1,?)", (offset,))
            try:
                if time.time() - last_sync >= 60:
                    sync_cosmetics(store)
                    last_sync = time.time()
                deliver_payments(store, api)
            except BridgeError as error:
                print(str(error))
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



