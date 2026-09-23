"""Bug #9: execute real rules and handler ASTs without importing live bot services."""
import ast
import asyncio
import copy
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import unquote

from quote_payments import (QuotePayments, PaymentRuleError, resolve_env_payment,
                            persist_balance_payment, off_session_message, payment_lock,
                            close_balance_checkout, prepare_balance_link, persist_checkout_balance)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
EMAIL = 'buyer@example.test'
SELLER = 'seller'


def quote_record(qid='DEV-1', **overrides):
    return {'id': 'q-' + qid, 'fields': dict(quote_id=qid, client_email=EMAIL,
            seller_slug=SELLER, status='accepted', total_ttc='1000', deposit_amount='300',
            remaining_amount='700', **overrides)}


def payment(role='balance', status='Pending', qid='DEV-1', rid='rec-balance', age=25):
    return {'id': rid, 'fields': {'Quote ID': qid, 'Payment Role': role, 'Status': status,
            'Client Key': EMAIL, 'Amount Cents': 70000 if role == 'balance' else 30000,
            'Sent At': (NOW - timedelta(hours=age)).isoformat(),
            'Content ID': 'seller-content', 'Checkout Session ID': 'cs-test', 'Caption': 'Original'}}


def response(data, status=200):
    result = Mock(status_code=status, text='offline')
    result.json.side_effect = lambda: copy.deepcopy(data)
    if status >= 400:
        result.raise_for_status.side_effect = RuntimeError('HTTP unavailable')
    return result


class OfflineHTTP:
    def __init__(self, quotes=None, payments=None):
        self.quotes = quotes if quotes is not None else [quote_record()]
        deposit = payment('deposit', 'Paid', rid='rec-deposit')
        deposit['fields'].update({'Stripe Customer ID': 'cus-test', 'Stripe Payment Method ID': 'pm-test'})
        self.payments = payments if payments is not None else [deposit]
        self.patches = []
        self.posts = []

    def get(self, url, **kwargs):
        table = unquote(url).split('/')[-1]
        if table.startswith('rec-'):
            rows = [r for r in self.payments if r['id'] == table]
            return response(rows[0] if rows else {}, 200 if rows else 404)
        if table == 'PWA Clients':
            return response({'records': []})
        rows = self.quotes if table == 'Quotes' else self.payments
        formula = kwargs.get('params', {}).get('filterByFormula', '')
        pairs = re.findall(r"\{([^}]+)\}='([^']*)'", formula)
        def matches(row):
            fields = row['fields']
            for name, value in pairs:
                if f"NOT({{{name}}}='')" in formula:
                    if not fields.get(name): return False
                elif name == 'Status' and 'OR(' in formula:
                    if fields.get(name) not in ('Pending', 'Paid'): return False
                elif fields.get(name) != value:
                    return False
            amount = re.search(r'\{Amount Cents\}=(\d+)', formula)
            return not amount or fields.get('Amount Cents') == int(amount.group(1))
        return response({'records': [copy.deepcopy(r) for r in rows if matches(r)]})

    def patch(self, url, **kwargs):
        self.patches.append((url, copy.deepcopy(kwargs['json']['fields'])))
        row = next(r for r in self.payments if r['id'] == url.split('/')[-1])
        row['fields'].update(kwargs['json']['fields'])
        return response(row)

    def post(self, url, **kwargs):
        self.posts.append((url, copy.deepcopy(kwargs.get('json'))))
        if 'Payment%20Links' in url:
            row = {'id': 'rec-new', 'fields': copy.deepcopy(kwargs['json']['fields'])}
            self.payments.append(row)
            return response(row)
        return response({'success': True})


class CancelHandler(Exception):
    pass


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)


def load_functions(file, names, scope):
    tree = ast.parse((ROOT / file).read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / file), 'exec'), scope)


def scope_for(http):
    return dict(requests=http, BASE_ID='offline', AIRTABLE_API_KEY='offline',
                QuotePayments=QuotePayments, PaymentRuleError=PaymentRuleError,
                resolve_env_payment=resolve_env_payment, payment_lock=payment_lock,
                close_balance_checkout=close_balance_checkout, datetime=datetime,
                prepare_balance_link=prepare_balance_link, persist_checkout_balance=persist_checkout_balance,
                Decimal=Decimal, ROUND_HALF_UP=ROUND_HALF_UP, re=re,
                types=SimpleNamespace(Message=object), CancelHandler=CancelHandler,
                print=lambda *args: None)


