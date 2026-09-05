"""Explicit historical French fixture overlay; never production defaults."""
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from .mapping import MappingError

DEFAULT_OVERLAYS = Path(__file__).resolve().parents[1] / 'tests/facturx/french-fixtures'


def enrich(invoice, source_file, scenario, overlays=DEFAULT_OVERLAYS):
    result = copy.deepcopy(invoice)
    if invoice['buyer']['type'] == 'Particulier':
        return result
    if scenario not in ('b2b-normal', 'b2b-deposit', 'b2b-balance'):
        raise MappingError('No confirmed French historical overlay for scenario')
    data = json.loads((Path(overlays) / (scenario + '.json')).read_text(encoding='utf-8'))
    if data['invoice_number'] != invoice['invoice_number'] or data['source_sha256'] != hashlib.sha256(Path(source_file).read_bytes()).hexdigest():
        raise MappingError('Historical overlay/source mismatch')
    if data['business_process_id'] != 'S2':
        raise MappingError('Only confirmed S2 historical fixtures supported')
    timestamp = datetime.fromisoformat(invoice['payment_date'].replace('Z', '+00:00'))
    if timestamp.tzinfo is None:
        raise MappingError('Historical payment_date must include timezone')
    result['business_process_id'] = data['business_process_id']
    for role in ('seller', 'buyer'):
        endpoint = data[role + '_endpoint']
        if not endpoint.get('value') or not endpoint.get('scheme_id'):
            raise MappingError('Missing explicit electronic address')
        result[role]['electronic_address'] = endpoint
    notes = data['notes']
    if sorted(n['subject_code'] for n in notes) != ['AAB', 'PMD', 'PMT'] or any(not n['content'].strip() for n in notes):
        raise MappingError('Missing/duplicate explicit legal note')
    result['notes'] = notes
    result['payment_terms'] = {'due_date': timestamp.astimezone(timezone.utc).date().isoformat()}
    return result
