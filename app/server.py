import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from app.engine import Company

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger(__name__)


def make_handler(company):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body, content_type='application/json; charset=utf-8'):
            raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == '/api/state':
                return self.reply(200, company.snapshot())
            if path == '/api/report':
                report = company.snapshot()['report']
                if report is None:
                    return self.reply(404, {'error': 'Hesabat hələ hazır deyil.'})
                return self.reply(200, report.encode(), 'text/markdown; charset=utf-8')
            files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
            if path not in files:
                return self.reply(404, {'error': 'Tapılmadı'})
            name, mime = files[path]
            self.reply(200, (ROOT / 'static' / name).read_bytes(), mime + '; charset=utf-8')

        def do_POST(self):
            origin = self.headers.get('Origin')
            allowed = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
            if origin and origin not in allowed:
                return self.reply(403, {'error': 'Origin qəbul edilmir.'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(415, {'error': 'JSON tələb olunur.'})
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 10000:
                    raise ValueError('Sorğunun ölçüsü uyğun deyil.')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('JSON obyekt gözlənilir.')
                path = urlparse(self.path).path
                if not path.startswith('/api/'):
                    return self.reply(404, {'error': 'Tapılmadı'})
                result = company.action(path.removeprefix('/api/'), data)
                self.reply(200, result)
            except (ValueError, TypeError) as exc:
                self.reply(400, {'error': str(exc)})
            except Exception:
                LOG.exception('Request failed')
                self.reply(500, {'error': 'Daxili xəta. Server jurnalını yoxlayın.'})

        def log_message(self, *_):
            pass
    return Handler


def serve():
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get('PORT', '8810'))
    company = Company(ROOT / 'data' / 'company.sqlite3')
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(company))
    stop = threading.Event()

    def scheduler():
        while not stop.wait(3):
            try:
                company.tick()
            except Exception:
                LOG.exception('Scheduler tick failed; state rolled back')

    worker = threading.Thread(target=scheduler, daemon=True)
    worker.start()
    print(f'Autonomous Inc. — http://127.0.0.1:{port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        worker.join()
        company.close()
