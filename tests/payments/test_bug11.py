"""Execute the real /env handler offline, reusing the existing payment fixture."""
import unittest
from unittest.mock import patch

import test_bug9 as fixtures


class EnvDescriptionTests(unittest.TestCase):
    def send(self, text, role='normal', media=False):
        original_loader = fixtures.load_functions

        def load(file, names, scope):
            original_loader(file, names, scope)
            if 'envoyer_contenu_payant' in names:
                handler = scope['envoyer_contenu_payant']

                async def with_text(message):
                    message.text = None if media else text
                    message.caption = text if media else None
                    return await handler(message)

                scope['envoyer_contenu_payant'] = with_text

        with patch.object(fixtures, 'load_functions', side_effect=load):
            http, scope, _ = fixtures.EnvHandlerTests().handler(role=role, media=media)
        endpoint = '/pwa/send-paid-content' if media else '/pwa/send-simple-payment'
        sent = [body for url, body in http.posts if url.endswith(endpoint)]
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['checkout_url'], 'https://checkout.invalid')
        self.assertNotIn('/env', sent[0]['text'].lower())
        return sent[0], http

    def test_text_before_command(self):
        payload, _ = self.send("Voici le paiement pour l'acompte /env50")
        self.assertEqual(payload['text'], "Voici le paiement pour l'acompte")
        self.assertEqual(payload['amount'], 5000)

    def test_text_after_command(self):
        payload, _ = self.send("/env50 Voici le paiement pour l'acompte")
        self.assertEqual(payload['text'], "Voici le paiement pour l'acompte")

    def test_command_only_fallback(self):
        payload, _ = self.send('/env50')
        self.assertEqual(payload['text'], '💳 Paiement requis.')

    def test_decimal_comma_accents_and_punctuation(self):
        payload, _ = self.send('Réglé à réception, merci ! /env49,90')
        self.assertEqual(payload['text'], 'Réglé à réception, merci !')
        self.assertEqual(payload['amount'], 4990)

    def test_media_caption_and_paywall_unchanged(self):
        payload, http = self.send('Voici votre fichier /env50', media=True)
        self.assertEqual(payload['text'], 'Voici votre fichier')
        self.assertTrue(payload['isMedia'])
        self.assertEqual(payload['mediaUrl'], 'https://media.invalid/image.jpg')
        self.assertEqual(payload['sessionId'], 'cs-test')
        self.assertEqual(payload['contentId'], http.payments[-1]['fields']['Content ID'])
        self.assertEqual(payload['amount'], 5000)
        self.assertFalse(any(url.endswith('/pwa/send-simple-payment') for url, _ in http.posts))

    def test_normal_deposit_balance_preserve_roles_and_links(self):
        for role in ('normal', 'deposit', 'balance'):
            with self.subTest(role=role):
                payload, http = self.send('Votre règlement /env700', role=role)
                self.assertEqual(payload['text'], 'Votre règlement')
                self.assertEqual(payload['amount'], 70000)
                fields = http.payments[-1]['fields']
                self.assertEqual(fields['Payment Role'], '' if role == 'normal' else role)
                self.assertEqual(fields['Quote ID'], '' if role == 'normal' else 'DEV-1')
                self.assertEqual(fields['Checkout Session ID'], 'cs-test')
                self.assertIn('Sent At', fields)


if __name__ == '__main__':
    unittest.main()
