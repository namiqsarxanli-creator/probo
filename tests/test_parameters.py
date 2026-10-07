import json
import unittest

from app.parameters import (PARAMETERS, normalise, parameter_schema, quote_values,
                            supports, verify_parameters)
from app.provider import Provider, SchemaRejected


SOURCES = [
    dict(id='s1', body='Sektor üzrə illik xərc 1.2 milyard USD təşkil edir. '
                       'Orta aylıq abunə 19 USD səviyyəsindədir. '
                       'Aylıq itki nisbəti 4% olaraq ölçülüb. '
                       'Satış dövrü 3 ay çəkir.'),
    dict(id='s2', body='Reklam yerləşdirmələrinin orta dəyəri min göstərişə 12,50 USD-dir.'),
]


def entry(**overrides):
    base = dict(key='arpu', value=19, unit='USD/ay', source_id='s1',
                quote='Orta aylıq abunə 19 USD səviyyəsindədir', confidence='direct', derivation='')
    base.update(overrides)
    return base


def payload(*entries):
    return json.dumps(dict(parameters=list(entries)), ensure_ascii=False)


class NumberReadingTest(unittest.TestCase):
    def test_plain_and_grouped_numbers(self):
        self.assertTrue(supports(1200, 'Şirkət 1,200 müştəriyə xidmət göstərir'))
        self.assertTrue(supports(1200, 'Şirkət 1 200 müştəriyə xidmət göstərir'))
        self.assertTrue(supports(1200, 'Şirkət 1.200 müştəriyə xidmət göstərir'))

    def test_decimal_separators_do_not_collide(self):
        self.assertTrue(supports(12.5, 'min göstərişə 12,50 USD'))
        self.assertTrue(supports(1234.56, 'ümumi 1,234.56 USD'))
        self.assertFalse(supports(15, 'artım 1.5 faiz bəndi olub'))

    def test_scale_words(self):
        self.assertTrue(supports(1_200_000_000, 'illik xərc 1.2 milyard USD'))
        self.assertTrue(supports(4_000_000, 'bazar 4 million istifadəçidir'))

    def test_percent_reads_as_fraction_and_as_written(self):
        values = quote_values('Aylıq itki nisbəti 4% olaraq ölçülüb')
        self.assertIn(4.0, values)
        self.assertIn(0.04, values)

    def test_rounding_tolerance_but_not_wrong_numbers(self):
        self.assertTrue(supports(19.05, 'qiymət 19.0 USD'))
        self.assertFalse(supports(21, 'qiymət 19 USD'))
        self.assertFalse(supports(19, 'qiymətdə rəqəm göstərilməyib'))


class SchemaTest(unittest.TestCase):
    def test_strict_mode_shape(self):
        item = parameter_schema()['properties']['parameters']['items']
        self.assertFalse(item['additionalProperties'])
        self.assertEqual(set(item['required']), set(item['properties']))
        self.assertEqual(item['properties']['key']['enum'], list(PARAMETERS))


class NormaliseTest(unittest.TestCase):
    def test_percent_churn_becomes_fraction(self):
        self.assertAlmostEqual(normalise('churn_monthly', 4, '%'), 0.04)
        self.assertAlmostEqual(normalise('churn_monthly', 0.04, 'hissə'), 0.04)

    def test_sales_cycle_units(self):
        self.assertEqual(normalise('sales_cycle_days', 3, 'ay'), 90)
        self.assertEqual(normalise('sales_cycle_days', 2, 'week'), 14)
        self.assertEqual(normalise('sales_cycle_days', 45, 'gün'), 45)


