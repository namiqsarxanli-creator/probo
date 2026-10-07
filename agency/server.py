"""Local HTTP API and panel for Sübut Agentliyi.

Same protections as the studio: loopback only, Host and Origin checks,
a per-process CSRF token on every write, and a CSP that forbids inline
script and style.
"""
import json
import logging
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.provider import Provider
from agency.engine import Agency
from agency.llm import Models

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / 'static'
LOG = logging.getLogger(__name__)
FILES = {'/': ('agency.html', 'text/html'), '/agency.js': ('agency.js', 'text/javascript'),
         '/agency.css': ('agency.css', 'text/css')}


def make_handler(agency):
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
                    return self.reply(200, dict(agency.snapshot(), csrf=token))
                if parts.path == '/api/document':
                    return self.reply(200, agency.document_body(query.get('id', [''])[0]))
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
                if parts.path == '/health':
                    return self.reply(200, {'ok': True})
            except ValueError as exc:
                return self.reply(404, {'error': str(exc)})
            if parts.path not in FILES:
                return self.reply(404, {'error': 'Tapılmadı.'})
            name, mime = FILES[parts.path]
            self.reply(200, (STATIC / name).read_bytes(), mime + '; charset=utf-8')

        def do_POST(self):
            port = self.server.server_port
            origin = self.headers.get('Origin')
            if (not self.host_ok() or (origin and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}'))
                    or not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), token)):
                return self.reply(403, {'error': 'Səhifəni yeniləyib əməliyyatı təkrar edin.'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(415, {'error': 'JSON tələb olunur.'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 200_000:
                    raise ValueError('Sorğu ölçüsü uyğun deyil.')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('JSON obyekt tələb olunur.')
                path = urlsplit(self.path).path
                actions = {
                    '/api/ticket': lambda: dict(job_id=agency.submit_ticket(data.get('message'))),
                    '/api/human': lambda: agency.human_reply(data.get('text')),
                    '/api/stress': lambda: dict(queued=agency.stress(int(data.get('count', 40)))),
                    '/api/tender': lambda: dict(job_id=agency.analyze_tender(data.get('document_id'))),
                    '/api/tender/upload': lambda: dict(document=_public(agency.add_tender(data.get('title'), data.get('body')))),
                    '/api/policy': lambda: dict(document=_public(agency.update_policy(data.get('body')))),
                    '/api/mode': lambda: agency.set_mode(data.get('mode')) or {},
                    '/api/settings': lambda: agency.set_policy(data.get('policy')) or {},
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


def _public(doc):
    return {k: doc[k] for k in ('id', 'title', 'version', 'created_at')}


def serve():
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get('PORT', '8830'))
    agency = Agency(ROOT / 'data' / 'agency.sqlite3', Models(Provider(ROOT)))
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(agency))
    stop = threading.Event()

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
    print(f'Sübut Agentliyi — http://127.0.0.1:{port}', flush=True)
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
