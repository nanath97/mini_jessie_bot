import copy
import socket
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from lxml import etree as ET

from billing_facturx.cli import SCENARIOS
from billing_facturx.french import enrich
from billing_facturx.mapping import load_invoice, map_invoice, MappingError, missing_requirements
from billing_facturx.cii import build_cii, NS
from billing_facturx.validation.validate import validate, validate_xsd, validate_schematron, interpret_svrl, parse_xml, verify_artifacts

FIXTURES = Path(__file__).resolve().parents[2] / 'Bridge/tests/billing/fixtures'


class CiiTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket.connect', 'socket.create_connection'):
            guard = patch(target, side_effect=AssertionError('Network forbidden in tests'))
            guard.start()
            self.addCleanup(guard.stop)

    def invoice(self, scenario='b2b-normal'):
        return load_invoice(FIXTURES / scenario / 'expected.invoice.json')

    def test_missing_required_fields(self):
        for key in ('invoice_number', 'invoice_date', 'currency', 'lines'):
            data = self.invoice()
            del data[key]
            with self.subTest(key=key), self.assertRaises(MappingError):
                build_cii(data)

    def test_no_rounding_or_total_repair(self):
        for value in ('0.511', 'NaN', '-1'):
            data = self.invoice()
            data['totals']['total_ht'] = Decimal(value)
            with self.subTest(value=value), self.assertRaises(MappingError):
                build_cii(data)
        data = self.invoice()
        data['totals']['total_ttc'] = Decimal('10')
        with self.assertRaises(MappingError):
            build_cii(data)

    def test_exemption_missing_fiscal_identifier_fails_explicitly(self):
        for scenario in SCENARIOS:
            data = self.invoice(scenario)
            self.assertEqual(missing_requirements(data), [])
            root = ET.fromstring(build_cii(data))
            self.assertEqual(root.xpath('//ram:SellerTradeParty/ram:SpecifiedTaxRegistration/ram:ID[@schemeID="FC"]/text()', namespaces=NS), [data['seller']['siren']])
            self.assertFalse(root.xpath('//ram:SpecifiedTaxRegistration/ram:ID[@schemeID="VA"]', namespaces=NS))
            for role, key, value in [('seller', 'siren', ''), ('seller', 'country', 'DE'), ('tax', 'exemption_code', '')]:
                invalid = copy.deepcopy(data)
                invalid[role][key] = value
                self.assertEqual(missing_requirements(invalid)[0]['rule'], 'BR-E-02')

    def test_artifacts_and_codes(self):
        verify_artifacts()
        from billing_facturx.validation.validate import ARTIFACTS
        db = ET.parse(str(ARTIFACTS / '2xslt/FACTUR-X_EN16931_codedb.xml'))
        for code in ('380', '386', '916', 'VATEX-FR-FRANCHISE'):
            self.assertTrue(db.xpath('//*[@value=$code]', code=code), code)

    def test_missing_engine_is_blocked_not_success(self):
        with patch.dict(sys.modules, {'saxonche': None}):
            report = validate_schematron(build_cii(self.invoice()), 'FACTUR-X_EN16931.xslt')
        self.assertEqual(report['status'], 'blocked')

    def test_missing_data_prevents_acceptance_even_if_validators_pass(self):
        data = self.invoice()
        del data['seller']['siren']
        with patch('billing_facturx.validation.validate.validate_schematron', return_value={'status': 'pass'}):
            report = validate(build_cii(data), data)
        self.assertFalse(report['accepted'])
        self.assertEqual(report['mandatory_data'][0]['rule'], 'BR-E-02')
        def engine(xml, name):
            return {'status': 'fail' if name.startswith('BR-FR') else 'pass'}
        with patch('billing_facturx.validation.validate.validate_schematron', side_effect=engine):
            b2c = self.invoice('b2c-normal')
            self.assertTrue(validate(build_cii(b2c), b2c)['accepted'])
            b2b = self.invoice()
            self.assertFalse(validate(build_cii(b2b), b2b)['accepted'])

    def test_svrl_failure_and_no_rule_are_not_success(self):
        report = interpret_svrl('<s:schematron-output xmlns:s="http://purl.oclc.org/dsdl/svrl"><s:fired-rule/><s:failed-assert id="TEST" flag="fatal"><s:text>Failure</s:text></s:failed-assert></s:schematron-output>')
        self.assertEqual(report['status'], 'fail')
        with self.assertRaises(ValueError):
            interpret_svrl('<s:schematron-output xmlns:s="http://purl.oclc.org/dsdl/svrl"/>')

    def test_dtd_and_network_blocked(self):
        with self.assertRaises(ValueError):
            parse_xml(b'<!DOCTYPE x SYSTEM "https://example.invalid"><x/>')
        with self.assertRaises(AssertionError):
            socket.create_connection(('example.invalid', 443))

    def test_no_due_date_or_payment_means_invented(self):
        root = ET.fromstring(build_cii(self.invoice()))
        for name in ('DueDateDateTime', 'SpecifiedTradeSettlementPaymentMeans', 'BusinessProcessSpecifiedDocumentContextParameter'):
            self.assertFalse(root.xpath('//ram:' + name, namespaces=NS))