def run_async(awaitable):
    async def guarded():
        with patch('socket.socket', side_effect=AssertionError('Live network forbidden')):
            return await awaitable
    return asyncio.run(guarded())


class EnvRulesTests(unittest.TestCase):
    def setUp(self):
        self.http = OfflineHTTP()
        self.scope = scope_for(self.http)
        load_functions('bott_webhook.py', ['find_matching_accepted_quote', 'find_matching_balance_quote'], self.scope)

    def resolve(self, cents):
        return resolve_env_payment(self.scope['find_matching_accepted_quote'],
                                   self.scope['find_matching_balance_quote'], EMAIL, SELLER, cents)

    def test_01_deposit_300(self):
        self.http.payments.clear()
        self.assertEqual(self.resolve(30000), ('DEV-1', 'deposit'))

    def test_02_03_balance_700_exact_identity(self):
        self.assertEqual(self.resolve(70000), ('DEV-1', 'balance'))

    def test_04_normal_150(self):
        self.assertEqual(self.resolve(15000), ('', ''))

    def test_05_deposit_pending_not_reassociated(self):
        self.http.payments[0]['fields']['Status'] = 'Pending'
        self.assertEqual(self.resolve(30000), ('', ''))

    def test_06_07_existing_balance_not_reassociated(self):
        for status in ('Pending', 'Paid'):
            with self.subTest(status=status):
                self.http.payments = [self.http.payments[0], payment(status=status)]
                self.assertEqual(self.resolve(70000), ('', ''))

    def test_08_no_paid_deposit(self):
        self.http.payments.clear()
        self.assertEqual(self.resolve(70000), ('', ''))

    def test_09_ambiguous_quotes(self):
        self.http.quotes.append(quote_record('DEV-2'))
        self.http.payments.append(payment('deposit', 'Paid', 'DEV-2', 'rec-deposit2'))
        with self.assertRaisesRegex(PaymentRuleError, 'Plusieurs devis'):
            self.resolve(70000)

    def test_deposit_has_priority(self):
        self.http.payments.clear()
        self.http.quotes[0]['fields']['remaining_amount'] = '300'
        self.assertEqual(self.resolve(30000), ('DEV-1', 'deposit'))

    def test_no_truncation_of_fractional_cent(self):
        self.http.quotes[0]['fields']['remaining_amount'] = '700.009'
        self.assertEqual(self.resolve(70000), ('', ''))

    def test_http_error_never_becomes_normal(self):
        self.http.get = Mock(return_value=response({}, 503))
        with self.assertRaises(RuntimeError):
            self.resolve(70000)

    def test_pagination_reads_all_candidates(self):
        http = Mock()
        http.get.side_effect = [response({'records': [quote_record()], 'offset': 'next'}),
                                response({'records': [quote_record('DEV-2')]})]
        self.assertEqual(len(QuotePayments(http, 'offline', 'offline').records('Quotes', 'x')), 2)
        self.assertEqual(http.get.call_args.kwargs['params']['offset'], 'next')


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.http = OfflineHTTP()
        self.row = payment()
        self.http.payments.append(self.row)
        self.store = QuotePayments(self.http, 'offline', 'offline')

    def select(self, cents=70000):
        return self.store.find_pending_balance(EMAIL, SELLER, cents, NOW)

    def test_10_16_young_balance_refused(self):
        self.row['fields']['Sent At'] = (NOW - timedelta(hours=23, minutes=59)).isoformat()
        with self.assertRaisesRegex(PaymentRuleError, '24 h'):
            self.select()

    def test_11_12_due_at_exactly_24_and_25_hours(self):
        for hours in (24, 25):
            with self.subTest(hours=hours):
                self.row['fields']['Sent At'] = (NOW - timedelta(hours=hours)).isoformat()
                self.assertEqual(self.select()['id'], 'rec-balance')

    def test_13_paid_between_selection_and_charge(self):
        selected = self.select()
        self.row['fields']['Status'] = 'Paid'
        with self.assertRaises(PaymentRuleError):
            self.store.validate_balance(self.store.get(selected['id']), EMAIL, SELLER, 70000, now=NOW)

    def test_14_multiple_pending(self):
        self.http.payments.append(payment(rid='rec-balance2'))
        with self.assertRaisesRegex(PaymentRuleError, 'Plusieurs soldes'):
            self.select()

    def test_15_no_pending_is_refused(self):
        self.http.payments.remove(self.row)
        with self.assertRaises(PaymentRuleError): self.select()

    def test_17_other_amount_is_refused(self):
        with self.assertRaisesRegex(PaymentRuleError, "700,00"): self.select(15000)

    def test_timestamp_formats_and_invalid(self):
        for value in ('2026-09-19T12:00:00', '2026-09-19T12:00:00Z', '2026-09-19T14:00:00+02:00'):
            with self.subTest(value=value):
                self.row['fields']['Sent At'] = value
                self.assertIsNotNone(self.select())
        for value in ('', None, 'invalid'):
            with self.subTest(value=value):
                self.row['fields']['Sent At'] = value
                with self.assertRaises(PaymentRuleError): self.select()

    def test_inconsistent_quote_seller_and_missing_deposit_refused(self):
        self.http.quotes[0]['fields']['seller_slug'] = 'another'
        with self.assertRaises(PaymentRuleError): self.select()
        self.http.quotes[0]['fields']['seller_slug'] = SELLER
        self.http.payments.remove(self.http.payments[0])
        with self.assertRaises(PaymentRuleError): self.select()

    def handler(self, amount=700, race=False):
        # Dates relative to real UTC for the production handler's clock.
        age = NOW - datetime.fromisoformat(self.row['fields']['Sent At'])
        self.row['fields']['Sent At'] = (datetime.now(timezone.utc) - age).isoformat()
        scope = scope_for(self.http)
        intent = SimpleNamespace(id='pi-test', status='succeeded')
        stripe = SimpleNamespace(PaymentIntent=SimpleNamespace(create=Mock(return_value=intent)),
                                 error=SimpleNamespace(CardError=type('CardError', (Exception,), {})))
        session = {'status': 'expired', 'payment_status': 'unpaid', 'amount_total': 70000,
                   'metadata': {'client_key': EMAIL, 'seller_slug': SELLER, 'content_id': 'seller-content'}}
        def retrieve(*args):
            if race: self.row['fields']['Status'] = 'Paid'
            return session
        stripe.checkout = SimpleNamespace(Session=SimpleNamespace(retrieve=Mock(side_effect=retrieve), expire=Mock()))
        scope.update(stripe=stripe, is_admin=lambda x: True,
                     get_pwa_client_by_topic=lambda x: {'email': EMAIL, 'seller_slug': SELLER})
        load_functions('bott_webhook.py', ['parse_amount_to_cents', 'encaisser_off_session'], scope)
        message = SimpleNamespace(text=f'/encaisser{amount}', from_user=SimpleNamespace(id=1),
                                  to_python=lambda: {'message_thread_id': 2}, reply=AsyncMock())
        try: run_async(scope['encaisser_off_session'](message))
        except CancelHandler: pass
        return stripe, message

    def test_handler_refuses_young_without_stripe_create(self):
        self.row['fields']['Sent At'] = (NOW - timedelta(hours=23, minutes=59)).isoformat()
        stripe, msg = self.handler()
        stripe.PaymentIntent.create.assert_not_called()
        self.assertIn('24 h', str(msg.reply.call_args))

    def test_handler_refuses_ambiguity_without_stripe_create(self):
        self.http.payments.append(payment(rid='rec-balance2'))
        stripe, _ = self.handler()
        stripe.PaymentIntent.create.assert_not_called()

    def test_handler_revalidates_paid_before_create(self):
        stripe, _ = self.handler(race=True)
        stripe.PaymentIntent.create.assert_not_called()

    def test_handler_transports_record_and_idempotency(self):
        stripe, _ = self.handler()
        args = stripe.PaymentIntent.create.call_args.kwargs
        self.assertEqual(args['metadata']['payment_link_record_id'], 'rec-balance')
        self.assertEqual(args['metadata']['payment_role'], 'balance')
        self.assertEqual(args['metadata']['quote_id'], 'DEV-1')
        self.assertEqual(args['idempotency_key'], 'novapulse-balance-rec-balance')
        self.assertEqual(self.row['fields']['Stripe Payment Intent ID'], 'pi-test')

    def test_handler_independent_collection_refused(self):
        stripe, _ = self.handler(150)
        stripe.PaymentIntent.create.assert_not_called()

    def test_checkout_already_paid_blocks_offsession(self):
        api = SimpleNamespace(checkout=SimpleNamespace(Session=SimpleNamespace(
            retrieve=Mock(return_value={'status': 'complete', 'payment_status': 'paid', 'amount_total': 70000,
                'metadata': {'client_key': EMAIL, 'seller_slug': SELLER, 'content_id': 'seller-content'}}),
            expire=Mock())))
        with self.assertRaisesRegex(PaymentRuleError, 'déjà payé'):
            close_balance_checkout(api, self.row, EMAIL, SELLER, 70000)
        api.checkout.Session.expire.assert_not_called()

    def test_open_checkout_closed_before_offsession(self):
        api = SimpleNamespace(checkout=SimpleNamespace(Session=SimpleNamespace(
            retrieve=Mock(return_value={'status': 'open', 'payment_status': 'unpaid', 'amount_total': 70000,
                'metadata': {'client_key': EMAIL, 'seller_slug': SELLER, 'content_id': 'seller-content'}}),
            expire=Mock(return_value={'status': 'expired'}))))
        close_balance_checkout(api, self.row, EMAIL, SELLER, 70000)
        api.checkout.Session.expire.assert_called_once_with('cs-test')

    def test_existing_intent_blocks_another_collection(self):
        self.row['fields']['Stripe Payment Intent ID'] = 'pi-in-progress'
        with self.assertRaisesRegex(PaymentRuleError, 'déjà engagé'):
            self.select()


