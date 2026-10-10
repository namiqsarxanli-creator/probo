"""Source documents split into citable clauses.

A policy or a tender is stored as plain text. `## Heading` lines open a
category; every other non-empty line is one clause with a stable id. The
version is a hash of the text, so every answer can name the exact wording it
relied on, and a changed document is detectably a different document.
"""
import hashlib
import io
import re
import zipfile
from xml.etree import ElementTree


def version_of(body):
    return hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]


# ── uploaded files ──────────────────────────────────────────────────────
FILE_TYPES = ('.pdf', '.docx', '.txt', '.md')
_W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def extract_text(name, raw):
    """Plain text of an uploaded tender: PDF, Word (.docx) or a text file.

    Headings in a Word file become `# ` lines so the card can name the section
    a clause came from; table rows become `cell | cell` lines.
    """
    suffix = '.' + str(name or '').rsplit('.', 1)[-1].lower() if '.' in str(name or '') else ''
    if suffix in ('.txt', '.md'):
        text = _decode(raw)
    elif suffix == '.docx':
        text = _docx_text(raw)
    elif suffix == '.pdf':
        text = _pdf_text(raw)
    else:
        raise ValueError('Bu fayl növü dəstəklənmir: PDF, Word (.docx) və ya TXT seçin.')
    text = re.sub(r'[ \t ]+\n', '\n', text.replace('\r\n', '\n').replace('\r', '\n'))
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    if len(text) < 80:
        raise ValueError('Fayldan oxunaqlı mətn çıxmadı. Skan edilmiş PDF-dirsə, mətni əl ilə yapışdırın.')
    return text


def _decode(raw):
    for encoding in ('utf-8-sig', 'utf-16', 'cp1254', 'cp1251'):
        try:
            text = raw.decode(encoding)
            if encoding != 'utf-16' or raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
                return text
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def _docx_text(raw):
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        info = archive.getinfo('word/document.xml')
    except (zipfile.BadZipFile, KeyError):
        raise ValueError('Word faylı oxunmadı: .docx formatında olduğuna əmin olun (köhnə .doc dəstəklənmir).') from None
    if info.file_size > 40_000_000:  # a zip bomb, not a tender
        raise ValueError('Word faylının mətni çox böyükdür.')
    body = ElementTree.fromstring(archive.read(info)).find(_W + 'body')
    lines = []
    for block in (body if body is not None else []):
        if block.tag == _W + 'p':
            lines.append(_docx_paragraph(block))
        elif block.tag == _W + 'tbl':
            for row in block.iter(_W + 'tr'):
                cells = [' '.join(_docx_paragraph(p) for p in cell.iter(_W + 'p')).strip() for cell in row.iter(_W + 'tc')]
                if any(cells):
                    lines.append(' | '.join(cells))
    return '\n'.join(lines)


def _docx_paragraph(paragraph):
    parts = []
    for node in paragraph.iter():
        if node.tag == _W + 't':
            parts.append(node.text or '')
        elif node.tag == _W + 'tab':
            parts.append('\t')
        elif node.tag in (_W + 'br', _W + 'cr'):
            parts.append('\n')
    text = ''.join(parts).strip()
    style = paragraph.find(f'{_W}pPr/{_W}pStyle')
    name = (style.get(_W + 'val') or '') if style is not None else ''
    if text and re.match(r'(heading|başlıq|title)', name, re.I):
        text = '# ' + text
    return text


def _pdf_text(raw):
    try:
        from pypdf import PdfReader  # optional: pip install pypdf
    except ImportError:
        raise ValueError('PDF üçün pypdf paketi lazımdır: py -3 -m pip install pypdf') from None
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted and not reader.decrypt(''):
            raise ValueError('PDF şifrəlidir; şifrəsiz nüsxəni yükləyin.')
        return '\n\n'.join((page.extract_text() or '') for page in reader.pages[:200])
    except ValueError:
        raise
    except Exception:
        raise ValueError('PDF faylı oxunmadı: fayl zədələnmiş ola bilər.') from None


def split(body, prefix='B'):
    """Clauses in reading order: id, category, text, and character span."""
    if not isinstance(body, str) or not body.strip():
        raise ValueError('Sənəd boşdur.')
    clauses, category, offset = [], 'Ümumi', 0
    for line in body.splitlines(keepends=True):
        start = offset
        offset += len(line)
        text = line.strip()
        if not text:
            continue
        if text.startswith('#'):
            category = text.lstrip('#').strip() or 'Ümumi'
            continue
        # Leading list markers are layout, not wording.
        cleaned = re.sub(r'^(?:[-*•]|\d{1,3}[.)])\s+', '', text)
        lead = line.find(cleaned)
        clauses.append(dict(id=f'{prefix}{len(clauses) + 1}', category=category, text=cleaned,
                            start=start + max(lead, 0), end=start + max(lead, 0) + len(cleaned)))
    if not clauses:
        raise ValueError('Sənəddə heç bir bənd tapılmadı.')
    return clauses


def categories(clauses):
    return list(dict.fromkeys(clause['category'] for clause in clauses))