def scenario_test(scenario):
    def run(self):
        data = self.invoice(scenario)
        snapshot = copy.deepcopy(data)
        data = enrich(data, FIXTURES / scenario / 'expected.invoice.json', scenario)
        self.assertEqual(self.invoice(scenario), snapshot)
        if scenario.startswith('b2b'):
            self.assertEqual(data['business_process_id'], 'S2')
            self.assertEqual(data['payment_terms']['due_date'], snapshot['payment_date'][:10])
            self.assertEqual({n['subject_code'] for n in data['notes']}, {'PMT', 'PMD', 'AAB'})
            with self.assertRaises(MappingError):
                altered = copy.deepcopy(snapshot)
                altered['invoice_number'] = 'wrong'
                enrich(altered, FIXTURES / scenario / 'expected.invoice.json', scenario)
        else:
            self.assertNotIn('notes', data)
        original = copy.deepcopy(data)
        xml = build_cii(data)
        self.assertEqual(data, original)
        self.assertEqual(xml, build_cii(data))
        self.assertEqual(validate_xsd(xml)['status'], 'pass')
        root = ET.fromstring(xml)
        def value(xpath):
            return root.xpath('string(' + xpath + ')', namespaces=NS)
        self.assertEqual(value('/rsm:CrossIndustryInvoice/rsm:ExchangedDocument/ram:ID'), data['invoice_number'])
        self.assertEqual(value('/rsm:CrossIndustryInvoice/rsm:ExchangedDocument/ram:TypeCode'), '386' if data['invoice_type']=='deposit' else '380')
        for key, tag in [('total_ht','LineTotalAmount'), ('vat_amount','TaxTotalAmount'), ('total_ttc','GrandTotalAmount'), ('prepaid_amount','TotalPrepaidAmount'), ('payable_amount','DuePayableAmount')]:
            self.assertEqual(Decimal(value('//ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:' + tag)), data['totals'][key])
        if 'balance' in scenario:
            self.assertEqual(value('//ram:InvoiceReferencedDocument/ram:IssuerAssignedID'), data['deposit_reference']['invoice_number'])
            self.assertEqual(value('//ram:InvoiceReferencedDocument/ram:FormattedIssueDateTime/qdt:DateTimeString'), data['deposit_reference']['invoice_date'].replace('-', ''))
        if scenario.startswith('b2b'):
            self.assertEqual(value('//ram:BuyerTradeParty/ram:SpecifiedLegalOrganization/ram:ID'), data['buyer']['siret'])
        else:
            self.assertFalse(root.xpath('//ram:BuyerTradeParty/ram:SpecifiedLegalOrganization', namespaces=NS))
    return run


for scenario in SCENARIOS:
    setattr(CiiTests, 'test_' + scenario.replace('-', '_'), scenario_test(scenario))


if __name__ == '__main__':
    unittest.main()
