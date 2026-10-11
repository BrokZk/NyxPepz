"""Catalogue informatif autonome. Python 3.10+, bibliothèque standard uniquement."""
import json
import os
import time
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


def menu(catalog):
    return {"inline_keyboard": [
        [{"text": item["title"], "callback_data": f"info:{i}"}]
        for i, item in enumerate(catalog)
    ]}


def handle(update, catalog, api):
    query = update.get("callback_query")
    if query:
        api("answerCallbackQuery", {"callback_query_id": query["id"]})
        message = query.get("message") or {}
        chat = message.get("chat") or {}
        if chat.get("type") != "private":
            return
        key = query.get("data", "")
        if key == "menu":
            text, keyboard = "NyxPepz — fiches informatives\n\n" + NOTICE, menu(catalog)
        elif key.startswith("info:") and key[5:].isdigit() and int(key[5:]) < len(catalog):
            item = catalog[int(key[5:])]
            text = item["title"] + "\n\n" + item["description"] + "\n\n" + NOTICE
            keyboard = {"inline_keyboard": [[{"text": "‹ Catalogue", "callback_data": "menu"}]]}
        else:
            return
        api("sendMessage", {"chat_id": chat["id"], "text": text, "reply_markup": keyboard})
        return
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if chat.get("type") == "private" and isinstance(message.get("text"), str):
        api("sendMessage", {
            "chat_id": chat["id"],
            "text": "NyxPepz — fiches informatives\n\n" + NOTICE,
            "reply_markup": menu(catalog),
        })


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
                    handle(update, catalog, api)
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
