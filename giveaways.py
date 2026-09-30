"""Free, private giveaways: entry review, immutable random draw and notification queue."""
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlsplit
from uuid import UUID

from flask import jsonify, request
from sqlalchemy import case, update
from sqlalchemy.exc import SQLAlchemyError


def now_ts():
    return int(time.time())


class AccountMissing(Exception):
    pass


def install_giveaways(app, db, User, Product, current_user, require_admin, customer_eligible=None):
    class Giveaway(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        creator_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
        client_id = db.Column(db.String(36), nullable=False)
        original = db.Column(db.JSON, nullable=False)
        title = db.Column(db.String(140), nullable=False)
        description = db.Column(db.String(4000), nullable=False, default='')
        prizes = db.Column(db.JSON, nullable=False)
        eligibility = db.Column(db.String(12), nullable=False, default='customers')
        ends_at = db.Column(db.BigInteger, nullable=False)
        status = db.Column(db.String(12), nullable=False, default='draft')
        version = db.Column(db.Integer, nullable=False, default=1)
        created_at = db.Column(db.BigInteger, nullable=False, default=now_ts)
        published_at = db.Column(db.BigInteger, nullable=True)
        closed_at = db.Column(db.BigInteger, nullable=True)
        drawn_at = db.Column(db.BigInteger, nullable=True)
        drawn_participant_count = db.Column(db.Integer, nullable=True)
        cancelled_at = db.Column(db.BigInteger, nullable=True)
        __table_args__ = (db.UniqueConstraint('creator_user_id', 'client_id', name='uq_giveaway_request'),)

    class GiveawayEntry(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        giveaway_id = db.Column(db.Integer, db.ForeignKey('giveaway.id'), nullable=False, index=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
        identity_key = db.Column(db.String(64), nullable=False)
        telegram_id = db.Column(db.BigInteger, nullable=True)
        first_name = db.Column(db.String(100), nullable=False, default='')
        username = db.Column(db.String(64), nullable=False, default='')
        joined_at = db.Column(db.BigInteger, nullable=False, default=now_ts)
        active = db.Column(db.Boolean, nullable=False, default=True)
        status = db.Column(db.String(12), nullable=False, default='pending')
        version = db.Column(db.Integer, nullable=False, default=1)
        reviewed_at = db.Column(db.BigInteger, nullable=True)
        reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
        __table_args__ = (
            db.UniqueConstraint('giveaway_id', 'user_id', name='uq_giveaway_user'),
            db.UniqueConstraint('giveaway_id', 'identity_key', name='uq_giveaway_identity'),
        )

    class GiveawayWinner(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        giveaway_id = db.Column(db.Integer, db.ForeignKey('giveaway.id'), nullable=False, index=True)
        entry_id = db.Column(db.Integer, db.ForeignKey('giveaway_entry.id'), nullable=False)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
        telegram_id = db.Column(db.BigInteger, nullable=True)
        first_name = db.Column(db.String(100), nullable=False, default='')
        username = db.Column(db.String(64), nullable=False, default='')
        rank = db.Column(db.Integer, nullable=False)
        prize = db.Column(db.JSON, nullable=False)
        notification_state = db.Column(db.String(12), nullable=False, default='pending', index=True)
        notification_attempts = db.Column(db.Integer, nullable=False, default=0)
        notification_next_attempt = db.Column(db.BigInteger, nullable=False, default=0)
        notification_lease_until = db.Column(db.BigInteger, nullable=False, default=0)
        notification_lease_token = db.Column(db.String(64), nullable=True)
        notification_error = db.Column(db.String(500), nullable=True)
        notified_at = db.Column(db.BigInteger, nullable=True)
        telegram_message_id = db.Column(db.BigInteger, nullable=True)
        __table_args__ = (
            db.UniqueConstraint('giveaway_id', 'rank', name='uq_giveaway_rank'),
            db.UniqueConstraint('giveaway_id', 'entry_id', name='uq_giveaway_winner_entry'),
        )

    def failure():
        db.session.rollback()
        return jsonify(error='Concours temporairement indisponibles. Réessayez.'), 503

    def identity_key(telegram_id):
        secret = app.secret_key.encode() if isinstance(app.secret_key, str) else app.secret_key
        return hmac.new(secret, ('giveaway:' + str(telegram_id)).encode(), hashlib.sha256).hexdigest()

    def body(allowed):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) - set(allowed):
            raise ValueError('Données invalides.')
        return data

    def version(value):
        if type(value) is not int or value < 1:
            raise ValueError('Version manquante. Actualisez la page.')
        return value

    def lock_user(user):
        result = db.session.execute(update(User).where(User.id == user.id).values(id=user.id))
        if not result.rowcount:
            raise AccountMissing()

    @app.errorhandler(AccountMissing)
    def giveaways_missing_account(_error):
        db.session.rollback()
        return jsonify(error='Ce compte n’existe plus. Ouvrez à nouveau l’application depuis Telegram.'), 401

    def lock_giveaway(gid):
        # A no-op update locks the parent row on PostgreSQL and serializes SQLite writers.
        result = db.session.execute(update(Giveaway).where(Giveaway.id == gid).values(version=Giveaway.version))
        if not result.rowcount:
            return None
        return db.session.get(Giveaway, gid, populate_existing=True)

    def visible(row, admin=False):
        return row is not None and (admin or row.status != 'draft')

    def not_found():
        db.session.rollback()
        return jsonify(error='Concours introuvable.'), 404

    def conflict(message='Le concours a changé. Actualisez avant de continuer.'):
        db.session.rollback()
        return jsonify(error=message), 409

    def current_entry(gid, uid):
        return GiveawayEntry.query.filter_by(giveaway_id=gid, user_id=uid).first()

    def entry_json(row):
        return dict(id=row.id, user_id=row.user_id, telegram_id=row.telegram_id, first_name=row.first_name,
                    username=row.username, joined_at=row.joined_at, active=row.active,
                    status=row.status if row.active else 'withdrawn', version=row.version,
                    reviewed_at=row.reviewed_at)

    def winner_json(row):
        # Leases are internal capability tokens and are never returned to the UI.
        return dict(id=row.id, rank=row.rank, prize=row.prize, telegram_id=row.telegram_id,
                    first_name=row.first_name, username=row.username, notification_state=row.notification_state,
                    notification_attempts=row.notification_attempts, notification_next_attempt=row.notification_next_attempt,
                    notification_error=row.notification_error, notified_at=row.notified_at,
                    telegram_message_id=row.telegram_message_id, gift=winner_gift(row, admin=True))

    def winner_gift(row, user=None, admin=False):
        gifts = app.extensions.get('nyx_gifts')
        return gifts['describe_for_winner'](row, user=user, admin=admin) if gifts else None

    def giveaway_json(row, user, admin=False, detail=False):
        own = current_entry(row.id, user.id)
        is_open = row.status == 'published' and now_ts() < row.ends_at
        count = GiveawayEntry.query.filter_by(giveaway_id=row.id, active=True, status='accepted').count()
        if row.status == 'drawn' and row.drawn_participant_count is not None:
            count = row.drawn_participant_count
        own_winner = GiveawayWinner.query.filter_by(giveaway_id=row.id, user_id=user.id).first() if row.status == 'drawn' else None
        result = dict(id=row.id, title=row.title, description=row.description, prizes=row.prizes,
                      eligibility=row.eligibility, ends_at=row.ends_at, status=row.status, version=row.version,
                      created_at=row.created_at, published_at=row.published_at, closed_at=row.closed_at,
                      drawn_at=row.drawn_at, cancelled_at=row.cancelled_at, participant_count=count,
                      joined=bool(own and own.active),
                      participation_status=(own.status if own.active else 'withdrawn') if own else None,
                      can_join=bool(is_open and not admin and not (own and own.active)),
                      can_withdraw=bool(is_open and own and own.active),
                      my_result={'rank': own_winner.rank, 'prize': own_winner.prize,
                                 'gift': winner_gift(own_winner, user=user)} if own_winner else None)
        if admin:
            result['pending_count'] = GiveawayEntry.query.filter_by(giveaway_id=row.id, active=True, status='pending').count()
            if detail:
                result['winners'] = [winner_json(winner) for winner in GiveawayWinner.query.filter_by(giveaway_id=row.id).order_by(GiveawayWinner.rank).all()]
        return result

    @app.before_request
    def giveaways_guard():
        path = request.path
        if not (path.startswith('/api/giveaways') or path.startswith('/api/admin/giveaways')):
            return
        if not current_user():
            return jsonify(error='Ouvrez l’application depuis votre compte Telegram.'), 401
        if path.startswith('/api/admin/giveaways') and not require_admin():
            return jsonify(error='Accès administrateur requis.'), 403
        if request.method in ('POST', 'PATCH', 'DELETE', 'PUT'):
            origin = request.headers.get('Origin')
            if origin:
                try:
                    parsed = urlsplit(origin)
                    same = parsed.scheme in ('http', 'https') and parsed.netloc.lower() == request.host.lower()
                except ValueError:
                    same = False
                if not same:
                    return jsonify(error='Origine de la requête refusée.'), 403

    @app.after_request
    def giveaways_private(response):
        if request.path.startswith('/api/giveaways') or request.path.startswith('/api/admin/giveaways'):
            response.headers['Cache-Control'] = 'private, no-store'
            response.vary.add('Cookie')
        return response

    @app.get('/api/giveaways')
    def giveaways_list():
        try:
            user = current_user()
            rows = Giveaway.query.filter(Giveaway.status != 'draft').order_by(Giveaway.id.desc()).limit(100).all()
            return jsonify(giveaways=[giveaway_json(row, user, bool(require_admin())) for row in rows])
        except SQLAlchemyError:
            return failure()

    @app.get('/api/giveaways/<int:gid>')
    def giveaway_detail(gid):
        try:
            user = current_user()
            admin = bool(require_admin())
            row = db.session.get(Giveaway, gid)
            if not visible(row, admin):
                return not_found()
            return jsonify(giveaway=giveaway_json(row, user, admin, admin))
        except SQLAlchemyError:
            return failure()

    @app.route('/api/giveaways/<int:gid>/join', methods=['POST', 'DELETE'])
    def giveaway_join(gid):
        user = current_user()
        try:
            body(set())
            if require_admin():
                return jsonify(error='Les administrateurs ne peuvent pas participer aux concours.'), 403
            lock_user(user)
            row = lock_giveaway(gid)
            if not visible(row):
                return not_found()
            own = current_entry(gid, user.id)
            if request.method == 'POST' and own and own.active:
                # A retry remains successful after closing/drawing; it never enters twice.
                db.session.rollback()
                return jsonify(giveaway=giveaway_json(row, user)), 200
            if request.method == 'DELETE' and own and not own.active:
                db.session.rollback()
                return jsonify(giveaway=giveaway_json(row, user)), 200
            if row.status != 'published' or now_ts() >= row.ends_at:
                return conflict('Les inscriptions à ce concours sont fermées.')
            if request.method == 'DELETE':
                if own:
                    own.active = False
                    own.version += 1
                db.session.commit()
                return jsonify(giveaway=giveaway_json(row, user))
            tid = user.telegram_id
            if type(tid) is not int or tid <= 0:
                raise ValueError('Compte Telegram invalide.')
            key = identity_key(tid)
            previous = GiveawayEntry.query.filter_by(giveaway_id=gid, identity_key=key).first()
            if previous and previous.user_id != user.id:
                return conflict('Ce compte Telegram a déjà été associé à une inscription à ce concours.')
            if own and own.reviewed_at is not None:
                # Withdrawal is not an appeal and must not erase a manual decision.
                status = own.status
            else:
                eligible = row.eligibility == 'everyone' or (customer_eligible is not None and bool(customer_eligible(user.id)))
                status = 'accepted' if eligible else 'pending'
            if own:
                own.active, own.status = True, status
                own.first_name, own.username = (user.first_name or '')[:100], (user.username or '')[:64]
                own.joined_at = now_ts()
                own.version += 1
            else:
                own = GiveawayEntry(giveaway_id=gid, user_id=user.id, identity_key=key, telegram_id=tid,
                                    first_name=(user.first_name or '')[:100], username=(user.username or '')[:64],
                                    joined_at=now_ts(), active=True, status=status, version=1)
                db.session.add(own)
            db.session.commit()
            return jsonify(giveaway=giveaway_json(row, user)), 201
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    def draft_values(data):
        title, description = data.get('title'), data.get('description', '')
        if not isinstance(title, str) or not title.strip() or len(title) > 140:
            raise ValueError('Saisissez un titre de 1 à 140 caractères.')
        if not isinstance(description, str) or len(description) > 4000:
            raise ValueError('La description est limitée à 4 000 caractères.')
        ends = data.get('ends_at')
        if type(ends) is not int or not 0 < ends <= 4102444800:
            raise ValueError('Date de clôture invalide.')
        eligibility = data.get('eligibility', 'customers')
        if eligibility not in ('customers', 'everyone'):
            raise ValueError('Condition de participation invalide.')
        prizes = data.get('prizes')
        if not isinstance(prizes, list) or not 1 <= len(prizes) <= 3:
            raise ValueError('Choisissez de un à trois lots, dans l’ordre du classement.')
        slots = []
        for prize in prizes:
            if not isinstance(prize, dict) or set(prize) != {'product_id', 'quantity'}:
                raise ValueError('Lot invalide.')
            if type(prize['product_id']) is not int or prize['product_id'] < 1 or type(prize['quantity']) is not int or not 1 <= prize['quantity'] <= 10:
                raise ValueError('Choisissez un produit et une quantité comprise entre 1 et 10 pour chaque lot.')
            slots.append(dict(product_id=prize['product_id'], quantity=prize['quantity']))
        return dict(title=title.strip(), description=description.strip(), ends_at=ends, eligibility=eligibility, prizes=slots)

    def prize_snapshots(slots):
        result = []
        for slot in slots:
            product = db.session.get(Product, slot['product_id'])
            if not product or not product.active:
                raise ValueError('Un produit choisi n’est plus disponible. Modifiez les lots du brouillon.')
            result.append(dict(product_id=product.id, name=product.name, format=product.format or '', quantity=slot['quantity']))
        return result

    @app.route('/api/admin/giveaways', methods=['GET', 'POST'])
    def giveaways_admin():
        user = current_user()
        try:
            if request.method == 'GET':
                rows = Giveaway.query.order_by(Giveaway.id.desc()).limit(200).all()
                return jsonify(giveaways=[giveaway_json(row, user, True) for row in rows])
            data = body({'client_id', 'title', 'description', 'prizes', 'ends_at', 'eligibility'})
            client_id = str(UUID(data.get('client_id', '')))
            values = draft_values(data)
            lock_user(user)
            existing = Giveaway.query.filter_by(creator_user_id=user.id, client_id=client_id).first()
            if existing:
                if existing.original != values:
                    return conflict('Cette création a déjà été reçue avec un autre contenu.')
                db.session.rollback()
                return jsonify(giveaway=giveaway_json(existing, user, True, True)), 200
            if values['ends_at'] <= now_ts():
                raise ValueError('Choisissez une date de clôture future.')
            row = Giveaway(creator_user_id=user.id, client_id=client_id, original=values,
                           title=values['title'], description=values['description'], prizes=prize_snapshots(values['prizes']),
                           ends_at=values['ends_at'], eligibility=values['eligibility'], status='draft', version=1)
            db.session.add(row)
            db.session.commit()
            return jsonify(giveaway=giveaway_json(row, user, True, True)), 201
        except (ValueError, TypeError, AttributeError) as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    @app.route('/api/admin/giveaways/<int:gid>', methods=['GET', 'PATCH'])
    def giveaway_admin_detail(gid):
        user = current_user()
        try:
            if request.method == 'GET':
                row = db.session.get(Giveaway, gid)
                if not row:
                    return not_found()
                return jsonify(giveaway=giveaway_json(row, user, True, True))
            data = body({'version', 'title', 'description', 'prizes', 'ends_at', 'eligibility'})
            requested_version = version(data.get('version'))
            values = draft_values(data)
            lock_user(user)
            row = lock_giveaway(gid)
            if not row:
                return not_found()
            if row.version != requested_version:
                return conflict()
            if row.status != 'draft':
                return conflict('Seul un brouillon peut être modifié.')
            if values['ends_at'] <= now_ts():
                raise ValueError('Choisissez une date de clôture future.')
            row.title, row.description = values['title'], values['description']
            row.prizes, row.ends_at, row.eligibility = prize_snapshots(values['prizes']), values['ends_at'], values['eligibility']
            row.version += 1
            db.session.commit()
            return jsonify(giveaway=giveaway_json(row, user, True, True))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    @app.post('/api/admin/giveaways/<int:gid>/<action>')
    def giveaway_admin_action(gid, action):
        user = current_user()
        if action not in ('publish', 'close', 'draw', 'cancel'):
            return not_found()
        try:
            data = body({'version'})
            requested_version = version(data.get('version'))
            lock_user(user)
            row = lock_giveaway(gid)
            if not row:
                return not_found()
            if action == 'draw' and row.status == 'drawn':
                db.session.rollback()
                return jsonify(giveaway=giveaway_json(row, user, True, True)), 200
            if row.version != requested_version:
                return conflict()
            if action == 'publish':
                if row.status != 'draft':
                    return conflict('Seul un brouillon peut être publié.')
                if row.ends_at <= now_ts():
                    raise ValueError('La date de clôture est passée. Modifiez le brouillon.')
                row.prizes = prize_snapshots(row.prizes)
                row.status, row.published_at = 'published', now_ts()
            elif action == 'close':
                if row.status != 'published':
                    return conflict('Seul un concours ouvert peut être clôturé.')
                row.status, row.closed_at = 'closed', now_ts()
            elif action == 'cancel':
                if row.status not in ('draft', 'published', 'closed'):
                    return conflict('Ce concours ne peut plus être annulé.')
                row.status, row.cancelled_at = 'cancelled', now_ts()
            else:
                if row.status not in ('published', 'closed'):
                    return conflict('Ce concours ne peut pas être tiré au sort.')
                if row.status == 'published' and now_ts() < row.ends_at:
                    return conflict('Attendez la date de fin ou clôturez explicitement les inscriptions avant le tirage.')
                if GiveawayEntry.query.filter_by(giveaway_id=gid, active=True, status='pending').count():
                    return conflict('Vérifiez toutes les inscriptions en attente avant le tirage.')
                entries = GiveawayEntry.query.filter_by(giveaway_id=gid, active=True, status='accepted').order_by(GiveawayEntry.id).all()
                if len(entries) < len(row.prizes):
                    return conflict('Il n’y a pas assez de participants acceptés pour attribuer tous les lots à des personnes distinctes.')
                gifts = app.extensions.get('nyx_gifts')
                if not gifts or not callable(gifts.get('issue_for_winner')):
                    db.session.rollback()
                    return jsonify(error='La création des cadeaux est temporairement indisponible. Réessayez le tirage.'), 503
                chosen = secrets.SystemRandom().sample(entries, len(row.prizes))
                for rank, (entry, prize) in enumerate(zip(chosen, row.prizes), 1):
                    winner = GiveawayWinner(giveaway_id=gid, entry_id=entry.id, user_id=entry.user_id,
                                                 telegram_id=entry.telegram_id, first_name=entry.first_name, username=entry.username,
                                                 rank=rank, prize=prize, notification_state='pending', notification_attempts=0,
                                                 notification_next_attempt=0, notification_lease_until=0)
                    db.session.add(winner)
                    db.session.flush()
                    # Gift creation and the immutable draw succeed or roll back together.
                    # The existing drawn replay returns above, without issuing old gifts.
                    gifts['issue_for_winner'](winner)
                row.status, row.drawn_at = 'drawn', now_ts()
                row.drawn_participant_count = len(entries)
                row.closed_at = row.closed_at or row.ends_at
            row.version += 1
            db.session.commit()
            return jsonify(giveaway=giveaway_json(row, user, True, True))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    @app.get('/api/admin/giveaways/<int:gid>/participants')
    def giveaway_participants(gid):
        try:
            if db.session.get(Giveaway, gid) is None:
                return not_found()
            raw_offset, raw_limit = request.args.get('offset', '0'), request.args.get('limit', '50')
            if not raw_offset.isdecimal() or not raw_limit.isdecimal():
                raise ValueError('Pagination invalide.')
            offset, limit = int(raw_offset), int(raw_limit)
            if offset > 1000000 or not 1 <= limit <= 100:
                raise ValueError('Pagination invalide.')
            status = request.args.get('status', 'all')
            if status not in ('all', 'accepted', 'pending', 'rejected', 'withdrawn'):
                raise ValueError('Filtre invalide.')
            query = GiveawayEntry.query.filter_by(giveaway_id=gid)
            if status == 'withdrawn':
                query = query.filter_by(active=False)
            elif status != 'all':
                query = query.filter_by(active=True, status=status)
            return jsonify(participants=[entry_json(row) for row in query.order_by(GiveawayEntry.joined_at, GiveawayEntry.id).offset(offset).limit(limit).all()],
                           total=query.count(), offset=offset, limit=limit)
        except (ValueError, TypeError) as exc:
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    @app.post('/api/admin/giveaways/<int:gid>/participants/<int:entry_id>/review')
    def giveaway_review(gid, entry_id):
        user = current_user()
        try:
            data = body({'decision', 'version'})
            requested_version = version(data.get('version'))
            if data.get('decision') not in ('accepted', 'rejected'):
                raise ValueError('Décision invalide.')
            lock_user(user)
            row = lock_giveaway(gid)
            if not row:
                return not_found()
            if row.status not in ('published', 'closed'):
                return conflict('Les inscriptions de ce concours ne peuvent plus être vérifiées.')
            entry = GiveawayEntry.query.filter_by(id=entry_id, giveaway_id=gid).first()
            if not entry:
                db.session.rollback()
                return jsonify(error='Inscription introuvable.'), 404
            if entry.version != requested_version:
                return conflict('Cette inscription a changé. Actualisez la liste.')
            if not entry.active or entry.status != 'pending':
                return conflict('Seule une inscription active en attente peut être vérifiée.')
            entry.status, entry.version = data['decision'], entry.version + 1
            entry.reviewed_at, entry.reviewed_by = now_ts(), user.id
            db.session.commit()
            return jsonify(participant=entry_json(entry), giveaway=giveaway_json(row, user, True, True))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    @app.post('/api/admin/giveaways/<int:gid>/winners/<int:winner_id>/retry')
    def giveaway_retry(gid, winner_id):
        user = current_user()
        try:
            body(set())
            lock_user(user)
            row = lock_giveaway(gid)
            if not row:
                return not_found()
            if row.status != 'drawn':
                return conflict('Le tirage doit être effectué avant de notifier les gagnants.')
            winner = GiveawayWinner.query.filter_by(id=winner_id, giveaway_id=gid).first()
            if not winner:
                db.session.rollback()
                return jsonify(error='Gagnant introuvable.'), 404
            if winner.user_id is None or winner.telegram_id is None:
                return conflict('Le compte du gagnant a été supprimé ; cette notification ne peut pas être renvoyée.')
            result = db.session.execute(update(GiveawayWinner).where(
                GiveawayWinner.id == winner_id, GiveawayWinner.giveaway_id == gid,
                GiveawayWinner.notification_state.in_(('blocked', 'failed')),
                GiveawayWinner.user_id.is_not(None), GiveawayWinner.telegram_id.is_not(None),
            ).values(notification_state='pending', notification_attempts=0, notification_next_attempt=now_ts(),
                     notification_lease_until=0, notification_lease_token=None, notification_error=None))
            if not result.rowcount:
                return conflict('Seule une notification bloquée ou en échec peut être réessayée.')
            db.session.commit()
            return jsonify(winner=winner_json(db.session.get(GiveawayWinner, winner_id, populate_existing=True)),
                           giveaway=giveaway_json(row, user, True, True))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    def purge_user(uid):
        """Caller holds the User lock. Retain draw ranks/prizes, erase contact snapshots."""
        ids = {row.giveaway_id for row in GiveawayEntry.query.filter_by(user_id=uid).all()}
        ids.update(row.giveaway_id for row in GiveawayWinner.query.filter_by(user_id=uid).all())
        for gid in sorted(ids):
            lock_giveaway(gid)
        GiveawayEntry.query.filter_by(user_id=uid).update(dict(user_id=None, telegram_id=None, first_name='', username='',
                                                             active=False, version=GiveawayEntry.version + 1), synchronize_session=False)
        GiveawayEntry.query.filter_by(reviewed_by=uid).update(dict(reviewed_by=None), synchronize_session=False)
        # Evaluate against the state at UPDATE time: a delivery finishing concurrently
        # must remain recorded as sent, even if an earlier ORM read saw "working".
        db.session.execute(update(GiveawayWinner).where(GiveawayWinner.user_id == uid).values(
            user_id=None, telegram_id=None, first_name='', username='',
            notification_state=case((GiveawayWinner.notification_state == 'sent', 'sent'), else_='blocked'),
            notification_error=case((GiveawayWinner.notification_state == 'sent', GiveawayWinner.notification_error), else_='Compte supprimé'),
            notification_lease_until=0, notification_lease_token=None,
        ).execution_options(synchronize_session=False))
        Giveaway.query.filter_by(creator_user_id=uid).update(dict(creator_user_id=None), synchronize_session=False)

    models = {'Giveaway': Giveaway, 'Entry': GiveawayEntry, 'Winner': GiveawayWinner, 'purge_user': purge_user}
    app.extensions['nyx_giveaways'] = models
    return models
