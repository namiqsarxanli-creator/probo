import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from app.sources import fetch_text
from app.studio import Studio


class SourceContentTests(unittest.TestCase):
    @patch('app.sources._fetch')
    def test_import_excludes_country_selector_and_navigation_from_ai_excerpt(self, fetch):
        countries = ''.join('<option>Country ' + str(i) + '</option>' for i in range(300))
        raw = ('<header>Header contacts<nav>Nested nav</nav></header><nav>Course menus</nav>'
               '<select aria-label="Phone number country">' + countries + '</select>'
               '<main><h1>Online course</h1><p>Adult online lessons are available in the evenings '
               'and weekends with a qualified teacher.</p></main><footer>Footer menus</footer>').encode()
        fetch.return_value = ('https://example.org/course', raw, 'text/html')
        _, body = fetch_text('https://example.org/course')
        self.assertIn('Adult online lessons', body[:3000])
        self.assertNotIn('Country ', body)
        self.assertNotIn('Course menus', body)
        self.assertNotIn('Footer menus', body)

    @patch('app.sources._fetch')
    def test_import_retains_table_price_and_inline_emphasis(self, fetch):
        fetch.return_value = ('https://example.org/course', b'<main><p>These <strong>online</strong> '
            b'courses support adult learners.</p><table><tr><td>Monthly plan</td><td>100 AZN</td>'
            b'</tr></table></main>', 'text/html')
        _, body = fetch_text('https://example.org/course')
        self.assertIn('100 AZN', body)
        self.assertIn('online', body)

    def test_trial_never_sees_prior_findings_with_unavailable_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            studio = Studio(Path(temp) / 'studio.sqlite3')
            try:
                pid = studio.action('create', dict(title='Trial context', objective='Mənbələrdəki məhsulları müqayisə et',
                    mode='demo', budget=1))['project_id']
                project = studio.get(pid)
                project['tasks'][0]['output'] = dict(findings=[dict(source_id=project['sources'][1]['id'],
                    claim='Mənbədə yoxlanmış məhsul məlumatı', quote=project['sources'][1]['body'][:50])], limitations='Yalnız mənbəyə əsaslanır.')
                trial = json.loads(studio.messages(project, project['tasks'][1], 'Profile', trial=True)[1]['content'])
                self.assertEqual(trial['prior_outputs'], [])
                self.assertEqual(len(trial['sources']), 1)
                work = json.loads(studio.messages(project, project['tasks'][1], 'Profile', trial=False)[1]['content'])
                self.assertEqual(len(work['prior_outputs']), 1)
            finally:
                studio.close()

    def test_source_excerpt_stays_bounded_and_preserves_reviewed_quote(self):
        from app.studio import source_excerpt
        body = 'Menyu mətnləri. ' * 1000 + 'Dəqiq kurs qiyməti 120 AZN-dir.'
        source = dict(id='source', body=body)
        project = dict(market_evidence=[dict(source_id='source', quote='Dəqiq kurs qiyməti 120 AZN-dir.')], tasks=[])
        excerpt = source_excerpt(source, project, 1000)
        self.assertLessEqual(len(excerpt.encode('utf-8')), 1000)
        self.assertIn('Dəqiq kurs qiyməti 120 AZN-dir.', excerpt)
