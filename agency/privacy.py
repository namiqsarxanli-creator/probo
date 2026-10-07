"""Personal data is masked before a customer message leaves the machine.

The answer to a policy question never depends on the customer's phone, card
or ID number, so the model does not need to see them. The original message
stays in the local database for the person who handles the case; only the
masked copy goes to the AI provider.
"""
import re

PATTERNS = [
    ('e-poçt', re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')),
    ('IBAN', re.compile(r'\bAZ\d{2}\s?[A-Z]{4}(?:\s?[A-Z0-9]){20}\b', re.IGNORECASE)),
    ('kart', re.compile(r'(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])')),
    ('telefon', re.compile(r'(?<![\d+])(?:\+?994|0)[\s-]?\(?(?:10|12|50|51|55|60|70|77|99)\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)')),
    ('vəsiqə', re.compile(r'\b(?:AZE\s?\d{8}|AA\s?\d{7})\b')),
    # Street addresses, not cities: "Gəncəyə göndərirsiniz?" needs the city to be answered.
    ('ünvan', re.compile(r'\b[A-ZƏÖÜÇŞĞİ][^\W\d_]+\s+(?:küçəsi|küç\.|prospekti|pr\.)\s*,?\s*(?:ev\s*)?\d+[\w/-]*'
                         r'(?:\s*,?\s*(?:mənzil|m\.)\s*\d+)?')),
    # FİN: seven upper-case letters and digits, at least one of each.
    ('FİN', re.compile(r'\b(?=[0-9A-Z]{7}\b)(?=[0-9A-Z]*\d)(?=[0-9A-Z]*[A-Z])[0-9A-Z]{7}\b')),
]


# "Adım Leyla Məmmədova", "ünvanım: ..." — the words after the cue are personal, the cue stays.
CUES = [
    ('ad', re.compile(r'(?i:\b(adım|ad-soyadım|adım və soyadım|mənim adım))\s+[A-ZƏÖÜÇŞĞİ][^\W\d_]+(?:\s+[A-ZƏÖÜÇŞĞİ][^\W\d_]+){0,2}')),
    # A bare "ünvan" only with a colon: "Ünvan dəyişmək olar?" is a question, not an address.
    ('ünvan', re.compile(r'(?i:\b(ünvanım\s*:?|ünvan\s*:))\s*(?!\[)[^.;!?\n]{3,80}')),
]


def mask(text):
    """(masked text, kinds found).

    Any run of 13–19 digits is masked as a card: a mistyped card number
    (failing the checksum) is still somebody's card number.
    """
    found = []

    def replace(kind):
        def swap(match):
            found.append(kind)
            return f'[{kind}]'
        return swap

    for kind, pattern in PATTERNS:
        text = pattern.sub(replace(kind), text)
    for kind, pattern in CUES:
        def keep_cue(match, kind=kind):
            found.append(kind)
            return f'{match.group(1)} [{kind}]'
        text = pattern.sub(keep_cue, text)
    return text, found
