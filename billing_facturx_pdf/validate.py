"""Structural checks are not a PDF/A certificate. veraPDF is a separate gate."""
import hashlib
import json
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from lxml import etree as ET
from pypdf import PdfReader
from pypdf.generic import DictionaryObject, ArrayObject, IndirectObject
from .xmp import ASSETS, FX, NS, VALUES


def verify_assets():
    for name, digest in json.loads((ASSETS/'sha256.json').read_text()).items():
        if hashlib.sha256((ASSETS/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Changed PDF asset: ' + name)


def inspect_pdf(pdf, xml):
    reader = PdfReader(BytesIO(pdf), strict=True)
    if reader.is_encrypted:
        raise ValueError('Encrypted PDF forbidden')
    root = reader.trailer['/Root']
    af = root['/AF']
    names = root['/Names']['/EmbeddedFiles']['/Names']
    if len(af) != 1 or len(names) != 2 or names[0] != 'factur-x.xml' or af[0] != names[1]:
        raise ValueError('Incorrect document-level AF/name tree association')
    spec = af[0].get_object()
    if spec['/F'] != 'factur-x.xml' or spec['/UF'] != 'factur-x.xml':
        raise ValueError('Wrong attachment filename')
    if spec['/AFRelationship'] != '/Alternative':
        raise ValueError('Wrong AFRelationship')
    embedded = spec['/EF']['/F']
    if embedded['/Subtype'] != '/text/xml' or embedded.get_data() != xml:
        raise ValueError('Changed XML or wrong MIME')
    params = embedded['/Params']
    if not str(params['/ModDate']).startswith('D:') or params['/Size'] != len(xml):
        raise ValueError('Missing attachment Params')
    xmp = ET.fromstring(root['/Metadata'].get_data(), ET.XMLParser(resolve_entities=False, no_network=True))
    for key, value in VALUES.items():
        if xmp.xpath('//fx:'+key+'/text()', namespaces=NS) != [value]:
            raise ValueError('Incorrect XMP: ' + key)
    if xmp.xpath('//pdfaSchema:namespaceURI/text()', namespaces=NS) != [FX]:
        raise ValueError('Wrong extension namespace')
    if xmp.xpath('//pdfaSchema:prefix/text()', namespaces=NS) != ['fx']:
        raise ValueError('Wrong XMP namespace prefix')
    if xmp.xpath('//pdfaid:part/text()', namespaces=NS) != ['3'] or xmp.xpath('//pdfaid:conformance/text()', namespaces=NS) != ['B']:
        raise ValueError('Wrong PDF/A declaration')
    original = ET.fromstring((ASSETS/'official-1.09.2.xmp.txt').read_bytes())
    path = '//pdfaExtension:schemas'
    # The whole supplied extension declaration is carried over unchanged.
    if ET.tostring(xmp.xpath(path,namespaces=NS)[0],method='c14n') != ET.tostring(original.xpath(path,namespaces=NS)[0],method='c14n'):
        raise ValueError('Changed official extension declaration')
    fonts = []
    for page in reader.pages:
        for f in page['/Resources']['/Font'].values():
            font = f.get_object()
            descendants = font.get('/DescendantFonts', [font])
            for child in descendants:
                child = child.get_object()
                descriptor = child.get('/FontDescriptor')
                if descriptor is None or not any(k in descriptor.get_object() for k in ('/FontFile','/FontFile2','/FontFile3')):
                    raise ValueError('Unembedded font: '+str(child.get('/BaseFont')))
            fonts.append(str(font['/BaseFont']))
    if not fonts:
        raise ValueError('No embedded fonts')
    forbidden = {'/JavaScript','/JS','/OpenAction','/AA','/Launch','/RichMedia','/AcroForm'}
    seen = set()
    def walk(obj):
        if isinstance(obj, IndirectObject):
            key = (obj.idnum, obj.generation)
            if key in seen: return
            seen.add(key);obj = obj.get_object()
        if isinstance(obj, DictionaryObject):
            if forbidden.intersection(obj): raise ValueError('Active content forbidden')
            if obj.get('/S') in ('/URI','/GoToR','/SubmitForm','/ImportData','/Launch','/JavaScript'):
                raise ValueError('External/active action forbidden')
            for value in obj.values(): walk(value)
        elif isinstance(obj, ArrayObject):
            for value in obj: walk(value)
    walk(root)
    intent = root['/OutputIntents'][0].get_object()
    if intent['/S'] != '/GTS_PDFA1' or intent['/DestOutputProfile']['/N'] != 3:
        raise ValueError('Missing RGB archival output intent')
    return {'status':'pass', 'pages':len(reader.pages), 'fonts':sorted(set(fonts)),
            'xml_sha256':hashlib.sha256(xml).hexdigest(), 'af_relationship':'Alternative',
            'mime':'text/xml', 'namespace':FX, 'pdfa_declaration':'3b',
            'pdfa_conformity':'Not established by structural checks'}


def run_verapdf(pdf_path, executable=None):
    command = str(executable) if executable else (shutil.which('verapdf') or shutil.which('verapdf.bat'))
    if not command:
        return {'status':'blocked', 'reason':'veraPDF unavailable; PDF/A conformity not attested'}
    try:
        run = subprocess.run([command,'--format','xml','--flavour','3b',str(Path(pdf_path).resolve())],
                             capture_output=True,timeout=120,check=False)
        report = ET.fromstring(run.stdout, ET.XMLParser(resolve_entities=False,no_network=True))
        results = report.xpath('//*[local-name()="validationReport"]')
        valid = run.returncode == 0 and len(results) == 1 and results[0].get('isCompliant') == 'true'
        return {'status':'pass' if valid else 'fail','exit_code':run.returncode,
                'report_xml':run.stdout.decode('utf-8'), 'stderr':run.stderr.decode('utf-8',errors='replace')}
    except (OSError, subprocess.TimeoutExpired, ET.XMLSyntaxError) as exc:
        return {'status':'blocked','reason':str(exc)}
