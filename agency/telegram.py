"""Telegram bridge: customers write to a bot, the agency answers through it.

Two loops. One long-polls Telegram for new messages and turns each into a
ticket; the other delivers finished answers. Only what the agency would send
anyway reaches the customer: replies that passed the guard, and the notice
that a person will take over. Drafts and shadow answers stay inside.

The bot token lives in `.env` (TELEGRAM_BOT_TOKEN) and is never logged.
"""
import json
import logging
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agency import support

LOG = logging.getLogger(__name__)
WELCOME = ('Salam! Bu, nümunə mağaza «Bazarım» üçün Söz Agentliyinin demo dəstək botudur.\n\n'
           'Sualınızı yazın — cavab yalnız mağazanın yazılı qaydalarına əsaslanır və hər cümlə '
           'göndərilməzdən əvvəl o qaydalarla yoxlanılır. Qaydalarda cavabı olmayan suallar əməkdaşa ötürülür.\n\n'
           'Qeyd: mesajınız cavab hazırlamaq üçün AI provayderinə göndərilir. Şəxsi məlumat yazmayın.')
TABLE = ('CREATE TABLE IF NOT EXISTS telegram(job_id TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, '
         'delivered INTEGER NOT NULL DEFAULT 0, created_at TEXT)')


def token_from(root):
    """TELEGRAM_BOT_TOKEN from this project's .env only, or None.

    Deliberately not from the process environment: a token left there by
    another project would let this server long-poll someone else's bot and
    swallow its messages.
    """
    env = Path(root) / '.env'
    if env.exists():
        for line in env.read_text(encoding='utf-8-sig').splitlines():
            if line.strip().startswith('TELEGRAM_BOT_TOKEN='):
                return line.split('=', 1)[1].strip().strip('"').strip("'") or None
    return None


class TelegramBridge:
    def __init__(self, agency, token, api=None):
        self.agency, self.token = agency, token
        self.api = api or self._call
        self.username, self.error = None, None
        with agency.lock, agency.db:
            agency.db.execute(TABLE)
        self.offset = agency.setting('telegram_offset', 0)

    def _call(self, method, params):
        request = Request(f'https://api.telegram.org/bot{self.token}/{method}', data=json.dumps(params).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=params.get('timeout', 0) + 15) as response:
                data = json.loads(response.read(2_000_000))
        except HTTPError as exc:
            # Never echo the URL: it contains the token.
            raise RuntimeError(f'Telegram HTTP {exc.code} qaytardı.') from None
        if not data.get('ok'):
            raise RuntimeError(str(data.get('description') or 'Telegram xətası')[:200])
        return data['result']

    def status(self):
        return dict(username=self.username, error=self.error,
                    link=f'https://t.me/{self.username}' if self.username else None)

    def hello(self):
        self.username = self.api('getMe', {}).get('username')
        return self.username

    def poll(self, timeout=25):
        """Turn new Telegram messages into tickets."""
        updates = self.api('getUpdates', {'offset': self.offset, 'timeout': timeout, 'allowed_updates': ['message']})
        for update in updates:
            self.offset = max(self.offset, update['update_id'] + 1)
            message = update.get('message') or {}
            chat, text = (message.get('chat') or {}).get('id'), (message.get('text') or '').strip()
            if not chat or not text:
                continue
            if text.startswith(('/start', '/help')):
                self.api('sendMessage', {'chat_id': chat, 'text': WELCOME})
                continue
            if text.startswith('/'):
                continue
            try:
                job = self.agency.submit_ticket(text[:2000], source='telegram')
            except ValueError as exc:
                self.api('sendMessage', {'chat_id': chat, 'text': str(exc)})
                continue
            with self.agency.lock, self.agency.db:
                self.agency.db.execute('INSERT OR IGNORE INTO telegram VALUES (?, ?, 0, datetime("now"))', (job, chat))
        if updates:
            with self.agency.lock, self.agency.db:
                self.agency.db.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', ('telegram_offset', json.dumps(self.offset)))
        return len(updates)

    def deliver(self):
        """Send answers that are final. Drafts wait for approval; shadow answers never go out."""
        with self.agency.lock:
            rows = self.agency._all('SELECT t.job_id, t.chat_id, j.status, j.result FROM telegram t '
                                    'JOIN jobs j ON j.id = t.job_id WHERE t.delivered = 0')
        sent = 0
        for row in rows:
            result = json.loads(row['result'] or '{}')
            if row['status'] == 'göndərildi':
                text = result.get('message')
            elif row['status'] == 'insana ötürüldü':
                text = result.get('message') or f'{support.GREETING} {support.HANDOFF}'
            elif row['status'] == 'kölgə':
                text = None  # shadow mode: drafted for comparison, never sent
            else:
                continue  # queued, working, or a draft awaiting approval
            if text:
                self.api('sendMessage', {'chat_id': row['chat_id'], 'text': text})
                sent += 1
            with self.agency.lock, self.agency.db:
                self.agency.db.execute('UPDATE telegram SET delivered = 1 WHERE job_id = ?', (row['job_id'],))
        return sent

    def start(self, stop):
        """Run both loops in daemon threads until `stop` is set."""
        def guarded(work, idle):
            backoff = 1
            while not stop.is_set():
                try:
                    work()
                    self.error, backoff = None, 1
                    stop.wait(idle)
                except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
                    self.error = str(exc)[:200]
                    LOG.warning('Telegram: %s', self.error)
                    stop.wait(min(60, backoff))
                    backoff *= 2
        try:
            self.hello()
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as exc:
            self.error = str(exc)[:200]
        threads = [threading.Thread(target=guarded, args=(self.poll, 0), daemon=True),
                   threading.Thread(target=guarded, args=(self.deliver, 1.0), daemon=True)]
        for thread in threads:
            thread.start()
        return threads
