"""Read-only sales totals from confirmed shop payments, in integer cents."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import jsonify, request
from sqlalchemy import and_, case, func
from sqlalchemy.exc import SQLAlchemyError


PARIS = ZoneInfo('Europe/Paris')
PERIODS = ('all', 'today', 'month', 'year')
PAID_STATUSES = ('paid', 'shipped', 'available', 'delivered')


def _period_bounds(period, now):
    """Return half-open UTC boundaries for a Paris calendar period."""
    if period == 'all':
        return None, None
    local = now.astimezone(PARIS)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'today':
        end = start + timedelta(days=1)
    elif period == 'month':
        start = start.replace(day=1)
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    else:
        start = start.replace(month=1, day=1)
        end = start.replace(year=start.year + 1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def install_sales(app, db, shop, ConfirmedOrderEvent, gifts, require_admin):
    Order = shop['Order']
    Event = ConfirmedOrderEvent

    @app.get('/api/shop/admin/sales')
    def admin_sales():
        try:
            if not require_admin():
                return jsonify(error='Interdit'), 403
            period = request.args.get('period', 'all')
            if period not in PERIODS:
                return jsonify(error='Période invalide.'), 400

            now = datetime.now(timezone.utc)
            start, end = _period_bounds(period, now)
            # Use payment confirmation time, never basket creation time. Old
            # paid orders without a matching event still belong to all-time CA.
            in_period = True if start is None else and_(Event.processed_at >= start, Event.processed_at < end)

            def total(value):
                return func.coalesce(func.sum(case((in_period, value), else_=0)), 0)

            row = db.session.query(
                total(1),
                total(Order.total_cents),
                total(Order.subtotal_cents - Order.discount_cents),
                total(Order.shipping_cents),
                total(Order.discount_cents),
                func.coalesce(func.sum(case((Event.id.is_(None), 1), else_=0)), 0),
            ).select_from(Order).outerjoin(Event, and_(
                Event.external_order_id == Order.reference,
                Event.user_id == Order.user_id,
            )).filter(
                Order.status.in_(PAID_STATUSES),
                ~gifts['order_clause'](Order.id),
            ).one()

            count, paid, products, shipping, discount, undated = (int(value) for value in row)
            return jsonify(
                period=period,
                timezone='Europe/Paris',
                generated_at=int(now.timestamp()),
                start_at=int(start.timestamp()) if start is not None else None,
                end_at=int(end.timestamp()) if end is not None else None,
                metrics=dict(orders=count, total_cents=paid, products_cents=products,
                             shipping_cents=shipping, discount_cents=discount,
                             average_cents=(paid + count // 2) // count if count else 0),
                undated_orders=undated,
            )
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception('Lecture du chiffre d’affaires indisponible')
            response = jsonify(error='Le suivi des ventes est temporairement indisponible. Réessayez.')
            response.headers['Retry-After'] = '1'
            return response, 503
