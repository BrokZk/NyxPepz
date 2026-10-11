"""Referral rewards: 10% of first paid goods, then 5%, with exact fractions."""
from datetime import datetime, timezone

UNITS_PER_POINT = 2000
MAX_POINTS = 2147483647
MAX_BASIS_CENTS = 10000000


def reward_units(paid_products_cents, first_paid):
    if type(paid_products_cents) is not int or not 0 <= paid_products_cents <= MAX_BASIS_CENTS:
        raise ValueError("Montant payé des produits invalide.")
    if type(first_paid) is not bool:
        raise ValueError("Historique de commande invalide.")
    # One cent gives .001 point at 10%, or .0005 point at 5%.
    return paid_products_cents * (2 if first_paid else 1)


def points_from_units(units):
    return units / UNITS_PER_POINT


def install_referral_rewards(app, db, User, ReferralOrderEvent):
    from sqlalchemy import update
    class ReferralBalance(db.Model):
        user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
        base_points = db.Column(db.Integer, nullable=False)
        earned_units = db.Column(db.BigInteger, default=0, nullable=False)

    class ReferralPercentageCredit(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        external_order_id = db.Column(db.String(128), unique=True, nullable=False)
        referred_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
        referrer_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
        paid_products_cents = db.Column(db.BigInteger, nullable=False)
        rate_percent = db.Column(db.Integer, nullable=False)
        points_units = db.Column(db.BigInteger, nullable=False)
        credited_at = db.Column(db.DateTime(timezone=True), default=lambda:datetime.now(timezone.utc), nullable=False)

    def credit(order_id, customer_id, referrer_id, paid_products_cents, first_paid):
        if referrer_id is None:
            return 0
        if customer_id == referrer_id:
            raise ValueError("Auto-parrainage interdit.")
        units = reward_units(paid_products_cents, first_paid)
        # Serialize percentage credits and preserve the historical integer balance.
        locked = db.session.execute(update(User).where(User.id == referrer_id).values(
            referral_points=User.referral_points), execution_options={"synchronize_session":False}).rowcount
        if locked != 1:
            raise ValueError("Parrain introuvable.")
        referrer = db.session.get(User,referrer_id)
        db.session.refresh(referrer)
        previous = ReferralPercentageCredit.query.filter_by(external_order_id=order_id).first()
        if previous:
            if previous.referred_user_id != customer_id or previous.referrer_user_id != referrer_id:
                raise ValueError("Cette commande appartient à un autre parrainage.")
            return 0
        legacy = ReferralOrderEvent.query.filter_by(external_order_id=order_id).first()
        if legacy:
            # Orders credited under the old rule are never retroactively recalculated.
            if legacy.referred_user_id != customer_id or legacy.referrer_user_id != referrer_id:
                raise ValueError("Historique de parrainage incohérent.")
            return 0
        balance = db.session.get(ReferralBalance,referrer_id)
        if balance is None:
            base = referrer.referral_points
            if type(base) is not int or not 0 <= base <= MAX_POINTS:
                raise ValueError("Solde de parrainage historique invalide.")
            balance = ReferralBalance(user_id=referrer_id,base_points=base,earned_units=0)
            db.session.add(balance)
        total = balance.base_points * UNITS_PER_POINT + balance.earned_units + units
        if total > MAX_POINTS * UNITS_PER_POINT:
            raise ValueError("Plafond de points de parrainage atteint.")
        balance.earned_units += units
        db.session.add(ReferralPercentageCredit(
            external_order_id=order_id,referred_user_id=customer_id,referrer_user_id=referrer_id,
            paid_products_cents=paid_products_cents,rate_percent=10 if first_paid else 5,points_units=units))
        db.session.add(ReferralOrderEvent(
            external_order_id=order_id,referred_user_id=customer_id,referrer_user_id=referrer_id))
        referrer.referral_points = total // UNITS_PER_POINT
        # No commit here: rewards share the order/payment transaction.
        return units

    def balance(user):
        row = db.session.get(ReferralBalance,user.id)
        if row:
            return points_from_units(row.base_points * UNITS_PER_POINT + row.earned_units)
        return user.referral_points

    def expected_whole(user_id):
        row = db.session.get(ReferralBalance,user_id)
        if row:
            return row.base_points + row.earned_units // UNITS_PER_POINT
        # Before the first percentage credit, keep existing historical points.
        return db.session.get(User,user_id).referral_points

    result = {"Balance":ReferralBalance,"Credit":ReferralPercentageCredit,
              "credit":credit,"balance":balance,"expected_whole":expected_whole}
    app.extensions["referral_rewards"] = result
    return result
