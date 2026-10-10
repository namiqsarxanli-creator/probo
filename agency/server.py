"""Local HTTP API and panel for Probo.

Same protections as the studio: loopback only, Host and Origin checks,
a per-process CSRF token on every write, and a CSP that forbids inline
script and style.
"""
import io
import json
import logging
import os
import secrets
import sqlite3
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.provider import Provider
from agency.engine import Agency
from agency.llm import Models
from agency.telegram import TelegramBridge, token_from

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / 'static'
LOG = logging.getLogger(__name__)
FILES = {'/': ('welcome.html', 'text/html'), '/workspace': ('agency.html', 'text/html'),
         '/welcome.css': ('welcome.css', 'text/css'), '/welcome.js': ('welcome.js', 'text/javascript'),
         '/agency.js': ('agency.js', 'text/javascript'),
         '/agency.css': ('agency.css', 'text/css'), '/capabilities.js': ('capabilities.js', 'text/javascript'),
         '/capabilities.css': ('capabilities.css', 'text/css'),
         # Mesaj Agentliyi skin; the display face is served locally because the CSP allows no font CDN.
         '/soz.css': ('soz.css', 'text/css'),
         '/fonts/unbounded-latin.woff2': ('fonts/unbounded-latin.woff2', 'font/woff2'),
         '/fonts/unbounded-latin-ext.woff2': ('fonts/unbounded-latin-ext.woff2', 'font/woff2'),
         # Komanda və HR skin: WebGL scenes drawn with a vendored three.js, since the CSP allows no script CDN.
         '/team.css': ('team.css', 'text/css'), '/team3d.js': ('team3d.js', 'text/javascript'),
         '/vendor/three.module.min.js': ('vendor/three.module.min.js', 'text/javascript'),
         '/fonts/archivo-wide-latin.woff2': ('fonts/archivo-wide-latin.woff2', 'font/woff2'),
         '/fonts/archivo-wide-latin-ext.woff2': ('fonts/archivo-wide-latin-ext.woff2', 'font/woff2'),
         # İnsan yoxlaması skin.
         '/review.css': ('review.css', 'text/css'),
         # Sifariş və stok skin (3D dispenser drawn with the vendored three.js).
         '/operations.css': ('operations.css', 'text/css'), '/ops3d.js': ('ops3d.js', 'text/javascript'),
         # Tender: Componine-style chapters under the forest hero.
         '/tender.css': ('tender.css', 'text/css'),
         '/fonts/marcellus-latin.woff2': ('fonts/marcellus-latin.woff2', 'font/woff2'),
         '/fonts/marcellus-latin-ext.woff2': ('fonts/marcellus-latin-ext.woff2', 'font/woff2'),
         # Qərar xəritəsi skin.
         '/trace.css': ('trace.css', 'text/css'),
         '/fonts/chivo-mono-latin.woff2': ('fonts/chivo-mono-latin.woff2', 'font/woff2'),
         '/fonts/chivo-mono-latin-ext.woff2': ('fonts/chivo-mono-latin-ext.woff2', 'font/woff2'),
         # Siyasət skin.
         '/policy.css': ('policy.css', 'text/css'), '/policy.js': ('policy.js', 'text/javascript'),
         '/fonts/inter-tight-latin.woff2': ('fonts/inter-tight-latin.woff2', 'font/woff2'),
         '/fonts/inter-tight-latin-ext.woff2': ('fonts/inter-tight-latin-ext.woff2', 'font/woff2'),
         '/fonts/source-serif-latin.woff2': ('fonts/source-serif-latin.woff2', 'font/woff2'),
         '/fonts/source-serif-latin-ext.woff2': ('fonts/source-serif-latin-ext.woff2', 'font/woff2')}

# İnsan yoxlaması: public-domain paintings with halftone laptops composited in.
for asset in ('review-syndics.webp', 'review-audit.webp', 'review-shadow.webp', 'review-peer.webp', 'review-regression.webp',
              'policy-cloud-1.webp', 'policy-cloud-2.webp', 'policy-cloud-3.webp',
              'tender-hands.webp', 'tender-scholar.webp', 'tender-portrait.webp'):
    FILES['/' + asset] = (asset, 'image/webp')

for asset in ('forest-hero.webp', 'forest-left.webp', 'forest-right.webp', 'forest-front.webp', 'forest-back.webp', 'forest-cloud.png'):
    FILES['/' + asset] = (asset, 'image/png' if asset.endswith('.png') else 'image/webp')


