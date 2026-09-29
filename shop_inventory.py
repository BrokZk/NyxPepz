"""One-time, reviewed migration of the old bot's stock into the app."""
import json
import os
import re
from urllib.parse import quote
import click
from sqlalchemy import update


def install_inventory(app, db, Product, CatalogUpdate, shop):
    def normalize(value):
        return re.sub(r'[^a-z0-9]', '', str(value).lower())

    def mapping(rows):
        if not rows or rows[0] != ['ID', 'Nom', 'Prix', 'Stock']:
            raise ValueError('Les colonnes de Produits doivent être ID, Nom, Prix, Stock')
        source = []
        for row in rows[1:]:
            if not row or not any(row):
                continue
            if len(row) < 4 or not str(row[3]).isdigit():
                raise ValueError('Une ligne de stock est incomplète ou invalide')
            stock = int(row[3])
            if stock > 1000000:
                raise ValueError('Stock trop élevé')
            source.append((normalize(row[1]), row[1], stock, row[2]))
        result, problems = [], []
        for product in Product.query.order_by(Product.id):
            names = [product.name]
            aliases = {'retatrutide': 'Reta', 'melanotan1': 'Mt1', 'melanotan2': 'Mt2', 'glowstack': 'Glow', 'klowstack': 'Klow'}
            if normalize(product.name) in aliases:
                names.append(aliases[normalize(product.name)])
            candidates = {normalize(name + (product.format or '')) for name in names}
            if normalize(product.name) == 'wolverinestack':
                candidates.add('wolverinestack')
            matches = [row for row in source if row[0] in candidates]
            if len(matches) != 1:
                problems.append(f'{product.name} {product.format}: correspondance absente ou ambiguë')
            else:
                match = matches[0]
                result.append({'id': product.id, 'name': product.name, 'format': product.format,
                    'stock': match[2], 'previous_stock': product.stock, 'app_price': product.price, 'sheet_price': match[3]})
        return result, problems

    @app.cli.command('shop-import-stock')
    @click.option('--apply', is_flag=True, help='Appliquer la reprise unique avant la première commande de l’app.')
    def import_stock(apply):
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        if os.environ.get('SHOP_ENABLED') == '1':
            raise click.ClickException('Fermez d’abord les nouvelles commandes : SHOP_ENABLED=0.')
        key = 'shop-stock-import-v1'
        if db.session.get(CatalogUpdate, key) or shop['Order'].query.first():
            raise click.ClickException('Reprise déjà faite ou commandes existantes : ne pas réimporter les stocks du bot.')
        try:
            credentials = service_account.Credentials.from_service_account_file(os.environ.get('GOOGLE_SERVICE_ACCOUNT_FILE', '/etc/secrets/google-service-account.json'), scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
            sheet = os.environ.get('GOOGLE_SHEET_ID', '')
            if not sheet:
                raise ValueError('Google Sheet non configuré')
            response = AuthorizedSession(credentials).get('https://sheets.googleapis.com/v4/spreadsheets/' + quote(sheet, safe='') + '/values/Produits!A1:D1000', timeout=20)
            response.raise_for_status()
            rows, problems = mapping(response.json().get('values', []))
            for row in rows:
                click.echo(f"{row['name']} {row['format']}: stock {row['previous_stock']} → {row['stock']} ; prix app {row['app_price']} €, Sheets {row['sheet_price']} € (prix non modifié)")
            for problem in problems:
                click.echo(problem)
            if problems:
                raise ValueError('Corrigez les correspondances avant la reprise ; aucun stock modifié.')
            if apply:
                db.session.add(CatalogUpdate(key=key))
                db.session.flush()
                for row in rows:
                    db.session.execute(update(Product).where(Product.id == row['id']).values(stock=row['stock']))
                db.session.commit()
                click.echo('Stocks repris. Le stock de l’app devient la référence pour ses nouvelles commandes.')
            else:
                db.session.rollback()
                click.echo('Simulation uniquement. Aucune donnée modifiée.')
        except Exception as exc:
            db.session.rollback()
            raise click.ClickException(str(exc) if isinstance(exc, ValueError) else type(exc).__name__) from None

    shop['map_inventory'] = mapping
