"""The existing notification worker can also serve the single-button bot menu."""
import os
import re
import secrets
import time
import requests
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

WELCOME_TEXT = ('🌙 Bienvenue chez NyxPepz !\n\n'
                '🔒 Pour votre sécurité, nous ne vous contacterons jamais en message privé '
                'pour prendre une commande ou vous demander un paiement.\n\n'
                '🛍️ Toutes les commandes passent exclusivement par notre application, '
                'accessible via le bouton « 🌙 Ouvrir NyxPepz » ci-dessous.\n\n'
                'Merci pour votre confiance 💙')


def is_group_start(text, username):
    """Accept this bot's /start, with an optional deep-link argument."""
    command = re.match(r'^/start(?:@([A-Za-z0-9_]+))?(?:\s|$)', text or '', re.IGNORECASE)
    return bool(command and (not command.group(1) or command.group(1).lower() == username.lower()))


class TelegramRetryAfter(RuntimeError):
    def __init__(self, seconds):
        super().__init__('Telegram demande une pause avant la prochaine tentative.')
        self.seconds = seconds


def install_launcher(app, db):
    class TelegramLauncherState(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        offset = db.Column(db.BigInteger, nullable=False, default=0)
        lease_until = db.Column(db.BigInteger, nullable=False, default=0)
        owner = db.Column(db.String(64))

    class TelegramMenuGuard(db.Model):
        # Separate table: existing launcher state needs no column migration.
        key = db.Column(db.String(160), primary_key=True)
        next_allowed = db.Column(db.BigInteger, nullable=False, default=0)
        last_update_id = db.Column(db.BigInteger, nullable=False, default=-1)

    def reserve_reply(chat, update_id):
        # Persist before sending: an uncertain network result must not resend the
        # same welcome. The user can retry /start after the cooldown.
        key = bot_username + ':' + str(chat['id'])
        now = int(time.time())
        row = db.session.get(TelegramMenuGuard, key)
        if row is None:
            row = TelegramMenuGuard(key=key, next_allowed=0, last_update_id=-1)
            db.session.add(row)
        if update_id <= row.last_update_id or now < row.next_allowed:
            return False
        row.last_update_id = update_id
        row.next_allowed = now + (300 if chat.get('type') in ('group', 'supergroup') else 30)
        db.session.commit()
        return True

    configured = False
    bot_username = ''
    has_main_app = False

    def tick():
        nonlocal configured, bot_username, has_main_app
        if os.environ.get('TELEGRAM_LAUNCHER_ENABLED') != '1':
            return
        token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        url = os.environ.get('SHOP_PUBLIC_URL', 'https://nyxpepz.onrender.com').rstrip('/')
        if not token or not url.startswith('https://'):
            return

        pause = db.session.get(TelegramMenuGuard, 'api-pause')
        if pause and pause.next_allowed > int(time.time()):
            return

        def call(method, data):
            response = requests.post('https://api.telegram.org/bot' + token + '/' + method, json=data, timeout=8)
            if response.status_code == 429:
                try:
                    seconds = max(1, int(response.json().get('parameters', {}).get('retry_after', 60)))
                except (TypeError, ValueError, AttributeError):
                    seconds = 60
                raise TelegramRetryAfter(seconds)
            if response.status_code == 403 and method in ('sendMessage', 'editMessageReplyMarkup'):
                return None
            if response.status_code == 400:
                description = response.json().get('description', '').lower()
                if method == 'answerCallbackQuery' and ('query is too old' in description or 'query id is invalid' in description):
                    return None
                if method == 'sendMessage' and isinstance(data.get('chat_id'), int) and data['chat_id'] < 0:
                    # Closed/deleted topics or missing send rights must not block the
                    # update queue and private starts for everybody else.
                    if any(reason in description for reason in ('topic_closed', 'message thread not found',
                            'not enough rights to send', 'have no rights to send', 'chat_write_forbidden')):
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
                identity = call('getMe', {})
                bot_username = identity.get('username', '')
                if not re.fullmatch(r'[A-Za-z0-9_]+', bot_username):
                    raise RuntimeError('Le nom public du bot Telegram est introuvable.')
                has_main_app = bool(identity.get('has_main_web_app'))
                for scope in ('default', 'all_private_chats'):
                    for language in ('', 'fr', 'en'):
                        call('deleteMyCommands', {'scope': {'type': scope}, 'language_code': language})
                call('setChatMenuButton', {'menu_button': {'type': 'web_app', 'text': 'Ouvrir NyxPepz', 'web_app': {'url': url}}})
                for language in ('', 'fr', 'en'):
                    call('setMyCommands', {'scope': {'type': 'all_group_chats'}, 'language_code': language,
                         'commands': [{'command': 'start', 'description': 'Ouvrir NyxPepz'}]})
                configured = True
            state = db.session.get(TelegramLauncherState, 1)
            updates = call('getUpdates', {'offset': state.offset, 'limit': 5, 'timeout': 0,
                                          'allowed_updates': ['message', 'callback_query']})
            for event in updates:
                # Renew ownership before another external operation.
                owned = db.session.execute(update(TelegramLauncherState).where(
                    TelegramLauncherState.id == 1, TelegramLauncherState.owner == owner,
                    TelegramLauncherState.lease_until >= int(time.time())
                ).values(lease_until=int(time.time()) + 240)).rowcount
                db.session.commit()
                if not owned:
                    break
                callback = event.get('callback_query')
                message = event.get('message') or (callback or {}).get('message') or {}
                chat = message.get('chat', {})
                if callback:
                    call('answerCallbackQuery', {'callback_query_id': callback['id'],
                         'text': 'Retrouvez toutes les fonctionnalités dans NyxPepz.'})
                    if chat.get('type') == 'private' and reserve_reply(chat, event['update_id']):
                        call('editMessageReplyMarkup', {'chat_id': chat['id'], 'message_id': message['message_id'],
                                                        'reply_markup': keyboard})
                elif (chat.get('type') == 'private'
                      and is_group_start(message.get('text'), bot_username)
                      and reserve_reply(chat, event['update_id'])):
                    call('sendMessage', {'chat_id': chat['id'],
                         'text': WELCOME_TEXT,
                         'reply_markup': keyboard})
                elif (chat.get('type') in ('group', 'supergroup')
                      and is_group_start(message.get('text'), bot_username)
                      and reserve_reply(chat, event['update_id'])):
                    # web_app buttons are private-chat only. Telegram's main-app
                    # link opens the app in a group; otherwise use the private bot.
                    link = 'https://t.me/' + bot_username + ('?startapp=group' if has_main_app else '?start=group')
                    text = WELCOME_TEXT
                    if not has_main_app:
                        text += '\n\nLe bouton ouvre le bot en privé : appuyez sur Démarrer, puis sur Ouvrir NyxPepz.'
                    payload = {'chat_id': chat['id'], 'text': text,
                               'reply_markup': {'inline_keyboard': [[{'text': '🌙 Ouvrir NyxPepz', 'url': link}]]}}
                    if message.get('is_topic_message') and isinstance(message.get('message_thread_id'), int):
                        payload['message_thread_id'] = message['message_thread_id']
                    call('sendMessage', payload)
                db.session.execute(update(TelegramLauncherState).where(TelegramLauncherState.id == 1,
                    TelegramLauncherState.owner == owner).values(offset=event['update_id'] + 1))
                db.session.commit()
        except TelegramRetryAfter as exc:
            db.session.rollback()
            pause = db.session.get(TelegramMenuGuard, 'api-pause')
            if pause is None:
                pause = TelegramMenuGuard(key='api-pause')
                db.session.add(pause)
            pause.next_allowed = int(time.time()) + exc.seconds
            db.session.commit()
            app.logger.warning('Menu Telegram : pause demandée par Telegram (%s secondes)', exc.seconds)
        except Exception as exc:
            db.session.rollback()
            # Never log raw requests exceptions: their URLs contain the bot token.
            app.logger.warning('Menu Telegram : %s', str(exc) if type(exc) is RuntimeError else type(exc).__name__)
        finally:
            db.session.execute(update(TelegramLauncherState).where(TelegramLauncherState.id == 1,
                TelegramLauncherState.owner == owner).values(lease_until=0, owner=None))
            db.session.commit()

    return tick

