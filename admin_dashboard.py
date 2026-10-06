"""Read-only dashboard. No exchange-rate or fee assumptions."""
from datetime import datetime, timedelta, timezone
from flask import jsonify, request
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sales import PARIS, PAID_STATUSES


def bounds(period, now):
    if period == 'all':
        return None, None
    start = now.astimezone(PARIS).replace(hour=0, minute=0, second=0, microsecond=0)
    start -= timedelta(days={'today': 0, '7d': 6, '30d': 29}[period])
    return start.astimezone(timezone.utc), now


def install_dashboard(app, db, shop, Event, gifts, User, Product, require_admin):
    Order, Record, Payment, Preparation = (shop[k] for k in ('Order', 'PaymentRecord', 'Payment', 'Preparation'))

    @app.get('/api/admin/dashboard')
    def dashboard():
        if not require_admin():
            return jsonify(error='Interdit'), 403
        period = request.args.get('period', 'today')
        if period not in ('today', '7d', '30d', 'all'):
            return jsonify(error='Période invalide'), 400
        try:
            now = datetime.now(timezone.utc)
            start, end = bounds(period, now)
            paid = db.session.query(Order, Event).outerjoin(Event, and_(
                Event.external_order_id == Order.reference, Event.user_id == Order.user_id
            )).filter(Order.status.in_(PAID_STATUSES), ~gifts['order_clause'](Order.id))
            undated = paid.filter(Event.id.is_(None)).count()
            if start is not None:
                paid = paid.filter(Event.processed_at >= start, Event.processed_at <= end)
            # Aggregate by latest explicit method; legacy proofs indicate crypto,
            # never EUR net. Unknown payments stay in their own bucket.
            latest = db.session.query(Record.order_id, func.max(Record.revision).label('revision')).group_by(Record.order_id).subquery()
            methods = dict(db.session.query(Record.order_id, Record.method).join(latest, and_(
                Record.order_id == latest.c.order_id, Record.revision == latest.c.revision)).all())
            crypto_ids = {r[0] for r in db.session.query(Payment.order_id).distinct()}
            split = {key: {'orders': 0, 'gross_cents': 0} for key in ('crypto', 'other', 'unknown')}
            gross = count = 0
            for order, event in paid:
                method = methods.get(order.id, 'crypto' if order.id in crypto_ids else 'unknown')
                bucket = 'crypto' if method == 'crypto' else 'unknown' if method == 'unknown' else 'other'
                split[bucket]['orders'] += 1
                split[bucket]['gross_cents'] += order.total_cents
                gross += order.total_cents
                count += 1
            today, _ = bounds('today', now)
            created = Order.query
            if start is not None:
                created = created.filter(Order.created_at >= int(start.timestamp()), Order.created_at <= int(now.timestamp()))
            prepared = db.session.query(Preparation.order_id).filter(Preparation.order_id == Order.id).exists()
            low = Product.query.filter(Product.active.is_(True), Product.stock <= 5).order_by(Product.stock, Product.id).all()
            clients = User.query
            if start is not None:
                clients = clients.filter(User.created_at >= start, User.created_at <= end)
            response = jsonify(period=period, timezone='Europe/Paris', generated_at=int(now.timestamp()),
                gross_cents=gross, paid_orders=count, fees_cents=None, net_cents=None,
                financial_notice='Net indisponible : frais et règlement net en EUR non vérifiés.',
                undated_orders=undated, history_notice='Historique non vérifié : dates de confirmation manquantes.' if undated else None,
                payment_split=split, orders_in_period=created.count(), clients_in_period=clients.count(), clients=User.query.count(),
                orders_today=Order.query.filter(Order.created_at >= int(today.timestamp()), Order.created_at <= int(now.timestamp())).count(),
                preparing=Order.query.filter(Order.status.in_(('paid', 'gifted')), ~prepared).count(),
                payment_review=Order.query.filter_by(status='payment_review').count(),
                missing_tracking=Order.query.filter(Order.status.in_(('shipped', 'available', 'delivered')),
                    or_(Order.tracking_number.is_(None), func.trim(Order.tracking_number) == '')).count(),
                low_stock=[dict(id=p.id, name=p.name, format=p.format, stock=p.stock) for p in low],
                scope_notice='CA : paiements confirmés sur la période, cadeaux exclus. Commandes et nouveaux clients : date de création. Alertes : état actuel. Stock faible : 5 ou moins.')
            response.headers['Cache-Control'] = 'no-store'
            return response
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception('Dashboard indisponible')
            return jsonify(error='Dashboard temporairement indisponible. Réessayez.'), 503
