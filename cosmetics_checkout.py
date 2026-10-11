"""Dedicated cosmetics checkout, sharing existing orders, payment and reward rules."""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from urllib.parse import parse_qsl

from flask import jsonify, request, render_template
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from shop import SHIPPING, COUNTRIES

CATEGORIES = ("Perte de poids", "Anti-Age/Peau/Cheveux", "Nootropique", "Récupération/Régénération")


def telegram_identity(init_data, token, now=None):
    if not isinstance(init_data, str) or not token or len(init_data) > 16000:
        return None
    pairs = parse_qsl(init_data, keep_blank_values=True)
    if len(dict(pairs)) != len(pairs):
        return None
    fields = dict(pairs)
    received = fields.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        now = int(time.time()) if now is None else now
        date = int(fields["auth_date"])
        user = json.loads(fields["user"])
        if not now - 86400 <= date <= now + 30:
            return None
        if type(user.get("id")) is not int or not 0 < user["id"] < 2**52:
            return None
        return user
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def bridge_signature(secret, timestamp, nonce, body):
    return hmac.new(secret.encode(), timestamp.encode() + b"." + nonce.encode() + b"." + body, hashlib.sha256).hexdigest()


def valid_products(values):
    if not isinstance(values, list) or len(values) > 40:
        raise ValueError("Catalogue de cosmétiques invalide.")
    seen = set()
    for item in values:
        if not isinstance(item, dict) or set(item) != {"id", "name", "cents", "category"}:
            raise ValueError("Produit cosmétique invalide.")
        if type(item["id"]) is not int or item["id"] < 1 or item["id"] in seen:
            raise ValueError("Identifiant produit invalide.")
        seen.add(item["id"])
        if not isinstance(item["name"], str) or not 1 <= len(item["name"].strip()) <= 80 or any(ord(c) < 32 for c in item["name"]):
            raise ValueError("Nom du produit invalide.")
        if type(item["cents"]) is not int or not 1 <= item["cents"] <= 99999999:
            raise ValueError("Prix cosmétique invalide.")
        category = item["category"]
        if not isinstance(category, str) or not 1 <= len(category.strip()) <= 48 or any(ord(c) < 32 or ord(c) == 127 for c in category):
            raise ValueError("Nom de catégorie invalide.")
    return values


