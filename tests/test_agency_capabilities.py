import tempfile
import unittest
from pathlib import Path
from agency.engine import Agency
from agency.capabilities import local_day
from agency import workforce
from tests.test_agency_engine import FakeModels


class CapabilitiesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.models = FakeModels()
        self.agency = Agency(Path(self.tmp.name)/'test.sqlite3', self.models)

    def tearDown(self):
        self.agency.close()
        self.tmp.cleanup()

    def test_demo_must_be_explicit_and_unknown_order_not_guessed(self):
        self.assertIsNone(self.agency.tool_reply('48213 sifarişim haradadır?'))
        self.agency.load_demo_operations()
        self.assertIsNone(self.agency.tool_reply('99999 sifarişim haradadır?'))
        self.assertIsNone(self.agency.tool_reply('48213 və 48214 sifarişlərim'))
        self.assertTrue(self.agency.tool_reply('48213 sifarişim haradadır?')['tool']['demo'])

    def test_prepare_does_not_change_stock_confirm_is_idempotent(self):
        self.agency.load_demo_operations()
        before = self.agency.operation_state()['stock']
        request = self.agency.prepare_exchange('48213','L')
        self.assertEqual(before, self.agency.operation_state()['stock'])
        self.agency.confirm_exchange(request['id'])
        self.agency.confirm_exchange(request['id'])
        self.agency.load_demo_operations()
        self.assertEqual(2, next(s['quantity'] for s in self.agency.operation_state()['stock'] if s['size']=='L'))
        with self.assertRaises(ValueError): self.agency.prepare_exchange('48213','S')

    def test_expired_and_unavailable_orders_are_blocked(self):
        self.agency.load_demo_operations()
        with self.assertRaises(ValueError): self.agency.prepare_exchange('48214','L')
        with self.assertRaises(ValueError): self.agency.prepare_exchange('48213','M')
        with self.assertRaises(ValueError): self.agency.prepare_exchange('not-found','L')

    def test_agent_can_prepare_exchange_but_cannot_confirm_it(self):
        self.agency.load_demo_operations()
        before = self.agency.operation_state()['stock']
        result = self.agency.tool_reply('48213 sifarişini L ölçüsünə dəyişmək istəyirəm')
        self.assertEqual('prepared',result['tool']['exchange']['state'])
        self.assertEqual(before,self.agency.operation_state()['stock'])
        self.assertIsNone(self.agency.tool_reply('48213 sifarişini M ölçüsünə dəyiş')['tool']['exchange'])

    def test_policy_and_stock_rechecked_on_confirmation(self):
        self.agency.load_demo_operations()
        request = self.agency.prepare_exchange('48213','L')
        with self.agency.db:
            self.agency.db.execute("UPDATE demo_stock SET quantity=0 WHERE size='L'")
        with self.assertRaises(ValueError): self.agency.confirm_exchange(request['id'])
        with self.agency.db:
            self.agency.db.execute("UPDATE demo_stock SET quantity=3 WHERE size='L'")
        self.agency.update_policy(self.agency.policy_document()['body']+'\nYeni bənd: İnsan təsdiqi tələb olunur.')
        with self.assertRaises(ValueError): self.agency.confirm_exchange(request['id'])

    def test_tools_do_not_call_model_or_improve_hr_score(self):
        self.agency.load_demo_operations()
        self.agency._hire('soz')
        self.models.calls.clear()
        worker = self.agency.workers('soz')[0]
        with self.agency.db:
            self.agency.db.execute("UPDATE workers SET status='active' WHERE id=?",(worker['id'],))
        job_id = self.agency.submit_ticket('48213 sifarişim haradadır?')
        job = self.agency._one('SELECT * FROM jobs WHERE id=?',(job_id,))
        self.agency._work(job, worker)
        self.assertEqual([],self.models.calls)
        attempts=self.agency.attempts('soz')
        self.assertEqual('tool',attempts[-1]['outcome'])
        self.assertEqual(0,workforce.stats(worker['id'],attempts)['judged'])
        trace=self.agency.decision_trace(job_id)
        self.assertEqual('Sifariş və stok oxuma',trace['steps'][1]['tool']['name'])
        self.assertEqual(self.agency.policy_document()['version'],trace['document']['version'])

    def tender(self):
        return self.agency._one("SELECT id FROM documents WHERE service='tender' AND sample='tender_komputer.md'") or self.agency._one("SELECT id FROM documents WHERE service='tender' ORDER BY created_at LIMIT 1")

    def test_company_missing_and_insufficient_turnover(self):
        did=self.tender()['id']
        self.assertEqual('incomplete',self.agency.company_fit(did)['outcome'])
        self.agency.save_company(dict(name='Test MMC',body=f'{local_day().year-1} illik dövriyyə: 100 000 AZN.'))
        fit=self.agency.company_fit(did)
        self.assertEqual('fails',fit['outcome'])
        self.assertTrue(any('100 000' in r['proof'] and r['status']=='fails' for r in fit['rows']))

    def test_company_proofs_and_missing_tax_clause(self):
        year=local_day().year-1
        body=f'{year} illik dövriyyə: 600 000 AZN.\n{year}-05-10 oxşar müqavilə uğurla icra edilib: A.\n{year}-09-15 oxşar müqavilə uğurla icra edilib: B.'
        self.agency.save_company(dict(name='Test MMC',body=body))
        fit=self.agency.company_fit(self.tender()['id'])
        self.assertEqual('incomplete',fit['outcome'])
        self.assertEqual(2,sum(r['status']=='matches' for r in fit['rows']))
        self.assertTrue(any('Vergi' in r['requirement'] and r['status']=='missing' for r in fit['rows']))

    def test_wrong_year_duplicate_or_invalid_dates_not_counted(self):
        year=local_day().year-3
        line=f'{year}-05-10 oxşar müqavilə uğurla icra edilib: A.'
        self.agency.save_company(dict(name='Test MMC',body=f'{year} illik dövriyyə: 600 000 AZN.\n{line}\n{line}\n2025-02-31 oxşar müqavilə uğurla icra edilib: B.'))
        fit=self.agency.company_fit(self.tender()['id'])
        self.assertFalse(any(r['status']=='matches' for r in fit['rows']))
