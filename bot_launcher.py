"""The existing notification worker can also serve the single-button bot menu."""
import os
import secrets
import time
import requests
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError


def install_launcher(app, db):
    class TelegramLauncherState(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        offset = db.Column(db.BigInteger, nullable=False, default=0)
        lease_until = db.Column(db.BigInteger, nullable=False, default=0)
        owner = db.Column(db.String(64))

    configured = False

    def tick():
        nonlocal configured
        if os.environ.get('TELEGRAM_LAUNCHER_ENABLED') != '1':
            return
        token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        url = os.environ.get('SHOP_PUBLIC_URL', 'https://nyxpepz.onrender.com').rstrip('/')
        if not token or not url.startswith('https://'):
            return

        def call(method, data):
            response = requests.post('https://api.telegram.org/bot' + token + '/' + method, json=data, timeout=8)
            if response.status_code == 403 and method in ('sendMessage', 'editMessageReplyMarkup'):
                return None
            if response.status_code == 400:
                description = response.json().get('description', '').lower()
                if method == 'answerCallbackQuery' and ('query is too old' in description or 'query id is invalid' in description):
                    return None
                if method == 'editMessageReplyMarkup' and 'message is not modified' in description:
                    return None
                if method == 'editMessageReplyMarkup' and ('message to edit not found' in description or "message can't be edited" in description):
                    return call('sendMessage', {'chat_id': data['chat_id'], 'text': 'Ouvrez NyxPepz pour continuer.', 'reply_markup': data['reply_markup']})
            if response.status_code == 409:
                raise RuntimeError('Un autre bot utilise déjà la réception Telegram : arrêter l’ancien bot.')
            # Do not propagate requests exceptions containing the secret URL.
            if not response.ok:
                raise RuntimeError('Telegram a refusé la demande (' + str(response.status_code) + ')')
            body = response.json()
            if not body.get('ok'):
                raise RuntimeError('Demande Telegram refusée')
            return body.get('result')

        if not db.session.get(TelegramLauncherState, 1):
            try:
                db.session.add(TelegramLauncherState(id=1))
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
        owner = secrets.token_hex(20)
        acquired = db.session.execute(update(TelegramLauncherState).where(
            TelegramLauncherState.id == 1, TelegramLauncherState.lease_until < int(time.time())
        ).values(owner=owner, lease_until=int(time.time()) + 240)).rowcount
        db.session.commit()
        if not acquired:
            return
        keyboard = {'inline_keyboard': [[{'text': '🌙 Ouvrir NyxPepz', 'web_app': {'url': url}}]]}
        try:
            if not configured:
                # Do not remove an existing webhook: that requires stopping its owner first.
                info = call('getWebhookInfo', {})
                if info.get('url'):
                    raise RuntimeError('Un webhook Telegram est actif : arrêter l’ancien bot avant activation.')
                for scope in ('default', 'all_private_chats'):
                    for language in ('', 'fr', 'en'):
                        call('deleteMyCommands', {'scope': {'type': scope}, 'language_code': language})
                call('setChatMenuButton', {'menu_button': {'type': 'web_app', 'text': 'Ouvrir NyxPepz', 'web_app': {'url': url}}})
                configured = True
            state = db.session.get(TelegramLauncherState, 1)
            updates = call('getUpdates', {'offset': state.offset, 'limit': 5, 'timeout': 0,
                                          'allowed_updates': ['message', 'callback_query']})
            for event in updates:
                callback = event.get('callback_query')
                message = event.get('message') or (callback or {}).get('message') or {}
                chat = message.get('chat', {})
                if callback:
                    call('answerCallbackQuery', {'callback_query_id': callback['id'],
                         'text': 'Retrouvez toutes les fonctionnalités dans NyxPepz.'})
                    if chat.get('type') == 'private':
                        call('editMessageReplyMarkup', {'chat_id': chat['id'], 'message_id': message['message_id'],
                                                        'reply_markup': keyboard})
                elif chat.get('type') == 'private' and message.get('text'):
                    call('sendMessage', {'chat_id': chat['id'],
                         'text': ('🌙 Bienvenue chez NyxPepz !\n\n'
                                  '🔒 Pour votre sécurité, nous ne vous contacterons jamais en message privé '
                                  'pour prendre une commande ou vous demander un paiement.\n\n'
                                  '🛍️ Toutes les commandes passent exclusivement par notre application, '
                                  'accessible via le bouton « 🌙 Ouvrir NyxPepz » ci-dessous.\n\n'
                                  'Merci pour votre confiance 💙'),
                         'reply_markup': keyboard})
                db.session.execute(update(TelegramLauncherState).where(TelegramLauncherState.id == 1,
                    TelegramLauncherState.owner == owner).values(offset=event['update_id'] + 1))
                db.session.commit()
        except Exception as exc:
            db.session.rollback()
            # Never log raw requests exceptions: their URLs contain the bot token.
            app.logger.warning('Menu Telegram : %s', str(exc) if type(exc) is RuntimeError else type(exc).__name__)
        finally:
            db.session.execute(update(TelegramLauncherState).where(TelegramLauncherState.id == 1,
                TelegramLauncherState.owner == owner).values(lease_until=0, owner=None))
            db.session.commit()

    return tick
