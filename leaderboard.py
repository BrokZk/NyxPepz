"""Monthly rankings from earned points, without exposing customer balances."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import jsonify, request
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import SQLAlchemyError


PARIS = ZoneInfo('Europe/Paris')
PAGE_SIZE = 50
PAID_STATUSES = ('paid', 'shipped', 'available', 'delivered')
MONTH_NAMES = (
    'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
    'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
)


def _month_bounds(now):
    """UTC limits of the current Paris calendar month, including DST changes."""
    local = now.astimezone(PARIS)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start.replace(year=start.year + 1, month=1) if start.month == 12
           else start.replace(month=start.month + 1))
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def install_leaderboard(app, db, User, ConfirmedOrderEvent, shop, gifts, current_user):
    Order = shop['Order']
    Event = ConfirmedOrderEvent

    def response(payload, status=200):
        result = jsonify(payload)
        result.headers['Cache-Control'] = 'no-store'
        return result, status

    @app.get('/api/leaderboard')
    def monthly_leaderboard():
        try:
            if not current_user():
                return response({'error': 'Non authentifié'}, 401)
            try:
                page = int(request.args.get('page', '1'))
            except (TypeError, ValueError):
                return response({'error': 'Page invalide.'}, 400)
            if page < 1:
                return response({'error': 'Page invalide.'}, 400)

            now = datetime.now(timezone.utc)
            local = now.astimezone(PARIS)
            start, end = _month_bounds(now)
            # A spent reward or an admin balance adjustment must not rewrite
            # this month's ranking. Only positive, confirmed earned events count.
            score = func.sum(Event.loyalty_points).label('earned_points')
            reached_at = func.max(Event.processed_at).label('reached_at')
            rankings = db.session.query(
                User.id, User.username, User.first_name, score, reached_at,
            ).join(Event, Event.user_id == User.id).outerjoin(
                Order, Order.reference == Event.external_order_id,
            ).filter(
                Event.loyalty_points > 0,
                Event.processed_at >= start,
                Event.processed_at < end,
                # Retain legitimate historical confirmations from outside the
                # shop; matched shop orders must belong to the same customer.
                or_(Order.id.is_(None), and_(
                    Order.user_id == Event.user_id,
                    Order.status.in_(PAID_STATUSES),
                    ~gifts['order_clause'](Order.id),
                )),
            ).group_by(User.id, User.username, User.first_name)

            total = rankings.count()
            pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            page = min(page, pages)
            offset = (page - 1) * PAGE_SIZE
            rows = rankings.order_by(
                score.desc(), reached_at.asc(), User.id.asc(),
            ).offset(offset).limit(PAGE_SIZE).all()
            # Keep this allowlist identical for customer and administrator
            # sessions: no score, balance, user ID or transaction details.
            return response({
                'entries': [
                    {'rank': offset + index + 1,
                     'name': row.username or row.first_name or 'Membre'}
                    for index, row in enumerate(rows)
                ],
                'period': local.strftime('%Y-%m'),
                'period_label': f'{MONTH_NAMES[local.month - 1]} {local.year}',
                'next_reset_at': int(end.timestamp()),
                'page': page,
                'pages': pages,
                'total': total,
                'has_next': page < pages,
            })
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception('Lecture du classement mensuel indisponible')
            result, status = response({
                'error': 'Le classement est temporairement indisponible. Réessayez.',
            }, 503)
            result.headers['Retry-After'] = '1'
            return result, status
