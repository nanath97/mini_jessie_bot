import ast
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import facturx_postpersist as hook

ROOT = Path(__file__).resolve().parents[2]


class HookTests(unittest.TestCase):
    def test_disabled_and_unsuccessful_responses_do_not_schedule(self):
        with patch.dict(os.environ, {'FACTURX_ENABLED':'false'}), patch.object(hook.threading, 'Thread') as thread:
            hook.enqueue_persisted_response(SimpleNamespace(status_code=200), 'seller')
            thread.assert_not_called()
        with patch.dict(os.environ, {'FACTURX_ENABLED':'true'}), patch.object(hook.threading, 'Thread') as thread:
            hook.enqueue_persisted_response(SimpleNamespace(status_code=500), 'seller')
            thread.assert_not_called()

    def test_scheduler_returns_before_io_and_handles_failure(self):
        response=Mock(status_code=200)
        with patch.dict(os.environ, {'FACTURX_ENABLED':'true'}), patch.object(hook.threading, 'Thread') as thread:
            hook.enqueue_persisted_response(response, 'seller')
            response.json.assert_not_called()
            thread.assert_called_once()
            self.assertTrue(thread.call_args.kwargs['daemon'])
            hook._slots.release()  # mocked thread never ran
            thread.side_effect=RuntimeError('cannot start')
            hook.enqueue_persisted_response(response, 'seller')

    def test_transport_preserves_persisted_fields_and_uses_auth(self):
        fields={'Status':'Paid','Invoice Number':'example','Paid At':'2026-01-01T12:00:00Z'}
        response=Mock(); response.json.return_value={'fields':fields}
        result=Mock(status=202);result.read.return_value=b'{"id":"job"}'
        result.__enter__=Mock(return_value=result);result.__exit__=Mock(return_value=False)
        with patch.dict(os.environ, {'FACTURX_BRIDGE_URL':'http://127.0.0.1:3001','FACTURX_SERVICE_TOKEN':'t'*64}), patch.object(hook.urllib.request,'build_opener') as opener:
            opener.return_value.open.return_value=result
            hook._slots.acquire();hook._deliver(response,'seller')
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(json.loads(request.data),{'paymentFields':fields,'sellerSlug':'seller'})
            self.assertEqual(request.get_header('Authorization'),'Bearer '+'t'*64)
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],5)

    def test_transport_error_is_swallowed(self):
        response=Mock();response.json.side_effect=ValueError('bad persisted JSON')
        hook._slots.acquire();hook._deliver(response,'seller')

    def run_handler(self, kind, success=True, existing=False):
        # Execute the REAL handler AST without importing production modules or
        # performing Stripe verification, Airtable HTTP or notifications live.
        tree=ast.parse((ROOT/'stripe_webhook.py').read_text(encoding='utf-8'))
        defs=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in ('mark_payment_link_as_paid_by_session','stripe_webhook')]
        persisted=Mock(status_code=200 if success else 500,text='mock')
        persisted.json.return_value={'fields':{'Status':'Paid','Invoice Number':'test'}}
        records=[{'id':'rec-test','fields':{}}] if kind=='checkout.session.completed' or existing else []
        requests=SimpleNamespace(get=Mock(return_value=SimpleNamespace(json=lambda:{'records':records},text='mock')),patch=Mock(return_value=persisted),post=Mock(return_value=persisted))
        event={'type':kind,'data':{'object':{'id':'event-object','amount_total':50,'metadata':{'seller_slug':'seller','channel':'novapulse_off_session' if kind=='payment_intent.succeeded' else ''}}}}
        enqueued=Mock()
        scope={'Request':object,'Header':lambda v:v,'router':SimpleNamespace(post=lambda p:lambda f:f),
            'stripe':SimpleNamespace(Webhook=SimpleNamespace(construct_event=lambda **k:event)),
            'requests':requests,'os':os,'datetime':__import__('datetime').datetime,
            'BASE_ID':'offline','PAYMENT_LINKS_TABLE':'Payment Links','AIRTABLE_API_KEY':'offline',
            'STRIPE_WEBHOOK_SECRET':'offline','get_next_invoice_number':lambda s:'test',
            'enqueue_persisted_response':enqueued,'authorized_admin_ids':[], 'print':lambda *a:None}
        exec(compile(ast.Module(body=defs,type_ignores=[]),'<targeted-handler>','exec'),scope)
        class Request:
            async def body(self): return b'offline'
        asyncio.run(scope['stripe_webhook'](Request()))
        self.assertEqual(enqueued.call_count,1 if success and not (existing and kind=='payment_intent.succeeded') else 0)
        if enqueued.called: self.assertIs(enqueued.call_args.args[0],persisted)

    def test_checkout_hook_after_success(self): self.run_handler('checkout.session.completed')
    def test_checkout_no_hook_after_failure(self): self.run_handler('checkout.session.completed',False)
    def test_offsession_hook_after_success(self): self.run_handler('payment_intent.succeeded')
    def test_offsession_no_hook_after_failure(self): self.run_handler('payment_intent.succeeded',False)
    def test_offsession_existing_record_unchanged(self): self.run_handler('payment_intent.succeeded',existing=True)


if __name__=='__main__': unittest.main()
