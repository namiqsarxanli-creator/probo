"""Bounded HTTPS source import; resolves and pins only public addresses."""
import http.client
import html
import json
import ipaddress
import socket
import ssl
import xml.etree.ElementTree as ET
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin, urlencode, quote, parse_qs


AZ_EN = {
    'azərbaycan': 'azerbaijan', 'azərbaycanda': 'azerbaijan', 'süni': 'artificial',
    'intellekt': 'intelligence', 'təhsil': 'education', 'platforma': 'platform',
    'platformasının': 'platform', 'bazar': 'market', 'bazara': 'market',
    'çıxarılması': 'launch', 'rəqəmsal': 'digital', 'məhsul': 'product',
    'məhsulun': 'product', 'şagird': 'student', 'şagirdlər': 'students',
    'tələbə': 'student', 'tələbələr': 'students', 'müəllim': 'teacher',
    'mobil': 'mobile', 'xidmət': 'service', 'xidmətlərinə': 'services',
    'fərdiləşdirilmiş': 'personalized', 'qiymət': 'price', 'risk': 'risk',
    'şirkət': 'company', 'şirkəti': 'company', 'strategiya': 'strategy',
    'müqayisəsi': 'comparison', 'müqayisə': 'comparison', 'fərq': 'difference',
}
STOP = {'üçün', 'və', 'ilə', 'bir', 'bu', 'əsas', 'uyğun', 'üzrə', 'olan', 'kimi',
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'into'}


def _tokens(value):
    return [x for x in re.findall(r'[^\W_]+', value.casefold(), re.UNICODE)
            if (len(x) > 2 or x == 'ai') and x not in STOP]


def _query_variants(query):
    words = _tokens(query)
    compact = words[:12]
    translated = [AZ_EN.get(word, word) for word in words]
    variants = [' '.join(compact), ' '.join(translated[:14])]
    technical = [word for word in translated if word.isascii() and word not in ('comparison', 'difference')]
    if len(technical) >= 2:
        variants.append(' '.join(technical[:12]))
    if 'ai' in query.casefold() and 'artificial intelligence' not in variants[1]:
        variants.append('artificial intelligence ' + ' '.join(translated[:10]))
    return list(dict.fromkeys(v for v in variants if len(v) >= 8))[:3]