class EnvHandlerTests(unittest.TestCase):
    def handler(self, role='balance', send_success=True, ambiguous=False, media=False,
                http=None, checkout_status='open', payment_status='unpaid', before_send=None):
        http = http or OfflineHTTP()
        scope = scope_for(http)
        bot = SimpleNamespace(send_message=AsyncMock(), get_file=AsyncMock(return_value=SimpleNamespace(file_path='offline')),
                              download_file=AsyncMock(return_value=io.BytesIO(b'offline-media')))
        save_scope = {'os': os, 'requests': http, 'BASE_ID': 'offline',
                      'AIRTABLE_API_KEY': 'offline', 'datetime': datetime, 'print': lambda *a: None}
        load_functions('payment_links.py', ['save_payment_link_to_airtable'], save_scope)
        lookup = Mock(side_effect=QuotePayments(http, 'offline', 'offline').find_balance_quote)
        if ambiguous: lookup.side_effect = PaymentRuleError('Plusieurs devis possibles')
        def retrieve(session_id):
            row = next(r for r in http.payments if r['fields'].get('Payment Role') == 'balance')
            return {'id': session_id, 'url': row['fields']['Payment Link URL'],
                    'status': checkout_status, 'payment_status': payment_status, 'amount_total': 70000,
                    'metadata': {'client_key': EMAIL, 'seller_slug': SELLER,
                                 'content_id': row['fields']['Content ID']}}
        stripe = SimpleNamespace(checkout=SimpleNamespace(Session=SimpleNamespace(retrieve=Mock(side_effect=retrieve))))
        scope.update(bot=bot, is_admin=lambda x: True, pending_notes={},
                     stripe=stripe,
                     get_pwa_client_by_topic=lambda x: {'email': EMAIL, 'seller_slug': SELLER},
                     get_pwa_client_by_email=lambda x: {'type_client': 'Particulier'},
                     detect_motif=lambda x: 'Original', BRIDGE_API_URL='https://bridge.invalid',
                     find_matching_accepted_quote=Mock(return_value={'quote_id': 'DEV-1'} if role == 'deposit' else None),
                     find_matching_balance_quote=lookup if role == 'balance' else Mock(return_value=None),
                     create_dynamic_checkout=Mock(return_value=('https://checkout.invalid',
                                                                 'cs-replacement' if checkout_status == 'expired' else 'cs-test')),
                     save_payment_link_to_airtable=save_scope['save_payment_link_to_airtable'])
        original_post = http.post
        def post(url, **kwargs):
            if url.endswith('/upload-media'):
                return response({'success': True, 'mediaUrl': 'https://media.invalid/image.jpg'})
            if '/pwa/' in url:
                if before_send: before_send()
                if not send_success: return response({'success': False}, 500)
            return original_post(url, **kwargs)
        load_functions('bott_webhook.py', ['parse_amount_to_cents', 'nettoyer_commande_env', 'envoyer_contenu_payant'], scope)
        message = SimpleNamespace(text='/env700 Rendu', caption=None, from_user=SimpleNamespace(id=1),
                                  to_python=lambda: {'message_thread_id': 2}, reply=AsyncMock(),
                                  photo=[SimpleNamespace(file_id='offline')] if media else None,
                                  video=None, document=None, animation=None, audio=None, voice=None)
        with patch.object(http, 'post', side_effect=post):
            run_async(scope['envoyer_contenu_payant'](message))
        return http, scope, message

    def test_real_env_persists_balance_and_stamps_after_send(self):
        http, _, _ = self.handler()
        row = http.payments[-1]['fields']
        self.assertEqual((row['Quote ID'], row['Payment Role'], row['Status']), ('DEV-1', 'balance', 'Pending'))
        self.assertTrue(row['Content ID'])
        self.assertEqual(row['Checkout Session ID'], 'cs-test')
        initial = next(body['fields'] for url, body in http.posts if 'Payment%20Links' in url)
        self.assertNotIn('Sent At', initial)
        self.assertIn('Sent At', row)

    def test_real_env_failed_send_has_no_collectable_timestamp(self):
        http, _, msg = self.handler(send_success=False)
        self.assertNotIn('Sent At', http.payments[-1]['fields'])
        self.assertIn('non confirmé', str(msg.reply.call_args))

    def test_real_env_ambiguity_creates_no_checkout_or_payment(self):
        http, scope, _ = self.handler(ambiguous=True)
        scope['create_dynamic_checkout'].assert_not_called()
        self.assertEqual(http.posts, [])

    def test_real_env_normal_and_deposit_keep_historical_timestamp(self):
        for role in ('normal', 'deposit'):
            with self.subTest(role=role):
                http, _, _ = self.handler(role)
                fields = http.payments[-1]['fields']
                self.assertEqual(fields['Payment Role'], '' if role == 'normal' else 'deposit')
                self.assertIn('Sent At', fields)

    def test_real_env_balance_media_preserves_paywall_identifiers(self):
        http, _, _ = self.handler(media=True)
        payload = next(body for url, body in http.posts if url.endswith('/pwa/send-paid-content'))
        self.assertTrue(payload['isMedia'])
        self.assertEqual(payload['mediaUrl'], 'https://media.invalid/image.jpg')
        self.assertEqual(payload['sessionId'], 'cs-test')
        self.assertEqual(payload['contentId'], http.payments[-1]['fields']['Content ID'])
        self.assertEqual(payload['amount'], 70000)

    def test_bridge_failure_blocks_collection_and_retry_reuses_single_balance(self):
        http, first_scope, _ = self.handler(send_success=False)
        original = copy.deepcopy(http.payments[-1])
        self.assertNotIn('Sent At', original['fields'])
        store = QuotePayments(http, 'offline', 'offline')
        with self.assertRaisesRegex(PaymentRuleError, 'Sent At'):
            store.find_pending_balance(EMAIL, SELLER, 70000)
        first_scope['stripe'].PaymentIntent = SimpleNamespace(create=Mock())
        load_functions('bott_webhook.py', ['encaisser_off_session'], first_scope)
        collect_message = SimpleNamespace(text='/encaisser700', from_user=SimpleNamespace(id=1),
                                          to_python=lambda: {'message_thread_id': 2}, reply=AsyncMock())
        with self.assertRaises(CancelHandler):
            run_async(first_scope['encaisser_off_session'](collect_message))
        first_scope['stripe'].PaymentIntent.create.assert_not_called()
        self.assertIn('Sent At', str(collect_message.reply.call_args))
        first_scope['create_dynamic_checkout'].assert_called_once()
        before = datetime.now(timezone.utc)
        def before_send():
            self.assertNotIn('Sent At', http.payments[-1]['fields'])
            with self.assertRaises(PaymentRuleError): store.find_pending_balance(EMAIL, SELLER, 70000)
        _, retry_scope, _ = self.handler(http=http, before_send=before_send)
        after = datetime.now(timezone.utc)
        retry_scope['create_dynamic_checkout'].assert_not_called()
        balances = store.balance_records(http.payments, 'DEV-1')
        self.assertEqual(len(balances), 1)
        row = balances[0]
        self.assertEqual(row['id'], original['id'])
        for key in ('Content ID', 'Checkout Session ID', 'Payment Link URL'):
            self.assertEqual(row['fields'][key], original['fields'][key])
        sent = datetime.fromisoformat(row['fields']['Sent At']).replace(tzinfo=timezone.utc)
        self.assertLessEqual(before, sent)
        self.assertLessEqual(sent, after)
        with self.assertRaisesRegex(PaymentRuleError, '24 h'):
            store.find_pending_balance(EMAIL, SELLER, 70000, sent + timedelta(hours=23, minutes=59))
        self.assertEqual(store.find_pending_balance(EMAIL, SELLER, 70000,
                                                   sent + timedelta(hours=24))['id'], original['id'])

    def test_lost_bridge_response_resumes_same_checkout_without_second_payment(self):
        http = OfflineHTTP()
        original_post = http.post
        attempts = []
        def delivered_then_timeout(url, **kwargs):
            result = original_post(url, **kwargs)
            if '/pwa/' in url:
                attempts.append(kwargs['json']['checkout_url'])
                raise TimeoutError('Response lost after delivery')
            return result
        with patch.object(http, 'post', side_effect=delivered_then_timeout):
            self.handler(http=http)
        self.assertNotIn('Sent At', http.payments[-1]['fields'])
        _, scope, _ = self.handler(http=http)
        scope['create_dynamic_checkout'].assert_not_called()
        sent = [body['checkout_url'] for url, body in http.posts if '/pwa/' in url]
        self.assertEqual(sent, [attempts[0], attempts[0]])
        self.assertEqual(len([r for r in http.payments if r['fields']['Payment Role'] == 'balance']), 1)

    def test_expired_unpaid_checkout_replaced_on_same_incomplete_row(self):
        http, _, _ = self.handler(send_success=False)
        original = copy.deepcopy(http.payments[-1])
        _, scope, _ = self.handler(http=http, checkout_status='expired')
        scope['create_dynamic_checkout'].assert_called_once()
        self.assertEqual(http.payments[-1]['id'], original['id'])
        self.assertEqual(http.payments[-1]['fields']['Content ID'], original['fields']['Content ID'])
        self.assertEqual(http.payments[-1]['fields']['Checkout Session ID'], 'cs-replacement')
        self.assertIn('Sent At', http.payments[-1]['fields'])
        self.assertEqual(len([r for r in http.payments if r['fields']['Payment Role'] == 'balance']), 1)

    def test_paid_checkout_during_failed_send_is_not_replaced_or_resent(self):
        http, _, _ = self.handler(send_success=False)
        before = len(http.posts)
        _, scope, msg = self.handler(http=http, checkout_status='complete', payment_status='paid')
        scope['create_dynamic_checkout'].assert_not_called()
        self.assertEqual(len(http.posts), before)
        self.assertNotIn('Sent At', http.payments[-1]['fields'])
        self.assertIn('déjà payé', str(msg.reply.call_args))

    def test_multiple_incomplete_balances_refuse_resume(self):
        http, _, _ = self.handler(send_success=False)
        duplicate = copy.deepcopy(http.payments[-1])
        duplicate['id'] = 'rec-duplicate'
        http.payments.append(duplicate)
        before = len(http.posts)
        _, scope, msg = self.handler(http=http)
        scope['create_dynamic_checkout'].assert_not_called()
        self.assertEqual(len(http.posts), before)
        self.assertIn('Plusieurs soldes', str(msg.reply.call_args))

    def test_successful_bridge_but_failed_timestamp_can_be_resumed(self):
        http = OfflineHTTP()
        original_patch = http.patch
        def fail_timestamp(url, **kwargs):
            if 'Sent At' in kwargs['json']['fields']:
                raise TimeoutError('Timestamp not persisted')
            return original_patch(url, **kwargs)
        with patch.object(http, 'patch', side_effect=fail_timestamp):
            self.handler(http=http)
        self.assertNotIn('Sent At', http.payments[-1]['fields'])
        _, scope, _ = self.handler(http=http)
        scope['create_dynamic_checkout'].assert_not_called()
        self.assertIn('Sent At', http.payments[-1]['fields'])

    def test_resume_rechecks_state_before_send_without_resetting_existing_timestamp(self):
        http, _, _ = self.handler(send_success=False)
        original_get = http.get
        reads = []
        sent_at = '2026-09-20T12:00:00'
        def another_delivery_completed(url, **kwargs):
            if url.endswith('/rec-new'):
                reads.append(url)
                if len(reads) == 2:
                    http.payments[-1]['fields']['Sent At'] = sent_at
            return original_get(url, **kwargs)
        before = len(http.posts)
        with patch.object(http, 'get', side_effect=another_delivery_completed):
            _, scope, msg = self.handler(http=http)
        scope['create_dynamic_checkout'].assert_not_called()
        self.assertEqual(http.payments[-1]['fields']['Sent At'], sent_at)
        self.assertEqual(len(http.posts), before)
        self.assertIn('non confirmé', str(msg.reply.call_args))