def make_handler(agency, bridge=None, sandbox=False, offline=False):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, mime='application/json; charset=utf-8', download=None):
            raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            headers = {'Content-Type': mime, 'Content-Length': str(len(raw)), 'Cache-Control': 'no-store',
                       'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                       'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; "
                                                  "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                                                  "base-uri 'none'; form-action 'self'"}
            if urlsplit(self.path).path == '/':
                headers['Content-Security-Policy'] += '; media-src https://assets.offloop.org'
            if download:
                headers['Content-Disposition'] = f'attachment; filename="{download}"'
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def host_ok(self):
            port = self.server.server_port
            return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

        def do_GET(self):
            if not self.host_ok():
                return self.reply(403, {'error': 'Host qəbul edilmir.'})
            parts = urlsplit(self.path)
            query = parse_qs(parts.query)
            try:
                if parts.path == '/api/state':
                    return self.reply(200, dict(agency.snapshot(), csrf=token, sandbox=sandbox, offline=offline,
                                                telegram=bridge.status() if bridge else None))
                if parts.path == '/api/document':
                    return self.reply(200, agency.document_body(query.get('id', [''])[0]))
                if parts.path == '/api/trace':
                    return self.reply(200, agency.decision_trace(query.get('job_id', [''])[0]))
                if parts.path == '/api/company/fit':
                    return self.reply(200, agency.company_fit(query.get('document_id', [''])[0]))
                if parts.path == '/api/audit':
                    service = query.get('service', ['soz'])[0]
                    snap = agency.snapshot()
                    if service not in snap['services']:
                        raise ValueError('Naməlum xidmət.')
                    body = json.dumps(dict(service=service, jobs=snap['services'][service]['jobs'],
                                           workers=snap['services'][service]['workers'],
                                           journal=[j for j in snap['journal'] if j['service'] == service]),
                                      ensure_ascii=False, indent=2).encode()
                    return self.reply(200, body, download=f'audit-{service}.json')
                if parts.path == '/api/telegram/qr.svg':
                    return self.reply(200, qr_svg(bridge.status()['link'] if bridge else None), 'image/svg+xml')
                if parts.path == '/health':
                    return self.reply(200, {'ok': True})
            except ValueError as exc:
                return self.reply(404, {'error': str(exc)})
            if parts.path not in FILES:
                return self.reply(404, {'error': 'Tapılmadı.'})
            name, mime = FILES[parts.path]
            self.reply(200, (STATIC / name).read_bytes(), mime if mime.startswith('font/') else mime + '; charset=utf-8')

        def do_POST(self):
            port = self.server.server_port
            # Read the body before any refusal: closing a socket with unread data
            # makes Windows reset the connection, and the client sees an abort
            # instead of the 403 it should get.
            try:
                size = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                size = -1
            # An uploaded tender file travels as base64 inside the JSON, so that route takes more.
            limit = 12_000_000 if urlsplit(self.path).path == '/api/tender/file' else 200_000
            body = self.rfile.read(size) if 0 < size <= limit else b''
            origin = self.headers.get('Origin')
            if (not self.host_ok() or (origin and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}'))
                    or not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), token)):
                return self.reply(403, {'error': 'Səhifəni yeniləyib əməliyyatı təkrar edin.'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(415, {'error': 'JSON tələb olunur.'})
            try:
                if not 0 < size <= limit:
                    raise ValueError('Fayl 8 MB-dan böyük olmamalıdır.' if limit > 200_000 else 'Sorğu ölçüsü uyğun deyil.')
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise ValueError('JSON obyekt tələb olunur.')
                path = urlsplit(self.path).path
                actions = {
                    '/api/operations/demo': lambda: agency.load_demo_operations(),
                    '/api/operations/prepare': lambda: agency.prepare_exchange(data.get('order_id'), data.get('size')),
                    '/api/operations/confirm': lambda: agency.confirm_exchange(data.get('exchange_id')),
                    '/api/company': lambda: agency.save_company(data),
                    '/api/ticket': lambda: dict(job_id=agency.submit_ticket(data.get('message'))),
                    '/api/human': lambda: agency.human_reply(data.get('text')),
                    '/api/stress': lambda: dict(queued=agency.stress(int(data.get('count', 40)))),
                    '/api/tender': lambda: dict(job_id=agency.analyze_tender(data.get('document_id'))),
                    '/api/tender/upload': lambda: dict(document=_public(agency.add_tender(data.get('title'), data.get('body')))),
                    '/api/tender/file': lambda: dict(document=_public(agency.add_tender_file(data.get('title'), data.get('name'),
                                                                                              data.get('data')))),
                    '/api/policy': lambda: dict(document=_public(agency.update_policy(data.get('body')))),
                    '/api/mode': lambda: agency.set_mode(data.get('mode')) or {},
                    '/api/settings': lambda: agency.set_policy(data.get('policy')) or {},
                    '/api/replay/restart': lambda: agency.restart_replay(data.get('speed')) or {},
                    '/api/approve': lambda: agency.approve_draft(data.get('job_id')) or {},
                    '/api/corrupt': lambda: agency.corrupt(data.get('worker_id')) or {},
                    '/api/review': lambda: agency.review(data.get('job_id'), data.get('verdict'), data.get('reply'),
                                                         data.get('note')) or {},
                }
                if path not in actions:
                    return self.reply(404, {'error': 'Tapılmadı.'})
                result = actions[path]()
                self.reply(200, dict(result, csrf=token))
            except (ValueError, TypeError) as exc:
                self.reply(400, {'error': str(exc)})
            except Exception:
                LOG.exception('Agency request failed')
                self.reply(500, {'error': 'Daxili xəta.'})

        def log_message(self, *_):
            pass

    return Handler


def qr_svg(link):
    """The bot link as a scannable QR code for the slide or the projector."""
    if not link:
        raise ValueError('Telegram botu qoşulmayıb.')
    try:
        import segno  # optional: pip install segno
    except ImportError:
        raise ValueError('QR üçün segno paketi lazımdır: py -3 -m pip install segno') from None
    buffer = io.BytesIO()
    # Dark on white with a quiet zone: what phone cameras read most reliably.
    segno.make(link, error='m').save(buffer, kind='svg', scale=10, border=4, dark='#0d1117', light='#ffffff')
    return buffer.getvalue()


def _public(doc):
    return {k: doc[k] for k in ('id', 'title', 'version', 'created_at')}


def copy_database(source, target):
    """A consistent single-file copy, even of a database another process is writing."""
    source, target = Path(source), Path(target)
    if not source.exists():
        raise SystemExit(f'Qeyd faylı tapılmadı: {source}')
    target.parent.mkdir(parents=True, exist_ok=True)
    reader = sqlite3.connect(f'file:{source.as_posix()}?mode=ro', uri=True)
    writer = sqlite3.connect(target)
    with writer:
        reader.backup(writer)
    reader.close()
    writer.close()
    return target


def serve(replay=None, speed=10.0, rehearsal=False):
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get('PORT', '8830'))
    if replay:
        # Replays run on a private copy, so the recording itself is never altered.
        copy = copy_database(replay, Path(tempfile.mkdtemp(prefix='agency-replay-')) / 'replay.sqlite3')
        agency = Agency(copy, Models(Provider(ROOT)), replay=speed)
        print(f'TƏKRAR rejimi: {replay} · sürət {speed:g}×', flush=True)
    elif rehearsal:
        # A fresh copy of the live database on every start: rehearse firing Kamal as often as
        # you like, the real team is untouched.
        copy = ROOT / 'data' / 'mesq.sqlite3'
        for suffix in ('', '-wal', '-shm'):
            Path(str(copy) + suffix).unlink(missing_ok=True)
        agency = Agency(copy_database(ROOT / 'data' / 'agency.sqlite3', copy), Models(Provider(ROOT)))
        print('MƏŞQ rejimi: canlı bazanın təzə surəti (data/mesq.sqlite3) — əsl baza dəyişmir', flush=True)
    else:
        agency = Agency(ROOT / 'data' / 'agency.sqlite3', Models(Provider(ROOT)))
    stop = threading.Event()
    bridge, telegram = None, None if replay else token_from(ROOT)
    if telegram:
        bridge = TelegramBridge(agency, telegram)
        bridge.start(stop)
        print('Telegram bot: ' + (f'https://t.me/{bridge.username}' if bridge.username else f'xəta — {bridge.error}'), flush=True)
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(agency, bridge, sandbox=rehearsal))

    def loop():
        while not stop.is_set():
            try:
                busy = agency.step()
            except Exception:
                LOG.exception('Agency step failed')
                busy = False
            stop.wait(0.05 if busy else 1.0)

    worker = threading.Thread(target=loop, daemon=True)
    worker.start()
    print(f'Probo — http://127.0.0.1:{port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        worker.join(timeout=70)
        server.server_close()
        if not worker.is_alive():
            agency.close()
