"""Payment accounting. Unknown settlement values stay NULL, never zero."""
import json
import time
from decimal import Decimal, InvalidOperation

import click
import requests
from flask import jsonify, request
from sqlalchemy import update, and_
from sqlalchemy.exc import SQLAlchemyError
from sales import PAID_STATUSES, PERIODS, _period_bounds
from datetime import datetime, timezone


def create_schema(db):
    """Add tables only; serialize PostgreSQL startup workers during DDL."""
    from sqlalchemy import text
    with db.engine.begin() as connection:
        if connection.dialect.name == 'postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(738194205)'))
        db.metadata.create_all(bind=connection, checkfirst=True)


def install_real_sales(app, db, shop, Event, gifts, require_admin):
    Order = shop['Order']

    class PaymentRecord(db.Model):
        __tablename__ = 'payment_record'
        id = db.Column(db.Integer, primary_key=True)
        order_id = db.Column(db.Integer, db.ForeignKey('shop_order.id'), unique=True, nullable=False)
        external_order_id = db.Column(db.String(40), nullable=False, index=True)
        payment_method = db.Column(db.String(40), nullable=False, default='unknown')
        payment_provider = db.Column(db.String(80))
        gross_eur = db.Column(db.Numeric(12, 2), nullable=False)
        fee_eur = db.Column(db.Numeric(12, 2))
        net_eur = db.Column(db.Numeric(12, 2))
        coin = db.Column(db.String(64))
        network = db.Column(db.String(80))
        value_coin = db.Column(db.Numeric(30, 12))
        value_forwarded_coin = db.Column(db.Numeric(30, 12))
        txid_in = db.Column(db.Text)
        txid_out = db.Column(db.Text)
        address_out = db.Column(db.Text)
        net_is_verified = db.Column(db.Boolean, nullable=False, default=False)
        status = db.Column(db.String(40), nullable=False, default='pending')
        paid_at = db.Column(db.BigInteger)
        created_at = db.Column(db.BigInteger, nullable=False, default=lambda: int(time.time()))
        updated_at = db.Column(db.BigInteger, nullable=False, default=lambda: int(time.time()))
        historical = db.Column(db.Boolean, nullable=False, default=False)
        evidence = db.Column(db.Text)
        revision = db.Column(db.Integer, nullable=False, default=0)

    class PaymentReceipt(db.Model):
        # One immutable record per signed transaction, including split payments.
        id = db.Column(db.Integer, primary_key=True)
        order_id = db.Column(db.Integer, db.ForeignKey('shop_order.id'), nullable=False, index=True)
        txid_in = db.Column(db.String(150), unique=True, nullable=False)
        payload = db.Column(db.JSON, nullable=False)
        received_at = db.Column(db.BigInteger, nullable=False)

    class PaymentAccountingAudit(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        order_id = db.Column(db.Integer, db.ForeignKey('shop_order.id'), nullable=False, index=True)
        revision = db.Column(db.Integer, nullable=False)
        payload = db.Column(db.JSON, nullable=False)
        created_at = db.Column(db.BigInteger, nullable=False)

    def invalidate(order):
        record = PaymentRecord.query.filter_by(order_id=order.id).first()
        if record:
            db.session.add(PaymentAccountingAudit(order_id=order.id, revision=record.revision,
                payload=dict(action='method_correction', evidence=record.evidence,
                             net_eur=str(record.net_eur), fee_eur=str(record.fee_eur)), created_at=int(time.time())))
            record.net_is_verified = False
            record.net_eur = record.fee_eur = None
            record.payment_method = shop['payment_record'](order)['method']
            record.revision += 1
            record.updated_at = int(time.time())
            apply_other(record, order)

    def apply_other(record, order):
        if record.payment_method in ('bank_transfer', 'paypal', 'cash', 'other') and not shop['Payment'].query.filter_by(order_id=order.id).first():
            record.net_eur = record.gross_eur
            record.fee_eur = Decimal('0')
            record.net_is_verified = True
            record.evidence = 'Règle Admin : autres moyens, brut = net'

    def ensure(order, historical=False):
        record = PaymentRecord.query.filter_by(order_id=order.id).first()
        if record is None:
            event = Event.query.filter_by(external_order_id=order.reference, user_id=order.user_id).first()
            stamp = event.processed_at if event else None
            if isinstance(stamp, datetime):
                stamp = int(stamp.replace(tzinfo=timezone.utc).timestamp()) if stamp.tzinfo is None else int(stamp.timestamp())
            record = PaymentRecord(order_id=order.id, external_order_id=order.reference,
                                   gross_eur=Decimal(order.total_cents) / 100,
                                   payment_method=shop['payment_record'](order)['method'],
                                   paid_at=stamp, historical=historical,
                                   status='paid' if order.status in PAID_STATUSES else 'pending')
            db.session.add(record)
            apply_other(record, order)
        return record

    def receipt(order, args):
        record = ensure(order)
        data = {k: args[k] for k in ('coin', 'value_coin', 'value_forwarded_coin', 'txid_in', 'address_out')}
        data['txid_out'] = args.get('txid_out')
        shares = json.loads(data['address_out'])
        share = next(Decimal(str(v)) for k, v in shares.items() if k.lower() == order.payout_wallet)
        merchant_coin = Decimal(data['value_forwarded_coin']) * share
        data['merchant_settled_coin'] = str(merchant_coin)
        data['settlement_difference_coin'] = str(Decimal(data['value_coin']) - merchant_coin)
        db.session.add(PaymentReceipt(order_id=order.id, txid_in=data['txid_in'], payload=data,
                                      received_at=int(time.time())))
        record.payment_provider = 'paygate.to'
        record.revision = (record.revision or 0) + 1
        # The hosted card checkout does not disclose the customer's actual method
        # or selected sub-provider. Crypto settlement alone proves neither.
        record.coin = data['coin']
        record.network = data['coin'].split('_', 1)[0] if '_' in data['coin'] else None
        record.value_coin = Decimal(data['value_coin'])
        record.value_forwarded_coin = Decimal(data['value_forwarded_coin'])
        record.txid_in, record.txid_out = data['txid_in'], data['txid_out']
        record.address_out = data['address_out']
        record.updated_at = int(time.time())

        record.status = 'received' if order.status not in PAID_STATUSES else 'paid'
        # Official callbacks contain no EUR settlement or historical FX rate.
        # Never treat USDC as EUR or use gross * forwarded / received.
        record.net_eur = record.fee_eur = None
        record.net_is_verified = False
        record.evidence = 'Callback PayGate signé ; valorisation EUR indisponible'

    def confirmed(order, method):
        record = ensure(order)
        record.payment_method = method
        record.status = 'paid'
        record.paid_at = int(time.time())
        record.updated_at = int(time.time())
        apply_other(record, order)

    def serialize(order, record):
        method = shop['payment_record'](order)['method']
        proof = shop['Payment'].query.filter_by(order_id=order.id).first()
        cents = lambda v: int(v * 100) if v is not None else None
        verified = bool(record and record.net_is_verified and record.payment_method == method)
        other_no_fee = method in ('bank_transfer', 'paypal', 'cash', 'other') and not proof
        verified = verified or other_no_fee
        return dict(reference=order.reference, payment_method=method,
                    payment_provider=(record.payment_provider if record else None) or ('paygate.to' if proof else None),
                    gross_cents=order.total_cents, fee_cents=0 if other_no_fee else cents(record.fee_eur) if verified else None,
                    net_cents=order.total_cents if other_no_fee else cents(record.net_eur) if verified else None, net_is_verified=verified,
                    net_label='Net vérifié' if verified else ('Net historique indisponible' if not record or record.historical else 'Net EUR indisponible'),
                    status=record.status if record else 'paid', paid_at=record.paid_at if record else None,
                    revision=record.revision if record else 0,
                    coin=record.coin if record else None, network=record.network if record else None,
                    value_coin=str(record.value_coin) if record and record.value_coin is not None else None,
                    value_forwarded_coin=str(record.value_forwarded_coin) if record and record.value_forwarded_coin is not None else None,
                    txid_in=record.txid_in if record else None, txid_out=record.txid_out if record else None,
                    address_out=record.address_out if record else None, evidence=record.evidence if record else None)

    @app.get('/api/shop/admin/sales/real')
    def real_sales():
        if not require_admin():
            return jsonify(error='Interdit'), 403
        period = request.args.get('period', 'all')
        if period not in PERIODS:
            return jsonify(error='Période invalide'), 400
        try:
            page = int(request.args.get('page', '1'))
            if page < 1:
                raise ValueError()
        except ValueError:
            return jsonify(error='Page invalide'), 400
        try:
            start, end = _period_bounds(period, datetime.now(timezone.utc))
            query = db.session.query(Order, PaymentRecord).outerjoin(PaymentRecord, PaymentRecord.order_id == Order.id).outerjoin(
                Event, and_(Event.external_order_id == Order.reference, Event.user_id == Order.user_id)).filter(
                    Order.status.in_(PAID_STATUSES), ~gifts['order_clause'](Order.id))
            if start:
                query = query.filter(Event.processed_at >= start, Event.processed_at < end)
            rows = [serialize(o, r) for o, r in query.order_by(Order.id.desc()).all()]
            def totals(items):
                known = [x for x in items if x['net_is_verified']]
                return dict(orders=len(items), gross_cents=sum(x['gross_cents'] for x in items),
                            fee_cents=sum(x['fee_cents'] for x in known), net_verified_cents=sum(x['net_cents'] for x in known),
                            verified_orders=len(known), unavailable_orders=len(items)-len(known),
                            unavailable_gross_cents=sum(x['gross_cents'] for x in items if not x['net_is_verified']))
            providers = sorted({x['payment_provider'] or 'Non traçable' for x in rows})
            return jsonify(period=period, metrics=totals(rows),
                           methods={k: totals([x for x in rows if ('crypto' if x['payment_method']=='crypto' else 'unknown' if x['payment_method']=='unknown' else 'other') == k]) for k in ('crypto','other','unknown')},
                           providers={p: totals([x for x in rows if (x['payment_provider'] or 'Non traçable') == p]) for p in providers},
                           orders=rows[(page-1)*50:page*50], page=page, pages=(len(rows)+49)//50)
        except SQLAlchemyError:
            db.session.rollback()
            return jsonify(error='Comptabilité temporairement indisponible'), 503

    @app.get('/api/shop/admin/orders/<reference>/accounting')
    def order_accounting(reference):
        if not require_admin():
            return jsonify(error='Interdit'), 403
        order = Order.query.filter_by(reference=reference).first_or_404()
        return jsonify(payment=serialize(order, PaymentRecord.query.filter_by(order_id=order.id).first()),
                       receipts=[dict(received_at=r.received_at, **r.payload) for r in PaymentReceipt.query.filter_by(order_id=order.id).all()],
                       audit=[dict(revision=r.revision, created_at=r.created_at, **r.payload) for r in PaymentAccountingAudit.query.filter_by(order_id=order.id).all()])

    @app.cli.command('payments-backfill')
    @click.option('--recover-status', is_flag=True, help='Lecture ponctuelle PayGate avec ipn_token ; aucun net EUR inventé.')
    def backfill(recover_status):
        count = recovered = 0
        for order in Order.query.filter(Order.status.in_(PAID_STATUSES), ~gifts['order_clause'](Order.id)).all():
            db.session.execute(update(Order).where(Order.id == order.id).values(status=Order.status))
            exists = PaymentRecord.query.filter_by(order_id=order.id).first()
            record = ensure(order, historical=True)
            count += exists is None
            proof = shop['Payment'].query.filter_by(order_id=order.id).first()
            if proof and record.payment_provider is None:
                record.payment_provider = 'paygate.to'
                record.coin, record.txid_in = proof.coin, proof.transaction_id
                record.value_coin = Decimal(proof.amount)
                record.evidence = 'Ancienne preuve locale ; net historique indisponible'
            if recover_status and order.ipn_token and not record.txid_out:
                try:
                    response = requests.get('https://api.paygate.to/control/payment-status.php', params={'ipn_token': order.ipn_token}, timeout=20)
                    response.raise_for_status()
                    data = response.json()
                    amount = Decimal(str(data.get('value_coin', 'NaN')))
                    if data.get('status') == 'paid' and amount.is_finite() and amount > 0 and isinstance(data.get('txid_out'), str) and isinstance(data.get('coin'), str):
                        record.payment_provider = 'paygate.to'
                        record.coin, record.txid_out, record.value_coin = data['coin'], data['txid_out'], amount
                        record.evidence = 'Statut récupéré par ipn_token ; net historique indisponible'
                        recovered += 1
                except (requests.RequestException, ValueError, InvalidOperation, AttributeError):
                    pass
            db.session.commit()
        click.echo(f'{count} ligne(s) ajoutée(s), {recovered} statut(s) récupéré(s). Aucun net historique estimé.')

    app.extensions['nyx_accounting'] = dict(PaymentRecord=PaymentRecord, PaymentReceipt=PaymentReceipt,
                                           receipt=receipt, confirmed=confirmed, invalidate=invalidate)
