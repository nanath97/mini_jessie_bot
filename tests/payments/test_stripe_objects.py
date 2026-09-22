"""Stripe response contracts, offline: .get() is forbidden on SDK objects."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_bug9 as fixtures
from quote_payments import (PaymentRuleError, QuotePayments, close_balance_checkout,
                            prepare_balance_link, persist_balance_payment)


class StripeObjectLike:
    def __init__(self, data):
        self.data = data

    def __getattr__(self, name):
        if name == 'get':
            raise AttributeError("'get' is a dict method, but a Session is not a dict. Use .to_dict() to convert it.")
        raise AttributeError(name)

    def __getitem__(self, key):
        return self.data[key]

    def __contains__(self, key):
        return key in self.data

    def to_dict(self):
        return {key: value.to_dict() if isinstance(value, StripeObjectLike) else copy.deepcopy(value)
                for key, value in self.data.items()}


class StripeResponseTests(unittest.TestCase):
    def setUp(self):
        self.row = fixtures.payment()

    def session(self, **changes):
        data = {'status': 'open', 'payment_status': 'unpaid', 'amount_total': 70000,
                'url': 'https://checkout.invalid', 'metadata': StripeObjectLike({
                    'client_key': fixtures.EMAIL, 'seller_slug': fixtures.SELLER,
                    'content_id': 'seller-content'})}
        data.update(changes)
        return StripeObjectLike(data)

    def api(self, session, expired=None):
        return SimpleNamespace(checkout=SimpleNamespace(Session=SimpleNamespace(
            retrieve=Mock(return_value=session),
            expire=Mock(return_value=expired if expired is not None else self.session(status='expired')))))

    def close(self, api):
        close_balance_checkout(api, self.row, fixtures.EMAIL, fixtures.SELLER, 70000)

    def test_a_open_stripe_session_expires_and_allows_collection(self):
        api = self.api(self.session())
        self.close(api)
        api.checkout.Session.expire.assert_called_once_with('cs-test')

    def test_b_paid_session_refused(self):
        api = self.api(self.session(payment_status='paid'))
        with self.assertRaisesRegex(PaymentRuleError, 'déjà payé'):
            self.close(api)
        api.checkout.Session.expire.assert_not_called()

    def test_c_complete_session_refused(self):
        with self.assertRaisesRegex(PaymentRuleError, 'déjà payé'):
            self.close(self.api(self.session(status='complete')))

    def test_d_wrong_client_metadata_refused(self):
        session = self.session()
        session.data['metadata'].data['client_key'] = 'wrong@example.test'
        with self.assertRaisesRegex(PaymentRuleError, 'incohérente'):
            self.close(self.api(session))

    def test_e_wrong_amount_refused(self):
        with self.assertRaisesRegex(PaymentRuleError, 'incohérente'):
            self.close(self.api(self.session(amount_total=69999)))

    def test_f_expired_stripe_session_allowed_without_expire(self):
        api = self.api(self.session(status='expired'))
        self.close(api)
        api.checkout.Session.expire.assert_not_called()

    def test_g_response_is_not_dict_and_reproduces_sdk_error(self):
        session = self.session()
        self.assertNotIsInstance(session, dict)
        with self.assertRaisesRegex(AttributeError, 'get.*dict method'):
            session.get('metadata')
        self.assertNotIsInstance(session.data['metadata'], dict)
        self.close(self.api(session))

    def test_wrong_seller_or_content_refused(self):
        for field in ('seller_slug', 'content_id'):
            with self.subTest(field=field):
                session = self.session()
                session.data['metadata'].data[field] = 'wrong'
                with self.assertRaisesRegex(PaymentRuleError, 'incohérente'):
                    self.close(self.api(session))

    def test_expire_must_return_expired(self):
        with self.assertRaisesRegex(PaymentRuleError, 'Impossible de fermer'):
            self.close(self.api(self.session(), self.session(status='open')))

    def run_collection(self, api):
        fixture = fixtures.CollectionTests()
        fixture.setUp()
        def close_sdk_response(stripe, record, email, seller, cents):
            stripe.PaymentIntent.create.assert_not_called()
            close_balance_checkout(api, record, email, seller, cents)
        with patch.object(fixtures, 'close_balance_checkout', side_effect=close_sdk_response):
            return fixture.handler()

    def test_handler_creates_intent_only_after_successful_sdk_expiration(self):
        api = self.api(self.session())
        stripe, _ = self.run_collection(api)
        api.checkout.Session.expire.assert_called_once()
        stripe.PaymentIntent.create.assert_called_once()
        self.assertEqual(stripe.PaymentIntent.create.call_args.kwargs['metadata']['payment_role'], 'balance')

    def test_handler_never_creates_intent_when_close_fails(self):
        cases = [self.session(payment_status='paid'), self.session(status='complete'),
                 self.session(amount_total=1)]
        for field in ('client_key', 'seller_slug', 'content_id'):
            session = self.session()
            session.data['metadata'].data[field] = 'wrong'
            cases.append(session)
        for session in cases:
            with self.subTest(data=session.to_dict()):
                stripe, message = self.run_collection(self.api(session))
                stripe.PaymentIntent.create.assert_not_called()
                self.assertNotIn('dict method', str(message.reply.call_args))
        for result in (self.session(status='open'), RuntimeError('Stripe unavailable')):
            api = self.api(self.session(), result)
            if isinstance(result, Exception): api.checkout.Session.expire.side_effect = result
            stripe, _ = self.run_collection(api)
            stripe.PaymentIntent.create.assert_not_called()

    def test_resume_uses_stripe_session_and_nested_metadata(self):
        http = fixtures.OfflineHTTP()
        del self.row['fields']['Sent At']
        http.payments.append(self.row)
        create, save = Mock(), Mock()
        result = prepare_balance_link(QuotePayments(http, 'offline', 'offline'), self.api(self.session()),
            create, save, quote_id='DEV-1', email=fixtures.EMAIL, seller_slug=fixtures.SELLER,
            amount_cents=70000, content_id='unused', admin_id='1', buyer_type='', caption='Original')
        self.assertEqual(result, ('https://checkout.invalid', 'cs-test', 'seller-content', 'rec-balance'))
        create.assert_not_called()
        save.assert_not_called()

    def test_webhook_stripe_payment_intent_updates_same_row_once(self):
        fixture = fixtures.WebhookTests()
        fixture.setUp()
        fixture.intent['metadata'] = StripeObjectLike(fixture.intent['metadata'])
        fixture.intent = StripeObjectLike(fixture.intent)
        self.assertEqual(fixture.webhook(), {'status': 'ok'})
        self.assertEqual(fixture.webhook(), {'status': 'ok'})
        self.assertEqual(fixture.row['fields']['Status'], 'Paid')
        self.assertEqual(len(fixture.http.patches), 1)
        fixture.number.assert_called_once()
        fixture.enqueue.assert_called_once()

    def test_dict_payload_with_stripe_metadata_is_supported(self):
        fixture = fixtures.WebhookTests()
        fixture.setUp()
        fixture.intent['metadata'] = StripeObjectLike(fixture.intent['metadata'])
        persist_balance_payment(QuotePayments(fixture.http, 'offline', 'offline'),
                                fixture.intent, fixture.number, fixture.enqueue)
        self.assertEqual(fixture.row['fields']['Status'], 'Paid')


if __name__ == '__main__':
    unittest.main()
