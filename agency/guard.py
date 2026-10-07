"""Deterministic evidence guard shared by both services.

Nothing here asks a model for an opinion. A statement passes only when:

* its quote occurs verbatim in the source document (punctuation, spacing,
  typographic quotes and dotted/dotless i are tolerated; wording is not);
* every date, clock time and number in the statement also occurs in that
  quote — a figure the quote does not contain is a figure the quote does not
  support;
* it does not turn a prohibition in the quote into a permission.

The guard is deliberately conservative: when in doubt it blocks, and every
block carries a reason a person can check against the document. What it
cannot see — a correct quote applied to the wrong situation — is measured
separately by sampling audits rather than claimed here.
"""
import re

from app.parameters import MULTIPLIERS, NUMBER, PERCENT, _readings

MONTHS = {'yanvar': 1, 'fevral': 2, 'mart': 3, 'aprel': 4, 'may': 5, 'iyun': 6, 'iyul': 7,
          'avqust': 8, 'sentyabr': 9, 'oktyabr': 10, 'noyabr': 11, 'dekabr': 12}
DATE_DMY = re.compile(r'\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b')
DATE_ISO = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')
DATE_WORDS = re.compile(r'\b(\d{1,2})\s+(' + '|'.join(MONTHS) + r')[^\W\d_]*\s+(\d{4})\b', re.IGNORECASE)
TIME = re.compile(r'\b(?:saat\s+)?([01]?\d|2[0-3])[:](\d{2})\b|\bsaat\s+([01]?\d|2[0-3])[.](\d{2})\b',
                  re.IGNORECASE)
WORD = re.compile(r'[^\W_]+', re.UNICODE)

# Same-length folding keeps character offsets valid for highlighting.
_FOLD = str.maketrans({'İ': 'i', 'I': 'i', 'ı': 'i', '“': '"', '”': '"', '„': '"', '«': '"', '»': '"',
                       '‘': "'", '’': "'", '–': '-', '—': '-', ' ': ' '})


def fold(text):
    folded = str(text).translate(_FOLD)
    lowered = folded.lower()
    return lowered if len(lowered) == len(folded) else folded


NEGATIVE_WORDS = {fold(w) for w in ('deyil', 'yox', 'yoxdur', 'heç', 'qadağandır', 'qadağan', 'olmaz',
                                    'mümkünsüz', 'olunmaz')}
# Azerbaijani negation lives in the verb: qaytarılmır, verilməz, edilməməlidir.
# Vowel harmony matters: back -maz/-mamalı, front -məz/-məməli (ə, not e).
# "-məməli" is usually followed by a copula ("edilməməlidir"), so it takes no word boundary;
# neither does the future negative "-məyəcək" ("qaytara bilməyəcəksiniz").
NEGATIVE_FORM = re.compile(r'[^\W\d_]{2,}(?:m[iuü]r(?:lar|lər)?\b|m[aeə]z\b|m[aeə]m[aeə]li|m[aeə]y[aeə]c[aeə][kqğ])')
# "-mayan" is a prohibition only when the clause ends in a copula, a few words
# later at most ("qaytarılmayan məhsullar siyahısına daxildir"); as a plain
# attribute it is not ("uyğun gəlməyən geyim 14 gün ərzində dəyişdirilə bilər").
NEGATIVE_PREDICATE = re.compile(r'[^\W\d_]{3,}m[aeə]y[aeə]n(?:\s+[^\W\d_]+){0,3}?\s+[^\W\d_]*d[iuü]r\b')
GUARD_VERSION = 5  # bump whenever a rule changes, so stored verdicts are re-checked
COURTESY = {fold(w) for w in ('salam', 'hörmətli', 'təşəkkür', 'edirik', 'edirəm', 'sağ', 'olun', 'xahiş',
                              'gününüz', 'xeyir', 'müraciət', 'müraciətiniz', 'üçün', 'və', 'bizə',
                              'yazdığınız', 'olsun', 'xoş', 'günlər', 'arzulayırıq', 'hər', 'zaman',
                              'xidmətinizdəyik', 'buyurun')}
STOP = {fold(w) for w in ('və', 'ilə', 'üçün', 'bu', 'o', 'bir', 'da', 'də', 'ki', 'isə', 'olan', 'olaraq',
                          'siz', 'sizin', 'biz', 'bizim', 'edə', 'bilər', 'bilərsiniz', 'olur', 'olunur',
                          'edilir', 'bəli', 'xeyr', 'amma', 'lakin', 'ancaq', 'həm', 'hansı', 'necə', 'nə',
                          'mən', 'mənə', 'mənim')}


