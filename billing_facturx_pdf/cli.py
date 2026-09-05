import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from billing_facturx.validation.validate import validate as validate_cii
from .inputs import ROOT, load_inputs
from .assemble import assemble
from .validate import inspect_pdf, verify_assets, run_verapdf


def main():
    fixtures = ROOT/'tests/facturx_pdf/fixtures'
    parser = argparse.ArgumentParser(description='B2B normal/deposit/balance; non-production prototype')
    parser.add_argument('--scenario',choices=['b2b-normal','b2b-deposit','b2b-balance'],default='b2b-normal')
    parser.add_argument('--invoice',type=Path)
    parser.add_argument('--xml',type=Path)
    parser.add_argument('--prior-report',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--verapdf',type=Path)
    parser.add_argument('--conformance',choices=['3b','3a'],default='3b')
    args = parser.parse_args()
    if args.out.exists(): parser.error('Output directory must not already exist')
    if args.conformance != '3b': parser.error('3a is reserved, not implemented; requires tagged content')
    verify_assets()
    scenario_fixtures = fixtures if args.scenario == 'b2b-normal' else fixtures/args.scenario
    args.invoice = args.invoice or ROOT/'Bridge/tests/billing/fixtures'/args.scenario/'expected.invoice.json'
    args.xml = args.xml or scenario_fixtures/'factur-x.xml'
    args.prior_report = args.prior_report or scenario_fixtures/'validation.json'
    invoice, xml, prior = load_inputs(args.invoice,args.xml,args.prior_report)
    if 'b2b-' + invoice['invoice_type'] != args.scenario:
        parser.error('Scenario does not match invoice type')
    pdf = assemble(invoice,xml,datetime.now(timezone.utc),args.conformance)
    structure = inspect_pdf(pdf,xml)
    args.out.mkdir(parents=True)
    target = args.out/(invoice['invoice_number'] + '-factur-x.pdf')
    target.write_bytes(pdf)
    cii = validate_cii(xml,invoice)
    for name in ('en16931','br_fr'):
        svrl = cii[name].pop('svrl',None)
        if svrl: (args.out/(name+'.svrl.xml')).write_text(svrl,encoding='utf-8')
    pdfa = run_verapdf(target,args.verapdf)
    svrl = pdfa.pop('report_xml',None)
    if svrl: (args.out/'verapdf.xml').write_text(svrl,encoding='utf-8')
    report = {'structure':structure,'historical_cii':prior,'current_cii':cii,'pdfa':pdfa,
              'production':False,'accepted':cii['accepted'] and pdfa['status']=='pass'}
    (args.out/'validation.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['accepted'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
