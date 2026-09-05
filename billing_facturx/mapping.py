"""Map normalized invoice JSON without changing monetary values."""
import copy
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


class MappingError(ValueError):
    pass


def required(obj, key):
    value = obj.get(key)
    if value is None or value == "":
        raise MappingError(f"Missing required field: {key}")
    return value


def number(value, money=False):
    try:
        if isinstance(value, bool):
            raise InvalidOperation
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise InvalidOperation
        if money and result != result.quantize(Decimal('.01')):
            raise MappingError("Amount has more than two decimals; no automatic rounding")
        return format(result, '.2f' if money else 'f')
    except (InvalidOperation, ValueError) as exc:
        raise MappingError(f"Invalid numeric value: {value!r}") from exc


def date102(value):
    # A payment timestamp is never substituted for the issue/due date.
    return date.fromisoformat(value).strftime('%Y%m%d')


def load_invoice(filename):
    return json.loads(Path(filename).read_text(encoding='utf-8'), parse_float=Decimal)


def seller_tax_registration(data):
    """BR-FR-CO-16: repeat the existing French SIREN in BT-32, never BT-31."""
    seller = data['seller']
    if seller.get('tax_registration_id'):
        return seller['tax_registration_id']
    siren = seller.get('siren')
    if (seller.get('country') == 'FR' and not seller.get('vat_number')
            and data['tax'].get('category') == 'E'
            and data['tax'].get('exemption_code') == 'VATEX-FR-FRANCHISE'
            and isinstance(siren, str) and siren.isascii()
            and siren.isdigit() and len(siren) == 9):
        return siren
    return None


def map_invoice(source):
    data = copy.deepcopy(source)
    kind = required(data, 'invoice_type')
    if kind not in ('normal', 'deposit', 'balance'):
        raise MappingError('Unsupported invoice_type')
    data['type_code'] = '386' if kind == 'deposit' else '380'
    required(data, 'invoice_number')
    date102(required(data, 'invoice_date'))
    required(data, 'currency')
    buyer_type = required(data['buyer'], 'type')
    if buyer_type not in ('Entreprise', 'Particulier'):
        raise MappingError('Unsupported buyer.type')
    for role in ('seller', 'buyer'):
        party = data[role]
        name = (party.get('legal_name') or party.get('name')) if role == 'seller' else ((party.get('company_name') or party.get('name')) if buyer_type == 'Entreprise' else party.get('name'))
        if not name:
            raise MappingError(f'Missing {role} name')
        party['display_name'] = name
        required(party, 'country')
        legal = party.get('siren') if role == 'seller' else party.get('siret')
        if legal:
            if not isinstance(legal, str) or not legal.isascii() or not legal.isdigit() or len(legal) not in (9, 14):
                raise MappingError(f'Invalid {role} SIREN/SIRET')
            party['legal_id'] = legal[:9]  # SIREN prefix of an explicitly supplied SIRET.
        if party.get('siret') and len(party['siret']) == 14:
            party['establishment_id'] = party['siret']
    lines = required(data, 'lines')
    if len(lines) != 1:
        raise MappingError('Initial adapter supports exactly one tax breakdown and one line')
    for line in lines:
        for key in ('line_number', 'description', 'unit', 'tax_category'):
            required(line, key)
        for key in ('quantity', 'unit_price_ht', 'line_total_ht', 'vat_rate'):
            number(required(line, key), money=key in ('unit_price_ht', 'line_total_ht'))
        if Decimal(str(line['quantity'])) <= 0:
            raise MappingError('Quantity must be positive')
    tax = data['tax']
    for key in ('rate', 'taxable_amount', 'tax_amount'):
        number(required(tax, key), money=key != 'rate')
    required(tax, 'category')
    if tax['category'] == 'E' and not (tax.get('exemption_code') or tax.get('exemption_reason')):
        raise MappingError('Missing VAT exemption reason/code')
    for key in ('total_ht', 'vat_amount', 'total_ttc', 'prepaid_amount', 'payable_amount'):
        number(required(data['totals'], key), money=True)
    # Compare provided totals; never replace them with computed totals.
    t = {k: Decimal(str(v)) for k, v in data['totals'].items()}
    if t['total_ht'] + t['vat_amount'] != t['total_ttc'] or t['total_ttc'] - t['prepaid_amount'] != t['payable_amount']:
        raise MappingError('Inconsistent supplied totals')
    if Decimal(str(lines[0]['line_total_ht'])) != t['total_ht'] or Decimal(str(tax['taxable_amount'])) != t['total_ht'] or Decimal(str(tax['tax_amount'])) != t['vat_amount']:
        raise MappingError('Inconsistent supplied line/tax totals')
    if lines[0]['tax_category'] != tax['category'] or Decimal(str(lines[0]['vat_rate'])) != Decimal(str(tax['rate'])):
        raise MappingError('Line/header tax mismatch')
    if kind == 'balance':
        ref = required(data, 'deposit_reference')
        required(ref, 'invoice_number')
        date102(required(ref, 'invoice_date'))
    fiscal_id = seller_tax_registration(data)
    if fiscal_id:
        data['seller']['tax_registration_id'] = fiscal_id
    return data


def missing_requirements(data):
    """Known blocking rule checked explicitly, not a replacement for Schematron."""
    errors = []
    if any(line['tax_category'] == 'E' for line in data['lines']):
        if not data['seller'].get('vat_number') and not seller_tax_registration(data):
            errors.append({'rule': 'BR-E-02', 'missing': 'Seller tax registration BT-31/BT-32/BT-63', 'detail': 'No fiscal identifier or eligible French franchise SIREN supplied.'})
    if Decimal(str(data['totals']['payable_amount'])) > 0:
        errors.append({'rule': 'BR-CO-25', 'missing': 'Due date or payment terms', 'detail': 'Normalized model has neither; payment_date is not a due date.'})
    return errors
