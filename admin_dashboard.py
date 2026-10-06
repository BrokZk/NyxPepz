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

    @app.get('/api/admin/dashboard/details')
    def dashboard_details():
        if not require_admin():
            return jsonify(error='Interdit'), 403
        metric = request.args.get('metric', '')
        period = request.args.get('period', 'today')
        allowed = ('gross', 'orders_today', 'orders_in_period', 'preparing', 'clients',
                   'clients_in_period', 'payment_review', 'low_stock', 'missing_tracking')
        try:
            page = int(request.args.get('page', '1'))
        except ValueError:
            return jsonify(error='Page invalide'), 400
        if metric not in allowed or period not in ('today', '7d', '30d', 'all') or page < 1:
            return jsonify(error='Filtre invalide'), 400
        try:
            now = datetime.now(timezone.utc)
            start, end = bounds(period, now)
            kind = 'orders'
            if metric in ('clients', 'clients_in_period'):
                kind = 'clients'
                query = User.query
                if metric == 'clients_in_period' and start is not None:
                    query = query.filter(User.created_at >= start, User.created_at <= end)
                query = query.order_by(User.created_at.desc(), User.id.desc())
            elif metric == 'low_stock':
                kind = 'products'
                query = Product.query.filter(Product.active.is_(True), Product.stock <= 5).order_by(Product.stock, Product.id)
            else:
                query = Order.query
                if metric == 'gross':
                    query = query.outerjoin(Event, and_(Event.external_order_id == Order.reference, Event.user_id == Order.user_id))
                    query = query.filter(Order.status.in_(PAID_STATUSES), ~gifts['order_clause'](Order.id))
                    if start is not None:
                        query = query.filter(Event.processed_at >= start, Event.processed_at <= end)
                elif metric in ('orders_today', 'orders_in_period'):
                    if metric == 'orders_today':
                        start, end = bounds('today', now)
                    if start is not None:
                        query = query.filter(Order.created_at >= int(start.timestamp()), Order.created_at <= int(end.timestamp()))
                elif metric == 'preparing':
                    prepared = db.session.query(Preparation.order_id).filter(Preparation.order_id == Order.id).exists()
                    query = query.filter(Order.status.in_(('paid', 'gifted')), ~prepared)
                elif metric == 'payment_review':
                    query = query.filter_by(status='payment_review')
                else:
                    query = query.filter(Order.status.in_(('shipped', 'available', 'delivered')),
                        or_(Order.tracking_number.is_(None), func.trim(Order.tracking_number) == ''))
                query = query.order_by(Order.created_at.desc(), Order.id.desc())
            total = query.count()
            pages = max(1, (total + 19) // 20)
            page = min(page, pages)
            rows = query.offset((page - 1) * 20).limit(20).all()
            if kind == 'clients':
                items = [dict(id=u.id, name=u.first_name or u.username or 'Membre', username=u.username,
                              telegram_id=str(u.telegram_id), points=u.loyalty_points,
                              created_at=u.created_at.isoformat() if u.created_at else None) for u in rows]
            elif kind == 'products':
                items = [dict(id=p.id, name=p.name, format=p.format, stock=p.stock, cat=p.category) for p in rows]
            else:
                owners = {u.id: u for u in User.query.filter(User.id.in_({o.user_id for o in rows})).all()}
                from shop import STATUSES
                items = []
                for order in rows:
                    owner = owners.get(order.user_id)
                    contact = order.contact or {}
                    items.append(dict(reference=order.reference, user_id=order.user_id,
                        name=' '.join(filter(None, (contact.get('first_name'), contact.get('last_name')))) or (owner.first_name if owner else None) or 'Client',
                        username=owner.username if owner else None, total_cents=order.total_cents,
                        status=order.status, status_label=STATUSES.get(order.status, order.status), created_at=order.created_at))
            response = jsonify(metric=metric, period=period, kind=kind, items=items, total=total, page=page, pages=pages,
                scope='Aujourd’hui · Europe/Paris' if metric == 'orders_today' else
                      'État actuel' if metric in ('preparing', 'payment_review', 'low_stock', 'missing_tracking', 'clients') else
                      'Période sélectionnée · Europe/Paris')
            response.headers['Cache-Control'] = 'no-store'
            return response
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception('Détail du Dashboard indisponible')
            return jsonify(error='Liste temporairement indisponible. Réessayez.'), 503

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
