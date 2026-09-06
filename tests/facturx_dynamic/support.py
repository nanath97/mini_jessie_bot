"""Historical supplements for tests only, never imported by the adapter."""
import json
import subprocess
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def builders():
    result = subprocess.run(['node', str(Path(__file__).with_name('export-builders.cjs'))], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True)
    return json.loads(result.stdout)


def inputs(scenario, record):
    config = deepcopy(record['seller_config'])
    context = {}
    if scenario.startswith('b2b'):
        overlay = json.loads((ROOT/'tests/facturx/french-fixtures'/f'{scenario}.json').read_text(encoding='utf-8'))
        if overlay['invoice_number'] != record['invoice']['invoice_number']:
            raise ValueError('Fixture overlay identity mismatch')
        config['facturx'] = {
            'seller_electronic_address': overlay['seller_endpoint'],
            'b2b_notes': {n['subject_code']: n['content'] for n in overlay['notes']},
            'payment_date_convention': 'paid_at_utc_date',
        }
        context = {'business_process_id': overlay['business_process_id'], 'buyer_electronic_address': overlay['buyer_endpoint']}
    return config, context


def reference(scenario):
    folder = ROOT/'tests/facturx_pdf/fixtures'
    return (folder if scenario == 'b2b-normal' else folder/scenario)/'factur-x.xml'