def install_cosmetics_checkout(app, db, User, new_code, shop):
    class CosmeticCatalog(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(80), nullable=False)
        cents = db.Column(db.Integer, nullable=False)
        category = db.Column(db.String(80), nullable=False)
        active = db.Column(db.Boolean, default=True, nullable=False)

    class CosmeticDraft(db.Model):
        id = db.Column(db.String(40), primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
        key = db.Column(db.String(64), nullable=False)
        items = db.Column(db.JSON, nullable=False)
        expires_at = db.Column(db.BigInteger, nullable=False)
        order_id = db.Column(db.Integer, db.ForeignKey("shop_order.id"))
        __table_args__ = (db.UniqueConstraint("user_id", "key", name="uq_cosmetic_draft"),)

    class CosmeticNonce(db.Model):
        id = db.Column(db.String(40), primary_key=True)
        expires_at = db.Column(db.BigInteger, nullable=False)

    class CosmeticDelivery(db.Model):
        order_id = db.Column(db.Integer, db.ForeignKey("shop_order.id"), primary_key=True)
        draft_id = db.Column(db.String(40), nullable=False)
        user_id = db.Column(db.BigInteger, nullable=False)
        payment_url = db.Column(db.Text, nullable=False)
        sent = db.Column(db.Boolean, default=False, nullable=False)
        lease = db.Column(db.String(64))
        lease_until = db.Column(db.BigInteger, default=0, nullable=False)

    class CosmeticAdminNotice(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        order_id = db.Column(db.Integer, db.ForeignKey("shop_order.id"), nullable=False)
        event = db.Column(db.String(80), nullable=False)
        sent = db.Column(db.Boolean, default=False, nullable=False)
        lease = db.Column(db.String(64))
        lease_until = db.Column(db.BigInteger, default=0, nullable=False)
        __table_args__ = (db.UniqueConstraint("order_id", "event", name="uq_cosmetic_admin_notice"),)

    Order, Profile = shop["Order"], shop["Profile"]
    from cosmetic_inventory import install_cosmetic_inventory
    from mondial_tracking import mondial_tracking_url
    inventory=install_cosmetic_inventory(app,db,CosmeticCatalog,Order)

    def admin_notice(order, event):
        if not CosmeticAdminNotice.query.filter_by(order_id=order.id, event=event).first():
            db.session.add(CosmeticAdminNotice(order_id=order.id, event=event))

    app.extensions["cosmetics_admin_notice"] = admin_notice

    def fail(message, status=400):
        db.session.rollback()
        return jsonify(error=message), status

    def owned_user(identity):
        tid = identity.get("id")
        if type(tid) is not int or not 0 < tid < 2**52:
            raise ValueError("Compte Telegram invalide.")
        user = User.query.filter_by(telegram_id=tid).first()
        if user is None:
            user = User(telegram_id=tid, first_name=str(identity.get("first_name", ""))[:100],
                        username=str(identity.get("username", ""))[:64], referral_code=new_code())
            db.session.add(user)
            db.session.flush()
        return user

    def quote(items, country):
        if country not in SHIPPING or not isinstance(items, list) or not 1 <= len(items) <= 40:
            raise ValueError("Panier ou pays de livraison invalide.")
        seen, lines = set(), []
        for item in items:
            if not isinstance(item, dict) or set(item) != {"cosmetic_id", "quantity"}:
                raise ValueError("Seuls les produits cosmétiques du bot peuvent être commandés ici.")
            pid, qty = item["cosmetic_id"], item["quantity"]
            if type(pid) is not int or pid < 1 or pid in seen or type(qty) is not int or not 1 <= qty <= 99:
                raise ValueError("Quantité invalide.")
            seen.add(pid)
            product = CosmeticCatalog.query.filter_by(id=pid).with_for_update().populate_existing().first()
            if not product or not product.active:
                raise ValueError("Un produit a été retiré. Revenez au panier.")
            inventory["check"](pid,qty)
            lines.append(dict(kind="cosmetic", cosmetic_id=pid, name=product.name, format="Cosmétique",
                              quantity=qty, unit_cents=product.cents, line_cents=product.cents * qty))
        lines.sort(key=lambda x: x["cosmetic_id"])
        subtotal = sum(line["line_cents"] for line in lines)
        if subtotal > 10000000:
            raise ValueError("Montant de commande trop élevé.")
        result = dict(lines=lines, country=country, subtotal_cents=subtotal, shipping_cents=SHIPPING[country],
                      total_cents=subtotal + SHIPPING[country], discount_cents=0, reward_points=0)
        result["quote_hash"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        return result

    def pay(draft, user):
        order = db.session.get(Order, draft.order_id)
        result = app.make_response(shop["payment_link"](order.reference, user=user))
        if result.status_code != 200:
            return result
        url = result.get_json()["url"]
        delivery = db.session.get(CosmeticDelivery, order.id)
        if not delivery:
            delivery = CosmeticDelivery(order_id=order.id, draft_id=draft.id, user_id=user.telegram_id, payment_url=url)
            db.session.add(delivery)
        else:
            delivery.payment_url = url
        db.session.commit()
        return jsonify(reference=order.reference, payment_url=url, queued=True)

    @app.before_request
    def cosmetics_guard():
        if not request.path.startswith("/api/cosmetics/"):
            return
        if request.content_length and request.content_length > 65536:
            return fail("Requête trop volumineuse.", 413)
        origin = request.headers.get("Origin")
        expected = os.environ.get("SHOP_PUBLIC_URL", "").rstrip("/")
        if origin and origin.rstrip("/") != expected:
            return fail("Origine refusée.", 403)

    @app.after_request
    def cosmetics_private(response):
        if request.path.startswith(("/api/cosmetics/", "/coordonnees")):
            response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                                     "X-Content-Type-Options": "nosniff"})
        return response

    @app.get("/coordonnees")
    def cosmetics_page():
        return render_template("cosmetics-contact.html")

    @app.post("/api/cosmetics/bridge")
    def cosmetics_bridge():
        raw = request.get_data()
        timestamp, nonce = request.headers.get("X-Nyx-Time", ""), request.headers.get("X-Nyx-Nonce", "")
        secret = os.environ.get("NYXPEPZ_BRIDGE_SECRET", "")
        if len(secret) < 32:
            return fail("Liaison du bot non configurée.", 503)
        if not timestamp.isdigit() or abs(int(time.time()) - int(timestamp)) > 60 or not re.fullmatch("[a-f0-9]{32}", nonce):
            return fail("Signature expirée.", 401)
        expected = bridge_signature(secret, timestamp, nonce, raw)
        if not hmac.compare_digest(expected, request.headers.get("X-Nyx-Signature", "")):
            return fail("Signature invalide.", 401)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return fail("Données invalides.")
        try:
            CosmeticNonce.query.filter(CosmeticNonce.expires_at < int(time.time())).delete()
            db.session.add(CosmeticNonce(id=nonce, expires_at=int(time.time()) + 120))
            db.session.flush()
            action = data.get("action")
            if action == "sync":
                incoming = valid_products(data.get("products"))
                current = {p.id: p for p in CosmeticCatalog.query.with_for_update().all()}
                active = {item["id"] for item in incoming}
                for item in incoming:
                    product = current.get(item["id"])
                    if not product:
                        product = CosmeticCatalog(id=item["id"])
                        db.session.add(product)
                    product.name, product.cents, product.category, product.active = item["name"], item["cents"], item["category"], True
                    inventory["row"](item["id"])  # Metadata sync never replaces quantities.
                for pid, product in current.items():
                    if pid not in active:
                        product.active = False
                db.session.commit()
                return jsonify(ok=True)
            if action == "deliveries":
                now = int(time.time())
                jobs = CosmeticDelivery.query.filter_by(sent=False).filter(CosmeticDelivery.lease_until < now).order_by(CosmeticDelivery.order_id).limit(10).all()
                results = []
                for job in jobs:
                    lease = secrets.token_hex(24)
                    count = db.session.execute(update(CosmeticDelivery).where(
                        CosmeticDelivery.order_id == job.order_id, CosmeticDelivery.sent == False,
                        CosmeticDelivery.lease_until < now).values(lease=lease, lease_until=now + 90)).rowcount
                    order = db.session.get(Order, job.order_id)
                    if count and order.status == "awaiting_payment" and order.expires_at > now:
                        results.append(dict(id=job.order_id, lease=lease, user_id=job.user_id,
                                            reference=order.reference, draft_id=job.draft_id, total_cents=order.total_cents,
                                            payment_url=job.payment_url))
                    elif count:
                        job.sent = True
                db.session.commit()
                return jsonify(deliveries=results)
            if action == "ack":
                count = db.session.execute(update(CosmeticDelivery).where(
                    CosmeticDelivery.order_id == data.get("id"), CosmeticDelivery.lease == data.get("lease"),
                    CosmeticDelivery.sent == False).values(sent=True)).rowcount
                db.session.commit()
                return jsonify(ok=bool(count))
            if action == "admin_notices":
                now = int(time.time())
                jobs = CosmeticAdminNotice.query.filter_by(sent=False).filter(CosmeticAdminNotice.lease_until < now).order_by(CosmeticAdminNotice.id).limit(10).all()
                result = []
                for job in jobs:
                    lease = secrets.token_hex(24)
                    changed = db.session.execute(update(CosmeticAdminNotice).where(
                        CosmeticAdminNotice.id == job.id, CosmeticAdminNotice.sent == False,
                        CosmeticAdminNotice.lease_until < now).values(lease=lease,lease_until=now+90)).rowcount
                    if changed:
                        order = db.session.get(Order,job.order_id)
                        owner = db.session.get(User,order.user_id)
                        result.append(dict(id=job.id,lease=lease,reference=order.reference,telegram_id=owner.telegram_id,
                                           total_cents=order.total_cents,event=job.event,status=order.status))
                db.session.commit()
                return jsonify(notices=result)
            if action == "ack_admin_notice":
                count=db.session.execute(update(CosmeticAdminNotice).where(
                    CosmeticAdminNotice.id==data.get("id"),CosmeticAdminNotice.lease==data.get("lease"),
                    CosmeticAdminNotice.sent==False).values(sent=True)).rowcount
                db.session.commit()
                return jsonify(ok=bool(count))
            if action=="stocks":
                result=[dict(id=product.id,available=inventory["availability"](product.id))
                        for product in CosmeticCatalog.query.filter_by(active=True).order_by(CosmeticCatalog.id)]
                db.session.commit()
                return jsonify(stocks=result)
            user = owned_user(data.get("user") or {})
            if action=="set_stock":
                if user.telegram_id!=8843973247:return fail("Accès Admin refusé.",403)
                pid,key=data.get("product_id"),data.get("key")
                if type(pid) is not int or pid<1 or not isinstance(key,str) or not re.fullmatch("[a-f0-9]{32}",key):
                    return fail("Modification de stock invalide.")
                available,duplicate=inventory["set_available"](pid,data.get("quantity"),key)
                db.session.commit()
                return jsonify(available=available,duplicate=duplicate)
            if action=="tracking":
                rows=Order.query.filter_by(user_id=user.id).filter(
                    Order.status.in_(("paid","shipped","available","delivered")),
                    Order.tracking_number.isnot(None),Order.tracking_number!="").order_by(Order.id.desc()).limit(20).all()
                result=[dict(reference=order.reference,number=order.tracking_number,
                             postal_code=order.contact.get("postal_code",""),
                             status=order.status,url=mondial_tracking_url(order.tracking_number,order.contact.get("postal_code","")))
                        for order in rows]
                db.session.commit()
                return jsonify(orders=result)
            if action == "profile":
                db.session.commit()
                return jsonify(points=user.loyalty_points, referral_points=app.extensions["referral_rewards"]["balance"](user), referral_code=user.referral_code)
            if action == "draft":
                if os.environ.get("COSMETICS_CHECKOUT_ENABLED") != "1":
                    return fail("Commandes cosmétiques temporairement fermées.", 503)
                key = data.get("key", "")
                if not isinstance(key, str) or not re.fullmatch("[a-f0-9]{32}", key):
                    raise ValueError("Identifiant de panier invalide.")
                items = data.get("items")
                quote(items, "FR")
                entry = CosmeticDraft.query.filter_by(user_id=user.id, key=key).first()
                if entry and entry.items != items:
                    return fail("Ce panier a changé.", 409)
                if not entry:
                    entry = CosmeticDraft(id=uuid.uuid4().hex, user_id=user.id, key=key, items=items, expires_at=int(time.time()) + 3600)
                    db.session.add(entry)
                if entry.expires_at <= int(time.time()):
                    return fail("Ce panier a expiré. Recommencez sa validation.", 409)
                db.session.commit()
                return jsonify(draft_id=entry.id, url=os.environ["SHOP_PUBLIC_URL"].rstrip("/") + "/coordonnees#draft=" + entry.id)
            if action == "status":
                entry = CosmeticDraft.query.filter_by(id=data.get("draft_id"), user_id=user.id).first()
                if not entry:
                    return fail("Commande introuvable.", 404)
                order = db.session.get(Order, entry.order_id) if entry.order_id else None
                db.session.commit()
                return jsonify(reference=order.reference if order else None, status=order.status if order else "coordonnees_attendues")
            if action == "alternate_payment":
                entry = CosmeticDraft.query.filter_by(id=data.get("draft_id"), user_id=user.id).first()
                if not entry or not entry.order_id:
                    return fail("Commande introuvable.",404)
                order = Order.query.filter_by(id=entry.order_id,user_id=user.id).with_for_update().populate_existing().first()
                if not order or order.status not in ("awaiting_payment","payment_review") or (order.status=="awaiting_payment" and order.expires_at<=int(time.time())):
                    return fail("Cette commande ne peut plus recevoir une demande de paiement.",409)
                previous = CosmeticAdminNotice.query.filter_by(order_id=order.id,event="alternate_payment").first()
                admin_notice(order,"alternate_payment")
                db.session.commit()
                return jsonify(ok=True,duplicate=bool(previous),reference=order.reference)
            if action == "retry_payment":
                entry = CosmeticDraft.query.filter_by(id=data.get("draft_id"), user_id=user.id).first()
                if not entry or not entry.order_id:
                    return fail("Enregistrez d'abord vos coordonnées.", 409)
                result = pay(entry, user)
                delivery = db.session.get(CosmeticDelivery, entry.order_id)
                if delivery:
                    delivery.sent, delivery.lease_until = False, 0
                    db.session.commit()
                return result
            return fail("Action inconnue.")
        except ValueError as exc:
            return fail(str(exc))
        except IntegrityError:
            return fail("Requête déjà traitée ou compte en cours de création. Réessayez.", 409)
        except (SQLAlchemyError, KeyError, TypeError):
            return fail("Liaison temporairement indisponible.", 503)

    @app.post("/api/cosmetics/customer")
    def cosmetics_customer():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return fail("Données invalides.")
        identity = telegram_identity(data.get("init_data"), os.environ.get("NYXPEPZ_CATALOG_BOT_TOKEN", ""))
        if not identity:
            return fail("Rouvrez le formulaire depuis NyxPepzShopBot.", 401)
        try:
            user = User.query.filter_by(telegram_id=identity["id"]).first()
            entry = CosmeticDraft.query.filter_by(id=data.get("draft_id"), user_id=user.id if user else -1).with_for_update().first()
            if not entry:
                return fail("Panier introuvable pour ce compte.", 404)
            action = data.get("action")
            if action == "load":
                profile = db.session.get(Profile, user.id)
                order = db.session.get(Order, entry.order_id) if entry.order_id else None
                if not order and entry.expires_at <= int(time.time()):
                    return fail("Panier expiré. Revenez au bot.", 409)
                result = dict(contact=profile.contact if profile else {}, countries=[
                    dict(code=code, name=COUNTRIES[code], shipping_cents=value) for code, value in SHIPPING.items()],
                    reference=order.reference if order else None, status=order.status if order else None,
                    quote=quote(entry.items, (profile.contact["country"] if profile else "FR")) if not order else None)
                db.session.commit()
                return jsonify(result)
            if entry.order_id:
                if action == "confirm":
                    return pay(entry, user)
                return fail("Ce panier est déjà enregistré.", 409)
            if entry.expires_at <= int(time.time()):
                return fail("Panier expiré.", 409)
            if action == "quote":
                result = quote(entry.items, data.get("country"))
                db.session.commit()
                return jsonify(quote=result)
            if action != "confirm" or data.get("accepted") is not True:
                return fail("Confirmez les coordonnées et le récapitulatif.")
            if os.environ.get("COSMETICS_CHECKOUT_ENABLED") != "1":
                return fail("Commandes cosmétiques temporairement fermées.", 503)
            if not shop["enabled"]() or not shop["config"]()["payment_enabled"]:
                return fail("Paiement non configuré.", 503)
            contact = shop["parse_contact"]({**(data.get("contact") or {}), "discovery": "Boutique cosmétiques Telegram"})
            db.session.execute(update(User).where(User.id == user.id).values(loyalty_points=User.loyalty_points))
            computed = quote(entry.items, contact["country"])
            if data.get("quote_hash") != computed["quote_hash"]:
                return fail("Les prix ont changé. Vérifiez le nouveau récapitulatif.", 409)
            if Order.query.filter_by(user_id=user.id, status="awaiting_payment").count() >= 3:
                return fail("Terminez ou annulez vos commandes en attente.", 409)
            now = int(time.time())
            order = Order(reference="NYX-" + uuid.uuid4().hex[:20].upper(), user_id=user.id,
                          checkout_key="cosmetic_" + entry.id, request_hash=computed["quote_hash"],
                          contact=contact, lines=computed["lines"], subtotal_cents=computed["subtotal_cents"],
                          shipping_cents=computed["shipping_cents"], total_cents=computed["total_cents"],
                          discount_cents=0, reward_points=0, reward_reserved=False, stock_reserved=True,
                          referrer_id=user.referred_by_user_id, loyalty_policy="euro1",
                          created_at=now, expires_at=now + 3600, payment_nonce=secrets.token_urlsafe(32))
            db.session.add(order)
            db.session.flush()
            inventory["reserve"](order)
            entry.order_id = order.id
            profile = db.session.get(Profile, user.id)
            if not profile:
                profile = Profile(user_id=user.id, contact=contact)
                db.session.add(profile)
            else:
                profile.contact = contact
            shop["enqueue"](order, "created")
            db.session.commit()
            return pay(entry, user)
        except ValueError as exc:
            return fail(str(exc))
        except (SQLAlchemyError, TypeError):
            return fail("Enregistrement temporairement indisponible. Réessayez avec le même panier.", 503)

    return {"Catalog": CosmeticCatalog, "Draft": CosmeticDraft, "Delivery": CosmeticDelivery, "AdminNotice": CosmeticAdminNotice, "quote": quote, "inventory": inventory}