def words(text):
    return WORD.findall(fold(text))


def locate(quote, document):
    """Character span of the quote inside the document, or None."""
    tokens = words(quote)
    if len(tokens) < 3:
        return None
    pattern = r'[\W_]*'.join(re.escape(token) for token in tokens)
    match = re.search(pattern, fold(document))
    return (match.start(), match.end()) if match else None


def dates(text):
    found = set()
    for day, month, year in DATE_DMY.findall(text):
        found.add(f'{int(year):04d}-{int(month):02d}-{int(day):02d}')
    for year, month, day in DATE_ISO.findall(text):
        found.add(f'{int(year):04d}-{int(month):02d}-{int(day):02d}')
    for day, month, year in DATE_WORDS.findall(fold(text)):
        found.add(f'{int(year):04d}-{MONTHS[month]:02d}-{int(day):02d}')
    return found


def times(text):
    found = set()
    for hour, minute, hour2, minute2 in TIME.findall(text):
        found.add(f'{int(hour or hour2):02d}:{minute or minute2}')
    return found


def _without_calendar(text):
    for pattern in (DATE_DMY, DATE_ISO, DATE_WORDS, TIME):
        text = pattern.sub(' ', text)
    return text


def numbers(text):
    """Each number as written, with every reading a careful reader could take."""
    found = []
    for token, suffix in NUMBER.findall(_without_calendar(str(text))):
        readings = set(_readings(token))
        word = (suffix or '').casefold()
        if word in MULTIPLIERS:
            readings |= {value * MULTIPLIERS[word] for value in readings}
        if word in PERCENT:
            readings |= {value / 100 for value in readings}
        if readings:
            found.append((token.strip(), readings))
    return found


def _same(a, b):
    return abs(a - b) <= max(abs(a), abs(b), 1.0) * 1e-9


# "500 000 AZN-dən az olmamalıdır" means "at least 500 000": a bound, not a prohibition.
# Tender and contract language is full of these; they must not read as negation.
BOUND = re.compile(r'\b(?:az|çox|artiq|aşaği|yuxari)\s+olma\w*|\başma(?:mali|z|y)\w*')


def is_negative(text):
    folded = BOUND.sub(' ', fold(text))
    return (bool(set(WORD.findall(folded)) & NEGATIVE_WORDS) or bool(NEGATIVE_FORM.search(folded))
            or bool(NEGATIVE_PREDICATE.search(folded)))


def check(statement, quote, document):
    """Verdict for one statement and the quote offered as its evidence."""
    statement, quote = str(statement or '').strip(), str(quote or '').strip()
    problems, notes, kinds, unsupported = [], [], [], []
    if not 2 <= len(statement) <= 600:
        problems.append('Cümlə boşdur və ya çox uzundur.')
        kinds.append('format')
    span = locate(quote, document) if 8 <= len(quote) <= 800 else None
    if span is None:
        problems.append('Sitat sənəddə tapılmadı.' if len(words(quote)) >= 3
                        else 'Sitat çox qısadır — ən azı üç söz lazımdır.')
        return dict(ok=False, problems=problems, notes=notes, span=None, kinds=kinds + ['quote'], unsupported=[])
    evidence = document[span[0]:span[1]]
    missing_dates = dates(statement) - dates(evidence)
    if missing_dates:
        problems.append('Tarix sitatda yoxdur: ' + ', '.join(sorted(missing_dates)) + '.')
        kinds.append('date')
    missing_times = times(statement) - times(evidence)
    if missing_times:
        problems.append('Saat sitatda yoxdur: ' + ', '.join(sorted(missing_times)) + '.')
        kinds.append('time')
    offered = [value for _, readings in numbers(evidence) for value in readings]
    for token, readings in numbers(statement):
        if not any(_same(a, b) for a in readings for b in offered):
            shown = ', '.join(t for t, _ in numbers(evidence)) or 'heç bir rəqəm'
            problems.append(f'«{token}» sitatda yoxdur. Sitatdakı rəqəmlər: {shown}.')
            kinds.append('number')
            unsupported.append(token)
    if is_negative(evidence) and not is_negative(statement):
        problems.append('Sitat qadağa və ya inkar bildirir, cümlə isə icazə kimi səslənir.')
        kinds.append('polarity')
    elif is_negative(statement) and not is_negative(evidence):
        notes.append('Cümlə inkar bildirir, sitat bildirmir — nəticə çıxarmadır, auditdə yoxlanmalıdır.')
    return dict(ok=not problems, problems=problems, notes=notes, span=list(span), kinds=kinds,
                unsupported=unsupported)


