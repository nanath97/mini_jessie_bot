import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlparse
from lxml import etree as ET
from ..mapping import missing_requirements

HERE = Path(__file__).parent
ARTIFACTS = HERE / 'artifacts'


def verify_artifacts():
    lock = json.loads((HERE / 'artifacts.lock.json').read_text(encoding='utf-8'))
    for name, digest in lock['sha256'].items():
        p = (ARTIFACTS / name).resolve()
        if not p.is_relative_to(ARTIFACTS.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise ValueError('Artifact integrity failure: ' + name)


class LocalResolver(ET.Resolver):
    def resolve(self, url, public_id, context):
        parsed = urlparse(url)
        if parsed.scheme == 'file':
            value = unquote(parsed.path)
            if len(value) > 2 and value[0] == '/' and value[2] == ':':
                value = value[1:]
            p = Path(value).resolve()
        elif parsed.scheme and len(parsed.scheme) != 1:
            raise ValueError('External resource forbidden')
        else:
            p = Path(url).resolve()
        if not p.is_relative_to(ARTIFACTS.resolve()):
            raise ValueError('Resource outside pinned artifacts')
        return self.resolve_filename(str(p), context)


def parse_xml(data):
    if b'<!DOCTYPE' in data or b'<!ENTITY' in data:
        raise ValueError('DTD/entities forbidden')
    return ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))


def validate_xsd(xml):
    verify_artifacts()
    parser = ET.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    parser.resolvers.add(LocalResolver())
    schema = ET.XMLSchema(ET.parse(str(ARTIFACTS / '1xsd/Factur-X_EN16931.xsd'), parser))
    tree = parse_xml(xml)
    ok = schema.validate(tree)
    return {'status': 'pass' if ok else 'fail', 'errors': [str(e) for e in schema.error_log]}


def interpret_svrl(svrl):
    root = parse_xml(svrl.encode('utf-8'))
    ns = {'s': 'http://purl.oclc.org/dsdl/svrl'}
    if root.tag != '{http://purl.oclc.org/dsdl/svrl}schematron-output':
        raise ValueError('Not a Schematron report')
    if not root.xpath('//s:fired-rule', namespaces=ns):
        raise ValueError('No Schematron rule executed')
    findings = [{'id': n.get('id'), 'flag': n.get('flag'), 'location': n.get('location'), 'message': ''.join(n.itertext()).strip()} for n in root.xpath('//s:failed-assert | //s:successful-report', namespaces=ns)]
    errors = [f for f in findings if f['flag'] not in ('warning', 'information', 'info')]
    return {'status': 'fail' if errors else 'pass', 'findings': findings}


def validate_schematron(xml, name):
    verify_artifacts()
    parse_xml(xml)
    try:
        from saxonche import PySaxonProcessor
    except ImportError:
        return {'status': 'blocked', 'reason': 'saxonche==12.9.0 unavailable; no Schematron execution'}
    # Local code lists are packaged beside their XSLT; no remote services.
    with PySaxonProcessor(license=False) as proc:
        proc.set_configuration_property('http://saxon.sf.net/feature/allowedProtocols', 'file')
        proc.set_configuration_property('http://saxon.sf.net/feature/allow-external-functions', 'false')
        executable = proc.new_xslt30_processor().compile_stylesheet(stylesheet_file=str(ARTIFACTS / '2xslt' / name))
        svrl = executable.transform_to_string(xdm_node=proc.parse_xml(xml_text=xml.decode('utf-8')))
    result = interpret_svrl(svrl)
    result['svrl'] = svrl
    return result


def validate(xml, invoice):
    result = {'xsd': validate_xsd(xml), 'mandatory_data': missing_requirements(invoice)}
    for label, name in [('en16931', 'FACTUR-X_EN16931.xslt'), ('br_fr', 'BR-FR-Flux2-Schematron-CII.xslt')]:
        try:
            result[label] = validate_schematron(xml, name)
        except Exception as exc:
            result[label] = {'status': 'blocked', 'reason': str(exc)}
    result['br_fr']['regulatory_scope'] = 'B2B' if invoice['buyer']['type'] == 'Entreprise' else 'B2C diagnostic only; not a B2B regulatory flow'
    required = ('xsd', 'en16931', 'br_fr') if invoice['buyer']['type'] == 'Entreprise' else ('xsd', 'en16931')
    result['br_fr']['required_for_acceptance'] = invoice['buyer']['type'] == 'Entreprise'
    result['accepted'] = not result['mandatory_data'] and all(result[k]['status'] == 'pass' for k in required)
    return result
