"""Local files only. No application/server import or fixture defaults."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from .adapter import adapt_invoice
from billing_facturx.cii import build_cii
from billing_facturx.validation.validate import validate
from billing_facturx_pdf.assemble import assemble
from billing_facturx_pdf.validate import inspect_pdf, verify_assets, run_verapdf


def generate(invoice, seller_config, context, out, verapdf=None):
    data = adapt_invoice(invoice, seller_config, context)
    out = Path(out)
    if out.exists():
        raise ValueError('Output directory must not already exist')
    verify_assets()
    xml = build_cii(data)
    pdf = assemble(data, xml, datetime.now(timezone.utc))
    structure = inspect_pdf(pdf, xml)
    cii = validate(xml, data)
    out.mkdir(parents=True)
    (out/'factur-x.xml').write_bytes(xml)
    target = out/'factur-x.pdf'
    target.write_bytes(pdf)
    for key in ('en16931', 'br_fr'):
        svrl = cii[key].pop('svrl', None)
        if svrl:
            (out/(key+'.svrl.xml')).write_text(svrl, encoding='utf-8')
    pdfa = run_verapdf(target, verapdf)
    report_xml = pdfa.pop('report_xml', None)
    if report_xml:
        (out/'verapdf.xml').write_text(report_xml, encoding='utf-8')
    report = {'structure': structure, 'cii': cii, 'pdfa': pdfa,
              'xml_sha256': hashlib.sha256(xml).hexdigest(),
              'scope': 'B2B' if data['buyer']['type'] == 'Entreprise' else 'B2C diagnostic only',
              'production': False, 'accepted': cii['accepted'] and pdfa['status'] == 'pass'}
    (out/'validation.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--invoice', type=Path, required=True)
    parser.add_argument('--seller-config', type=Path, required=True)
    parser.add_argument('--context', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--verapdf', type=Path)
    args = parser.parse_args()
    def read(path):
        return json.loads(path.read_text(encoding='utf-8-sig'))
    report = generate(read(args.invoice), read(args.seller_config), read(args.context) if args.context else {}, args.out, args.verapdf)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['accepted'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