class VerifyTest(unittest.TestCase):
    def test_accepts_directly_quoted_figure(self):
        result = verify_parameters(payload(entry()), SOURCES)
        self.assertEqual(result['rejected'], [])
        self.assertEqual(result['verified'][0]['key'], 'arpu')
        self.assertEqual(result['verified'][0]['grade'], 'verified')

    def test_rejects_quote_absent_from_source(self):
        result = verify_parameters(payload(entry(quote='Orta aylıq abunə 19 USD deyil')), SOURCES)
        self.assertEqual(result['verified'], [])
        self.assertIn('tapılmadı', result['rejected'][0]['reason'])

    def test_rejects_figure_absent_from_its_own_quote(self):
        result = verify_parameters(payload(entry(value=29)), SOURCES)
        self.assertEqual(result['verified'], [])
        self.assertIn('rəqəm yoxdur', result['rejected'][0]['reason'])

    def test_rejects_unknown_source(self):
        result = verify_parameters(payload(entry(source_id='s9')), SOURCES)
        self.assertIn('Naməlum mənbə', result['rejected'][0]['reason'])

    def test_rejects_value_outside_plausible_range(self):
        quote = 'Aylıq itki nisbəti 4% olaraq ölçülüb'
        result = verify_parameters(payload(entry(key='churn_monthly', value=4, unit='hissə', quote=quote)), SOURCES)
        self.assertEqual(result['verified'], [])
        self.assertIn('aralıqdan', result['rejected'][0]['reason'])

    def test_same_figure_with_percent_unit_is_accepted(self):
        quote = 'Aylıq itki nisbəti 4% olaraq ölçülüb'
        result = verify_parameters(payload(entry(key='churn_monthly', value=4, unit='%', quote=quote)), SOURCES)
        self.assertAlmostEqual(result['verified'][0]['value'], 0.04)
        self.assertEqual(result['verified'][0]['stated'], 4)

    def test_derived_value_needs_a_derivation(self):
        quote = 'Sektor üzrə illik xərc 1.2 milyard USD təşkil edir'
        bare = entry(key='market_size', value=600_000_000, unit='USD', quote=quote, confidence='derived')
        self.assertIn('hesablama izahı', verify_parameters(payload(bare), SOURCES)['rejected'][0]['reason'])
        explained = dict(bare, derivation='Sektor xərcinin yarısı bu seqmentə aiddir.')
        self.assertEqual(verify_parameters(payload(explained), SOURCES)['verified'][0]['grade'], 'derived')

    def test_duplicate_key_is_reported_not_silently_dropped(self):
        result = verify_parameters(payload(entry(), entry()), SOURCES)
        self.assertEqual(len(result['verified']), 1)
        self.assertIn('təkrar', result['rejected'][0]['reason'])

    def test_missing_keys_are_listed_with_coverage(self):
        result = verify_parameters(payload(entry()), SOURCES)
        self.assertNotIn('arpu', result['missing'])
        self.assertIn('cac', result['missing'])
        self.assertAlmostEqual(result['coverage'], round(1 / len(PARAMETERS), 3))

    def test_malformed_payloads(self):
        for raw in ('not json', json.dumps({'parameters': 'x'}), json.dumps({'parameters': []})):
            with self.assertRaises(ValueError):
                verify_parameters(raw, SOURCES)


class ProviderSchemaTest(unittest.TestCase):
    def build(self, tmp='.'):
        provider = Provider(tmp)
        provider.config = lambda: dict(AI_BASE_URL='https://api.example.test/v1', AI_API_KEY='k',
                                       AI_MODEL='test-model', AI_INPUT_USD_PER_MILLION='0.1',
                                       AI_OUTPUT_USD_PER_MILLION='0.2')
        return provider

    def test_prepare_requests_constrained_decoding(self):
        call = self.build().prepare([{'role': 'user', 'content': 'x'}], parameter_schema(), 'market_parameters')
        block = call['payload']['response_format']
        self.assertEqual(block['type'], 'json_schema')
        self.assertTrue(block['json_schema']['strict'])
        self.assertEqual(block['json_schema']['name'], 'market_parameters')

    def test_prepare_without_schema_keeps_json_object(self):
        call = self.build().prepare([{'role': 'user', 'content': 'x'}])
        self.assertEqual(call['payload']['response_format'], {'type': 'json_object'})

    def test_rejected_schema_falls_back_once_and_says_so(self):
        provider = self.build()
        call = provider.prepare([{'role': 'user', 'content': 'x'}], parameter_schema())
        seen = []

        def send(_call, payload):
            seen.append(payload['response_format']['type'])
            if payload['response_format']['type'] == 'json_schema':
                raise SchemaRejected()
            return dict(content='{}', cost=1, usage={}, estimated=False, schema_enforced=True)

        provider.send = send
        result = provider.execute(call)
        self.assertEqual(seen, ['json_schema', 'json_object'])
        self.assertFalse(result['schema_enforced'])


if __name__ == '__main__':
    unittest.main()
