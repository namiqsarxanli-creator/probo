"""Source documents split into citable clauses.

A policy or a tender is stored as plain text. `## Heading` lines open a
category; every other non-empty line is one clause with a stable id. The
version is a hash of the text, so every answer can name the exact wording it
relied on, and a changed document is detectably a different document.
"""
import hashlib
import re


def version_of(body):
    return hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]


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
