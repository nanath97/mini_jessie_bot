import hashlib
import json
from pathlib import Path
from billing_facturx.mapping import load_invoice
from billing_facturx.french import enrich
from billing_facturx.cii import build_cii
from billing_facturx.validation.validate import interpret_svrl

ROOT = Path(__file__).resolve().parents[1]


def load_inputs(invoice_path, xml_path, prior_report):
    source = load_invoice(invoice_path)
    if source.get('invoice_type') not in ('normal', 'deposit', 'balance') or source.get('buyer', {}).get('type') != 'Entreprise':
        raise ValueError('Only B2B normal, deposit and balance invoices are supported')
    invoice = enrich(source, invoice_path, 'b2b-' + source['invoice_type'])
    xml = Path(xml_path).read_bytes()
    # Regeneration is only a read-only consistency check. The ORIGINAL bytes are embedded.
    if build_cii(invoice) != xml:
        raise ValueError('Readable input does not reproduce the exact validated XML')
    prior = json.loads(Path(prior_report).read_text(encoding='utf-8'))
    if prior['xml_sha256'] != hashlib.sha256(xml).hexdigest() or prior['source_sha256'] != hashlib.sha256(Path(invoice_path).read_bytes()).hexdigest():
        raise ValueError('Historical validation provenance mismatch')
    if not prior['accepted'] or any(prior[k]['status'] != 'pass' for k in ('xsd','en16931','br_fr')):
        raise ValueError('Input must have historical XSD + EN16931 + BR-FR PASS')
    for name in ('en16931','br_fr'):
        svrl = Path(prior_report).parent/(name+'.svrl.xml')
        if interpret_svrl(svrl.read_text(encoding='utf-8'))['status'] != 'pass':
            raise ValueError('Historical SVRL not PASS')
    return invoice, xml, {'status':'pass','kind':'preserved historical validation, not a fresh Schematron run',
                          'xml_sha256':prior['xml_sha256']}