class WebhookTests(unittest.TestCase):
    def setUp(self):
        self.http = OfflineHTTP()
        self.row = payment()
        self.http.payments.append(self.row)
        self.enqueue = Mock()
        self.number = Mock(return_value='NP-test')
        self.intent = {'id': 'pi-test', 'amount_received': 70000, 'customer': 'cus-test',
                       'payment_method': 'pm-test', 'metadata': {
                           'channel': 'novapulse_off_session', 'payment_link_record_id': 'rec-balance',
                           'client_key': EMAIL, 'seller_slug': SELLER, 'quote_id': 'DEV-1', 'payment_role': 'balance'}}

    def webhook(self):
        event = {'type': 'payment_intent.succeeded', 'data': {'object': self.intent}}
        scope = scope_for(self.http)
        scope.update(Request=object, Header=lambda x: x, os=os, HTTPException=HTTPException,
                     stripe=SimpleNamespace(Webhook=SimpleNamespace(construct_event=lambda **kw: event)),
                     STRIPE_WEBHOOK_SECRET='offline', PAYMENT_LINKS_TABLE='Payment Links',
                     persist_balance_payment=persist_balance_payment, off_session_message=off_session_message,
                     get_next_invoice_number=self.number, enqueue_persisted_response=self.enqueue)
        load_functions('stripe_webhook.py', ['stripe_webhook'], scope)
        with patch.dict(os.environ, {'BRIDGE_API_URL': 'https://bridge.invalid'}):
            return run_async(scope['stripe_webhook'](SimpleNamespace(body=AsyncMock(return_value=b'offline'))))

    def test_18_to_23_update_existing_once_and_preserve_content(self):
        original = copy.deepcopy(self.row['fields'])
        self.assertEqual(self.webhook(), {'status': 'ok'})
        self.assertEqual(self.row['fields']['Status'], 'Paid')
        for key in ('Quote ID', 'Payment Role', 'Sent At', 'Content ID', 'Checkout Session ID', 'Caption'):
            self.assertEqual(self.row['fields'][key], original[key])
        self.assertFalse(any('Payment%20Links' in url for url, _ in self.http.posts))
        self.assertEqual(self.webhook(), {'status': 'ok'})
        self.number.assert_called_once()
        self.enqueue.assert_called_once()
        self.assertEqual(len(self.http.patches), 1)
        unlocked = [body for url, body in self.http.posts if url.endswith('/pwa/unlock')]
        self.assertEqual(unlocked[0]['contentId'], original['Content ID'])

    def test_24_paid_with_another_intent_refused(self):
        self.row['fields'].update({'Status': 'Paid', 'Stripe Payment Intent ID': 'pi-other'})
        with self.assertRaises(HTTPException): self.webhook()
        self.assertEqual(self.http.patches, [])
        self.number.assert_not_called()
        self.enqueue.assert_not_called()

    def test_25_26_normal_creates_normal_row_and_generic_message(self):
        self.intent['metadata'].update(payment_role='', quote_id='', payment_link_record_id='')
        self.webhook()
        created = [body['fields'] for url, body in self.http.posts if 'Payment%20Links' in url]
        self.assertEqual(len(created), 1)
        self.assertEqual((created[0]['Quote ID'], created[0]['Payment Role']), ('', ''))
        messages = [body['text'] for url, body in self.http.posts if url.endswith('/pwa/send-admin-message')]
        self.assertEqual(len(messages), 1)
        self.assertNotIn('solde', messages[0].lower())

    def test_27_balance_message(self):
        self.webhook()
        messages = [body['text'] for url, body in self.http.posts if url.endswith('/pwa/send-admin-message')]
        self.assertIn('solde', messages[0])

    def test_missing_reference_or_identity_mismatch_never_creates(self):
        for key, value in (('payment_link_record_id', ''), ('client_key', 'other'), ('quote_id', 'DEV-other')):
            with self.subTest(key=key):
                before = dict(self.intent['metadata'])
                self.intent['metadata'][key] = value
                with self.assertRaises(HTTPException): self.webhook()
                self.intent['metadata'] = before
        self.assertEqual(self.http.patches, [])
        self.assertEqual(self.http.posts, [])

    def test_patch_failure_does_not_invoice_and_requests_retry(self):
        self.http.patch = Mock(side_effect=RuntimeError('unavailable'))
        with self.assertRaises(HTTPException) as exc: self.webhook()
        self.assertEqual(exc.exception.status_code, 503)
        self.enqueue.assert_not_called()

    def test_amount_mismatch_never_mutates(self):
        self.intent['amount_received'] = 69999
        with self.assertRaises(HTTPException): self.webhook()
        self.assertEqual(self.http.patches, [])
        self.number.assert_not_called()

    def test_concurrent_same_process_deliveries_invoice_once(self):
        from concurrent.futures import ThreadPoolExecutor
        def deliver():
            return persist_balance_payment(QuotePayments(self.http, 'offline', 'offline'),
                                           self.intent, self.number, self.enqueue)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: deliver(), range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.number.assert_called_once()
        self.enqueue.assert_called_once()

    def test_checkout_balance_paid_before_24_hours(self):
        scope = scope_for(self.http)
        scope.update(PAYMENT_LINKS_TABLE='Payment Links', get_next_invoice_number=self.number,
                     enqueue_persisted_response=self.enqueue)
        # Isolate the balance row so session lookup selects exactly that record.
        self.http.payments = [self.row]
        self.row['fields']['Sent At'] = NOW.isoformat()
        load_functions('stripe_webhook.py', ['mark_payment_link_as_paid_by_session'], scope)
        fn = scope['mark_payment_link_as_paid_by_session']
        self.assertEqual(fn('cs-test', {'Stripe Payment Intent ID': 'pi-checkout'}, SELLER), 'rec-balance')
        self.assertEqual(self.row['fields']['Status'], 'Paid')
        self.assertEqual(self.row['fields']['Payment Role'], 'balance')
        fn('cs-test', {'Stripe Payment Intent ID': 'pi-checkout'}, SELLER)
        self.number.assert_called_once()
        self.enqueue.assert_called_once()

    def concurrent_checkout(self, intent_ids):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        scope = scope_for(self.http)
        scope.update(PAYMENT_LINKS_TABLE='Payment Links', get_next_invoice_number=self.number,
                     enqueue_persisted_response=self.enqueue)
        self.http.payments = [self.row]
        load_functions('stripe_webhook.py', ['mark_payment_link_as_paid_by_session'], scope)
        original_get = self.http.get
        barrier = Barrier(2)
        snapshots = []
        def overlapping_get(url, **kwargs):
            result = original_get(url, **kwargs)
            if kwargs.get('params', {}).get('filterByFormula') == "{Checkout Session ID}='cs-test'":
                snapshots.append(result.json()['records'][0]['fields']['Status'])
                barrier.wait(timeout=5)
            return result
        with patch.object(self.http, 'get', side_effect=overlapping_get), ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(scope['mark_payment_link_as_paid_by_session'],
                        'cs-test', {'Stripe Payment Intent ID': pi}, SELLER) for pi in intent_ids]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(snapshots, ['Pending', 'Pending'])
        self.number.assert_called_once()
        self.enqueue.assert_called_once()
        self.assertEqual(len(self.http.patches), 1)
        self.assertEqual(self.row['fields']['Status'], 'Paid')
        return results

    def test_concurrent_checkout_balance_same_intent_invoices_once(self):
        self.assertEqual(self.concurrent_checkout(['pi-checkout', 'pi-checkout']), ['rec-balance', 'rec-balance'])
        self.assertEqual(self.row['fields']['Stripe Payment Intent ID'], 'pi-checkout')

    def test_concurrent_checkout_balance_different_intents_never_overwrite(self):
        results = self.concurrent_checkout(['pi-checkout1', 'pi-checkout2'])
        self.assertEqual(results.count('rec-balance'), 1)
        self.assertEqual(results.count(None), 1)

    def test_checkout_normal_and_deposit_keep_existing_persistence(self):
        for role in ('', 'deposit'):
            with self.subTest(role=role):
                self.setUp()
                self.row['fields']['Payment Role'] = role
                self.http.payments = [self.row]
                scope = scope_for(self.http)
                scope.update(PAYMENT_LINKS_TABLE='Payment Links', get_next_invoice_number=self.number,
                             enqueue_persisted_response=self.enqueue)
                load_functions('stripe_webhook.py', ['mark_payment_link_as_paid_by_session'], scope)
                self.assertEqual(scope['mark_payment_link_as_paid_by_session'](
                    'cs-test', {'Stripe Payment Intent ID': 'pi-checkout'}, SELLER), 'rec-balance')
                self.assertEqual(self.row['fields']['Payment Role'], role)
                self.assertEqual(self.row['fields']['Status'], 'Paid')
                self.number.assert_called_once()
                self.enqueue.assert_called_once()


if __name__ == '__main__':
    unittest.main()
