"""Collection is quote-only; every refusal exercises the real handler offline."""
import copy
import unittest
from unittest.mock import patch

import test_bug9 as fixtures


class EncaisserLockTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CollectionTests()
        self.fixture.setUp()
        self.http = self.fixture.http
        self.row = self.fixture.row

    def refused(self, amount=700, expected=None):
        stripe, message = self.fixture.handler(amount)
        stripe.PaymentIntent.create.assert_not_called()
        if expected:
            self.assertIn(expected, str(message.reply.call_args))
        return stripe

    def test_exact_amount_and_decimal_comma_allowed(self):
        for amount in ('700', '700,00'):
            with self.subTest(amount=amount):
                self.setUp()
                stripe, _ = self.fixture.handler(amount)
                stripe.PaymentIntent.create.assert_called_once()
                self.assertEqual(stripe.PaymentIntent.create.call_args.kwargs['amount'], 70000)

    def test_wrong_amounts_never_create_intent(self):
        for amount in ('710', '699', '700,10', '699,99', '700,001', '0'):
            with self.subTest(amount=amount):
                self.setUp()
                self.refused(amount, '700,00' if amount not in ('700,001', '0') else 'Montant invalide')

    def test_no_quote(self):
        self.http.quotes.clear()
        self.refused(expected='Aucun solde')

    def test_quote_not_accepted(self):
        self.http.quotes[0]['fields']['status'] = 'sent'
        self.refused(expected='Aucun solde')

    def test_no_paid_deposit(self):
        self.http.payments[0]['fields']['Status'] = 'Pending'
        self.refused(expected='acompte Paid')

    def test_deposit_of_another_quote(self):
        self.http.payments[0]['fields']['Quote ID'] = 'DEV-other'
        self.refused(expected='acompte Paid')

    def test_no_pending_balance_with_saved_card(self):
        self.http.payments.remove(self.row)
        self.refused(expected='Aucun solde')

    def test_paid_balance_with_saved_card(self):
        self.row['fields']['Status'] = 'Paid'
        self.refused(expected='Aucun solde')

    def test_no_quote_id(self):
        self.row['fields']['Quote ID'] = ''
        self.refused(expected='Aucun solde')

    def test_other_client_or_seller(self):
        for field, value in (('client_email', 'other@example.test'), ('seller_slug', 'other')):
            with self.subTest(field=field):
                self.setUp()
                self.http.quotes[0]['fields'][field] = value
                self.refused(expected='Aucun solde')

    def test_wrong_remaining_amount(self):
        self.http.quotes[0]['fields']['remaining_amount'] = '699.99'
        self.refused(expected='incohérent')

    def test_ambiguous_balances_even_with_different_amounts(self):
        extra = fixtures.payment(rid='rec-other')
        extra['fields']['Amount Cents'] = 12300
        self.http.payments.append(extra)
        self.refused(expected='Plusieurs soldes')

    def test_missing_or_invalid_sent_at(self):
        for value in (None, '', 'invalid'):
            with self.subTest(value=value):
                self.setUp()
                stored = copy.deepcopy(self.row)
                stored['fields']['Sent At'] = value
                self.http.payments[-1] = stored
                self.refused(expected='Sent At')

    def test_before_24_hours(self):
        self.row['fields']['Sent At'] = (fixtures.NOW - fixtures.timedelta(hours=23, minutes=59)).isoformat()
        self.refused(expected='24 h')

    def test_defensive_guard_if_lookup_returns_none(self):
        with patch.object(fixtures.QuotePayments, 'find_pending_balance', return_value=None):
            self.refused(expected='Aucun solde')

    def test_other_seller_balance_does_not_make_own_balance_ambiguous(self):
        other_quote = fixtures.quote_record('DEV-other')
        other_quote['fields']['seller_slug'] = 'other'
        self.http.quotes.append(other_quote)
        self.http.payments.append(fixtures.payment(qid='DEV-other', rid='rec-other'))
        stripe, _ = self.fixture.handler()
        stripe.PaymentIntent.create.assert_called_once()

    def test_duplicate_quote_identity_refused(self):
        self.http.quotes.append(copy.deepcopy(self.http.quotes[0]))
        self.refused(expected='ambigu')

    def test_lookup_failure_refused_without_disclosing_exception(self):
        with patch.object(fixtures.QuotePayments, 'find_pending_balance',
                          side_effect=RuntimeError('sensitive-service-detail')):
            stripe, message = self.fixture.handler()
        stripe.PaymentIntent.create.assert_not_called()
        self.assertNotIn('sensitive-service-detail', str(message.reply.call_args))
        self.assertIn('Encaissement refusé', str(message.reply.call_args))

    def test_independent_env_still_allowed(self):
        fixture = fixtures.EnvRulesTests()
        fixture.setUp()
        self.assertEqual(fixture.resolve(15000), ('', ''))


if __name__ == '__main__':
    unittest.main()
