"""Only local normalized JSON inputs. Nonzero exit on any rejected/blocked candidate."""
import argparse
import hashlib
import json
from pathlib import Path
from .mapping import load_invoice
from .french import enrich
from .cii import build_cii
from .validation.validate import validate

SCENARIOS = ('b2b-normal', 'b2b-deposit', 'b2b-balance', 'b2c-normal', 'b2c-deposit', 'b2c-balance')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    # Prevent accidental overwriting of fixtures or other existing output files.
    if args.out.exists():
        parser.error('Output directory already exists; choose a new directory')
    args.out.mkdir(parents=True)
    results = {}
    for scenario in SCENARIOS:
        filename = args.fixtures / scenario / 'expected.invoice.json'
        try:
            invoice = enrich(load_invoice(filename), filename, scenario)
            xml = build_cii(invoice)
            report = validate(xml, invoice)
            report['source_sha256'] = hashlib.sha256(filename.read_bytes()).hexdigest()
            report['xml_sha256'] = hashlib.sha256(xml).hexdigest()
            report['document_status'] = ('validated' if invoice['buyer']['type'] == 'Entreprise' else 'diagnostic only') if report['accepted'] else 'REJECTED_DIAGNOSTIC_CANDIDATE'
            report['scope'] = 'B2B' if invoice['buyer']['type'] == 'Entreprise' else 'diagnostic only'
            dest = args.out / scenario
            dest.mkdir()
            (dest / 'factur-x.xml').write_bytes(xml)
            for label in ('en16931', 'br_fr'):
                svrl = report[label].pop('svrl', None)
                if svrl is not None:
                    (dest / (label + '.svrl.xml')).write_text(svrl, encoding='utf-8')
            (dest / 'validation.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
            results[scenario] = report
        except Exception as exc:
            results[scenario] = {'accepted': False, 'error': str(exc)}
    (args.out / 'summary.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({s: {k: v.get(k) for k in ('accepted', 'xsd', 'en16931', 'br_fr', 'mandatory_data', 'error') if k in v} for s,v in results.items()}, ensure_ascii=False))
    return 0 if all(r['accepted'] for r in results.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
