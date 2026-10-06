"""Editorial protocols, preserving original documents through an additive import."""
import json
from pathlib import Path
from urllib.parse import urlsplit
import click
from flask import jsonify, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


def install_protocols(app, db, Marker, require_admin):
    class Protocol(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        title = db.Column(db.String(200), nullable=False)
        category = db.Column(db.String(100), nullable=False)
        description = db.Column(db.Text, nullable=False, default='')
        content = db.Column(db.Text, nullable=False, default='')
        steps = db.Column(db.JSON, nullable=False, default=list)
        image_url = db.Column(db.Text, nullable=False, default='')
        active = db.Column(db.Boolean, nullable=False, default=True)
        sort_order = db.Column(db.Integer, nullable=False, default=0)
        legacy = db.Column(db.JSON, nullable=False, default=dict)

    def source():
        return json.loads((Path(app.root_path) / 'static/protocols.json').read_text(encoding='utf-8'))

    def serialize(p):
        return dict(p.legacy, id=p.id, title=p.title, category=p.category, description=p.description,
                    content=p.content, steps=p.steps, image_url=p.image_url, active=p.active, sort_order=p.sort_order)

    def migrate():
        key = 'protocols-editorial-import-v1'
        if db.session.get(Marker, key):
            return False
        try:
            db.session.add(Marker(key=key))
            db.session.flush()  # concurrent starts serialize on the unique marker
            data = source()
            labels = {c['id']: c['label'] for c in data['categories']}
            for i, entry in enumerate(data['entries']):
                db.session.add(Protocol(title=entry['title'], category=labels.get(entry['category'], entry['category']),
                    sort_order=i, legacy=entry))
            db.session.commit()
            return True
        except IntegrityError:
            db.session.rollback()
            if db.session.get(Marker, key):
                return False
            raise
        except Exception:
            db.session.rollback()
            raise

    @app.cli.command('protocols-migrate')
    def migrate_command():
        Protocol.__table__.create(db.engine, checkfirst=True)
        click.echo('Protocoles importés.' if migrate() else 'Migration déjà appliquée.')

    def validate(payload):
        if not isinstance(payload, dict):
            raise ValueError('Objet JSON attendu')
        allowed = {'title', 'category', 'description', 'content', 'steps', 'image_url', 'active', 'sort_order'}
        if payload.keys() - allowed:
            raise ValueError('Champ inconnu')
        result = {}
        for key, value in payload.items():
            if key in ('title', 'category', 'description', 'content', 'image_url'):
                limit = {'title': 200, 'category': 100, 'image_url': 2048}.get(key, 50000)
                if not isinstance(value, str) or len(value) > limit:
                    raise ValueError('Texte invalide : ' + key)
                if key in ('title', 'category') and not value.strip():
                    raise ValueError('Titre et catégorie obligatoires')
                if key == 'image_url' and value:
                    url = urlsplit(value)
                    if not (value.startswith('/static/') and not url.netloc) and not (url.scheme == 'https' and url.hostname and not url.username and not url.password):
                        raise ValueError('Image : URL HTTPS ou chemin /static/ attendu')
            elif key == 'active' and type(value) is not bool:
                raise ValueError('Visibilité invalide')
            elif key == 'sort_order' and (type(value) is not int or not -100000 <= value <= 100000):
                raise ValueError('Ordre invalide')
            elif key == 'steps':
                if not isinstance(value, list) or len(value) > 50 or any(
                    not isinstance(s, dict) or set(s) != {'title', 'text'} or
                    not isinstance(s['title'], str) or not isinstance(s['text'], str) or
                    len(s['title']) > 200 or len(s['text']) > 10000 for s in value):
                    raise ValueError('Étapes invalides')
            result[key] = value.strip() if key in ('title', 'category') else value
        return result

    @app.get('/api/protocols')
    def public_protocols():
        entries = [serialize(p) for p in Protocol.query.filter_by(active=True).order_by(Protocol.sort_order, Protocol.id)]
        categories = [dict(id=c, label=c, fullLabel=c, icon='◇') for c in dict.fromkeys(e['category'] for e in entries)]
        return jsonify(entries=entries, categories=categories, sources=source()['sources'])

    @app.route('/api/admin/protocols', methods=['GET', 'POST'])
    @app.route('/api/admin/protocols/<int:pid>', methods=['GET', 'PATCH', 'DELETE'])
    def admin_protocols(pid=None):
        if not require_admin():
            return jsonify(error='Interdit'), 403
        try:
            p = db.session.get(Protocol, pid) if pid is not None else None
            if pid is not None and p is None:
                return jsonify(error='Protocole introuvable'), 404
            if request.method == 'GET':
                response = jsonify(serialize(p) if p else [serialize(row) for row in Protocol.query.order_by(Protocol.sort_order, Protocol.id)])
                response.headers['Cache-Control'] = 'no-store'
                return response
            if request.method == 'DELETE':
                db.session.delete(p)
                db.session.commit()
                return jsonify(ok=True)
            values = validate(request.get_json(silent=True))
            if request.method == 'POST':
                if not {'title', 'category'} <= values.keys():
                    raise ValueError('Titre et catégorie obligatoires')
                p = Protocol(**values)
                db.session.add(p)
            else:
                for key, value in values.items():
                    setattr(p, key, value)
                if 'steps' in values:
                    p.legacy = {key: value for key, value in p.legacy.items()
                                if key not in ('mix', 'concentration', 'start', 'then', 'rhythm', 'blockLabels')}
            db.session.commit()
            return jsonify(serialize(p)), 201 if request.method == 'POST' else 200
        except ValueError as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception('Enregistrement des protocoles indisponible')
            return jsonify(error='Base de données temporairement indisponible'), 503

    return {'Model': Protocol, 'migrate': migrate}
