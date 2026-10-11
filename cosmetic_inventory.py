"""Cosmetics inventory: server-owned, transactional reservations and idempotent edits."""
import time
from sqlalchemy import update

MAX_STOCK = 1000000


def install_cosmetic_inventory(app, db, Catalog, Order):
    class CosmeticStock(db.Model):
        cosmetic_id = db.Column(db.Integer, db.ForeignKey("cosmetic_catalog.id"), primary_key=True)
        available = db.Column(db.Integer, default=0, nullable=False)

    class CosmeticReservation(db.Model):
        order_id = db.Column(db.Integer, db.ForeignKey("shop_order.id"), primary_key=True)
        items = db.Column(db.JSON, nullable=False)
        active = db.Column(db.Boolean, default=True, nullable=False)

    class CosmeticStockChange(db.Model):
        key = db.Column(db.String(32), primary_key=True)
        cosmetic_id = db.Column(db.Integer, db.ForeignKey("cosmetic_catalog.id"), nullable=False)
        quantity = db.Column(db.Integer, nullable=False)
        changed_at = db.Column(db.BigInteger, default=lambda:int(time.time()), nullable=False)

    def row(pid):
        stock = CosmeticStock.query.filter_by(cosmetic_id=pid).with_for_update().populate_existing().first()
        if stock is None:
            stock = CosmeticStock(cosmetic_id=pid, available=0)
            db.session.add(stock)
            db.session.flush()
        return stock

    def availability(pid):
        return row(pid).available

    def check(pid, quantity):
        if availability(pid) < quantity:
            raise ValueError("RUPTURE DE STOCK ou quantité indisponible. Actualisez votre panier.")

    def reserve(order):
        items = sorted([dict(cosmetic_id=line["cosmetic_id"],quantity=line["quantity"])
                        for line in order.lines if line.get("kind")=="cosmetic"],key=lambda x:x["cosmetic_id"])
        if not items:
            return
        if db.session.get(CosmeticReservation,order.id):
            return
        for item in items:
            row(item["cosmetic_id"])
            count=db.session.execute(update(CosmeticStock).where(
                CosmeticStock.cosmetic_id==item["cosmetic_id"],CosmeticStock.available>=item["quantity"]
            ).values(available=CosmeticStock.available-item["quantity"]),execution_options={"synchronize_session":False}).rowcount
            if count!=1:
                raise ValueError("Un produit vient d'être épuisé. Vérifiez votre panier.")
        db.session.add(CosmeticReservation(order_id=order.id,items=items,active=True))

    def release(order):
        reservation=CosmeticReservation.query.filter_by(order_id=order.id).with_for_update().populate_existing().first()
        if not reservation or not reservation.active:
            return
        count=db.session.execute(update(CosmeticReservation).where(
            CosmeticReservation.order_id==order.id,CosmeticReservation.active==True
        ).values(active=False),execution_options={"synchronize_session":False}).rowcount
        if not count:return
        for item in sorted(reservation.items,key=lambda x:x["cosmetic_id"]):
            changed=db.session.execute(update(CosmeticStock).where(
                CosmeticStock.cosmetic_id==item["cosmetic_id"],CosmeticStock.available<=MAX_STOCK-item["quantity"]
            ).values(available=CosmeticStock.available+item["quantity"]),execution_options={"synchronize_session":False}).rowcount
            if changed!=1:
                raise ValueError("Stock incohérent lors de la restitution. Vérifiez-le avant de réessayer.")

    def ensure(order):
        reservation=CosmeticReservation.query.filter_by(order_id=order.id).with_for_update().populate_existing().first()
        # Orders predating this feature were never deducted from its stock.
        if not reservation or reservation.active:
            return
        for item in sorted(reservation.items,key=lambda x:x["cosmetic_id"]):
            count=db.session.execute(update(CosmeticStock).where(
                CosmeticStock.cosmetic_id==item["cosmetic_id"],CosmeticStock.available>=item["quantity"]
            ).values(available=CosmeticStock.available-item["quantity"]),execution_options={"synchronize_session":False}).rowcount
            if count!=1:
                raise ValueError("Paiement tardif : stock cosmétique insuffisant. Traitement manuel nécessaire.")
        reservation.active=True

    def set_available(pid, quantity, key):
        if type(quantity) is not int or not 0<=quantity<=MAX_STOCK:
            raise ValueError("Le stock doit être un entier entre 0 et 1 000 000.")
        product=db.session.get(Catalog,pid)
        if not product or not product.active:
            raise ValueError("Produit introuvable.")
        stock=row(pid)
        previous=db.session.get(CosmeticStockChange,key)
        if previous:
            if previous.cosmetic_id!=pid or previous.quantity!=quantity:
                raise ValueError("Cette modification de stock a déjà été utilisée.")
            return stock.available,True
        pending=CosmeticReservation.query.join(Order,Order.id==CosmeticReservation.order_id).filter(
            CosmeticReservation.active==True,Order.status.in_(("awaiting_payment","payment_review"))).all()
        returnable=sum(item["quantity"] for reservation in pending for item in reservation.items if item["cosmetic_id"]==pid)
        if quantity>MAX_STOCK-returnable:
            raise ValueError("Stock trop élevé compte tenu des commandes encore réservées.")
        db.session.add(CosmeticStockChange(key=key,cosmetic_id=pid,quantity=quantity))
        stock.available=quantity
        return quantity,False

    result={"Stock":CosmeticStock,"Reservation":CosmeticReservation,"Change":CosmeticStockChange,
            "row":row,"availability":availability,"check":check,"reserve":reserve,
            "release":release,"ensure":ensure,"set_available":set_available}
    app.extensions["cosmetic_inventory"]=result
    return result
