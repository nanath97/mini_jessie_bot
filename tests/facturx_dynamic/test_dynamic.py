import copy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone
from io import BytesIO
from pypdf import PdfReader
from billing_facturx_dynamic import adapt_invoice, AdapterError
from billing_facturx.cii import build_cii
from billing_facturx.validation.validate import validate_xsd
from billing_facturx_pdf.assemble import assemble
from billing_facturx_pdf.validate import inspect_pdf
if __package__:
    from .support import builders, inputs, reference
else:
    from support import builders, inputs, reference


class DynamicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = builders()

    def test_missing_real_b2b_configuration_is_explicit(self):
        for name, record in self.records.items():
            if name.startswith('b2b'):
                with self.assertRaises(AdapterError) as error:
                    adapt_invoice(record['invoice'], record['seller_config'])
                for path in ('business_process_id', 'seller_electronic_address', 'buyer_electronic_address', 'PMT', 'PMD', 'AAB', 'payment_date_convention'):
                    self.assertIn(path, str(error.exception))

    def test_each_required_b2b_field(self):
        record = self.records['b2b-normal']
        paths = [('context','business_process_id'), ('context','buyer_electronic_address','value'), ('context','buyer_electronic_address','scheme_id'),
                 ('config','facturx','seller_electronic_address','value'), ('config','facturx','seller_electronic_address','scheme_id'),
                 ('config','facturx','b2b_notes','PMT'), ('config','facturx','b2b_notes','PMD'), ('config','facturx','b2b_notes','AAB'),
                 ('config','facturx','payment_date_convention')]
        for path in paths:
            config, context = inputs('b2b-normal', record)
            obj = {'config':config, 'context':context}
            for key in path[:-1]: obj = obj[key]
            del obj[path[-1]]
            with self.subTest(path=path), self.assertRaises(AdapterError):
                adapt_invoice(record['invoice'], config, context)

    def test_no_snapshot_identity_or_endpoint_constants(self):
        record = self.records['b2b-normal']
        invoice = copy.deepcopy(record['invoice'])
        config, context = inputs('b2b-normal', record)
        invoice['invoice_number'] = 'DYNAMIC-42'
        invoice['seller']['name'] = invoice['seller']['legal_name'] = 'Dynamic seller'
        invoice['seller']['siren'] = config['company']['siren'] = '111222333'
        context['buyer_electronic_address'] = {'value':'buyer@example.test','scheme_id':'EM'}
        config['facturx']['seller_electronic_address'] = {'value':'seller@example.test','scheme_id':'EM'}
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            result = adapt_invoice(invoice, config, context)
            xml = build_cii(result)
        self.assertIn(b'DYNAMIC-42', xml)
        self.assertIn(b'buyer@example.test', xml)
        self.assertIn(b'seller@example.test', xml)
        self.assertEqual(result['totals'], invoice['totals'])

    def test_invalid_dates_and_unsupported_process(self):
        record = self.records['b2b-normal']
        config, context = inputs('b2b-normal', record)
        for date in ('', '2026-01-01', 'not-a-date'):
            invoice = copy.deepcopy(record['invoice']); invoice['payment_date'] = date
            with self.assertRaises(AdapterError): adapt_invoice(invoice, config, context)
        context['business_process_id'] = 'S1'
        with self.assertRaises(AdapterError): adapt_invoice(record['invoice'], config, context)

    def test_utc_convention_is_explicit(self):
        record = self.records['b2b-normal']; config, context = inputs('b2b-normal', record)
        invoice = copy.deepcopy(record['invoice']); invoice['payment_date'] = '2026-08-24T00:30:00+02:00'
        self.assertEqual(adapt_invoice(invoice, config, context)['payment_terms']['due_date'], '2026-08-23')

    def test_conflicting_seller_rejected(self):
        record = self.records['b2c-normal']; config = copy.deepcopy(record['seller_config'])
        config['company']['siren'] = '111222333'
        with self.assertRaises(AdapterError): adapt_invoice(record['invoice'], config)

    def test_pdf_uses_actual_tax_identifiers(self):
        # Rendering must not label every seller SIREN as FC when VAT applies.
        from billing_facturx_pdf.render import render
        invoice = copy.deepcopy(self.records['b2c-normal']['invoice'])
        invoice['seller']['vat_number'] = 'FR11111222333'
        invoice['buyer']['vat_number'] = 'FR22999888777'
        invoice['tax']['category'] = 'S'
        invoice['tax']['exemption_code'] = ''
        text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(render(invoice))).pages)
        self.assertNotIn('Identifiant fiscal (FC)', text)
        self.assertIn('FR11111222333', text)
        self.assertIn('FR22999888777', text)

    def test_amounts_are_supplied_not_rebuilt(self):
        record = self.records['b2c-normal']
        invoice = copy.deepcopy(record['invoice'])
        for key in ('total_ht', 'total_ttc', 'prepaid_amount'): invoice['totals'][key] = 123.45
        invoice['tax']['taxable_amount'] = 123.45
        invoice['lines'][0]['unit_price_ht'] = invoice['lines'][0]['line_total_ht'] = 123.45
        result = adapt_invoice(invoice, record['seller_config'])
        self.assertEqual(result, invoice)
        self.assertIn(b'123.45', build_cii(result))

    def test_missing_policy_writes_nothing(self):
        from billing_facturx_dynamic.cli import generate
        record = self.records['b2b-normal']
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'invoice'
            with self.assertRaises(AdapterError):
                generate(record['invoice'], record['seller_config'], {}, target)
            self.assertFalse(target.exists())

    def test_blocked_validator_never_accepts_output(self):
        from billing_facturx_dynamic.cli import generate
        record = self.records['b2c-normal']
        validation = {'accepted':False, 'en16931':{'status':'blocked'}, 'br_fr':{'status':'blocked'}}
        with tempfile.TemporaryDirectory() as folder, patch('billing_facturx_dynamic.cli.validate', return_value=validation), patch('billing_facturx_dynamic.cli.run_verapdf', return_value={'status':'pass'}):
            report = generate(record['invoice'], record['seller_config'], {}, Path(folder)/'invoice')
            self.assertFalse(report['accepted'])


def scenario_test(scenario):
    def test(self):
        record = self.records[scenario]; before = copy.deepcopy(record)
        config, context = inputs(scenario, record)
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            invoice = adapt_invoice(record['invoice'], config, context)
            xml = build_cii(invoice)
            self.assertEqual(xml, reference(scenario).read_bytes())
            self.assertEqual(validate_xsd(xml)['status'], 'pass')
            pdf = assemble(invoice, xml, datetime(2026,9,6,tzinfo=timezone.utc))
            inspect_pdf(pdf, xml)
        self.assertEqual(record, before)
        for field in ('lines','tax','totals','source','quote','deposit_reference','invoice_date','payment_date'):
            self.assertEqual(invoice.get(field), record['invoice'].get(field))
        text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
        self.assertIn(invoice['invoice_number'], text)
        if scenario.startswith('b2c'):
            self.assertNotIn('notes', invoice)
            self.assertNotIn('40 EUR', text)
        else:
            for note in invoice['notes']: self.assertIn(note['subject_code'], text)
        if invoice.get('quote'): self.assertIn(invoice['quote']['quote_id'], text)
        if invoice.get('deposit_reference'): self.assertIn(invoice['deposit_reference']['invoice_number'], text)
    return test


for segment in ('b2b','b2c'):
    for kind in ('normal','deposit','balance'):
        scenario = segment+'-'+kind
        setattr(DynamicTests, 'test_'+scenario.replace('-','_'), scenario_test(scenario))

if __name__ == '__main__': unittest.main()
