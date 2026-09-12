'use strict';
const { SellersError } = require('./errors.cjs');
const { validSellerId } = require('./activation-token.cjs');
const FIELDS = Object.freeze(['company_name', 'legal_name', 'legal_status', 'siren', 'siret', 'address', 'postal_code', 'city', 'country', 'email', 'phone', 'vat_status', 'vat_number', 'default_vat_rate', 'calendly']);
function validateFields(body, sellerId) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw new SellersError(400, 'INVALID_PAYLOAD');
  if (Object.hasOwn(body, 'seller_id') && body.seller_id !== sellerId) throw new SellersError(403, 'SELLER_MISMATCH');
  if (Object.keys(body).some(key => key !== 'seller_id' && !FIELDS.includes(key))) throw new SellersError(400, 'FORBIDDEN_FIELD');
  const fields = {};
  for (const key of FIELDS) {
    if (!Object.hasOwn(body, key)) continue;
    const value = body[key];
    if (key === 'default_vat_rate') {
      if (!['string', 'number'].includes(typeof value) || String(value).trim() === '' || !Number.isFinite(Number(value)) || Number(value) < 0) throw new SellersError(400, 'INVALID_VAT_RATE');
      fields[key] = Number(value);
    } else {
      if (typeof value !== 'string' || value.length > 2000) throw new SellersError(400, 'INVALID_FIELD');
      fields[key] = value.trim();
    }
  }
  if (!fields.country || !fields.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(fields.email)) throw new SellersError(400, 'INVALID_COUNTRY_OR_EMAIL');
  if (fields.calendly) {
    let url;
    try { url = new URL(fields.calendly); } catch { throw new SellersError(400, 'INVALID_CALENDLY'); }
    if (url.protocol !== 'https:' || url.hostname !== 'calendly.com' || url.username || url.password || url.port) throw new SellersError(400, 'INVALID_CALENDLY');
  }
  return fields;
}
function createSellersService(base) {
  async function findUnique(sellerId) {
    if (!validSellerId(sellerId)) throw new SellersError(400, 'INVALID_SELLER_ID');
    let records;
    try { records = await base('NovaPulse Sellers').select({ filterByFormula: `{Seller_id}="${sellerId}"`, maxRecords: 2 }).all(); }
    catch (error) {
  console.error("❌ AIRTABLE SELLER FIND ERROR:", {
    message: error?.message,
    statusCode: error?.statusCode,
    error: error?.error,
  });
  throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
}
    if (!records.length) throw new SellersError(404, 'SELLER_NOT_FOUND');
    if (records.length !== 1) throw new SellersError(409, 'DUPLICATE_SELLER');
    if (records[0].fields.Seller_id !== sellerId) throw new SellersError(409, 'SELLER_ID_CONFLICT');
    return records[0];
  }
  return { findUnique, async update(sellerId, fields) {
    const record = await findUnique(sellerId);
    try { await base('NovaPulse Sellers').update(record.id, fields); }
    catch (error) {
  console.error("❌ AIRTABLE SELLER UPDATE ERROR:", {
    message: error?.message,
    statusCode: error?.statusCode,
    error: error?.error,
  });
  throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
}
    return { ok: true, seller_id: sellerId };
  } };
}
module.exports = { createSellersService, validateFields };
