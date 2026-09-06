"""Explicit configuration only; no fixture, network or builder dependency."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from billing_facturx.mapping import map_invoice, missing_requirements


class AdapterError(ValueError):
    pass


def adapt_invoice(invoice, seller_config, context=None):
    """Adapt a paid builder snapshot. Amounts and commercial data stay untouched.

    seller_config.facturx supplies seller policy; context supplies transaction
    information. No contact email or legal identifier becomes an endpoint by
    inference. UTC payment-date use requires explicit policy confirmation.
    """
    if not isinstance(invoice, dict) or not isinstance(seller_config, dict) or (context is not None and not isinstance(context, dict)):
        raise AdapterError('invoice, seller_config and context must be JSON objects')
    data = deepcopy(invoice)
    context = context or {}
    errors = []
    def need(obj, key, path):
        value = obj.get(key) if isinstance(obj, dict) else None
        if not isinstance(value, str) or not value.strip():
            errors.append(path + ': required non-empty string')
        return value
    company = seller_config.get('company', {})
    for key in ('siren', 'country'):
        value = need(company, key, 'seller_config.company.' + key)
        if value and value != data.get('seller', {}).get(key):
            errors.append('seller_config.company.' + key + ': conflicts with invoice snapshot')
    for key in ('business_process_id', 'notes', 'payment_terms'):
        if key in data:
            errors.append('invoice.' + key + ': expected un-enriched builder snapshot')
    for role in ('seller', 'buyer'):
        if 'electronic_address' in data.get(role, {}):
            errors.append('invoice.' + role + '.electronic_address: use explicit context/config')
    need(data, 'invoice_date', 'invoice.invoice_date')
    paid = need(data, 'payment_date', 'invoice.payment_date')
    timestamp = None
    if paid:
        try:
            timestamp = datetime.fromisoformat(paid.replace('Z', '+00:00'))
            if timestamp.tzinfo is None:
                raise ValueError('timezone missing')
        except ValueError:
            errors.append('invoice.payment_date: ISO timestamp with timezone required')
    try:
        if Decimal(str(data['totals']['payable_amount'])) != 0:
            errors.append('invoice.totals.payable_amount: only already-paid builder invoices supported')
    except (KeyError, ValueError, ArithmeticError):
        errors.append('invoice.totals.payable_amount: invalid or missing')
    if data.get('buyer', {}).get('type') == 'Entreprise':
        policy = seller_config.get('facturx', {})
        if not isinstance(policy, dict):
            raise AdapterError('seller_config.facturx: expected object')
        process = need(context, 'business_process_id', 'context.business_process_id')
        if process and process != 'S2':
            errors.append('context.business_process_id: only explicitly confirmed S2 paid services supported')
        data['business_process_id'] = process
        for role, obj in [('seller', policy), ('buyer', context)]:
            key = role + '_electronic_address'
            endpoint = obj.get(key, {})
            for field in ('value', 'scheme_id'):
                need(endpoint, field, ('seller_config.facturx.' if role == 'seller' else 'context.') + key + '.' + field)
            data[role]['electronic_address'] = deepcopy(endpoint)
        notes = policy.get('b2b_notes', {})
        data['notes'] = []
        for code in ('PMT', 'PMD', 'AAB'):
            content = need(notes, code, 'seller_config.facturx.b2b_notes.' + code)
            data['notes'].append({'subject_code': code, 'content': content})
        if policy.get('payment_date_convention') != 'paid_at_utc_date':
            errors.append('seller_config.facturx.payment_date_convention: explicit paid_at_utc_date confirmation required for S2')
        if timestamp:
            data['payment_terms'] = {'due_date': timestamp.astimezone(timezone.utc).date().isoformat()}
    elif data.get('buyer', {}).get('type') == 'Particulier':
        if context:
            errors.append('context: B2C regulatory enrichment is not supported; diagnostic only')
    else:
        errors.append('invoice.buyer.type: expected Entreprise or Particulier')
    if errors:
        raise AdapterError('\n'.join(errors))
    try:
        mapped = map_invoice(data)
        missing = missing_requirements(mapped)
        if missing:
            raise AdapterError(str(missing))
    except ValueError as exc:
        raise AdapterError(str(exc)) from exc
    # map_invoice validates and derives CII identifiers on its private copy.
    # Return the builder amounts/types without normalization or recalculation.
    return data
