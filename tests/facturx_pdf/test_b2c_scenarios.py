import copy
import json
import shutil
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

FIXTURES = ROOT/'tests/facturx_pdf/fixtures'
SOURCES = ROOT/'Bridge/tests/billing/fixtures'


class B2CTests(unittest.TestCase):
    def test_brfr_failure_does_not_reject_b2c(self):
        scenario = 'b2c-normal'
        with tempfile.TemporaryDirectory() as tmp:
            report = json.loads((FIXTURES/scenario/'validation.json').read_text(encoding='utf-8'))
            report['accepted'] = False
            report['br_fr'] = {'status':'fail'}
            path = Path(tmp)/'validation.json'
            path.write_text(json.dumps(report),encoding='utf-8')
            shutil.copyfile(FIXTURES/scenario/'en16931.svrl.xml',Path(tmp)/'en16931.svrl.xml')
            # No BR-FR SVRL is required for B2C acceptance.
            invoice, xml, prior = load_inputs(SOURCES/scenario/'expected.invoice.json',FIXTURES/scenario/'factur-x.xml',path)
            self.assertEqual(prior['status'],'pass')
            report['en16931']['status'] = 'fail'
            path.write_text(json.dumps(report),encoding='utf-8')
            with self.assertRaises(ValueError):
                load_inputs(SOURCES/scenario/'expected.invoice.json',FIXTURES/scenario/'factur-x.xml',path)

    def test_brfr_still_required_for_b2b(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = json.loads((FIXTURES/'validation.json').read_text(encoding='utf-8'))
            report['br_fr'] = {'status':'fail'}
            path = Path(tmp)/'validation.json'
            path.write_text(json.dumps(report),encoding='utf-8')
            with self.assertRaises(ValueError):
                load_inputs(SOURCES/'b2b-normal/expected.invoice.json',FIXTURES/'factur-x.xml',path)


def scenario_test(scenario):
    def run(self):
        source = SOURCES/scenario/'expected.invoice.json'
        original = source.read_bytes()
        fixture = FIXTURES/scenario
        invoice, xml, prior = load_inputs(source,fixture/'factur-x.xml',fixture/'validation.json')
        snapshot = copy.deepcopy(invoice)
        with patch('socket.socket.connect',side_effect=AssertionError('Network forbidden')):
            pdf = assemble(invoice,xml,datetime(2026,9,6,12,tzinfo=timezone.utc))
        self.assertEqual(invoice,snapshot)
        self.assertEqual(source.read_bytes(),original)
        self.assertEqual(inspect_pdf(pdf,xml)['status'],'pass')
        self.assertEqual(validate_xsd(xml)['status'],'pass')
        self.assertEqual(prior['status'],'pass')
        reader = PdfReader(BytesIO(pdf))
        self.assertEqual(reader.attachments['factur-x.xml'],[xml])
        text = ' '.join(' '.join(p.extract_text() for p in reader.pages).split())
        for absent in ['PMT','PMD','AAB','40 EUR','recouvrement','Cadre de facturation','Adresse de facturation','échéance']:
            self.assertNotIn(absent,text)
        self.assertIn(invoice['buyer']['name'],text)
        self.assertIn('Net à payer',text)
        self.assertIn({'normal':'Facture normale','deposit':"Facture d'acompte",'balance':'Facture de solde'}[invoice['invoice_type']],text)
        for node in ET.fromstring(xml).iter():
            if len(node) or not node.text or not node.text.strip(): continue
            value = node.text.strip()
            if node.tag.endswith('DateTimeString') and node.get('format') == '102':
                value = value[:4]+'-'+value[4:6]+'-'+value[6:8]
            self.assertIn(value,text,ET.QName(node).localname)
        if invoice.get('quote'):
            self.assertIn(invoice['quote']['quote_id'],text)
        if invoice.get('deposit_reference'):
            ref=invoice['deposit_reference']
            self.assertIn("Facture d'acompte : "+ref['invoice_number']+' du '+ref['invoice_date'],text)
    return run


for scenario in ('b2c-normal','b2c-deposit','b2c-balance'):
    setattr(B2CTests,'test_'+scenario.replace('-','_'),scenario_test(scenario))
