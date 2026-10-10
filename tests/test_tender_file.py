"""Tender files uploaded as PDF, Word or text become plain text the card can quote."""
import io
import unittest
import zipfile

from agency import documents

BODY = ('Satınalan təşkilat: Test Agentliyi. Təkliflərin son təqdim tarixi 2026-11-20, saat 18:00. '
        'Təklif təminatı təklif qiymətinin 1 faizi həcmində bank zəmanəti ilə təqdim edilməlidir.')


def docx(paragraphs, table=()):
    w = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    def para(text, style=None):
        props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ''
        return f'<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>'
    rows = ''.join('<w:tr>' + ''.join(f'<w:tc>{para(c)}</w:tc>' for c in row) + '</w:tr>' for row in table)
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{w}"><w:body>'
           + ''.join(para(t, s) for t, s in paragraphs) + (f'<w:tbl>{rows}</w:tbl>' if rows else '') + '</w:body></w:document>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    return buffer.getvalue()


def pdf(text):
    """A one-page PDF with a single line of Latin text, written by hand."""
    stream = f'BT /F1 12 Tf 40 760 Td ({text}) Tj ET'.encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
               b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    out, offsets = io.BytesIO(), []
    out.write(b'%PDF-1.4\n')
    for n, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b'%d 0 obj\n' % n + body + b'\nendobj\n')
    xref = out.tell()
    out.write(b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1))
    for offset in offsets:
        out.write(b'%010d 00000 n \n' % offset)
    out.write(b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objects) + 1, xref))
    return out.getvalue()


class ExtractTextTest(unittest.TestCase):
    def test_text_file_keeps_azerbaijani_letters(self):
        self.assertEqual(documents.extract_text('tender.txt', BODY.encode('utf-8')), BODY)

    def test_word_headings_become_hash_lines_and_tables_rows(self):
        raw = docx([('Ümumi şərtlər', 'Heading1'), (BODY, None)], table=[('Lot 1', '90 gün'), ('Lot 2', '60 gün')])
        text = documents.extract_text('Elan.DOCX', raw)
        self.assertTrue(text.startswith('# Ümumi şərtlər\n'))
        self.assertIn(BODY, text)
        self.assertIn('Lot 1 | 90 gün', text)

    def test_unsupported_and_empty_files_are_refused_with_a_reason(self):
        with self.assertRaisesRegex(ValueError, 'dəstəklənmir'):
            documents.extract_text('elan.doc', b'whatever')
        with self.assertRaisesRegex(ValueError, 'oxunaqlı mətn'):
            documents.extract_text('elan.txt', b'qisa')
        with self.assertRaisesRegex(ValueError, 'Word faylı oxunmadı'):
            documents.extract_text('elan.docx', b'not a zip')

    def test_pdf_text_is_read(self):
        try:
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest('pypdf is not installed in this interpreter')
        line = 'Tender deadline 2026-11-20 at 18:00; bid guarantee 1 percent of the bid price, bank guarantee.'
        self.assertIn('2026-11-20', documents.extract_text('elan.pdf', pdf(line)))


if __name__ == '__main__':
    unittest.main()
