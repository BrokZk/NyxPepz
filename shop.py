"""Mini-app checkout. All prices, stock and payment transitions are server-owned."""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode, unquote, urlparse

import click
import requests
from flask import jsonify, request
from shop_packs import inventory_lines
from sqlalchemy import update, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

SHIPPING = {"FR": 500, "BE": 500, "ES": 1000}
COUNTRIES = {"FR": "France", "BE": "Belgique", "ES": "Espagne"}
REWARDS = {150: 1000, 300: 2500, 500: 5000, 750: 8000}
STATUSES = {"awaiting_payment": "En attente de paiement", "payment_review": "Paiement reçu — vérification",
            "paid": "Payée", "shipped": "Expédiée", "available": "Disponible au point de retrait",
            "delivered": "Livrée", "cancelled": "Annulée", "expired": "Réservation expirée"}


def install_shop(app, db, User, Product, ConfirmedOrderEvent, ReferralOrderEvent,
                 current_user, require_admin, packs=None):
    class ShopOrder(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        reference = db.Column(db.String(40), unique=True, nullable=False)
        user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
        checkout_key = db.Column(db.String(64), nullable=False)
        request_hash = db.Column(db.String(64), nullable=False)
        contact = db.Column(db.JSON, nullable=False)
        lines = db.Column(db.JSON, nullable=False)
        subtotal_cents = db.Column(db.Integer, nullable=False)
        shipping_cents = db.Column(db.Integer, nullable=False)
        total_cents = db.Column(db.Integer, nullable=False)
        discount_cents = db.Column(db.Integer, default=0, nullable=False)
        reward_points = db.Column(db.Integer, default=0, nullable=False)
        reward_reserved = db.Column(db.Boolean, default=False, nullable=False)
        status = db.Column(db.String(32), default="awaiting_payment", nullable=False)
        referrer_id = db.Column(db.Integer, nullable=True)
        loyalty_policy = db.Column(db.String(24), nullable=False)
        points = db.Column(db.Integer, default=0, nullable=False)
        created_at = db.Column(db.BigInteger, nullable=False)
        expires_at = db.Column(db.BigInteger, nullable=False)
        stock_reserved = db.Column(db.Boolean, default=True, nullable=False)
        payment_nonce = db.Column(db.String(64), nullable=False)
        encrypted_wallet = db.Column(db.Text)
        receiving_wallet = db.Column(db.String(80))
        payout_wallet = db.Column(db.String(80))
        ipn_token = db.Column(db.Text)
        payment_note = db.Column(db.String(300))
        tracking_number = db.Column(db.String(64))
        sync_lease_until = db.Column(db.BigInteger, default=0, nullable=False)
        sync_lease_token = db.Column(db.String(48))
        __table_args__ = (db.UniqueConstraint("user_id", "checkout_key", name="uq_shop_checkout"),)

    class ShopPayment(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        order_id = db.Column(db.Integer, db.ForeignKey("shop_order.id"), nullable=False)
        transaction_id = db.Column(db.String(150), nullable=False, unique=True)
        coin = db.Column(db.String(64), nullable=False)
        amount = db.Column(db.String(80), nullable=False)
        forwarded_amount = db.Column(db.String(80), nullable=False)
        received_at = db.Column(db.BigInteger, nullable=False)

    class ShopProfile(db.Model):
        user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
        contact = db.Column(db.JSON, nullable=False)

    class ShopLoyalty(db.Model):
        user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
        paid_cents = db.Column(db.BigInteger, default=0, nullable=False)

    class ShopOutbox(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        event_key = db.Column(db.String(160), unique=True, nullable=False)
        order_id = db.Column(db.Integer, db.ForeignKey("shop_order.id"), nullable=False)
        kind = db.Column(db.String(32), nullable=False)
        recipient = db.Column(db.String(32), default="", nullable=False)
        state = db.Column(db.String(20), default="pending", nullable=False)
        attempts = db.Column(db.Integer, default=0, nullable=False)
        next_attempt = db.Column(db.BigInteger, default=0, nullable=False)
        lease_until = db.Column(db.BigInteger, default=0, nullable=False)
        lease_token = db.Column(db.String(48))
        last_error = db.Column(db.String(160))

    from ambassadors import install_ambassadors
    ambassadors = install_ambassadors(app, db, User, ShopOrder, ConfirmedOrderEvent, current_user, require_admin)

    def fail(message, status=400):
        db.session.rollback()
        return jsonify(error=message), status

    @app.before_request
    def shop_same_origin():
        if request.path.startswith('/api/shop/') and request.method == 'POST':
            origin = request.headers.get('Origin')
            expected = os.environ.get('SHOP_PUBLIC_URL', request.host_url).rstrip('/')
            if origin and origin.rstrip('/') != expected:
                return fail('Origine de requête refusée', 403)

    def enabled():
        return os.environ.get("SHOP_ENABLED") == "1"

    def policy():
        return "euro1"

    def paygate_ready():
        return (os.environ.get("PAYGATE_ENABLED") == "1"
                and re.fullmatch(r"0x[0-9a-fA-F]{40}", os.environ.get("PAYGATE_WALLET", ""))
                and os.environ.get("SHOP_PUBLIC_URL", "").startswith("https://")
                and (Path(app.root_path) / "paygate_callback_public.pem").is_file())

    def config():
        return {"enabled": enabled(), "payment_enabled": bool(paygate_ready()),
                "countries": [{"code": k, "name": COUNTRIES[k], "shipping_cents": v} for k, v in SHIPPING.items()],
                "loyalty_policy": policy(), "reward_configured": True,
                "rewards": [{"points": p, "discount_cents": v} for p, v in REWARDS.items()],
                "referral_rule": "first_paid_order",
                "payment_notice": "Le paiement s’ouvre chez PayGate. Les éventuels frais du prestataire y sont affichés."}

    def serialize(order, admin=False):
        data = {"reference": order.reference, "lines": order.lines,
                "subtotal_cents": order.subtotal_cents, "shipping_cents": order.shipping_cents,
                "total_cents": order.total_cents, "status": order.status,
                "discount_cents": order.discount_cents, "reward_points": order.reward_points,
                "status_label": STATUSES.get(order.status, order.status), "created_at": order.created_at,
                "expires_at": order.expires_at, "points": order.points,
                "country": order.contact["country"], "tracking_number": order.tracking_number,
                "can_pay": order.status == "awaiting_payment" and order.expires_at > int(time.time()) and bool(paygate_ready())}
        if admin:
            owner = db.session.get(User, order.user_id)
            data.update(contact=order.contact, telegram_id=owner.telegram_id if owner else None,
                        username=owner.username if owner else None, payment_note=order.payment_note,
                        payments=[{"coin": p.coin, "amount": p.amount, "forwarded_amount": p.forwarded_amount,
                                   "transaction_id": p.transaction_id} for p in ShopPayment.query.filter_by(order_id=order.id)],
                        sync_pending=ShopOutbox.query.filter(ShopOutbox.order_id == order.id, ShopOutbox.state != "done").count())
        return data

    def parse_contact(value):
        if not isinstance(value, dict):
            raise ValueError("Coordonnées manquantes")
        limits = {"first_name": 80, "last_name": 80, "email": 180, "phone": 30,
                  "address": 180, "address_extra": 120, "postal_code": 12, "city": 90,
                  "country": 2, "discovery": 200}
        contact = {}
        for key, limit in limits.items():
            text = value.get(key, "")
            if not isinstance(text, str) or len(text.strip()) > limit or any(ord(c) < 32 for c in text):
                raise ValueError("Coordonnées invalides")
            contact[key] = text.strip()
            if not contact[key] and key != "address_extra":
                raise ValueError("Complétez tous les champs obligatoires")
        contact["country"] = contact["country"].upper()
        if contact["country"] not in SHIPPING:
            raise ValueError("Livraison disponible uniquement en France, Belgique et Espagne")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact["email"]):
            raise ValueError("Adresse email invalide")
        if not re.fullmatch(r"\+?[0-9 ()\.\-]{7,30}", contact["phone"]):
            raise ValueError("Numéro de téléphone invalide")
        length = 4 if contact["country"] == "BE" else 5
        if not re.fullmatch(r"\d{" + str(length) + r"}", contact["postal_code"]):
            raise ValueError("Code postal invalide pour ce pays")
        return contact

    def quote(payload):
        if not isinstance(payload, dict):
            raise ValueError("Panier invalide")
        country = payload.get("country")
        if country not in SHIPPING:
            raise ValueError("Choisissez France, Belgique ou Espagne")
        requested = payload.get("items")
        if not isinstance(requested, list) or not 1 <= len(requested) <= 50:
            raise ValueError("Le panier doit contenir entre 1 et 50 produits différents")
        quantities = {}
        for item in requested:
            if not isinstance(item, dict):
                raise ValueError("Article invalide")
            kind = 'pack_id' if 'pack_id' in item else 'product_id'
            if 'pack_id' in item and 'product_id' in item:
                raise ValueError("Article ambigu")
            pid, qty = item.get(kind), item.get("quantity")
            if type(pid) is not int or type(qty) is not int or pid < 1 or not 1 <= qty <= 99 or (kind, pid) in quantities:
                raise ValueError("Quantité ou article invalide")
            quantities[(kind, pid)] = qty
        lines = []
        for kind, pid in sorted(quantities):
            qty = quantities[(kind, pid)]
            if kind == 'pack_id':
                if not packs:
                    raise ValueError('Pack indisponible')
                lines.append(packs['line'](pid, qty))
                continue
            product = db.session.get(Product, pid)
            if not product or not product.active or product.stock < qty:
                raise ValueError("Un produit n’est plus disponible dans la quantité demandée")
            if type(product.price) is not int or not 0 < product.price <= 100000:
                raise ValueError("Prix du produit indisponible")
            lines.append({"product_id": pid, "name": product.name, "format": product.format,
                          "quantity": qty, "unit_cents": product.price * 100,
                          "line_cents": product.price * 100 * qty})
        for part in inventory_lines(lines):
            product = db.session.get(Product, part['product_id'])
            if not product or not product.active or product.stock < part['quantity']:
                raise ValueError('Stock insuffisant pour les produits et packs réunis')
        subtotal = sum(x["line_cents"] for x in lines)
        if subtotal > 10000000:
            raise ValueError("Montant de commande trop élevé")
        reward = payload.get("reward_points", 0)
        if type(reward) is not int or reward not in (0, *REWARDS):
            raise ValueError("Récompense invalide")
        discount = REWARDS.get(reward, 0)
        user = current_user()
        if reward and (not user or user.loyalty_points < reward):
            raise ValueError("Solde de points insuffisant")
        if discount > subtotal:
            raise ValueError("Le montant des produits doit couvrir la réduction choisie")
        result = {"lines": lines, "country": country, "subtotal_cents": subtotal,
                  "discount_cents": discount, "reward_points": reward,
                  "shipping_cents": SHIPPING[country], "total_cents": subtotal - discount + SHIPPING[country]}
        result["quote_hash"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        return result

    def enqueue(order, event):
        # One durable entry per event and destination; workers never recreate orders.
        destinations = [("sheets", "")]
        destinations += [("telegram_" + event, value.strip()) for value in os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",") if value.strip().isdigit()]
        if event in ("created", "paid", "shipped", "available", "delivered"):
            user = db.session.get(User, order.user_id)
            if user:
                destinations.append(("client_" + event, str(user.telegram_id)))
        for kind, recipient in destinations:
            key = f"{order.reference}:{event}:{kind}:{recipient}"
            if not ShopOutbox.query.filter_by(event_key=key).first():
                db.session.add(ShopOutbox(event_key=key, order_id=order.id, kind=kind, recipient=recipient))

    def release(order, status):
        changed = db.session.execute(update(ShopOrder).where(ShopOrder.id == order.id,
            ShopOrder.status == "awaiting_payment", ShopOrder.stock_reserved == True).values(
                status=status, stock_reserved=False), execution_options={"synchronize_session": False}).rowcount
        if not changed:
            return False
        for line in inventory_lines(order.lines):
            db.session.execute(update(Product).where(Product.id == line["product_id"]).values(stock=Product.stock + line["quantity"]))
        if order.reward_reserved:
            db.session.execute(update(User).where(User.id == order.user_id).values(loyalty_points=User.loyalty_points + order.reward_points))
            db.session.execute(update(ShopOrder).where(ShopOrder.id == order.id).values(reward_reserved=False))
        db.session.refresh(order)
        enqueue(order, status)
        return True

    def expire_orders():
        orders = ShopOrder.query.filter(ShopOrder.status == "awaiting_payment", ShopOrder.expires_at <= int(time.time())).all()
        count = sum(1 for order in orders if release(order, "expired"))
        db.session.commit()
        return count

    @app.get("/api/shop/config")
    def shop_config():
        return jsonify(config())

    @app.get("/api/shop/profile")
    def shop_profile():
        user = current_user()
        if not user:
            return fail("Ouvrez l’application depuis Telegram", 401)
        profile = db.session.get(ShopProfile, user.id)
        return jsonify(contact=profile.contact if profile else {}, has_referrer=user.referred_by_user_id is not None)

    @app.post("/api/shop/quote")
    def shop_quote():
        if not current_user():
            return fail("Ouvrez l’application depuis Telegram", 401)
        try:
            expire_orders()
            return jsonify(quote(request.get_json(silent=True)))
        except ValueError as exc:
            return fail(str(exc))
        except SQLAlchemyError:
            return fail("Service momentanément indisponible", 503)

    @app.post("/api/shop/orders")
    def create_order():
        user = current_user()
        if not user:
            return fail("Ouvrez l’application depuis Telegram", 401)
        if not enabled() or not paygate_ready() or policy() == "pending":
            return fail("Les commandes en ligne sont en cours de préparation", 503)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return fail("Commande invalide")
        key = request.headers.get("Idempotency-Key", "")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{16,64}", key):
            return fail("Identifiant de validation manquant")
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        try:
            # Serialize orders and referral assignment for this customer.
            db.session.execute(update(User).where(User.id == user.id).values(loyalty_points=User.loyalty_points))
            db.session.refresh(user)
            previous = ShopOrder.query.filter_by(user_id=user.id, checkout_key=key).first()
            if previous:
                if previous.request_hash != digest:
                    return fail("Cette validation correspond à un autre panier", 409)
                return jsonify(order=serialize(previous), duplicate=True)
            if ShopOrder.query.filter_by(user_id=user.id, status="awaiting_payment").count() >= 3:
                return fail("Terminez ou annulez vos commandes en attente", 409)
            contact = parse_contact(payload.get("contact"))
            computed = quote({"items": payload.get("items"), "country": contact["country"], "reward_points": payload.get("reward_points", 0)})
            if payload.get("quote_hash") != computed["quote_hash"]:
                return fail("Le panier a changé. Vérifiez le nouveau total avant de confirmer.", 409)
            code = payload.get("referral_code", "")
            if not isinstance(code, str) or len(code) > 20:
                return fail("Code de parrainage invalide")
            code = code.strip().upper()
            if code:
                referrer = User.query.filter_by(referral_code=code).first()
                if not referrer:
                    return fail("Code de parrainage inconnu")
                if referrer.id == user.id:
                    return fail("Auto-parrainage interdit")
                if user.referred_by_user_id not in (None, referrer.id):
                    return fail("Un parrain est déjà associé à votre compte")
                user.referred_by_user_id = referrer.id
            ambassador = ambassadors['prepare'](user, payload.get('ambassador_code', ''))
            prices = {x['product_id']: x['unit_cents'] for x in computed['lines'] if 'product_id' in x}
            for line in inventory_lines(computed["lines"]):
                conditions = [Product.id == line['product_id'], Product.active == True, Product.stock >= line['quantity']]
                if line['product_id'] in prices:
                    conditions.append(Product.price * 100 == prices[line['product_id']])
                changed = db.session.execute(update(Product).where(*conditions).values(
                        stock=Product.stock - line["quantity"])).rowcount
                if changed != 1:
                    return fail("Le stock ou le prix vient de changer. Vérifiez votre panier.", 409)
            reward = computed["reward_points"]
            if reward:
                changed = db.session.execute(update(User).where(User.id == user.id, User.loyalty_points >= reward).values(loyalty_points=User.loyalty_points - reward)).rowcount
                if changed != 1:
                    return fail("Vos points ont changé. Vérifiez la récompense choisie.", 409)
            now = int(time.time())
            order = ShopOrder(reference="NYX-" + uuid.uuid4().hex[:20].upper(), user_id=user.id,
                checkout_key=key, request_hash=digest, contact=contact, lines=computed["lines"],
                subtotal_cents=computed["subtotal_cents"], shipping_cents=computed["shipping_cents"],
                total_cents=computed["total_cents"], referrer_id=user.referred_by_user_id,
                discount_cents=computed["discount_cents"], reward_points=reward, reward_reserved=bool(reward),
                loyalty_policy=policy(), created_at=now, expires_at=now + 3600,
                payment_nonce=secrets.token_urlsafe(32))
            db.session.add(order)
            profile = db.session.get(ShopProfile, user.id)
            if profile:
                profile.contact = contact
            else:
                db.session.add(ShopProfile(user_id=user.id, contact=contact))
            db.session.flush()
            ambassadors['attach'](order, ambassador)
            enqueue(order, "created")
            db.session.commit()
            return jsonify(order=serialize(order)), 201
        except ValueError as exc:
            return fail(str(exc))
        except (IntegrityError, SQLAlchemyError):
            return fail("Impossible d’enregistrer la commande. Réessayez avec le même panier.", 503)

    @app.get("/api/shop/orders")
    def list_orders():
        user = current_user()
        if not user:
            return fail("Non authentifié", 401)
        try:
            expire_orders()
            return jsonify([serialize(o) for o in ShopOrder.query.filter_by(user_id=user.id).order_by(ShopOrder.id.desc()).limit(100)])
        except SQLAlchemyError:
            return fail("Commandes momentanément indisponibles", 503)

    @app.post("/api/shop/orders/<reference>/cancel")
    def cancel_order(reference):
        user = current_user()
        if not user:
            return fail("Non authentifié", 401)
        order = ShopOrder.query.filter_by(reference=reference, user_id=user.id).first()
        if not order:
            return fail("Commande introuvable", 404)
        try:
            if not release(order, "cancelled"):
                return fail("Cette commande ne peut plus être annulée ici", 409)
            db.session.commit()
            return jsonify(order=serialize(order))
        except SQLAlchemyError:
            return fail("Annulation indisponible", 503)

    @app.post("/api/shop/orders/<reference>/pay")
    def payment_link(reference):
        user = current_user()
        if not user:
            return fail("Non authentifié", 401)
        if not enabled() or not paygate_ready():
            return fail("Paiement indisponible pour le moment", 503)
        order = ShopOrder.query.filter_by(reference=reference, user_id=user.id).first()
        if not order:
            return fail("Commande introuvable", 404)
        if order.status != "awaiting_payment" or order.expires_at <= int(time.time()):
            return fail("Cette commande n’est plus en attente de paiement", 409)
        try:
            if not order.encrypted_wallet:
                # Identical callback URL makes creation retry-safe at PayGate.
                callback = os.environ["SHOP_PUBLIC_URL"].rstrip('/') + '/api/shop/paygate/callback?' + urlencode({"order": order.reference, "nonce": order.payment_nonce})
                wallet = os.environ["PAYGATE_WALLET"]
                response = requests.get("https://api.paygate.to/control/wallet.php", params={"address": wallet, "callback": callback}, timeout=20)
                response.raise_for_status()
                data = response.json()
                receiving = data.get("polygon_address_in", "")
                encrypted = data.get("address_in", "")
                if not re.fullmatch(r"0x[0-9a-fA-F]{40}", receiving) or not isinstance(encrypted, str) or not encrypted or len(encrypted) > 6000:
                    raise ValueError("Réponse PayGate invalide")
                db.session.execute(update(ShopOrder).where(ShopOrder.id == order.id, ShopOrder.encrypted_wallet == None).values(
                    encrypted_wallet=encrypted, receiving_wallet=receiving.lower(), payout_wallet=wallet.lower(), ipn_token=data.get("ipn_token")))
                db.session.commit()
                db.session.refresh(order)
            if order.status != "awaiting_payment" or order.expires_at <= int(time.time()):
                return fail("Commande expirée ou déjà traitée", 409)
            # address_in is already percent-encoded by PayGate; decode exactly once.
            url = "https://checkout.paygate.to/pay.php?" + urlencode({"address": unquote(order.encrypted_wallet),
                "amount": f"{order.total_cents // 100}.{order.total_cents % 100:02d}", "currency": "EUR", "email": order.contact["email"]})
            return jsonify(url=url)
        except (requests.RequestException, ValueError, SQLAlchemyError):
            return fail("PayGate est momentanément indisponible. Votre commande est conservée.", 503)

    def verify_callback():
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        if request.headers.get("X-PayGate-Key-Id") != "v1":
            return False
        try:
            key = serialization.load_pem_public_key((Path(app.root_path) / "paygate_callback_public.pem").read_bytes())
            base = os.environ["SHOP_PUBLIC_URL"].rstrip('/') + '/api/shop/paygate/callback'
            signed = base.encode() + b'?' + request.query_string
            key.verify(base64.b64decode(request.headers.get("X-PayGate-Signature", ""), validate=True), signed, padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False

    @app.get("/api/shop/paygate/callback")
    def payment_callback():
        if not verify_callback():
            return fail("Signature invalide", 403)
        if any(len(request.args.getlist(key)) != 1 for key in request.args):
            return fail("Paramètres ambigus")
        order = ShopOrder.query.filter_by(reference=request.args.get("order", "")).first()
        if not order or not hmac.compare_digest(order.payment_nonce, request.args.get("nonce", "")):
            return fail("Commande introuvable", 404)
        if not order.receiving_wallet or order.receiving_wallet != request.args.get("address_in", "").lower():
            return fail("Adresse de réception incorrecte", 409)
        try:
            value = Decimal(request.args.get("value_coin", ""))
            forwarded = Decimal(request.args.get("value_forwarded_coin", ""))
            shares = json.loads(request.args.get("address_out", "{}"))
            shares = {k.lower(): Decimal(str(v)) for k, v in shares.items()}
            if not value.is_finite() or value <= 0 or not forwarded.is_finite() or forwarded <= 0:
                raise ValueError()
            share = shares.get(order.payout_wallet)
            if share is None or not share.is_finite() or not 0 < share <= 1:
                raise ValueError()
            txid, coin = request.args.get("txid_in", ""), request.args.get("coin", "")
            if not re.fullmatch(r"[A-Za-z0-9:_-]{10,150}", txid) or not re.fullmatch(r"[a-zA-Z0-9_]{2,64}", coin):
                raise ValueError()
            # A signed crypto transfer does not prove that the full EUR invoice
            # was paid. Keep it in review until the gross EUR amount is verified.
            db.session.execute(update(ShopOrder).where(ShopOrder.id == order.id).values(status=ShopOrder.status))
            previous = ShopPayment.query.filter_by(transaction_id=txid).first()
            if previous:
                if previous.order_id != order.id:
                    return fail("Transaction déjà associée", 409)
                db.session.commit()
                return jsonify(ok=True, duplicate=True)
            db.session.refresh(order)
            db.session.add(ShopPayment(order_id=order.id, transaction_id=txid, coin=coin,
                amount=str(value), forwarded_amount=str(forwarded * share), received_at=int(time.time())))
            if order.status not in ("paid", "shipped", "available", "delivered"):
                order.status = "payment_review"
            db.session.flush()
            enqueue(order, "payment_received_" + str(ShopPayment.query.filter_by(order_id=order.id).count()))
            db.session.commit()
            return jsonify(ok=True)
        except (ValueError, InvalidOperation, TypeError, AttributeError):
            return fail("Confirmation incomplète")
        except SQLAlchemyError:
            return fail("Confirmation temporairement indisponible", 503)

    def credit_order(order):
        user = db.session.get(User, order.user_id)
        db.session.execute(update(User).where(User.id == user.id).values(loyalty_points=User.loyalty_points))
        db.session.refresh(user)
        progress = db.session.get(ShopLoyalty, user.id)
        if not progress:
            progress = ShopLoyalty(user_id=user.id, paid_cents=0)
            db.session.add(progress)
        paid = order.subtotal_cents - order.discount_cents
        points = (progress.paid_cents + paid) // 100 - progress.paid_cents // 100
        progress.paid_cents += paid
        if user.loyalty_points + points > 2147483647:
            raise ValueError("Plafond de points atteint")
        first_paid = ConfirmedOrderEvent.query.filter_by(user_id=user.id).first() is None
        ambassadors['credit'](order, first_paid)
        db.session.add(ConfirmedOrderEvent(external_order_id=order.reference, user_id=user.id, loyalty_points=points))
        user.loyalty_points += points
        order.points = points
        already_referred = ReferralOrderEvent.query.filter_by(referred_user_id=user.id).first()
        if order.referrer_id is not None and not already_referred and first_paid:
            if order.referrer_id == user.id:
                raise ValueError("Auto-parrainage interdit")
            changed = db.session.execute(update(User).where(User.id == order.referrer_id).values(referral_points=User.referral_points)).rowcount
            if changed != 1:
                raise ValueError("Parrain introuvable")
            db.session.add(ReferralOrderEvent(external_order_id=order.reference, referred_user_id=user.id, referrer_user_id=order.referrer_id))
            db.session.flush()
            # Preserve historical credits; from this revision there is at most
            # one new event per referred customer, after their first paid order.
            count = ReferralOrderEvent.query.filter_by(referrer_user_id=order.referrer_id).count()
            db.session.execute(update(User).where(User.id == order.referrer_id).values(referral_points=count))

    @app.get("/api/shop/admin/orders")
    def admin_orders():
        if not require_admin():
            return fail("Interdit", 403)
        groups = {'action': ('awaiting_payment', 'payment_review', 'paid'),
                  'shipping': ('shipped', 'available'), 'history': ('paid', 'shipped', 'available', 'delivered')}
        group = request.args.get('group')
        query = ShopOrder.query
        if group is not None:
            if group not in groups:
                return fail('Filtre invalide')
            query = query.filter(ShopOrder.status.in_(groups[group]))
        before = request.args.get('before', type=int)
        if before:
            query = query.filter(ShopOrder.id < before)
        orders = query.order_by(ShopOrder.id.desc()).limit(51 if group else 200).all()
        if group:
            return jsonify(orders=[serialize(o, True) for o in orders[:50]],
                           next_before=orders[49].id if len(orders) > 50 else None)
        return jsonify([serialize(o, True) for o in orders])

    @app.post("/api/shop/admin/orders/<reference>/confirm-payment")
    def confirm_payment(reference):
        if not require_admin():
            return fail("Interdit", 403)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return fail('Données invalides')
        order = ShopOrder.query.filter_by(reference=reference).first()
        if not order:
            return fail("Commande introuvable", 404)
        try:
            if order.status in ("paid", "shipped", "available", "delivered"):
                return jsonify(order=serialize(order, True), duplicate=True)
            if type(payload.get("confirmed_total_cents")) is not int or payload["confirmed_total_cents"] != order.total_cents:
                return fail("Vérifiez le montant total payé en euros avant validation")
            note = payload.get("note", "")
            if not isinstance(note, str) or not 3 <= len(note.strip()) <= 300:
                return fail("Indiquez la référence de votre vérification du paiement")
            changed = db.session.execute(update(ShopOrder).where(ShopOrder.id == order.id, ShopOrder.status == "payment_review").values(status="paid"), execution_options={"synchronize_session": False}).rowcount
            if not changed:
                return fail("Aucun paiement à vérifier pour cette commande", 409)
            db.session.refresh(order)
            if not order.stock_reserved:
                for line in inventory_lines(order.lines):
                    changed = db.session.execute(update(Product).where(Product.id == line["product_id"], Product.stock >= line["quantity"]).values(stock=Product.stock - line["quantity"])).rowcount
                    if changed != 1:
                        return fail("Paiement tardif : stock insuffisant, traitement manuel nécessaire", 409)
                order.stock_reserved = True
            if order.reward_points and not order.reward_reserved:
                changed = db.session.execute(update(User).where(User.id == order.user_id, User.loyalty_points >= order.reward_points).values(loyalty_points=User.loyalty_points - order.reward_points)).rowcount
                if changed != 1:
                    return fail("Paiement tardif : les points de la récompense ne sont plus disponibles", 409)
                order.reward_reserved = True
            order.payment_note = note.strip()
            credit_order(order)
            enqueue(order, "paid")
            db.session.commit()
            return jsonify(order=serialize(order, True))
        except ValueError as exc:
            return fail(str(exc), 409)
        except SQLAlchemyError:
            return fail("Validation indisponible ; aucun point crédité partiellement", 503)

    @app.post("/api/shop/admin/orders/<reference>/shipping")
    def update_shipping(reference):
        if not require_admin():
            return fail("Interdit", 403)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return fail('Données invalides')
        status, number = payload.get("status"), payload.get("tracking_number", "")
        if status not in ("shipped", "available", "delivered") or not isinstance(number, str) or not re.fullmatch(r"[A-Za-z0-9-]{4,64}", number):
            return fail("Statut ou numéro de suivi invalide")
        order = ShopOrder.query.filter_by(reference=reference).first()
        if not order:
            return fail("Commande introuvable", 404)
        allowed = {"shipped": ("paid",), "available": ("shipped",), "delivered": ("shipped", "available")}
        try:
            if order.status == status and order.tracking_number == number:
                return jsonify(order=serialize(order, True), duplicate=True)
            changed = db.session.execute(update(ShopOrder).where(ShopOrder.id == order.id, ShopOrder.status.in_(allowed[status])).values(status=status, tracking_number=number), execution_options={"synchronize_session": False}).rowcount
            if not changed:
                return fail("Cette transition de livraison n’est pas possible", 409)
            db.session.refresh(order)
            enqueue(order, status)
            db.session.commit()
            return jsonify(order=serialize(order, True))
        except SQLAlchemyError:
            return fail("Mise à jour indisponible", 503)

    @app.cli.command("shop-expire")
    def expire_command():
        click.echo(f"{expire_orders()} réservations expirées")

    app.extensions["nyx_shop"] = {"Order": ShopOrder, "Payment": ShopPayment, "Profile": ShopProfile,
        "Outbox": ShopOutbox, "Loyalty": ShopLoyalty, "serialize": serialize, "expire": expire_orders}
    return app.extensions["nyx_shop"]
