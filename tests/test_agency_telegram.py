import tempfile
import unittest
from pathlib import Path

from agency.engine import Agency
from agency.telegram import TelegramBridge, WELCOME, token_from
from tests.test_agency_engine import FakeModels


class FakeTelegram:
    def __init__(self):
        self.inbox, self.sent = [], []

    def __call__(self, method, params):
        if method == 'getMe':
            return {'username': 'bazarim_demo_bot'}
        if method == 'getUpdates':
            batch = [u for u in self.inbox if u['update_id'] >= params['offset']]
            return batch
        if method == 'sendMessage':
            self.sent.append((params['chat_id'], params['text']))
            return {}
        raise AssertionError(method)

    def write(self, chat, text):
        self.inbox.append({'update_id': len(self.inbox) + 100, 'message': {'chat': {'id': chat}, 'text': text}})


class TelegramTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.agency = Agency(Path(self.folder.name) / 'agency.sqlite3', FakeModels())
        self.addCleanup(self.agency.close)
        while self.agency.step():
            pass
        self.api = FakeTelegram()
        self.bridge = TelegramBridge(self.agency, 'token', api=self.api)

    def work(self):
        while self.agency.step():
            pass

    def test_start_explains_the_bot_and_the_data_use(self):
        self.api.write(7, '/start')
        self.bridge.poll(timeout=0)
        self.assertEqual(self.api.sent, [(7, WELCOME)])
        self.assertIn('AI provayderinə göndərilir', WELCOME)

    def test_message_becomes_a_ticket_and_the_verified_answer_comes_back(self):
        self.api.write(7, 'Bakı daxilində çatdırılma neçəyədir?')
        self.bridge.poll(timeout=0)
        self.assertEqual(self.bridge.deliver(), 0)  # nothing final yet
        self.work()
        self.assertEqual(self.bridge.deliver(), 1)
        chat, text = self.api.sent[0]
        self.assertEqual(chat, 7)
        self.assertIn('5 AZN', text)
        self.assertEqual(self.bridge.deliver(), 0)  # never twice

    def test_offset_survives_a_restart(self):
        self.api.write(7, 'Bakı daxilində çatdırılma neçəyədir?')
        self.bridge.poll(timeout=0)
        again = TelegramBridge(self.agency, 'token', api=self.api)
        self.assertEqual(again.poll(timeout=0), 0)  # the same update is not turned into a second ticket
        self.assertEqual(len([j for j in self.agency.snapshot()['services']['soz']['jobs'] if j['source'] == 'telegram']), 1)

    def test_drafts_wait_for_approval_and_shadow_answers_never_go_out(self):
        self.agency.set_mode('draft')
        self.api.write(7, 'Bakı daxilində çatdırılma neçəyədir?')
        self.bridge.poll(timeout=0)
        self.work()
        self.assertEqual(self.bridge.deliver(), 0)
        draft = next(j for j in self.agency.snapshot()['services']['soz']['jobs'] if j['source'] == 'telegram')
        self.agency.approve_draft(draft['id'])
        self.assertEqual(self.bridge.deliver(), 1)
        self.agency.set_mode('shadow')
        self.api.write(8, 'Bakı daxilində çatdırılma neçəyədir?')
        self.bridge.poll(timeout=0)
        self.work()
        self.assertEqual(self.bridge.deliver(), 0)
        self.assertFalse(any(chat == 8 for chat, _ in self.api.sent))

    def test_a_question_outside_the_rules_gets_the_handoff_notice(self):
        self.api.write(9, 'Mağazanız harada yerləşir?')
        self.bridge.poll(timeout=0)
        self.work()
        self.bridge.deliver()
        self.assertIn('əməkdaşımıza ötürdük', self.api.sent[-1][1])

    def test_only_drafts_can_be_approved(self):
        with self.assertRaises(ValueError):
            self.agency.approve_draft('yoxdur')

    def test_token_is_read_from_env_file(self):
        folder = Path(self.folder.name)
        (folder / '.env').write_text('AI_MODEL=x\nTELEGRAM_BOT_TOKEN="123:abc"\n', encoding='utf-8')
        self.assertEqual(token_from(folder), '123:abc')
        (folder / '.env').write_text('TELEGRAM_BOT_TOKEN=\n', encoding='utf-8')
        self.assertIsNone(token_from(folder))


if __name__ == '__main__':
    unittest.main()
