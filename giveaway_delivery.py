"""Durable private winner messages, dispatched by the existing shop worker.

Telegram does not provide a sendMessage idempotency key. A response lost after
acceptance can therefore cause a duplicate on retry. Leases prevent concurrent
sends and the attempt limit bounds retries; a recorded success is never retried.
"""
import os
import re
import secrets
import time
from urllib.parse import urlsplit

import requests
from sqlalchemy import func, update
from sqlalchemy.exc import SQLAlchemyError

MAX_ATTEMPTS = 5
LEASE_SECONDS = 120
RETRY_STATES = ("pending", "working")
STATES = (*RETRY_STATES, "sent", "blocked", "failed")


def _app_url():
    url = os.environ.get("SHOP_PUBLIC_URL", "").strip()
    if not url or len(url) > 2048 or any(ord(char) <= 32 or ord(char) == 127 for char in url):
        return None
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname or ""
        if (parsed.scheme != "https" or not hostname or parsed.username is not None
                or parsed.password is not None or parsed.fragment or "\\" in url
                or (parsed.port is not None and not 0 < parsed.port <= 65535)):
            return None
        if not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                   for label in hostname.rstrip('.').split('.')):
            return None
    except ValueError:
        return None
    return url


def _plain(value, limit):
    return re.sub(r"[\x00-\x1f\x7f]", " ", value if isinstance(value, str) else "").strip()[:limit]


def _payload(winner, giveaway, gift=None):
    prize = winner.prize
    if (not isinstance(prize, dict) or not _plain(prize.get("name"), 160)
            or type(prize.get("quantity")) is not int or prize["quantity"] < 1
            or type(winner.rank) is not int or winner.rank < 1):
        return None
    name = _plain(winner.first_name, 80)
    place = "1re" if winner.rank == 1 else str(winner.rank) + "e"
    product = (_plain(prize["name"], 160) + " " + _plain(prize.get("format"), 80)).strip()
    text = ("🎉 Félicitations" + (", " + name if name else "") + " !\n\n"
            + "Vous avez gagné au concours « " + _plain(giveaway.title, 160) + " ».\n"
            + "Classement : " + place + " place\n"
            + "Votre lot : " + str(prize["quantity"]) + " × " + product + "\n\n")
    if gift and gift.get('status') == 'active' and _plain(gift.get('code'), 80):
        text += ("Votre code cadeau personnel : " + _plain(gift['code'], 80) + "\n"
                 "Votre lot et sa livraison sont offerts : total 0 €.\n"
                 "Ouvrez l’application NyxPepz, ajoutez le lot indiqué à votre panier, "
                 "puis saisissez votre code cadeau et renseignez votre adresse pour le recevoir. "
                 "Ce code est lié à votre compte Telegram et s’utilise une seule fois.")
    elif gift and gift.get('status') == 'claimed':
        text += ("Votre cadeau a déjà été commandé, avec livraison offerte et un total de 0 €. "
                 "Retrouvez son suivi dans l’application NyxPepz.")
    elif gift and gift.get('status') == 'revoked':
        text += "Ce cadeau a été annulé. Contactez NyxPepz pour vérifier la remise de votre lot."
    else:
        # Old draws stay unchanged; sending a notification never creates a gift.
        text += ("Retrouvez votre lot dans l’application NyxPepz et contactez l’organisateur "
                 "pour organiser sa remise.")
    payload = {"chat_id": winner.telegram_id, "text": text}
    url = _app_url()
    if url:
        # Winners receive a private message, where Telegram supports the same
        # authenticated Mini App button used by the existing bot launcher.
        payload["reply_markup"] = {"inline_keyboard": [[{
            "text": "Ouvrir NyxPepz", "web_app": {"url": url}
        }]]}
    return payload


def _retry_after(body, response):
    parameters = body.get("parameters")
    delay = parameters.get("retry_after") if isinstance(parameters, dict) else None
    if delay is None:
        delay = response.headers.get("Retry-After")
    if isinstance(delay, str) and re.fullmatch(r"[0-9]{1,9}", delay):
        delay = int(delay)
    # Store only a bounded integer; never persist provider text or headers.
    return min(delay, 31536000) if type(delay) is int and delay > 0 else 0


def _send(token, payload):
    try:
        response = requests.post("https://api.telegram.org/bot" + token + "/sendMessage",
                                 json=payload, timeout=15)
    except requests.Timeout:
        return "retry", "telegram_timeout", None, 0
    except requests.RequestException:
        return "retry", "telegram_network_error", None, 0
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    http_status = response.status_code
    error_code = body.get("error_code")
    code = error_code if type(error_code) is int and 400 <= error_code <= 599 else http_status
    if http_status == 403 or code == 403:
        return "blocked", "telegram_blocked", None, 0
    description = body.get("description", "")
    if code == 400 and isinstance(description, str) and any(reason in description.lower() for reason in (
            "chat not found", "user not found", "user is deactivated", "bot was blocked")):
        return "blocked", "telegram_chat_not_found", None, 0
    if http_status == 429 or code == 429:
        return "retry", "telegram_rate_limited", None, _retry_after(body, response)
    result = body.get("result")
    message_id = result.get("message_id") if isinstance(result, dict) else None
    if 200 <= http_status < 300 and body.get("ok") is True and type(message_id) is int and message_id > 0:
        return "sent", None, message_id, 0
    error = "telegram_http_" + str(code) if type(code) is int and 400 <= code <= 599 else "telegram_bad_response"
    return "retry", error, None, 0


