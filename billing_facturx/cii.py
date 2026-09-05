"""CII D22B EN16931 serializer. Can render rejected diagnostic candidates."""
from lxml import etree as ET
from .mapping import map_invoice, date102, number

NS = {
    'rsm': 'urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100',
    'ram': 'urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100',
    'udt': 'urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100',
    'qdt': 'urn:un:unece:uncefact:data:standard:QualifiedDataType:100',
}


def element(parent, name, value=None, **attrs):
    prefix, local = name.split(':') if ':' in name else ('ram', name)
    result = ET.SubElement(parent, ET.QName(NS[prefix], local), **attrs)
    if value is not None:
        result.text = str(value)
    return result


def party(parent, role, data):
    p = element(parent, role + 'TradeParty')
    if data.get('establishment_id'):
        element(p, 'GlobalID', data['establishment_id'], schemeID='0009')
    element(p, 'Name', data['display_name'])
    if data.get('legal_id'):
        element(element(p, 'SpecifiedLegalOrganization'), 'ID', data['legal_id'], schemeID='0002')
    if data.get('phone') or data.get('email'):
        contact = element(p, 'DefinedTradeContact')
        if data.get('phone'):
            element(element(contact, 'TelephoneUniversalCommunication'), 'CompleteNumber', data['phone'])
        if data.get('email'):
            element(element(contact, 'EmailURIUniversalCommunication'), 'URIID', data['email'])
    address = element(p, 'PostalTradeAddress')
    for key, name in [('postal_code', 'PostcodeCode'), ('address' if role == 'Seller' else 'address_1', 'LineOne'), ('address_2', 'LineTwo'), ('city', 'CityName'), ('country', 'CountryID')]:
        if data.get(key):
            element(address, name, data[key])
    if data.get('electronic_address'):
        endpoint = data['electronic_address']
        element(element(p, 'URIUniversalCommunication'), 'URIID', endpoint['value'], schemeID=endpoint['scheme_id'])
    # Contact email is not assumed to be a registered electronic routing address.
    for key, scheme in [('vat_number', 'VA'), ('tax_registration_id', 'FC')]:
        if data.get(key):
            element(element(p, 'SpecifiedTaxRegistration'), 'ID', data[key], schemeID=scheme)


def build_cii(source):
    d = map_invoice(source)
    root = ET.Element(ET.QName(NS['rsm'], 'CrossIndustryInvoice'), nsmap=NS)
    context = element(root, 'rsm:ExchangedDocumentContext')
    if d.get('business_process_id'):
        element(element(context, 'BusinessProcessSpecifiedDocumentContextParameter'), 'ID', d['business_process_id'])
    element(element(context, 'GuidelineSpecifiedDocumentContextParameter'), 'ID', 'urn:cen.eu:en16931:2017')
    doc = element(root, 'rsm:ExchangedDocument')
    element(doc, 'ID', d['invoice_number'])
    element(doc, 'TypeCode', d['type_code'])
    element(element(doc, 'IssueDateTime'), 'udt:DateTimeString', date102(d['invoice_date']), format='102')
    for note in d.get('notes', []):
        n = element(doc, 'IncludedNote')
        element(n, 'Content', note['content'])
        element(n, 'SubjectCode', note['subject_code'])
    transaction = element(root, 'rsm:SupplyChainTradeTransaction')
    for line in d['lines']:
        item = element(transaction, 'IncludedSupplyChainTradeLineItem')
        element(element(item, 'AssociatedDocumentLineDocument'), 'LineID', line['line_number'])
        element(element(item, 'SpecifiedTradeProduct'), 'Name', line['description'])
        price = element(element(item, 'SpecifiedLineTradeAgreement'), 'NetPriceProductTradePrice')
        element(price, 'ChargeAmount', number(line['unit_price_ht'], True))
        element(element(item, 'SpecifiedLineTradeDelivery'), 'BilledQuantity', number(line['quantity']), unitCode=line['unit'])
        settlement = element(item, 'SpecifiedLineTradeSettlement')
        tax = element(settlement, 'ApplicableTradeTax')
        element(tax, 'TypeCode', 'VAT')
        element(tax, 'CategoryCode', line['tax_category'])
        element(tax, 'RateApplicablePercent', number(line['vat_rate']))
        element(element(settlement, 'SpecifiedTradeSettlementLineMonetarySummation'), 'LineTotalAmount', number(line['line_total_ht'], True))
    agreement = element(transaction, 'ApplicableHeaderTradeAgreement')
    party(agreement, 'Seller', d['seller'])
    party(agreement, 'Buyer', d['buyer'])
    if d.get('quote', {}).get('quote_id'):
        ref = element(agreement, 'AdditionalReferencedDocument')
        element(ref, 'IssuerAssignedID', d['quote']['quote_id'])
        element(ref, 'TypeCode', '916')
    element(transaction, 'ApplicableHeaderTradeDelivery')
    settlement = element(transaction, 'ApplicableHeaderTradeSettlement')
    element(settlement, 'InvoiceCurrencyCode', d['currency'])
    tax = element(settlement, 'ApplicableTradeTax')
    element(tax, 'CalculatedAmount', number(d['tax']['tax_amount'], True))
    element(tax, 'TypeCode', 'VAT')
    if d['tax'].get('exemption_reason'):
        element(tax, 'ExemptionReason', d['tax']['exemption_reason'])
    element(tax, 'BasisAmount', number(d['tax']['taxable_amount'], True))
    element(tax, 'CategoryCode', d['tax']['category'])
    if d['tax'].get('exemption_code'):
        element(tax, 'ExemptionReasonCode', d['tax']['exemption_code'])
    element(tax, 'RateApplicablePercent', number(d['tax']['rate']))
    if d.get('payment_terms', {}).get('due_date'):
        terms = element(settlement, 'SpecifiedTradePaymentTerms')
        element(element(terms, 'DueDateDateTime'), 'udt:DateTimeString', date102(d['payment_terms']['due_date']), format='102')
    totals = element(settlement, 'SpecifiedTradeSettlementHeaderMonetarySummation')
    for key, name in [('total_ht','LineTotalAmount'), ('total_ht','TaxBasisTotalAmount'), ('vat_amount','TaxTotalAmount'), ('total_ttc','GrandTotalAmount'), ('prepaid_amount','TotalPrepaidAmount'), ('payable_amount','DuePayableAmount')]:
        element(totals, name, number(d['totals'][key], True), **({'currencyID':d['currency']} if key=='vat_amount' else {}))
    if d.get('deposit_reference'):
        ref = element(settlement, 'InvoiceReferencedDocument')
        element(ref, 'IssuerAssignedID', d['deposit_reference']['invoice_number'])
        element(element(ref, 'FormattedIssueDateTime'), 'qdt:DateTimeString', date102(d['deposit_reference']['invoice_date']), format='102')
    return ET.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)
