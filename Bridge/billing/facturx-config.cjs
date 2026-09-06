'use strict';

class FacturxConfigError extends Error {
  constructor(fields) {
    super('Missing or invalid Factur-X fields: ' + fields.join(', '));
    this.code = 'FACTURX_CONFIG_MISSING';
    this.fields = fields;
  }
}
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);

function mapSellerConfig(invoice, config, privateContext = {}) {
  const errors = [];
  if (!object(config?.company)) errors.push('company');
  if (!object(privateContext)) errors.push('context');
  const company = config?.company;
  const buyerType = invoice?.buyer?.type;
  if (!['Entreprise', 'Particulier'].includes(buyerType)) errors.push('invoice.buyer.type');
  if (buyerType === 'Particulier') {
    if (errors.length) throw new FacturxConfigError(errors);
    // B2C does not inherit any B2B notes, endpoint lists or process defaults.
    return { sellerConfig: {company: structuredClone(company)}, context: {} };
  }
  const policy = object(config?.facturx) ? config.facturx : {};
  const supplied = object(privateContext) ? privateContext : {};
  function required(value, path) {
    if (typeof value !== 'string' || !value.trim()) errors.push(path);
  }
  function endpoint(value, path) {
    required(value?.value, path + '.value');
    required(value?.scheme_id, path + '.scheme_id');
  }
  endpoint(policy.seller_electronic_address, 'facturx.seller_electronic_address');
  endpoint(supplied.buyer_electronic_address, 'context.buyer_electronic_address');
  const processPath = 'facturx.business_process_by_type.' + invoice?.invoice_type;
  const process = policy.business_process_by_type?.[invoice?.invoice_type];
  required(process, processPath);
  if (typeof process === 'string' && process.trim() && process !== 'S2') errors.push(processPath + ' (only explicitly confirmed S2 supported)');
  if (supplied.business_process_id !== undefined && supplied.business_process_id !== process) errors.push('context.business_process_id (conflicts with seller config)');
  for (const code of ['PMT','PMD','AAB']) required(policy.b2b_notes?.[code], 'facturx.b2b_notes.' + code);
  if (policy.payment_date_convention !== 'paid_at_utc_date') errors.push('facturx.payment_date_convention (explicit paid_at_utc_date confirmation required)');
  if (errors.length) throw new FacturxConfigError(errors);
  // An allowlist prevents any obsolete public buyer directory reaching Python.
  return { sellerConfig: {company: structuredClone(company), facturx: {
    seller_electronic_address: structuredClone(policy.seller_electronic_address),
    b2b_notes: Object.fromEntries(['PMT','PMD','AAB'].map(code=>[code,policy.b2b_notes[code]])),
    payment_date_convention: policy.payment_date_convention,
    business_process_by_type: {[invoice.invoice_type]: process},
  }}, context: {business_process_id:process, buyer_electronic_address: structuredClone(supplied.buyer_electronic_address)} };
}
module.exports = { mapSellerConfig, FacturxConfigError };
