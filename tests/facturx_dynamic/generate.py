"""Generate six TEST outputs from builders plus explicit historical supplements."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from billing_facturx_dynamic.cli import generate
from billing_facturx_dynamic import adapt_invoice
from billing_facturx.cii import build_cii
from support import builders, inputs, reference

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--verapdf', type=Path)
args = parser.parse_args()
if args.out.exists(): parser.error('Output directory must not already exist')
records = builders()
prepared = {}
for name, record in records.items():
    config, context = inputs(name, record)
    if build_cii(adapt_invoice(record['invoice'], config, context)) != reference(name).read_bytes():
        raise ValueError('Historical CII byte mismatch: '+name)
    prepared[name] = (config, context)
accepted = True
for name, record in records.items():
    config, context = prepared[name]
    report = generate(record['invoice'], config, context, args.out/name, args.verapdf)
    report['test_provenance'] = 'Actual offline builders; B2B configuration supplemented ONLY from confirmed historical overlays; not real seller policy'
    report['historical_xml_identical'] = True
    (args.out/name/'validation.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(name, 'XSD='+report['cii']['xsd']['status'], 'EN16931='+report['cii']['en16931']['status'], 'BR-FR='+report['cii']['br_fr']['status'], 'PDF/A='+report['pdfa']['status'], 'historical XML identical')
    accepted = accepted and report['accepted']
raise SystemExit(0 if accepted else 2)
