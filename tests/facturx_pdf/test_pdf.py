import copy
import importlib.util
import json
import socket
import tempfile
import unittest
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from lxml import etree as ET
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject
from billing_facturx.validation.validate import validate as validate_cii, validate_xsd
from billing_facturx_pdf.assemble import assemble
from billing_facturx_pdf.inputs import ROOT, load_inputs
from billing_facturx_pdf.validate import inspect_pdf, verify_assets, run_verapdf
from billing_facturx_pdf.xmp import NS, VALUES, FX, make_xmp

FIXTURES = ROOT/'tests/facturx_pdf/fixtures'
INVOICE = ROOT/'Bridge/tests/billing/fixtures/b2b-normal/expected.invoice.json'


class PdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.invoice, cls.xml, cls.prior = load_inputs(INVOICE,FIXTURES/'factur-x.xml',FIXTURES/'validation.json')
        with patch('socket.socket.connect',side_effect=AssertionError('Offline only')):
            cls.pdf = assemble(cls.invoice,cls.xml,datetime(2026,9,5,12,tzinfo=timezone.utc))

    def setUp(self):
        guard = patch('socket.socket.connect',side_effect=AssertionError('Offline only'))
        guard.start();self.addCleanup(guard.stop)
        self.reader = PdfReader(BytesIO(self.pdf))
        self.root = self.reader.trailer['/Root']
        self.spec = self.root['/AF'][0].get_object()

    def test_pdf_generated(self):
        self.assertTrue(self.pdf.startswith(b'%PDF-1.7'))
        self.assertEqual(len(self.reader.pages),1)

    def test_extract_xml_exact_bytes(self):
        self.assertEqual(self.reader.attachments['factur-x.xml'],[self.xml])

    def test_filename(self):
        self.assertEqual(self.spec['/F'],'factur-x.xml')
        self.assertEqual(self.spec['/UF'],'factur-x.xml')

    def test_mime(self):
        self.assertEqual(self.spec['/EF']['/F']['/Subtype'],'/text/xml')

    def test_document_af_and_name_tree(self):
        self.assertEqual(self.root['/AF'][0],self.root['/Names']['/EmbeddedFiles']['/Names'][1])
        self.assertEqual(self.root['/Names']['/EmbeddedFiles']['/Names'][0],'factur-x.xml')

    def test_relationship(self):
        self.assertEqual(self.spec['/AFRelationship'],'/Alternative')

    def test_params_moddate(self):
        p = self.spec['/EF']['/F']['/Params']
        self.assertEqual(p['/ModDate'],'D:20260905120000Z')
        self.assertEqual(p['/Size'],len(self.xml))

    def test_xmp_exact_official_schema_and_values(self):
        verify_assets()
        result = inspect_pdf(self.pdf,self.xml)
        self.assertEqual(result['namespace'],FX)
        root = ET.fromstring(self.root['/Metadata'].get_data())
        for name, expected in VALUES.items():
            self.assertEqual(root.xpath('//fx:'+name+'/text()',namespaces=NS),[expected])
        self.assertNotIn(b'LE FOURNISSEUR',self.root['/Metadata'].get_data())
        self.assertNotIn(b'F20220023',self.root['/Metadata'].get_data())

    def test_all_fonts_embedded(self):
        result = inspect_pdf(self.pdf,self.xml)
        self.assertEqual(len(result['fonts']),2)
        self.assertTrue(all('BitstreamVeraSans' in f for f in result['fonts']))

    def test_no_active_content_and_no_encryption(self):
        self.assertFalse(self.reader.is_encrypted)
        self.assertEqual(inspect_pdf(self.pdf,self.xml)['status'],'pass')
        with socket.socket() as connection:
            with self.assertRaises(AssertionError): connection.connect(('127.0.0.1',80))

    def test_readable_matches_xml_information(self):
        text = ' '.join(p.extract_text() for p in self.reader.pages)
        text = ' '.join(text.split())
        for note in self.invoice['notes']:
            self.assertIn(note['subject_code']+' - '+note['content'],text)
        xml = ET.fromstring(self.xml)
        # Every textual leaf of this exact XML is represented in the readable.
        # Date and decimal lexical formats are rendered without semantic changes.
        for node in xml.iter():
            if len(node) or not node.text or not node.text.strip(): continue
            value = node.text.strip()
            if node.tag.endswith('DateTimeString') and node.get('format') == '102':
                value = value[:4]+'-'+value[4:6]+'-'+value[6:8]
            if value == '0.00': self.assertIn('0.00',text);continue
            self.assertIn(value,text,ET.QName(node).localname)

    def test_source_snapshot_not_mutated(self):
        before = copy.deepcopy(self.invoice)
        assemble(self.invoice,self.xml,datetime.now(timezone.utc))
        self.assertEqual(self.invoice,before)
        self.assertEqual(load_inputs(INVOICE,FIXTURES/'factur-x.xml',FIXTURES/'validation.json')[1],self.xml)

    def test_changed_xml_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            changed = Path(d)/'factur-x.xml'
            changed.write_bytes(self.xml.replace(b'NP-2026-000008',b'NP-2026-999999'))
            with self.assertRaises(ValueError): load_inputs(INVOICE,changed,FIXTURES/'validation.json')
        with self.assertRaises(ValueError): inspect_pdf(self.pdf,self.xml+b' ')

    def test_wrong_af_rejected(self):
        writer = PdfWriter(clone_from=BytesIO(self.pdf))
        writer.root_object['/AF'][0].get_object()[NameObject('/AFRelationship')] = NameObject('/Data')
        data = BytesIO();writer.write(data)
        with self.assertRaises(ValueError): inspect_pdf(data.getvalue(),self.xml)

    def test_cii_prior_pass_preserved_and_xsd_rerun(self):
        self.assertEqual(self.prior['status'],'pass')
        self.assertEqual(validate_xsd(self.xml)['status'],'pass')

    @unittest.skipUnless(importlib.util.find_spec('saxonche'), 'BLOCKED: SaxonC unavailable for fresh Schematron execution')
    def test_live_cii_xsd_en16931_brfr(self):
        self.assertTrue(validate_cii(self.xml,self.invoice)['accepted'])

    def test_missing_verapdf_is_blocked_not_pass(self):
        with patch('billing_facturx_pdf.validate.shutil.which',return_value=None):
            self.assertEqual(run_verapdf('not-used.pdf')['status'],'blocked')

    def test_empty_verapdf_report_cannot_pass(self):
        from subprocess import CompletedProcess
        with patch('billing_facturx_pdf.validate.subprocess.run',return_value=CompletedProcess([],0,b'<report/>',b'')):
            self.assertEqual(run_verapdf('not-used.pdf','validator')['status'],'fail')

    def test_3a_cannot_be_claimed_by_metadata_switch(self):
        with self.assertRaises(NotImplementedError):
            make_xmp(self.invoice,datetime.now(timezone.utc),'3a')


if __name__ == '__main__': unittest.main()