def contradictions(statements):
    """Pairs in one reply that allow and forbid the same action.

    A correct quote applied to the wrong case is invisible sentence by
    sentence; within one reply it often shows up as "can be returned" next to
    "cannot be returned". Sharing a content stem and differing in polarity is
    enough to stop the reply and let a second worker or a person decide.
    """
    found = []
    tagged = [(text, is_negative(text), predicate(text), is_scoped(text)) for text in statements]
    for i, (a, neg_a, stems_a, scoped_a) in enumerate(tagged):
        for b, neg_b, stems_b, scoped_b in tagged[i + 1:]:
            # "Can within 14 days. If that has passed, cannot." is a rule and its edge, not a contradiction.
            if neg_a != neg_b and stems_a & stems_b and not (scoped_a or scoped_b):
                found.append((a, b))
    return found


SCOPE_WORDS = {fold(w) for w in ('əgər', 'halda', 'təqdirdə', 'isə', 'sonra', 'keçdikdən', 'bitdikdən', 'yalnız')}
# Conditionals and "when" clauses narrow a statement: keçibsə, qaytarsanız, olduqda, gəldikdə.
SCOPE_FORM = re.compile(r'[^\W\d_]{2,}(?:s[aeə]|s[aeə]n[iu]z|d[iuü]qda|d[iuü]kd[aeə]|t[iuü]qda|t[iuü]kd[aeə])\b')


def is_scoped(text):
    folded = fold(text)
    return bool(set(words(text)) & SCOPE_WORDS) or bool(SCOPE_FORM.search(folded))


def _stems(text):
    return {token[:5] for token in words(text) if token not in STOP and not token.isdigit() and len(token) > 1}


def predicate(text):
    """Stems of the closing words. Azerbaijani is verb-final, so this is the predicate:
    "...qaytarıla bilər" and "...qaytarıla bilməz" share it; "...işləyir" and
    "...mövcud deyil" do not, however many other words the sentences share."""
    tokens = [t for t in words(text) if not t.isdigit() and len(t) > 1 and t not in STOP]
    return {token[:5] for token in tokens[-2:]}


def spans(document):
    """Sentence-level spans: smaller than a clause, so a citation stays specific."""
    found = []
    for match in re.finditer(r'[^\n.;!?]+(?:[.;!?](?=\s|$)|$)', document):
        text = match.group().strip()
        if len(words(text)) >= 3:
            lead = match.group().find(text)
            found.append((match.start() + lead, match.start() + lead + len(text)))
    return found


def ground(statement, document, minimum=0.15):
    """Best matching evidence span for a statement written without a citation."""
    wanted = _stems(statement)
    best, score = None, 0.0
    for start, end in spans(document):
        offered = _stems(document[start:end])
        if not wanted or not offered:
            continue
        overlap = len(wanted & offered) / len(wanted | offered)
        if overlap > score:
            best, score = (start, end), overlap
    return (best, round(score, 3)) if best and score >= minimum else (None, round(score, 3))


def is_courtesy(sentence):
    tokens = [token for token in words(sentence) if not token.isdigit()]
    return bool(tokens) and all(token in COURTESY for token in tokens) and not numbers(sentence)


def sentences(text):
    return [part.strip() for part in re.split(r'(?<=[.!?])\s+|\n+', str(text)) if part.strip()]


def check_free_text(text, document):
    """Verdict for a reply written by a person, citation found automatically."""
    verdicts = []
    for sentence in sentences(text):
        if is_courtesy(sentence):
            verdicts.append(dict(text=sentence, ok=True, courtesy=True, problems=[], notes=[], span=None))
            continue
        span, score = ground(sentence, document)
        if span is None:
            verdicts.append(dict(text=sentence, ok=False, courtesy=False, span=None, notes=[],
                                 problems=['Qaydalarda bu cümləyə uyğun bənd tapılmadı.'], score=score))
            continue
        verdict = check(sentence, document[span[0]:span[1]], document)
        verdicts.append(dict(verdict, text=sentence, courtesy=False, score=score))
    return dict(ok=bool(verdicts) and all(v['ok'] for v in verdicts), sentences=verdicts)
