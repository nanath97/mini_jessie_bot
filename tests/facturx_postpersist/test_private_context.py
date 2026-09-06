"""Validate the real checkout/context handoff without importing live services."""
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


class PrivateContextTests(unittest.TestCase):
    def checkout(self, custom_fields, success=True):
        tree = ast.parse((ROOT/'stripe_webhook.py').read_text(encoding='utf-8'))
        defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in ('mark_payment_link_as_paid_by_session', 'stripe_webhook')]
        response = Mock(status_code=200 if success else 500, text='offline')
        enqueued = Mock()
        requests = SimpleNamespace(
            get=Mock(return_value=SimpleNamespace(json=lambda:{'records':[{'id':'rec-offline','fields':{}}]},text='offline')),
            patch=Mock(return_value=response), post=Mock(return_value=response))
        event = {'type':'checkout.session.completed','data':{'object':{
            'id':'offline-session','amount_total':51,'metadata':{'seller_slug':'seller'},
            'customer_details':{'email':'contact@example.test'},
            'custom_fields':[{'key':k,'text':{'value':v}} for k,v in custom_fields.items()]}}}
        scope = {'Request':object,'Header':lambda v:v,'router':SimpleNamespace(post=lambda p:lambda f:f),
            'stripe':SimpleNamespace(Webhook=SimpleNamespace(construct_event=lambda **kwargs:event)),
            'requests':requests,'os':os,'datetime':__import__('datetime').datetime,
            'BASE_ID':'offline','PAYMENT_LINKS_TABLE':'Payment Links','AIRTABLE_API_KEY':'offline',
            'STRIPE_WEBHOOK_SECRET':'offline','get_next_invoice_number':lambda s:'offline-invoice',
            'enqueue_persisted_response':enqueued,'authorized_admin_ids':[], 'print':lambda *args:None}
        exec(compile(ast.Module(body=defs,type_ignores=[]),'<isolated-handler>','exec'),scope)
        class Request:
            async def body(self): return b'offline'
        async def run():
            # Windows creates the event loop's local socket pair before this guard.
            with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
                await scope['stripe_webhook'](Request())
        asyncio.run(run())
        return enqueued, response, requests

    def test_checkout_explicit_address_reaches_postpersist(self):
        # Use the existing confirmed historical endpoint, never a production fallback.
        overlay=json.loads((ROOT/'tests/facturx/french-fixtures/b2b-normal.json').read_text(encoding='utf-8'))
        endpoint=overlay['buyer_endpoint']
        enqueued,response,requests=self.checkout({'buyer_company_name':'Offline company','electronic_billing_address':endpoint['value']})
        enqueued.assert_called_once_with(response,'seller',{'buyer_electronic_address':endpoint})
        persisted=requests.patch.call_args.kwargs['json']['fields']
        self.assertNotIn('context',persisted)
        self.assertNotIn('buyer_electronic_address',persisted)
        self.assertEqual(persisted['Status'],'Paid')

    def test_b2b_without_address_has_no_fallback(self):
        enqueued,response,_=self.checkout({'buyer_company_name':'Offline company','buyer_siret':'908582307'})
        enqueued.assert_called_once_with(response,'seller',{})

    def test_b2c_email_does_not_become_endpoint(self):
        enqueued,response,_=self.checkout({})
        enqueued.assert_called_once_with(response,'seller',{})

    def test_failed_persistence_does_not_send_context(self):
        enqueued,_,_=self.checkout({'electronic_billing_address':'908582307'},success=False)
        enqueued.assert_not_called()

    def transport(self, context):
        response=Mock();response.json.return_value={'fields':{'Status':'Paid','Invoice Number':'offline'}}
        result=Mock(status=202);result.read.return_value=b'{"id":"offline-job"}'
        result.__enter__=Mock(return_value=result);result.__exit__=Mock(return_value=False)
        with patch.dict(os.environ,{'FACTURX_BRIDGE_URL':'http://127.0.0.1:3001','FACTURX_SERVICE_TOKEN':'t'*64}), \
             patch('socket.socket',side_effect=AssertionError('Network forbidden')), \
             patch.object(hook.urllib.request,'build_opener') as opener:
            opener.return_value.open.return_value=result
            self.assertTrue(hook._slots.acquire(blocking=False))
            hook._deliver(response,'seller',context)
            opener.return_value.open.assert_called_once()
            return json.loads(opener.return_value.open.call_args.args[0].data)

    def test_nonempty_private_context_is_transmitted_unchanged(self):
        context={'buyer_electronic_address':{'value':'908582307','scheme_id':'0225'}}
        body=self.transport(context)
        self.assertEqual(body['context'],context)
        self.assertNotIn('buyer_electronic_address',body['paymentFields'])

    def test_empty_context_preserves_historical_transport(self):
        for context in (None,{}):
            with self.subTest(context=context): self.assertNotIn('context',self.transport(context))

    def test_scheduler_forwards_context_without_blocking(self):
        context={'buyer_electronic_address':{'value':'908582307','scheme_id':'0225'}}
        response=Mock(status_code=200)
        with patch.dict(os.environ,{'FACTURX_ENABLED':'true'}),patch.object(hook.threading,'Thread') as thread:
            hook.enqueue_persisted_response(response,'seller',context)
            try:
                self.assertEqual(thread.call_args.kwargs['args'],(response,'seller',context))
                thread.return_value.start.assert_called_once()
                response.json.assert_not_called()
            finally: hook._slots.release()

if __name__=='__main__': unittest.main()
