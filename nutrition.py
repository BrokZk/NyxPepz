"""Private nutrition journal, with estimates independent from the shop."""
import calendar
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from flask import jsonify, request
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError


def load_food_catalog(path):
    """Keep source nutrition values on the server; the browser only sends an ID."""
    with Path(path).open(encoding='utf-8') as stream:
        return json.load(stream)


def install_nutrition(app, db, current_user, WeightEntry):
    class NutritionProfile(db.Model):
        user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)
        data = db.Column(db.JSON, nullable=False)
        version = db.Column(db.Integer, nullable=False, default=1)

    class NutritionDay(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
        day = db.Column(db.Date, nullable=False)
        targets = db.Column(db.JSON, nullable=True)
        complete = db.Column(db.Boolean, nullable=False, default=False)
        version = db.Column(db.Integer, nullable=False, default=0)
        __table_args__ = (db.UniqueConstraint('user_id', 'day', name='uq_nutrition_day'),)

    class NutritionEntry(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
        client_id = db.Column(db.String(36), nullable=False)
        day = db.Column(db.Date, nullable=False)
        meal = db.Column(db.String(12), nullable=False)
        food = db.Column(db.JSON, nullable=False)
        grams = db.Column(db.Numeric(12, 3), nullable=False)
        original = db.Column(db.JSON, nullable=False)
        version = db.Column(db.Integer, nullable=False, default=1)
        __table_args__ = (
            db.UniqueConstraint('user_id', 'client_id', name='uq_nutrition_client'),
            db.Index('ix_nutrition_entry_day', 'user_id', 'day'),
        )

    class NutritionFavorite(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
        entry_id = db.Column(db.Integer, nullable=False)
        food = db.Column(db.JSON, nullable=False)
        __table_args__ = (db.UniqueConstraint('user_id', 'entry_id', name='uq_nutrition_favorite'),)

    class NutritionDeletedEntry(db.Model):
        # Only the opaque request ID survives an entry deletion, never its food data.
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
        client_id = db.Column(db.String(36), nullable=False)
        __table_args__ = (db.UniqueConstraint('user_id', 'client_id', name='uq_nutrition_deleted_client'),)

    meal_names = ('breakfast', 'lunch', 'dinner', 'snack')
    activity_factors = {'sedentary': 1.2, 'light': 1.375, 'moderate': 1.55, 'high': 1.725}
    profile_fields = {'version', 'age', 'height_cm', 'weight_kg', 'sex', 'activity', 'goal',
                      'standard_calculation_ok', 'protein_mode', 'custom_kcal', 'custom_protein_g'}

    def failure():
        db.session.rollback()
        return jsonify(error='Nutrition temporairement indisponible. Réessayez.'), 503

    def require_body(allowed):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) - set(allowed):
            raise ValueError('Données invalides.')
        return data

    def number(value, low, high, nullable=False):
        if value is None and nullable:
            return None
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise ValueError('Valeur numérique invalide.')
        if isinstance(value, str) and not re.fullmatch(r'\d{1,8}(?:[.,]\d{1,3})?', value.strip()):
            raise ValueError('Saisissez un nombre positif, avec trois décimales maximum.')
        try:
            result = Decimal(str(value).strip().replace(',', '.'))
        except (InvalidOperation, ValueError):
            raise ValueError('Valeur numérique invalide.')
        if not result.is_finite() or not Decimal(str(low)) <= result <= Decimal(str(high)):
            raise ValueError('Valeur hors plage.')
        return float(result.quantize(Decimal('.001'), rounding=ROUND_HALF_UP))

    def valid_day(value):
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('Date invalide.')
        result = date.fromisoformat(value)
        if not 1900 <= result.year <= 2100:
            raise ValueError('Date hors plage.')
        return result

    def valid_version(value, new=False):
        if type(value) is not int or value < (0 if new else 1):
            raise ValueError('Version manquante. Actualisez la page.')
        return value

    def text(value, limit=180):
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError('Nom d’aliment invalide.')
        return value.strip()

    def lock_user(user):
        # One writer per account, including first-day creation and completion.
        # This also prevents profile changes/entry creation racing account deletion.
        db.session.execute(update(type(user)).where(type(user).id == user.id).values(id=user.id))

    @app.before_request
    def nutrition_guard():
        if not request.path.startswith('/api/nutrition'):
            return
        if not current_user():
            return jsonify(error='Ouvrez l’application depuis votre compte Telegram.'), 401
        if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return
        origin = request.headers.get('Origin')
        if origin:
            try:
                parsed = urlsplit(origin)
                same_host = parsed.scheme in ('http', 'https') and parsed.netloc.lower() == request.host.lower()
            except ValueError:
                same_host = False
            if not same_host:
                return jsonify(error='Origine de la requête refusée.'), 403

    @app.after_request
    def nutrition_private(response):
        if request.path.startswith('/api/nutrition'):
            response.headers['Cache-Control'] = 'private, no-store'
            response.vary.add('Cookie')
        return response

    def estimate(profile):
        if profile is None:
            return None
        p = profile.data
        bmi = p['weight_kg'] / (p['height_cm'] / 100) ** 2
        result = dict(maintenance_kcal=None, kcal_target=None, protein_target_g=None,
                      planned_deficit_kcal=None, bmi=round(bmi, 1), notice='', method='manual')
        eligible = p['standard_calculation_ok'] and p['age'] <= 80 and 18.5 <= bmi <= 40
        notices = []
        if eligible:
            base = 10 * p['weight_kg'] + 6.25 * p['height_cm'] - 5 * p['age'] + (5 if p['sex'] == 'male' else -161)
            maintenance = int(round(base * activity_factors[p['activity']] / 10) * 10)
            floor = 1800 if p['sex'] == 'male' else 1500
            result['maintenance_kcal'] = maintenance
            result['method'] = 'Mifflin–St Jeor × activité (estimation)'
            if maintenance >= floor:
                target = maintenance
                if p['goal'] == 'gentle_loss' and bmi >= 25:
                    target = max(floor, int(round(maintenance * .9 / 10) * 10))
                elif p['goal'] == 'gentle_loss':
                    notices.append('Le calcul automatique conserve un objectif de maintien pour cet IMC.')
                result['kcal_target'] = target
            else:
                notices.append('Aucun objectif calorique automatique : faites définir votre repère par un professionnel.')
            result['protein_target_g'] = round(p['weight_kg'] * (.83 if p['protein_mode'] == 'standard' else 1.2))
        else:
            notices.append('Le calcul automatique ne s’applique pas à ce profil. Le journal reste disponible ; vous pouvez saisir des repères convenus avec un professionnel.')
        if p['custom_kcal'] is not None:
            result['kcal_target'] = p['custom_kcal']
            notices.append('Objectif calorique saisi manuellement.')
        if p['custom_protein_g'] is not None:
            result['protein_target_g'] = p['custom_protein_g']
        if result['maintenance_kcal'] is not None and result['kcal_target'] is not None:
            result['planned_deficit_kcal'] = result['maintenance_kcal'] - result['kcal_target']
        result['notice'] = ' '.join(notices)
        return result

    def profile_json(row):
        return None if row is None else {**row.data, 'version': row.version}

    def current_targets(uid):
        return estimate(db.session.get(NutritionProfile, uid))

    def latest_weight(uid):
        row = WeightEntry.query.filter_by(user_id=uid).order_by(WeightEntry.created_at.desc(), WeightEntry.id.desc()).first()
        if not row:
            return None
        when = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
        return {'weight': row.weight_kg, 'date': when.isoformat()}

    @app.route('/api/nutrition/profile', methods=['GET', 'PUT'])
    def nutrition_profile():
        user = current_user()
        try:
            if request.method == 'PUT':
                data = require_body(profile_fields)
                version = valid_version(data.get('version'), True)
                if type(data.get('age')) is not int or not 18 <= data['age'] <= 100:
                    raise ValueError('Le calcul est réservé aux adultes de 18 à 100 ans.')
                if data.get('sex') not in ('female', 'male') or data.get('activity') not in activity_factors:
                    raise ValueError('Choisissez les paramètres du calcul et votre activité.')
                if data.get('goal') not in ('maintain', 'gentle_loss') or data.get('protein_mode') not in ('standard', 'active'):
                    raise ValueError('Objectif invalide.')
                if type(data.get('standard_calculation_ok')) is not bool:
                    raise ValueError('Précisez si le calcul standard convient à votre situation.')
                values = {key: data[key] for key in ('age', 'sex', 'activity', 'goal', 'protein_mode', 'standard_calculation_ok')}
                values.update(height_cm=number(data.get('height_cm'), 100, 250), weight_kg=number(data.get('weight_kg'), 30, 350),
                              custom_kcal=number(data.get('custom_kcal'), 1500, 5000, True),
                              custom_protein_g=number(data.get('custom_protein_g'), 20, 300, True))
                lock_user(user)
                row = db.session.get(NutritionProfile, user.id, populate_existing=True)
                if (row.version if row else 0) != version:
                    db.session.rollback()
                    return jsonify(error='Le profil a changé. Actualisez avant de le modifier.'), 409
                if row:
                    row.data, row.version = values, row.version + 1
                else:
                    row = NutritionProfile(user_id=user.id, data=values, version=1)
                    db.session.add(row)
                db.session.commit()
            else:
                row = db.session.get(NutritionProfile, user.id)
            return jsonify(profile=profile_json(row), latest_weight=latest_weight(user.id), estimate=estimate(row))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    def day_row(uid, day, create=False):
        row = NutritionDay.query.filter_by(user_id=uid, day=day).first()
        if row is None and create:
            row = NutritionDay(user_id=uid, day=day, targets=current_targets(uid), complete=False, version=0)
            db.session.add(row)
            db.session.flush()
        return row

    def totals(entries):
        kcal, protein = Decimal(0), Decimal(0)
        incomplete = False
        for row in entries:
            ratio = Decimal(str(row.grams)) / 100
            kcal += ratio * Decimal(str(row.food['kcal_per_100g']))
            if row.food['protein_per_100g'] is None:
                incomplete = True
            else:
                protein += ratio * Decimal(str(row.food['protein_per_100g']))
        return {'kcal': float(kcal.quantize(Decimal('.1'), rounding=ROUND_HALF_UP)),
                'protein_g': float(protein.quantize(Decimal('.1'), rounding=ROUND_HALF_UP)),
                'protein_incomplete': incomplete}

    def entry_json(row):
        nutrients = totals([row])
        return {'id': row.id, 'client_id': row.client_id, 'date': row.day.isoformat(), 'meal': row.meal,
                **row.food, 'grams': float(row.grams), 'kcal': nutrients['kcal'],
                'protein_g': None if nutrients['protein_incomplete'] else nutrients['protein_g'], 'version': row.version}

    def day_json(uid, day, row=None, entries=None, include_entries=True):
        if entries is None:
            entries = NutritionEntry.query.filter_by(user_id=uid, day=day).order_by(NutritionEntry.id).all()
        if row is None:
            row = day_row(uid, day)
        targets = row.targets if row else current_targets(uid)
        summary = totals(entries)
        deficit = None
        if row and row.complete and targets and targets.get('maintenance_kcal') is not None:
            deficit = round(targets['maintenance_kcal'] - summary['kcal'], 1)
        result = {'date': day.isoformat(), 'version': row.version if row else 0, 'complete': bool(row and row.complete),
                  'targets': targets, 'totals': summary, 'estimated_deficit_kcal': deficit}
        if include_entries:
            result['entries'] = [entry_json(entry) for entry in entries]
        return result

    @app.route('/api/nutrition/day', methods=['GET', 'POST'])
    def nutrition_day():
        user = current_user()
        try:
            if request.method == 'GET':
                return jsonify(day_json(user.id, valid_day(request.args.get('date'))))
            data = require_body({'date', 'version', 'complete', 'refresh_targets'})
            day = valid_day(data.get('date'))
            version = valid_version(data.get('version'), True)
            if type(data.get('complete')) is not bool:
                raise ValueError('Statut de journée invalide.')
            refresh_targets = data.get('refresh_targets', False)
            if type(refresh_targets) is not bool or (refresh_targets and data['complete']):
                raise ValueError('Actualisez les repères uniquement sur une journée ouverte.')
            # Allow the current calendar day in all inhabited UTC offsets.
            if data['complete'] and day > datetime.now(timezone.utc).date() + timedelta(days=1):
                raise ValueError('Une journée future ne peut pas être terminée.')
            lock_user(user)
            row = day_row(user.id, day)
            if (row.version if row else 0) != version:
                db.session.rollback()
                return jsonify(error='La journée a changé. Actualisez avant de continuer.'), 409
            if refresh_targets and row and row.complete:
                db.session.rollback()
                return jsonify(error='Une journée terminée conserve ses repères. Rouvrez-la avant de les modifier.'), 409
            if data['complete'] and not NutritionEntry.query.filter_by(user_id=user.id, day=day).first():
                raise ValueError('Ajoutez au moins un aliment avant de terminer la journée.')
            row = row or day_row(user.id, day, True)
            if refresh_targets:
                row.targets = current_targets(user.id)
            row.complete, row.version = data['complete'], row.version + 1
            db.session.commit()
            return jsonify(day_json(user.id, day, row))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    def food_snapshot(data):
        food_id = data.get('food_id')
        if food_id is not None:
            if not isinstance(food_id, str) or len(food_id) > 120:
                raise ValueError('Aliment inconnu.')
            catalog = load_food_catalog(Path(app.root_path) / 'static' / 'nutrition-foods.json')
            item = next((item for item in catalog if item.get('id') == food_id), None)
            if not item:
                raise ValueError('Aliment inconnu. Actualisez la recherche.')
            if item.get('kcal_per_100g') is None:
                raise ValueError('L’énergie de cet aliment n’est pas renseignée. Saisissez les valeurs de son étiquette.')
            return {'food_id': food_id, 'name': text(item.get('name'), 400),
                    'kcal_per_100g': number(item.get('kcal_per_100g'), 0, 1000),
                    'protein_per_100g': number(item.get('protein_per_100g'), 0, 100, True),
                    'state': str(item.get('state', ''))[:100], 'source': str(item.get('source', 'Ciqual'))[:120],
                    'source_url': str(item.get('source_url', ''))[:500], 'source_code': str(item.get('source_code', ''))[:100]}
        return {'food_id': None, 'name': text(data.get('name')),
                'kcal_per_100g': number(data.get('kcal_per_100g'), 0, 1000),
                'protein_per_100g': number(data.get('protein_per_100g'), 0, 100, True),
                'state': '', 'source': 'etiquette', 'source_url': '', 'source_code': ''}

    def mutation_key(data, day, grams):
        # Replay compares the original request even if its food source changed.
        base = {'date': day.isoformat(), 'meal': data['meal'], 'food_id': data.get('food_id'), 'grams': grams}
        if data.get('food_id') is None:
            base.update(name=text(data.get('name')), kcal_per_100g=number(data.get('kcal_per_100g'), 0, 1000),
                        protein_per_100g=number(data.get('protein_per_100g'), 0, 100, True))
        return base

    def reopen(uid, day):
        row = day_row(uid, day, True)
        row.complete, row.version = False, row.version + 1

    @app.post('/api/nutrition/entries')
    def nutrition_entry_create():
        user = current_user()
        try:
            data = require_body({'client_id', 'date', 'meal', 'food_id', 'name', 'grams', 'kcal_per_100g', 'protein_per_100g', 'source'})
            client_id = str(UUID(data.get('client_id', '')))
            day = valid_day(data.get('date'))
            grams = number(data.get('grams'), .1, 3000)
            if data.get('meal') not in meal_names:
                raise ValueError('Choisissez un repas.')
            original = mutation_key(data, day, grams)
            lock_user(user)
            if NutritionDeletedEntry.query.filter_by(user_id=user.id, client_id=client_id).first():
                db.session.rollback()
                return jsonify(error='Cette saisie a été supprimée. Créez un nouvel ajout pour la réenregistrer.'), 409
            existing = NutritionEntry.query.filter_by(user_id=user.id, client_id=client_id).first()
            if existing:
                db.session.rollback()
                if existing.original != original:
                    return jsonify(error='Cette saisie a déjà été reçue avec un autre contenu. Actualisez.'), 409
                return jsonify(entry=entry_json(existing)), 200
            row = NutritionEntry(user_id=user.id, client_id=client_id, day=day, meal=data['meal'],
                                 grams=grams, food=food_snapshot(data), original=original, version=1)
            db.session.add(row)
            reopen(user.id, day)
            db.session.commit()
            return jsonify(entry=entry_json(row)), 201
        except (ValueError, TypeError, AttributeError) as exc:
            db.session.rollback()
            return jsonify(error=str(exc) or 'Saisie invalide.'), 400
        except (OSError, json.JSONDecodeError):
            db.session.rollback()
            return jsonify(error='Catalogue alimentaire indisponible. Vous pouvez saisir les valeurs de l’étiquette.'), 503
        except SQLAlchemyError:
            return failure()

    @app.route('/api/nutrition/entries/<int:entry_id>', methods=['PATCH', 'DELETE'])
    def nutrition_entry_change(entry_id):
        user = current_user()
        try:
            data = require_body({'version', 'grams', 'meal'} if request.method == 'PATCH' else {'version'})
            version = valid_version(data.get('version'))
            lock_user(user)
            row = NutritionEntry.query.filter_by(id=entry_id, user_id=user.id).first()
            if not row:
                db.session.rollback()
                return jsonify(error='Aliment introuvable.'), 404
            if row.version != version:
                db.session.rollback()
                return jsonify(error='Cet aliment a changé sur un autre appareil. Actualisez.'), 409
            if request.method == 'PATCH':
                if set(data) == {'version'}:
                    raise ValueError('Indiquez une quantité ou un repas.')
                if 'grams' in data:
                    row.grams = number(data['grams'], .1, 3000)
                if 'meal' in data:
                    if data['meal'] not in meal_names:
                        raise ValueError('Choisissez un repas.')
                    row.meal = data['meal']
                row.version += 1
            reopen(user.id, row.day)
            if request.method == 'DELETE':
                db.session.add(NutritionDeletedEntry(user_id=user.id, client_id=row.client_id))
                db.session.delete(row)
            db.session.commit()
            return jsonify(ok=True) if request.method == 'DELETE' else jsonify(entry=entry_json(row))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    @app.get('/api/nutrition/history')
    def nutrition_history():
        user = current_user()
        try:
            month = request.args.get('month', '')
            if not re.fullmatch(r'\d{4}-\d{2}', month):
                raise ValueError('Mois invalide.')
            start = valid_day(month + '-01')
            end = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
            days = NutritionDay.query.filter(NutritionDay.user_id == user.id, NutritionDay.day.between(start, end)).order_by(NutritionDay.day).all()
            entries = NutritionEntry.query.filter(NutritionEntry.user_id == user.id, NutritionEntry.day.between(start, end)).order_by(NutritionEntry.id).all()
            grouped = {}
            for entry in entries:
                grouped.setdefault(entry.day, []).append(entry)
            return jsonify(days=[day_json(user.id, row.day, row, grouped.get(row.day, []), False) for row in days])
        except (ValueError, TypeError) as exc:
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    def reusable_food(row):
        return {**row.food, 'grams': float(row.grams), 'entry_id': row.id}

    @app.get('/api/nutrition/recent')
    def nutrition_recent():
        try:
            rows = NutritionEntry.query.filter_by(user_id=current_user().id).order_by(NutritionEntry.id.desc()).limit(150).all()
            foods, seen = [], set()
            for row in rows:
                key = json.dumps(row.food, ensure_ascii=False, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    foods.append(reusable_food(row))
                if len(foods) == 20:
                    break
            return jsonify(foods=foods)
        except SQLAlchemyError:
            return failure()

    @app.route('/api/nutrition/favorites', methods=['GET', 'POST'])
    def nutrition_favorites():
        user = current_user()
        try:
            if request.method == 'POST':
                data = require_body({'entry_id'})
                if type(data.get('entry_id')) is not int:
                    raise ValueError('Aliment invalide.')
                lock_user(user)
                entry = NutritionEntry.query.filter_by(user_id=user.id, id=data['entry_id']).first()
                if not entry:
                    db.session.rollback()
                    return jsonify(error='Aliment introuvable.'), 404
                favorite = NutritionFavorite.query.filter_by(user_id=user.id, entry_id=entry.id).first()
                created = favorite is None
                if created:
                    if NutritionFavorite.query.filter_by(user_id=user.id).count() >= 200:
                        raise ValueError('La limite de 200 favoris est atteinte.')
                    favorite = NutritionFavorite(user_id=user.id, entry_id=entry.id, food=reusable_food(entry))
                    db.session.add(favorite)
                db.session.commit()
                return jsonify(favorite={**favorite.food, 'id': favorite.id}), 201 if created else 200
            rows = NutritionFavorite.query.filter_by(user_id=user.id).order_by(NutritionFavorite.id.desc()).all()
            return jsonify(foods=[{**row.food, 'id': row.id} for row in rows])
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    @app.delete('/api/nutrition/favorites/<int:favorite_id>')
    def nutrition_favorite_delete(favorite_id):
        try:
            user = current_user()
            lock_user(user)
            row = NutritionFavorite.query.filter_by(id=favorite_id, user_id=user.id).first()
            if not row:
                db.session.rollback()
                return jsonify(error='Favori introuvable.'), 404
            db.session.delete(row)
            db.session.commit()
            return jsonify(ok=True)
        except SQLAlchemyError:
            return failure()

    @app.get('/api/nutrition/export')
    def nutrition_export():
        try:
            uid = current_user().id
            profile = db.session.get(NutritionProfile, uid)
            entries = NutritionEntry.query.filter_by(user_id=uid).order_by(NutritionEntry.day, NutritionEntry.id).all()
            days = NutritionDay.query.filter_by(user_id=uid).order_by(NutritionDay.day).all()
            grouped = {}
            for entry in entries:
                grouped.setdefault(entry.day, []).append(entry)
            favorites = NutritionFavorite.query.filter_by(user_id=uid).order_by(NutritionFavorite.id).all()
            response = jsonify(format_version=1, exported_at=datetime.now(timezone.utc).isoformat(),
                               profile=profile_json(profile), entries=[entry_json(row) for row in entries],
                               days=[day_json(uid, row.day, row, grouped.get(row.day, []), False) for row in days],
                               favorites=[{**row.food, 'id': row.id} for row in favorites])
            response.headers['Content-Disposition'] = 'attachment; filename="nyxpepz-nutrition.json"'
            return response
        except SQLAlchemyError:
            return failure()

    def purge_user(uid, keep_request_ids=False):
        # Caller owns the transaction; shared weights deliberately remain separate.
        if keep_request_ids:
            existing = {row.client_id for row in NutritionDeletedEntry.query.filter_by(user_id=uid).all()}
            for row in NutritionEntry.query.filter_by(user_id=uid).all():
                if row.client_id not in existing:
                    db.session.add(NutritionDeletedEntry(user_id=uid, client_id=row.client_id))
            db.session.flush()
        models = [NutritionFavorite, NutritionEntry, NutritionDay, NutritionProfile]
        if not keep_request_ids:
            models.insert(0, NutritionDeletedEntry)
        for model in models:
            model.query.filter_by(user_id=uid).delete(synchronize_session=False)

    @app.delete('/api/nutrition')
    def nutrition_delete():
        try:
            data = require_body({'confirm'})
            if data.get('confirm') is not True:
                raise ValueError('Confirmez la suppression des données Nutrition.')
            user = current_user()
            lock_user(user)
            purge_user(user.id, keep_request_ids=True)
            db.session.commit()
            return jsonify(ok=True)
        except (ValueError, TypeError) as exc:
            return jsonify(error=str(exc)), 400
        except SQLAlchemyError:
            return failure()

    models = {'Profile': NutritionProfile, 'Day': NutritionDay, 'Entry': NutritionEntry,
              'Favorite': NutritionFavorite, 'DeletedEntry': NutritionDeletedEntry, 'purge_user': purge_user}
    app.extensions['nyx_nutrition'] = models
    return models