def public_url(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError('Mənbə üçün standart portlu HTTPS ünvanı tələb olunur.')
    return parts


class Extractor(HTMLParser):
    SKIP_TAGS = {'script', 'style', 'noscript', 'svg', 'nav', 'header', 'footer', 'select'}
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=12, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def _fetch(url, accepted=('text/html', 'text/plain'), limit=1_000_000):
    for _ in range(4):
        parts = public_url(url)
        addresses = {a[4][0] for a in socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
            raise ValueError('Lokal və xüsusi şəbəkə ünvanlarından mənbə idxalı qadağandır.')
        conn = PinnedHTTPS(parts.hostname, sorted(addresses)[0])
        try:
            path = parts.path or '/'
            if parts.query:
                path += '?' + parts.query
            conn.request('GET', path, headers={'User-Agent': 'AutonomousInc-Research/0.2', 'Accept': 'text/html,text/plain'})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                url = urljoin(url, response.getheader('Location', ''))
                continue
            if response.status != 200:
                raise ValueError(f'Mənbə HTTP {response.status} qaytardı. Mətni əl ilə əlavə edə bilərsiniz.')
            mime = response.getheader('Content-Type', '')
            if not any(t in mime for t in accepted):
                raise ValueError('Mənbənin məzmun formatı dəstəklənmir.')
            raw = response.read(limit + 1)
            if len(raw) > limit:
                raise ValueError('Mənbə 1 MB limitini aşdı. Lazımi hissəni əl ilə əlavə edin.')
            return url, raw, mime
        finally:
            conn.close()
    raise ValueError('Mənbədə yönləndirmə sayı çoxdur.')


def fetch_text(url):
    url, raw, mime = _fetch(url)
    text = raw.decode('utf-8', errors='replace')
    if 'html' in mime:
        parser = Extractor()
        parser.feed(text)
        text = '\n'.join(parser.parts)
    if len(text.strip()) < 40:
        raise ValueError('Səhifədən yetərli mətn alınmadı. Mənbə mətnini əl ilə əlavə edin.')
    return url, text[:16000]


class SearchLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.current = [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'result-link' in attrs.get('class', '').split():
            href = attrs.get('href', '')
            target = parse_qs(urlsplit(href).query).get('uddg', [href])[0]
            self.current = [target, '']

    def handle_data(self, data):
        if self.current is not None:
            self.current[1] += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            self.links.append(self.current)
            self.current = None


def search_sources(query, limit=4):
    """Search public pages and keep bounded, auditable text snapshots."""
    query = ' '.join(str(query).split())[:500]
    if len(query) < 8:
        raise ValueError('Avtomatik mənbə axtarışı üçün mövzu daha ətraflı yazılmalıdır.')
    candidates, seen, found = [], set(), []
    relevance = set(AZ_EN.get(word, word) for word in _tokens(query))
    variants = _query_variants(query)
    for variant in reversed(variants):
        try:
            _, raw, _ = _fetch('https://lite.duckduckgo.com/lite/?' + urlencode({'q': variant}),
                               ('text/html',), 500_000)
            parser = SearchLinks()
            parser.feed(raw.decode('utf-8', errors='replace'))
            for url, title in parser.links[:12]:
                try:
                    public_url(url)
                except ValueError:
                    continue
                if url not in seen:
                    seen.add(url)
                    score = len(relevance & set(_tokens(title + ' ' + url)))
                    if score:
                        candidates.append((score, title.strip() or urlsplit(url).hostname, url, ''))
        except (ValueError, OSError, TimeoutError):
            pass
        if len(candidates) >= 4:
            break
    # Web results cover documentation and evergreen articles; news alone misses them.
    for variant in variants:
        search_url = 'https://www.bing.com/search?' + urlencode({'q': variant, 'format': 'rss'})
        try:
            _, raw, _ = _fetch(search_url, ('xml', 'rss', 'text/plain'), 500_000)
            root = ET.fromstring(raw)
        except (ValueError, ET.ParseError, OSError, TimeoutError):
            continue
        for item in root.findall('.//item')[:12]:
            title = html.unescape((item.findtext('title') or '').strip())
            url = (item.findtext('link') or '').strip()
            description = html.unescape((item.findtext('description') or '').strip())
            try:
                public_url(url)
            except ValueError:
                continue
            if url not in seen:
                seen.add(url)
                score = len(relevance & set(AZ_EN.get(word, word) for word in _tokens(title + ' ' + description)))
                if score:
                    candidates.append((score, title or urlsplit(url).hostname, url, description))
        if len(candidates) >= 8:
            break
    # Wikipedia provides stable, readable topic context when web search is sparse.
    wiki_url = 'https://en.wikipedia.org/w/api.php?' + urlencode({
        'action': 'query', 'generator': 'search', 'gsrsearch': variants[-1],
        'gsrlimit': min(limit, 4), 'prop': 'extracts', 'exintro': 1,
        'explaintext': 1, 'format': 'json'})
    try:
        _, wiki_raw, _ = _fetch(wiki_url, ('application/json',), 500_000)
        wiki_pages = json.loads(wiki_raw).get('query', {}).get('pages', {}).values()
        ranked = []
        for page in wiki_pages:
            title = str(page.get('title', '')).strip()
            body = str(page.get('extract', '')).strip()
            score = len(relevance & set(AZ_EN.get(word, word) for word in _tokens(title + ' ' + body[:1000])))
            if score >= 2 and title and len(body) >= 80:
                ranked.append((score, dict(title=title, url='https://en.wikipedia.org/wiki/' + quote(title.replace(' ', '_')),
                                           body=body[:16000], origin='web')))
        ranked.sort(key=lambda item: item[0], reverse=True)
        found.extend(item[1] for item in ranked[:2])
    except (ValueError, OSError, TimeoutError, json.JSONDecodeError):
        pass
    for variant in variants:
        search_url = 'https://news.google.com/rss/search?' + urlencode(
            {'q': variant, 'hl': 'en', 'gl': 'US', 'ceid': 'US:en'})
        try:
            _, raw, _ = _fetch(search_url, ('xml', 'rss', 'text/plain'), 500_000)
            root = ET.fromstring(raw)
        except (ValueError, ET.ParseError, OSError, TimeoutError):
            continue
        for item in root.findall('.//item')[:12]:
            title = (item.findtext('title') or '').strip()
            url = (item.findtext('link') or '').strip()
            description = html.unescape((item.findtext('description') or '').strip())
            if '<' in description:
                parser = Extractor()
                parser.feed(description)
                description = ' '.join(parser.parts)
            try:
                public_url(url)
            except ValueError:
                continue
            if url not in seen:
                seen.add(url)
                score = len(relevance & set(AZ_EN.get(word, word) for word in _tokens(title + ' ' + description)))
                if score:
                    candidates.append((score, title or urlsplit(url).hostname, url, description))
    candidates.sort(key=lambda item: item[0], reverse=True)
    strongly_related = [item for item in candidates if item[0] >= 3]
    if len(strongly_related) >= 2:
        candidates = strongly_related
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch_text, url): (title, url, description)
                for _, title, url, description in candidates[:12]}
        for job in as_completed(jobs):
            title, source_url, description = jobs[job]
            try:
                final_url, body = job.result()
                found.append(dict(title=title[:180], url=final_url, body=body, origin='web'))
            except (ValueError, OSError, TimeoutError):
                fallback = f'{title}. {description}'.strip()
                if len(fallback) >= 40:
                    found.append(dict(title=title[:180], url=source_url,
                                      body=fallback[:16000], origin='search'))
    found.sort(key=lambda source: source['origin'] != 'web')
    unique = {source['url']: source for source in found}
    return list(unique.values())[:limit]
