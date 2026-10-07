import json
import logging
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from app.market import STRATEGIES, plan
from app.studio import Studio

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger(__name__)


def make_handler(studio):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, mime='application/json; charset=utf-8', download=None):
            raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            for key, value in {'Content-Type': mime, 'Content-Length': str(len(raw)), 'Cache-Control': 'no-store',
                'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items():
                self.send_header(key, value)
            if download:
                self.send_header('Content-Disposition', f'attachment; filename="{download}"')
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def host_ok(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.host_ok():
                return self.reply(403, {'error': 'Host qəbul edilmir.'})
            parts = urlsplit(self.path)
            if parts.path == '/api/studio':
                return self.reply(200, dict(studio.snapshot(), csrf=token))
            if parts.path == '/api/portal':
                query = parse_qs(parts.query)
                try:
                    return self.reply(200, dict(studio.portal_project(query.get('id', [''])[0],
                                                                     query.get('token', [''])[0]), csrf=token))
                except ValueError:
                    return self.reply(403, {'error': 'Müştəri keçidi etibarsızdır.'})
            if parts.path == '/api/calendar':
                try:
                    project_id = parse_qs(parts.query).get('id', [''])[0]
                    return self.reply(200, studio.calendar(project_id), 'text/calendar; charset=utf-8',
                                      'tasks.ics')
                except ValueError as exc:
                    return self.reply(404, {'error': str(exc)})
            if parts.path == '/api/evaluation/export':
                try:
                    project_id = parse_qs(parts.query).get('id', [''])[0]
                    with studio.lock:
                        p = studio.get(project_id)
                        payload = dict(project_id=p['id'], title=p['title'], dataset_version=p['eval_version'],
                                       cases=p['eval_cases'], runs=p['eval_runs'])
                    return self.reply(200, payload, download='quality-evaluation.json')
                except ValueError as exc:
                    return self.reply(404, {'error': str(exc)})
            if parts.path == '/health':
                return self.reply(200, {'ok': True, 'version': '0.2'})
            if parts.path == '/api/arena/strategies':
                return self.reply(200, {key: dict(preset, key=key) for key, preset in STRATEGIES.items()})
            if parts.path == '/api/export':
                try:
                    project_id = parse_qs(parts.query).get('id', [''])[0]
                    if parse_qs(parts.query).get('format') == ['json']:
                        with studio.lock:
                            payload = json.dumps(studio.get(project_id), ensure_ascii=False, indent=2).encode()
                        return self.reply(200, payload, download='research-audit.json')
                    return self.reply(200, studio.report(project_id).encode(), 'text/markdown; charset=utf-8', 'research-report.md')
                except ValueError as exc:
                    return self.reply(404, {'error': str(exc)})
            files = {'/': ('studio.html', 'text/html'), '/portal': ('portal.html', 'text/html'),
                     '/studio_research.js': ('studio_research.js', 'text/javascript'),
                     '/studio_validation.js': ('studio_validation.js', 'text/javascript'),
                     '/studio_validation.css': ('studio_validation.css', 'text/css'),
                     '/portal.js': ('portal.js', 'text/javascript'),
                     '/studio_modules.js': ('studio_modules.js', 'text/javascript'),
                     '/studio_modules.css': ('studio_modules.css', 'text/css'),
                     '/studio_eval.js': ('studio_eval.js', 'text/javascript'),
                     '/studio_eval.css': ('studio_eval.css', 'text/css'),
                     '/studio.js': ('studio.js', 'text/javascript'),
                     '/studio_extra.js': ('studio_extra.js', 'text/javascript'),
                     '/studio.css': ('studio.css', 'text/css'), '/stage.css': ('stage.css', 'text/css'),
                     '/studio_extra.css': ('studio_extra.css', 'text/css')}
            if parts.path not in files:
                return self.reply(404, {'error': 'Tapılmadı.'})
            name, mime = files[parts.path]
            self.reply(200, (ROOT / 'static' / name).read_bytes(), mime + '; charset=utf-8')

        def do_POST(self):
            origin = self.headers.get('Origin')
            allowed = (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}')
            if not self.host_ok() or (origin and origin not in allowed) or not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), token):
                return self.reply(403, {'error': 'Səhifəni yeniləyib əməliyyatı təkrar edin.'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(415, {'error': 'JSON tələb olunur.'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 100_000:
                    raise ValueError('Sorğu ölçüsü uyğun deyil.')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('JSON obyekt tələb olunur.')
                path = urlsplit(self.path).path
                if path == '/api/arena':
                    # Pure computation over the posted figures; it touches no
                    # stored project and spends nothing at the AI provider.
                    return self.reply(200, plan(data))
                if path == '/api/portal/feedback':
                    entry = studio.portal_feedback(data.get('project_id'), data.get('portal_token'), data.get('message'))
                    return self.reply(200, {'feedback': entry})
                if not path.startswith('/api/studio/'):
                    return self.reply(404, {'error': 'Tapılmadı.'})
                result = studio.action(path.removeprefix('/api/studio/'), data)
                self.reply(200, result)
            except (ValueError, TypeError) as exc:
                self.reply(400, {'error': str(exc)})
            except (OSError, TimeoutError):
                self.reply(502, {'error': 'Mənbə ilə əlaqə alınmadı. Mətnini əl ilə daxil edin.'})
            except Exception:
                LOG.exception('Studio request failed')
                self.reply(500, {'error': 'Daxili xəta. Əməliyyatın vəziyyətini yeniləyib yoxlayın.'})

        def log_message(self, *_):
            pass
    return Handler


def serve():
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get('PORT', '8812'))
    studio = Studio(ROOT / 'data' / 'studio.sqlite3')
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(studio))
    stop = threading.Event()

    def loop():
        while not stop.wait(3):
            try:
                studio.tick()
            except Exception:
                LOG.exception('Studio execution failed')
    worker = threading.Thread(target=loop, daemon=True)
    worker.start()
    def source_loop():
        while not stop.wait(2):
            try:
                studio.discover_pending()
            except Exception:
                LOG.exception('Source discovery failed')
    source_worker = threading.Thread(target=source_loop, daemon=True)
    source_worker.start()
    print(f'Autonomous Inc. Studio 0.2 — http://127.0.0.1:{port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        worker.join(timeout=65)
        source_worker.join(timeout=65)
        server.server_close()
        if not worker.is_alive() and not source_worker.is_alive():
            studio.close()