def install_giveaway_delivery(app, db, giveaways):
    Giveaway, Winner = giveaways["Giveaway"], giveaways["Winner"]

    def status(giveaway_id=None):
        query = db.session.query(Winner.notification_state, func.count(Winner.id))
        if giveaway_id is not None:
            query = query.filter(Winner.giveaway_id == giveaway_id)
        counts = dict.fromkeys(STATES, 0)
        for state, count in query.group_by(Winner.notification_state):
            if state in counts:
                counts[state] = count
        return {"configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()),
                "counts": counts, "max_attempts": MAX_ATTEMPTS}

    def due_conditions(now):
        return (Winner.notification_state.in_(RETRY_STATES), Winner.notification_next_attempt <= now,
                Winner.notification_lease_until <= now,
                Winner.giveaway_id.in_(db.select(Giveaway.id).where(Giveaway.status == "drawn")))

    def finish(winner_id, lease_token, state, error=None, next_attempt=0, message_id=None):
        values = {"notification_state": state, "notification_error": error,
                  "notification_next_attempt": next_attempt, "notification_lease_until": 0,
                  "notification_lease_token": None}
        if state == "sent":
            values.update(notified_at=int(time.time()), telegram_message_id=message_id)
        changed = db.session.execute(update(Winner).where(
            Winner.id == winner_id, Winner.notification_state == "working",
            Winner.notification_lease_token == lease_token
        ).values(**values), execution_options={"synchronize_session": False}).rowcount
        db.session.commit()
        return bool(changed)

    def run_jobs(limit=3):
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token or type(limit) is not int or limit <= 0:
            return 0
        processed = 0
        try:
            now = int(time.time())
            # A worker crash after its final claim must not leave the notification
            # permanently working or permit an unlimited number of sends.
            db.session.execute(update(Winner).where(*due_conditions(now),
                Winner.notification_attempts >= MAX_ATTEMPTS).values(
                    notification_state="failed", notification_error="retry_exhausted",
                    notification_lease_until=0, notification_lease_token=None,
                    notification_next_attempt=0), execution_options={"synchronize_session": False})
            candidates = [row.id for row in db.session.query(Winner.id).filter(
                *due_conditions(now), Winner.notification_attempts < MAX_ATTEMPTS
            ).order_by(Winner.id).limit(min(limit, 30))]
            db.session.commit()
            for winner_id in candidates:
                lease_token = secrets.token_hex(20)
                now = int(time.time())
                changed = db.session.execute(update(Winner).where(Winner.id == winner_id,
                    *due_conditions(now), Winner.notification_attempts < MAX_ATTEMPTS).values(
                        notification_state="working", notification_lease_until=now + LEASE_SECONDS,
                        notification_lease_token=lease_token,
                        notification_attempts=Winner.notification_attempts + 1
                    ), execution_options={"synchronize_session": False}).rowcount
                db.session.commit()
                if not changed:
                    continue
                # Re-read immediately before sending: deleting an account clears
                # its contact snapshot and lease, which this worker must respect.
                winner = Winner.query.filter_by(id=winner_id).populate_existing().first()
                if (not winner or winner.notification_state != "working"
                        or winner.notification_lease_token != lease_token
                        or winner.notification_lease_until <= int(time.time())):
                    db.session.rollback()
                    continue
                giveaway = Giveaway.query.filter_by(id=winner.giveaway_id).populate_existing().first()
                if not giveaway or giveaway.status != "drawn":
                    finish(winner_id, lease_token, "blocked", "giveaway_unavailable")
                    continue
                if type(winner.telegram_id) is not int or not 0 < winner.telegram_id < 2 ** 52:
                    finish(winner_id, lease_token, "blocked",
                           "missing_telegram_id" if winner.telegram_id is None else "invalid_telegram_id")
                    continue
                gifts = app.extensions.get('nyx_gifts')
                gift = gifts['describe_for_winner'](winner, admin=True) if gifts else None
                payload = _payload(winner, giveaway, gift)
                if payload is None:
                    finish(winner_id, lease_token, "failed", "invalid_prize")
                    continue
                attempts = winner.notification_attempts
                db.session.commit()
                try:
                    state, error, message_id, provider_delay = _send(token, payload)
                except Exception:
                    # Never store exception text: HTTP errors may contain the
                    # secret token URL, message contents or personal details.
                    state, error, message_id, provider_delay = "retry", "delivery_error", None, 0
                next_attempt = 0
                if state == "retry":
                    state = "failed" if attempts >= MAX_ATTEMPTS else "pending"
                    if state == "pending":
                        next_attempt = int(time.time()) + max(min(3600, 15 * 2 ** attempts), provider_delay)
                saved = finish(winner_id, lease_token, state, error, next_attempt, message_id)
                if saved and state == "sent":
                    processed += 1
        except SQLAlchemyError:
            # A persisted lease remains retryable after expiry. Do not bring down
            # unrelated shop delivery or leak database/provider details to logs.
            db.session.rollback()
        return processed

    extension = {"run_jobs": run_jobs, "status": status}
    app.extensions["nyx_giveaway_delivery"] = extension
    return extension
