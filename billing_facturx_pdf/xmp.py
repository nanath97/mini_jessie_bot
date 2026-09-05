from datetime import timezone
from pathlib import Path
from lxml import etree as ET

ASSETS = Path(__file__).parent / 'assets'
FX = 'urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#'
NS = {
    'fx': FX, 'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'pdf': 'http://ns.adobe.com/pdf/1.3/', 'xmp': 'http://ns.adobe.com/xap/1.0/',
    'pdfaid': 'http://www.aiim.org/pdfa/ns/id/',
    'pdfaSchema': 'http://www.aiim.org/pdfa/ns/schema#',
    'pdfaExtension': 'http://www.aiim.org/pdfa/ns/extension/',
}
VALUES = {'DocumentType': 'INVOICE', 'DocumentFileName': 'factur-x.xml',
          'Version': '1.0', 'ConformanceLevel': 'EN 16931'}
PRODUCER = 'Bridge offline Factur-X PDF prototype'


def make_xmp(invoice, created_at, conformance='3b'):
    if conformance != '3b':
        raise NotImplementedError('3a requires a tagged accessible renderer; changing XMP alone is forbidden')
    root = ET.fromstring((ASSETS / 'official-1.09.2.xmp.txt').read_bytes(),
                         ET.XMLParser(resolve_entities=False, no_network=True))
    def set_text(xpath, value):
        nodes = root.xpath(xpath, namespaces=NS)
        if len(nodes) != 1:
            raise ValueError('Unexpected official XMP structure: ' + xpath)
        nodes[0].text = value
    for key, value in VALUES.items():
        set_text('//fx:' + key, value)
    set_text('//pdfaSchema:namespaceURI', FX)
    set_text('//pdfaid:part', '3')
    set_text('//pdfaid:conformance', 'B')
    title = 'Facture ' + invoice['invoice_number']
    author = invoice['seller'].get('legal_name') or invoice['seller']['name']
    set_text('//dc:title/rdf:Alt/rdf:li', title)
    set_text('//dc:creator/rdf:Seq/rdf:li', author)
    set_text('//dc:description/rdf:Alt/rdf:li', title + ' - ' + invoice['invoice_date'])
    set_text('//pdf:Producer', PRODUCER)
    set_text('//xmp:CreatorTool', PRODUCER)
    stamp = created_at.astimezone(timezone.utc).isoformat(timespec='seconds')
    for name in ('CreateDate', 'ModifyDate'):
        set_text('//xmp:' + name, stamp)
    return (b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            + ET.tostring(root, encoding='UTF-8') + b'\n<?xpacket end="w"?>')
