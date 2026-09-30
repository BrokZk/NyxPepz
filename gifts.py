"""Private, account-bound product gifts. Redemption creates no sale or credit."""
import hashlib
import json
import re
import secrets
import time
import uuid

from flask import jsonify, request
from sqlalchemy import update, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


def install_gifts(app, db, User, Product, shop, current_user, require_admin):
    Order = shop['Order']

    class GiftGrant(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        code = db.Column(db.String(40), unique=True, nullable=False)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
        recipient_telegram_id = db.Column(db.BigInteger, nullable=True)
        creator_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
        lines = db.Column(db.JSON, nullable=False)
        source_winner_id = db.Column(db.Integer, db.ForeignKey('giveaway_winner.id'), unique=True, nullable=True)
        client_id = db.Column(db.String(36), unique=True, nullable=True)
        request_hash = db.Column(db.String(64), nullable=True)
        created_at = db.Column(db.BigInteger, nullable=False)
        claimed_at = db.Column(db.BigInteger, nullable=True)
        status = db.Column(db.String(12), nullable=False, default='active')
        order_id = db.Column(db.Integer, db.ForeignKey('shop_order.id'), unique=True, nullable=True)

    def fail(message, status=400):
        db.session.rollback()
        return jsonify(error=message), status

    def body(allowed):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) - set(allowed):
            raise ValueError('Données invalides.')
        return payload

    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def lock_user(uid):
        return db.session.execute(update(User).where(User.id == uid).values(
            loyalty_points=User.loyalty_points), execution_options={'synchronize_session': False}).rowcount == 1

    def lock_grant(gid, uid=None):
        conditions = [GiftGrant.id == gid]
        if uid is not None:
            conditions.append(GiftGrant.user_id == uid)
        changed = db.session.execute(update(GiftGrant).where(*conditions).values(
            status=GiftGrant.status), execution_options={'synchronize_session': False}).rowcount
        return db.session.get(GiftGrant, gid, populate_existing=True) if changed else None

    def normalized_items(items):
        if not isinstance(items, list) or not 1 <= len(items) <= 20:
            raise ValueError('Choisissez entre 1 et 20 produits.')
        result = []
        seen = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {'product_id', 'quantity'}:
                raise ValueError('Produit cadeau invalide.')
            pid, quantity = item['product_id'], item['quantity']
            if type(pid) is not int or pid < 1 or type(quantity) is not int or not 1 <= quantity <= 99 or pid in seen:
                raise ValueError('Produit ou quantité invalide.')
            seen.add(pid)
            result.append({'product_id': pid, 'quantity': quantity})
        return sorted(result, key=lambda item: item['product_id'])

    def snapshots(items):
        result = []
        for item in items:
            product = db.session.get(Product, item['product_id'])
            if not product or not product.active:
                raise ValueError('Un produit est indisponible.')
            result.append({**item, 'name': product.name, 'format': product.format or ''})
        return result

    def order_clause(order_id):
        return db.session.query(GiftGrant.id).filter(GiftGrant.order_id == order_id).exists()

    def is_gift_order(order):
        oid = order if isinstance(order, int) else order.id
        return GiftGrant.query.filter_by(order_id=oid).first() is not None

    def order_gift_id(order):
        row = GiftGrant.query.filter_by(order_id=order.id).first()
        return row.id if row else None

    def describe(gift, admin=False):
        order = db.session.get(Order, gift.order_id) if gift.order_id else None
        data = dict(id=gift.id, code=gift.code, status=gift.status, lines=gift.lines,
                    created_at=gift.created_at, claimed_at=gift.claimed_at, expires_at=None,
                    source='giveaway' if gift.source_winner_id else 'manual',
                    source_winner_id=gift.source_winner_id,
                    order_reference=order.reference if order else None,
                    can_claim=gift.status == 'active' and gift.user_id is not None and shop['enabled'](),
                    shipping_free=True, total_cents=0)
        if admin:
            recipient = db.session.get(User, gift.user_id) if gift.user_id else None
            data.update(user_id=gift.user_id, recipient={
                'id': recipient.id, 'telegram_id': recipient.telegram_id,
                'first_name': recipient.first_name, 'username': recipient.username,
                'name': recipient.first_name or recipient.username or 'Membre',
            } if recipient else None)
        return data

    def get_by_winner(winner_id):
        if type(winner_id) is not int or winner_id < 1:
            return None
        return GiftGrant.query.filter_by(source_winner_id=winner_id).first()

    def describe_for_winner(winner, user=None, admin=False):
        gift = get_by_winner(winner.id)
        if gift is None or not (admin or (user and gift.user_id == user.id)):
            return None
        return describe(gift, admin)

    def issue_for_winner(winner):
        """Called under the Giveaway lock after winner flush; caller commits.

        Never acquire the winning User lock here: purge holds User then Giveaway.
        The Giveaway lock protects its winner identity until this transaction ends.
        """
        if winner.id is None:
            raise ValueError('Le gagnant doit être enregistré avant l’émission du cadeau.')
        previous = get_by_winner(winner.id)
        if previous:
            return previous
        user = db.session.get(User, winner.user_id) if winner.user_id else None
        if not user or user.telegram_id != winner.telegram_id:
            raise ValueError('Le compte gagnant n’existe plus. Actualisez le concours.')
        prize = winner.prize
        items = normalized_items([{'product_id': prize.get('product_id'), 'quantity': prize.get('quantity')}])
        lines = [{**items[0], 'name': str(prize.get('name') or 'Produit cadeau'),
                  'format': str(prize.get('format') or '')}]
        gift = GiftGrant(code='NYX-' + secrets.token_hex(16).upper(), user_id=user.id,
                         recipient_telegram_id=user.telegram_id, lines=lines,
                         source_winner_id=winner.id, created_at=int(time.time()), status='active')
        db.session.add(gift)
        db.session.flush()
        return gift

    def purge_user(uid):
        # Caller holds User and has already purged giveaways under their locks.
        # A claimed gift has an Order, so the existing deletion guard rejects it.
        GiftGrant.query.filter(GiftGrant.user_id == uid, GiftGrant.order_id.is_(None)).update(
            dict(user_id=None, recipient_telegram_id=None, status='revoked'), synchronize_session=False)
        GiftGrant.query.filter_by(creator_user_id=uid).update(dict(creator_user_id=None), synchronize_session=False)

    @app.get('/api/shop/gifts')
    def own_gifts():
        user = current_user()
        if not user:
            return fail('Ouvrez l’application depuis Telegram.', 401)
        rows = GiftGrant.query.filter_by(user_id=user.id).order_by(GiftGrant.id.desc()).limit(100).all()
        return jsonify(gifts=[describe(row) for row in rows])

    @app.post('/api/shop/gifts/lookup')
    def lookup_gift():
        user = current_user()
        if not user:
            return fail('Ouvrez l’application depuis Telegram.', 401)
        try:
            payload = body({'code'})
            code = payload.get('code')
            if not isinstance(code, str):
                raise ValueError('Code cadeau invalide.')
            code = code.strip().upper()
            gift = GiftGrant.query.filter_by(code=code, user_id=user.id).first() if re.fullmatch(r'NYX-[0-9A-F]{32}', code) else None
            if gift is None:
                return fail('Cadeau introuvable pour ce compte.', 404)
            return jsonify(gift=describe(gift))
        except ValueError as exc:
            return fail(str(exc))

    @app.post('/api/shop/gifts/<int:gid>/claim')
    def claim_gift(gid):
        user = current_user()
        if not user:
            return fail('Ouvrez l’application depuis Telegram.', 401)
        try:
            payload = body({'contact', 'items'})
            contact = shop['parse_contact'](payload.get('contact'))
            key = request.headers.get('Idempotency-Key', '')
            if not re.fullmatch(r'[a-zA-Z0-9_-]{16,64}', key):
                raise ValueError('Identifiant de validation manquant.')
            checkout_key = 'gift-' + hashlib.sha256(key.encode()).hexdigest()[:59]
            if not lock_user(user.id):
                return fail('Ce compte n’existe plus.', 401)
            gift = lock_grant(gid, user.id)
            if gift is None:
                return fail('Cadeau introuvable pour ce compte.', 404)
            expected_items = sorted([{'product_id': line['product_id'], 'quantity': line['quantity']}
                                     for line in gift.lines], key=lambda item: item['product_id'])
            if 'items' in payload:
                try:
                    if normalized_items(payload['items']) != expected_items:
                        raise ValueError()
                except ValueError:
                    return fail('Le panier doit contenir uniquement les articles et quantités du lot offert.')
            fingerprint = digest({'gift_id': gid, 'contact': contact, 'items': expected_items})
            if gift.status == 'claimed':
                order = db.session.get(Order, gift.order_id)
                if not order or order.request_hash != fingerprint:
                    return fail('Ce cadeau a déjà été utilisé avec d’autres coordonnées.', 409)
                db.session.commit()
                return jsonify(gift=describe(gift), order=shop['serialize'](order), duplicate=True)
            if gift.status != 'active':
                return fail('Ce cadeau a été révoqué.', 409)
            if not shop['enabled']():
                return fail('Les commandes sont momentanément indisponibles.', 503)
            if Order.query.filter_by(user_id=user.id, checkout_key=checkout_key).first():
                return fail('Cette validation correspond à une autre commande.', 409)
            for line in sorted(gift.lines, key=lambda item: item['product_id']):
                changed = db.session.execute(update(Product).where(
                    Product.id == line['product_id'], Product.active == True,
                    Product.name == line['name'], func.coalesce(Product.format, '') == line['format'],
                    Product.stock >= line['quantity'],
                ).values(stock=Product.stock - line['quantity'])).rowcount
                if changed != 1:
                    return fail('Un produit cadeau a changé ou est indisponible. Contactez l’administrateur ; votre cadeau reste inutilisé.', 409)
            now = int(time.time())
            order = Order(reference='NYX-' + uuid.uuid4().hex[:20].upper(), user_id=user.id,
                          checkout_key=checkout_key, request_hash=fingerprint, contact=contact,
                          lines=[{**line, 'unit_cents': 0, 'line_cents': 0} for line in gift.lines],
                          subtotal_cents=0, shipping_cents=0, total_cents=0, discount_cents=0,
                          reward_points=0, reward_reserved=False, referrer_id=None, points=0,
                          loyalty_policy='gift', status='gifted', stock_reserved=True,
                          created_at=now, expires_at=now, payment_nonce=secrets.token_urlsafe(32))
            db.session.add(order)
            db.session.flush()
            gift.status, gift.order_id, gift.claimed_at = 'claimed', order.id, now
            profile = db.session.get(shop['Profile'], user.id)
            if profile:
                profile.contact = contact
            else:
                db.session.add(shop['Profile'](user_id=user.id, contact=contact))
            db.session.flush()
            shop['enqueue'](order, 'gifted')
            db.session.commit()
            return jsonify(gift=describe(gift), order=shop['serialize'](order)), 201
        except ValueError as exc:
            return fail(str(exc))
        except SQLAlchemyError:
            return fail('Validation momentanément indisponible. Réessayez avec les mêmes coordonnées.', 503)

    @app.get('/api/shop/admin/gifts')
    def admin_gifts():
        if not require_admin():
            return fail('Interdit.', 403)
        try:
            page = int(request.args.get('page', '1'))
            if page < 1:
                raise ValueError()
        except (TypeError, ValueError):
            return fail('Page invalide.')
        query = GiftGrant.query
        status = request.args.get('status')
        if status not in (None, ''):
            if status not in ('active', 'claimed', 'revoked'):
                return fail('Filtre invalide.')
            query = query.filter_by(status=status)
        total = query.count()
        pages = max(1, (total + 9) // 10)
        page = min(page, pages)
        rows = query.order_by(GiftGrant.id.desc()).offset((page - 1) * 10).limit(10).all()
        return jsonify(gifts=[describe(row, True) for row in rows], page=page, page_size=10, pages=pages, total=total)

    @app.post('/api/shop/admin/gifts')
    def create_gift():
        admin = require_admin()
        if not admin:
            return fail('Interdit.', 403)
        key = fingerprint = None
        try:
            payload = body({'client_id', 'user_id', 'items'})
            key = str(uuid.UUID(payload.get('client_id', '')))
            uid = payload.get('user_id')
            if type(uid) is not int or uid < 1:
                raise ValueError('Choisissez un destinataire.')
            items = normalized_items(payload.get('items'))
            fingerprint = digest({'user_id': uid, 'items': items})
            previous = GiftGrant.query.filter_by(client_id=key).first()
            if previous:
                if previous.request_hash != fingerprint:
                    return fail('Cette création correspond à un autre cadeau.', 409)
                return jsonify(gift=describe(previous, True), duplicate=True)
            if not lock_user(uid):
                return fail('Destinataire introuvable.', 404)
            recipient = db.session.get(User, uid, populate_existing=True)
            # Recheck after the recipient lock serializes simultaneous retries.
            previous = GiftGrant.query.filter_by(client_id=key).first()
            if previous:
                if previous.request_hash != fingerprint:
                    return fail('Cette création correspond à un autre cadeau.', 409)
                db.session.commit()
                return jsonify(gift=describe(previous, True), duplicate=True)
            gift = GiftGrant(code='NYX-' + secrets.token_hex(16).upper(), user_id=uid,
                             recipient_telegram_id=recipient.telegram_id, creator_user_id=admin.id,
                             lines=snapshots(items), client_id=key, request_hash=fingerprint,
                             created_at=int(time.time()), status='active')
            db.session.add(gift)
            db.session.commit()
            return jsonify(gift=describe(gift, True)), 201
        except (ValueError, TypeError, AttributeError) as exc:
            return fail(str(exc) if isinstance(exc, ValueError) else 'Données invalides.')
        except IntegrityError:
            db.session.rollback()
            previous = GiftGrant.query.filter_by(client_id=key).first() if key else None
            if previous:
                if previous.request_hash != fingerprint:
                    return fail('Cette création correspond à un autre cadeau.', 409)
                return jsonify(gift=describe(previous, True), duplicate=True)
            return fail('Création momentanément indisponible. Réessayez avec le même formulaire.', 503)
        except SQLAlchemyError:
            return fail('Création momentanément indisponible. Réessayez avec le même formulaire.', 503)

    @app.get('/api/shop/admin/gifts/<int:gid>')
    def admin_gift_detail(gid):
        if not require_admin():
            return fail('Interdit.', 403)
        gift = db.session.get(GiftGrant, gid)
        if gift is None:
            return fail('Cadeau introuvable.', 404)
        return jsonify(gift=describe(gift, True))

    @app.post('/api/shop/admin/gifts/<int:gid>/revoke')
    def revoke_gift(gid):
        if not require_admin():
            return fail('Interdit.', 403)
        try:
            body(set())
            row = db.session.get(GiftGrant, gid)
            if row is None:
                return fail('Cadeau introuvable.', 404)
            # Same User -> Gift lock order as redemption and account deletion.
            if row.user_id is not None:
                lock_user(row.user_id)
            gift = lock_grant(gid)
            if gift is None:
                return fail('Cadeau introuvable.', 404)
            if gift.status == 'claimed' or gift.order_id is not None:
                return fail('Ce cadeau a déjà été utilisé.', 409)
            gift.status = 'revoked'
            db.session.commit()
            return jsonify(gift=describe(gift, True))
        except ValueError as exc:
            return fail(str(exc))
        except SQLAlchemyError:
            return fail('Révocation indisponible. Réessayez.', 503)

    extension = dict(Grant=GiftGrant, issue_for_winner=issue_for_winner, get_by_winner=get_by_winner,
                     describe_for_winner=describe_for_winner, describe=describe, purge_user=purge_user,
                     is_gift_order=is_gift_order, order_clause=order_clause, order_gift_id=order_gift_id)
    app.extensions['nyx_gifts'] = extension
    return extension
