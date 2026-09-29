"""Durable delivery of order notifications and Google Sheets mirrors.

The worker is an explicit server command, never a browser-triggered side effect.
"""
import json
import os
import secrets
import time
from urllib.parse import quote

import click
import requests
from sqlalchemy import or_, update

HEADERS = ["Commande", "Créée le (UTC)", "Statut", "Telegram ID", "Pseudo Telegram", "Prénom", "Nom",
           "Email", "Téléphone", "Adresse", "Complément", "Code postal", "Ville", "Pays", "Origine",
           "Articles", "Produits EUR", "Livraison EUR", "Total EUR", "Points gagnés", "Numéro de suivi", "Réduction EUR", "Points utilisés"]


def install_delivery(app, db, User, shop):
    from bot_launcher import install_launcher
    launcher_tick = install_launcher(app, db)
    shop['launcher_tick'] = launcher_tick
    Order, Outbox = shop["Order"], shop["Outbox"]

    def sheets_session():
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "/etc/secrets/google-service-account.json")
        credentials = service_account.Credentials.from_service_account_file(path, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return AuthorizedSession(credentials)

    def sheet_write(order):
        spreadsheet = os.environ.get("GOOGLE_SHEET_ID", "")
        if not spreadsheet:
            raise RuntimeError("Google Sheets non configuré")
        client = sheets_session()
        base = "https://sheets.googleapis.com/v4/spreadsheets/" + quote(spreadsheet, safe='')
        title = "App_Commandes"
        metadata = client.get(base, params={"fields": "sheets.properties"}, timeout=20)
        metadata.raise_for_status()
        sheets = {s["properties"]["title"]: s["properties"] for s in metadata.json().get("sheets", [])}
        if title not in sheets:
            response = client.post(base + ':batchUpdate', json={"requests": [{"addSheet": {"properties": {"title": title, "gridProperties": {"rowCount": max(1000, order.id + 10), "columnCount": len(HEADERS)}}}}]}, timeout=20)
            if not response.ok:
                # A concurrent worker may have just created the sheet.
                metadata = client.get(base, params={"fields": "sheets.properties"}, timeout=20)
                metadata.raise_for_status()
                sheets = {s["properties"]["title"]: s["properties"] for s in metadata.json().get("sheets", [])}
                if title not in sheets:
                    response.raise_for_status()
        elif sheets[title].get("gridProperties", {}).get("rowCount", 0) <= order.id:
            response = client.post(base + ':batchUpdate', json={"requests": [{"appendDimension": {"sheetId": sheets[title]["sheetId"], "dimension": "ROWS", "length": 1000}}]}, timeout=20)
            response.raise_for_status()
        header_url = base + '/values/' + quote("'App_Commandes'!A1:W1", safe='')
        existing = client.get(header_url, timeout=20)
        existing.raise_for_status()
        header = existing.json().get("values", [])
        if header and header[0] != HEADERS:
            raise RuntimeError("En-têtes App_Commandes modifiés : vérifier avant synchronisation")
        if not header:
            response = client.put(header_url, params={"valueInputOption": "RAW"}, json={"values": [HEADERS]}, timeout=20)
            response.raise_for_status()
        # Fixed database-derived rows are idempotent even after a network timeout.
        # This dedicated tab must not be reordered or used by the old bot.
        row = order.id + 1
        target = base + '/values/' + quote(f"'App_Commandes'!A{row}:W{row}", safe='')
        existing = client.get(target, timeout=20)
        existing.raise_for_status()
        occupied = existing.json().get("values", [])
        if occupied and occupied[0] and occupied[0][0] != order.reference:
            raise RuntimeError("Ligne occupée par une autre commande : synchronisation arrêtée")
        user = db.session.get(User, order.user_id)
        from datetime import datetime, timezone
        c = order.contact
        data = [order.reference, datetime.fromtimestamp(order.created_at, timezone.utc).isoformat(), order.status,
                str(user.telegram_id), user.username or "", c["first_name"], c["last_name"], c["email"], c["phone"],
                c["address"], c["address_extra"], c["postal_code"], c["city"], c["country"], c["discovery"],
                " | ".join(f"{x['quantity']} × {x['name']} {x['format']} ({x['unit_cents']/100:.2f} €)" for x in order.lines),
                order.subtotal_cents / 100, order.shipping_cents / 100, order.total_cents / 100, order.points, order.tracking_number or "", order.discount_cents / 100, order.reward_points]
        response = client.put(target, params={"valueInputOption": "RAW"}, json={"values": [data]}, timeout=20)
        response.raise_for_status()

    def telegram_send(order, job):
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise RuntimeError("Bot Telegram non configuré")
        customer = job.kind.startswith('client_')
        event = job.kind.split('_', 1)[1]
        messages = {"created": "Nouvelle commande reçue — en attente de paiement", "paid": "Commande payée et validée",
                    "shipped": "Votre colis a été expédié", "available": "Votre colis est disponible au point de retrait / locker",
                    "delivered": "Colis livré", "expired": "Réservation expirée", "cancelled": "Commande annulée"}
        heading = messages.get(event, "Paiement reçu — montant à vérifier" if event.startswith('payment_received') else event)
        if customer and event == "created":
            heading = "Votre commande est enregistrée — paiement en attente"
        text = f"{heading}\n{order.reference}\nTotal : {order.total_cents / 100:.2f} €"
        text += '\n' + '\n'.join(f"{x['quantity']} × {x['name']} {x['format']}" for x in order.lines)
        if order.tracking_number:
            text += '\nNuméro de suivi : ' + order.tracking_number
        payload = {"chat_id": job.recipient, "text": text[:3900]}
        if not customer:
            user = db.session.get(User, order.user_id)
            text += '\nClient : ' + order.contact['first_name'] + ' ' + order.contact['last_name']
            if user.username:
                text += ' (@' + user.username + ')'
            payload["text"] = text[:3900]
            payload["reply_markup"] = {"inline_keyboard": [[{"text": "Contacter le client", "url": 'https://t.me/' + user.username if user.username else 'tg://user?id=' + str(user.telegram_id)}]]}
        response = requests.post('https://api.telegram.org/bot' + token + '/sendMessage', json=payload, timeout=20)
        if customer and response.status_code == 403:
            # Customer blocked the bot or has not granted write access. Do not
            # retry forever; the order remains available in their app profile.
            return "client_unreachable"
        response.raise_for_status()
        if not response.json().get("ok"):
            raise RuntimeError("Telegram a refusé le message")
        return None

    def run_jobs(limit=30):
        now = int(time.time())
        candidates = [r.id for r in Outbox.query.filter(Outbox.state != 'done', Outbox.next_attempt <= now,
            Outbox.lease_until <= now).order_by(Outbox.id).limit(limit)]
        db.session.commit()
        processed = 0
        for job_id in candidates:
            token = secrets.token_hex(20)
            changed = db.session.execute(update(Outbox).where(Outbox.id == job_id, Outbox.state != 'done',
                Outbox.lease_until <= int(time.time())).values(lease_until=int(time.time()) + 600, lease_token=token, state='working')) .rowcount
            db.session.commit()
            if not changed:
                continue
            job = db.session.get(Outbox, job_id)
            order = db.session.get(Order, job.order_id)
            # Serialize external writes for one order so an older Sheets
            # snapshot cannot overwrite a newer status from another worker.
            order_lock = db.session.execute(update(Order).where(Order.id == order.id,
                Order.sync_lease_until <= int(time.time())).values(sync_lease_until=int(time.time())+600, sync_lease_token=token)).rowcount
            if not order_lock:
                db.session.execute(update(Outbox).where(Outbox.id == job_id, Outbox.lease_token == token).values(state='pending', lease_until=0, lease_token=None))
                db.session.commit()
                continue
            db.session.commit()
            db.session.refresh(order)
            try:
                note = None
                if job.kind == 'sheets':
                    sheet_write(order)
                else:
                    note = telegram_send(order, job)
                db.session.execute(update(Outbox).where(Outbox.id == job_id, Outbox.lease_token == token).values(
                    state='done', lease_until=0, lease_token=None, last_error=note))
                db.session.execute(update(Order).where(Order.id == order.id, Order.sync_lease_token == token).values(sync_lease_until=0, sync_lease_token=None))
                db.session.commit()
                processed += 1
            except Exception as exc:
                db.session.rollback()
                job = db.session.get(Outbox, job_id)
                attempts = job.attempts + 1
                # Do not log HTTP URLs: Telegram URLs contain the bot secret.
                db.session.execute(update(Outbox).where(Outbox.id == job_id, Outbox.lease_token == token).values(
                    state='pending', lease_until=0, lease_token=None, attempts=attempts,
                    next_attempt=int(time.time()) + min(3600, 15 * (2 ** min(attempts, 8))),
                    last_error=type(exc).__name__))
                db.session.execute(update(Order).where(Order.id == order.id, Order.sync_lease_token == token).values(sync_lease_until=0, sync_lease_token=None))
                db.session.commit()
        return processed

    @app.cli.command('shop-dispatch')
    @click.option('--loop', is_flag=True, help='Worker continu : traiter les notifications et synchroniser Sheets.')
    def dispatch(loop):
        import signal
        import threading
        stop = threading.Event()
        if loop:
            signal.signal(signal.SIGTERM, lambda *_: stop.set())
            signal.signal(signal.SIGINT, lambda *_: stop.set())
        while not stop.is_set():
            shop['expire']()
            count = run_jobs()
            if loop:
                launcher_tick()
            if not loop:
                click.echo(f'{count} envois traités')
                return
            stop.wait(10)

    shop['run_jobs'] = run_jobs
    shop['sheet_write'] = sheet_write
    shop['telegram_send'] = telegram_send
