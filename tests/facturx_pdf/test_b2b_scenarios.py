import copy
import tempfile
import unittest
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from lxml import etree as ET
from pypdf import PdfReader
from billing_facturx.validation.validate import validate_xsd
from billing_facturx_pdf.inputs import ROOT, load_inputs
from billing_facturx_pdf.assemble import assemble
from billing_facturx_pdf.validate import inspect_pdf

SCENARIOS = ('b2b-normal','b2b-deposit','b2b-balance')
FIXTURES = ROOT/'tests/facturx_pdf/fixtures'


class ThreeB2BTests(unittest.TestCase):
    def test_b2c_with_b2b_xml_rejected(self):
        with self.assertRaises(ValueError):
            load_inputs(ROOT/'Bridge/tests/billing/fixtures/b2c-normal/expected.invoice.json',
                        FIXTURES/'factur-x.xml',FIXTURES/'validation.json')

    def test_cross_scenario_xml_rejected(self):
        with self.assertRaises(ValueError):
            load_inputs(ROOT/'Bridge/tests/billing/fixtures/b2b-balance/expected.invoice.json',
                        FIXTURES/'b2b-deposit/factur-x.xml',FIXTURES/'b2b-deposit/validation.json')


def scenario_test(scenario):
    def run(self):
        fixture = FIXTURES if scenario == 'b2b-normal' else FIXTURES/scenario
        source = ROOT/'Bridge/tests/billing/fixtures'/scenario/'expected.invoice.json'
        before = source.read_bytes()
        invoice, xml, prior = load_inputs(source,fixture/'factur-x.xml',fixture/'validation.json')
        snapshot = copy.deepcopy(invoice)
        with patch('socket.socket.connect',side_effect=AssertionError('Offline only')):
            pdf = assemble(invoice,xml,datetime(2026,9,5,12,tzinfo=timezone.utc))
        self.assertEqual(invoice,snapshot)
        self.assertEqual(source.read_bytes(),before)
        report = inspect_pdf(pdf,xml)
        self.assertEqual(report['status'],'pass')
        self.assertEqual(prior['status'],'pass')
        self.assertEqual(validate_xsd(xml)['status'],'pass')
        reader = PdfReader(BytesIO(pdf))
        self.assertEqual(reader.attachments['factur-x.xml'],[xml])
        text = ' '.join(' '.join(p.extract_text() for p in reader.pages).split())
        self.assertIn('Quantité / unité', text)
        self.assertIn('Net à payer', text)
        title = {'b2b-normal':'Facture normale','b2b-deposit':"Facture d'acompte",'b2b-balance':'Facture de solde'}[scenario]
        self.assertIn(title,text)
        # Every existing XML textual leaf remains represented in the readable.
        for node in ET.fromstring(xml).iter():
            if len(node) or not node.text or not node.text.strip(): continue
            value = node.text.strip()
            if node.tag.endswith('DateTimeString') and node.get('format') == '102':
                value = value[:4]+'-'+value[4:6]+'-'+value[6:8]
            self.assertIn(value,text,ET.QName(node).localname)
        for note in invoice['notes']: self.assertIn(note['content'],text)
        if scenario == 'b2b-normal':
            self.assertNotIn('Devis :',text)
        else:
            self.assertIn('Devis : '+invoice['quote']['quote_id'],text)
        if scenario == 'b2b-balance':
            ref = invoice['deposit_reference']
            self.assertIn("Facture d'acompte : "+ref['invoice_number']+' du '+ref['invoice_date'],text)
        # No new deduction from the balance: preserve the supplied totals.
        for key in ('total_ht','total_ttc','prepaid_amount','payable_amount'):
            self.assertIn(format(invoice['totals'][key],'.2f')+' EUR',text)
    return run


for scenario in SCENARIOS:
    setattr(ThreeB2BTests,'test_'+scenario.replace('-','_'),scenario_test(scenario))
