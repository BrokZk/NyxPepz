"""Explicit bundle composition; order snapshots retain the purchased ingredients."""
from flask import jsonify, request
from sqlalchemy.exc import IntegrityError


def inventory_lines(lines):
    quantities = {}
    for line in lines:
        parts = line.get('components') if 'pack_id' in line else [line]
        for part in parts:
            pid = part['product_id']
            quantities[pid] = quantities.get(pid, 0) + part['quantity']
    return [{'product_id': pid, 'quantity': qty} for pid, qty in sorted(quantities.items())]


def install_packs(app, db, Product, Pack, Marker, require_admin):
    class PackComposition(db.Model):
        pack_id = db.Column(db.Integer, db.ForeignKey('promo_pack.id'), primary_key=True)
        components = db.Column(db.JSON, nullable=False)

    def composition(pack):
        row = db.session.get(PackComposition, pack.id)
        return row.components if row else []

    def serialize(pack):
        parts = composition(pack)
        items = []
        stock = 99 if parts and pack.active and pack.price > 0 else 0
        for part in parts:
            p = db.session.get(Product, part['product_id'])
            if not p or not p.active:
                stock = 0
            else:
                stock = min(stock, p.stock // part['quantity'])
            items.append({**part, 'name': p.name if p else 'Produit indisponible',
                          'format': p.format if p else ''})
        return dict(id=pack.id, title=pack.title, subtitle=pack.subtitle, price=pack.price,
                    image_url=pack.image_url, active=pack.active, sort_order=pack.sort_order,
                    components=items, stock=stock, purchasable=bool(parts) and pack.price > 0)

    def line(pid, qty):
        # Admin changes and checkout lock the same pack row on PostgreSQL.
        pack = Pack.query.filter_by(id=pid).with_for_update().populate_existing().first()
        if not pack or not pack.active:
            raise ValueError('Pack indisponible')
        data = serialize(pack)
        if not data['purchasable'] or not 0 < pack.price <= 100000 or data['stock'] < qty:
            raise ValueError('Un pack n’est plus disponible dans la quantité demandée')
        parts = [{**p, 'quantity': p['quantity'] * qty} for p in data['components']]
        description = ' + '.join(f"{p['quantity']} × {p['name']} {p['format']}" for p in data['components'])
        return dict(pack_id=pid, name=pack.title, format=description, quantity=qty,
                    unit_cents=pack.price * 100, line_cents=pack.price * 100 * qty, components=parts)

    def validate_parts(parts):
        if not isinstance(parts, list) or len(parts) > 20:
            raise ValueError('Composition invalide')
        seen = set()
        result = []
        for part in parts:
            if not isinstance(part, dict):
                raise ValueError('Composition invalide')
            pid, qty = part.get('product_id'), part.get('quantity')
            if type(pid) is not int or type(qty) is not int or not 1 <= qty <= 99 or pid in seen or not db.session.get(Product, pid):
                raise ValueError('Produit ou quantité invalide dans le pack')
            seen.add(pid)
            result.append(dict(product_id=pid, quantity=qty))
        return sorted(result, key=lambda x: x['product_id'])

    def save(pack, data):
        if not isinstance(data, dict):
            raise ValueError('Données pack invalides')
        for name, size in [('title', 140), ('subtitle', 220)]:
            value = data.get(name, getattr(pack, name) or '')
            if not isinstance(value, str) or len(value.strip()) > size or (name == 'title' and not value.strip()):
                raise ValueError('Titre ou description invalide')
            setattr(pack, name, value.strip())
        for name in ('price', 'sort_order'):
            value = data.get(name, getattr(pack, name) or 0)
            if type(value) is not int or not 0 <= value <= 100000:
                raise ValueError('Prix ou ordre invalide')
            setattr(pack, name, value)
        if 'active' in data:
            if type(data['active']) is not bool:
                raise ValueError('Statut invalide')
            pack.active = data['active']
        if 'image_url' in data:
            value = data['image_url']
            if value is not None and (not isinstance(value, str) or len(value) > 2048):
                raise ValueError('Image invalide')
            pack.image_url = value or None
        if 'components' in data:
            parts = validate_parts(data['components'])
            db.session.flush()
            row = db.session.get(PackComposition, pack.id)
            if row:
                row.components = parts
            else:
                db.session.add(PackComposition(pack_id=pack.id, components=parts))

    @app.get('/api/packs')
    def packs():
        rows = Pack.query.filter_by(active=True).order_by(Pack.sort_order, Pack.id).all()
        return jsonify([serialize(p) for p in rows if p.price > 0])

    @app.get('/api/admin/packs')
    def admin_packs():
        if not require_admin():
            return jsonify(error='Interdit'), 403
        return jsonify([serialize(p) for p in Pack.query.order_by(Pack.sort_order, Pack.id)])

    @app.post('/api/admin/packs')
    def admin_pack_create():
        if not require_admin():
            return jsonify(error='Interdit'), 403
        try:
            pack = Pack(active=True)
            db.session.add(pack)
            with db.session.no_autoflush:
                save(pack, request.get_json(silent=True))
            db.session.commit()
            return jsonify(id=pack.id), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400

    @app.route('/api/admin/packs/<int:pid>', methods=['PATCH', 'DELETE'])
    def admin_pack_item(pid):
        if not require_admin():
            return jsonify(error='Interdit'), 403
        pack = Pack.query.filter_by(id=pid).with_for_update().first()
        if not pack:
            return jsonify(error='Pack introuvable'), 404
        try:
            if request.method == 'DELETE':
                row = db.session.get(PackComposition, pid)
                if row:
                    db.session.delete(row)
                    db.session.flush()
                db.session.delete(pack)
            else:
                save(pack, request.get_json(silent=True))
            db.session.commit()
            return jsonify(ok=True)
        except ValueError as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400

    def seed():
        key = '2026-09-29-purchasable-packs-v1'
        if db.session.get(Marker, key):
            return
        known = {
            'Pack Reta 10 + GHK-CU': [('Retatrutide', '10 mg'), ('GHK-Cu', '50 mg')],
            'Pack Reta 15 + Cagri': [('Retatrutide', '15 mg'), ('Cagrilintide', '10 mg')],
        }
        descriptions = {'Pack Reta 10 + GHK-CU': 'Retatrutide 10 mg + GHK-CU',
                        'Pack Reta 15 + Cagri': 'Retatrutide 15 mg + Cagrilintide'}
        try:
            db.session.add(Marker(key=key))
            db.session.flush()
            for pack in Pack.query.all():
                if pack.title not in known or pack.subtitle != descriptions[pack.title] or db.session.get(PackComposition, pack.id):
                    continue
                parts = []
                for name, dose in known[pack.title]:
                    matches = [p for p in Product.query.all() if p.name.lower() == name.lower() and p.format == dose]
                    if len(matches) != 1:
                        break
                    parts.append(dict(product_id=matches[0].id, quantity=1))
                if len(parts) == len(known[pack.title]):
                    db.session.add(PackComposition(pack_id=pack.id, components=parts))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if not db.session.get(Marker, key):
                raise

    return {'line': line, 'seed': seed, 'Composition': PackComposition}
