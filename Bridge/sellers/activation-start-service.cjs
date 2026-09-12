'use strict';
const { randomBytes } = require('node:crypto');
const { SellersError } = require('./errors.cjs');
const { issueActivationToken, validSellerId } = require('./activation-token.cjs');
const { validClientId } = require('./client-session-token.cjs');
const { createSellersService } = require('./service.cjs');
function createActivationStartService({ base, clientTable = 'PWA Clients', generateSellerId = () => 'sel_' + randomBytes(16).toString('hex') }) {
  const locks = new Map();
  // Retain ambiguous writes until a reciprocal link confirms creation. No blind retry.
  const uncertainCreates = new Set();
  const sellers = createSellersService(base);
  async function read(table, id) {
    let record;
    try { record = await base(table).find(id); }
    catch (error) { throw new SellersError(error?.statusCode === 404 ? 404 : 502, error?.statusCode === 404 ? 'RECORD_NOT_FOUND' : 'AIRTABLE_UNAVAILABLE'); }
    if (record?.id !== id || !record.fields) throw new SellersError(409, 'INCONSISTENT_RECORD');
    return record;
  }
  function linkedSeller(client) {
    const ids = client.fields['NovaPulse Sellers'];
    if (ids === undefined || (Array.isArray(ids) && ids.length === 0)) return null;
    if (!Array.isArray(ids) || ids.length !== 1 || !validClientId(ids[0])) throw new SellersError(409, 'SELLER_LINK_CONFLICT');
    return ids[0];
  }
  async function checkSeller(recordId, clientId) {
    const row = await read('NovaPulse Sellers', recordId);
    const owners = row.fields.pwa_client;
    if (!Array.isArray(owners) || owners.length !== 1 || owners[0] !== clientId) throw new SellersError(409, 'SELLER_OWNER_CONFLICT');
    if (!validSellerId(row.fields.Seller_id)) throw new SellersError(409, 'SELLER_ID_MISSING_OR_INVALID');
    const unique = await sellers.findUnique(row.fields.Seller_id);
    if (unique.id !== row.id) throw new SellersError(409, 'SELLER_ID_CONFLICT');
    return row.fields.Seller_id;
  }
  async function start(clientId) {
    if (!validClientId(clientId)) throw new SellersError(401, 'INVALID_CLIENT_TOKEN');
    let release;
    const previous = locks.get(clientId) || Promise.resolve();
    const current = new Promise(resolve => { release = resolve; });
    locks.set(clientId, current);
    await previous;
    try {
      // Fail before any Airtable write if the existing seller-token secret is missing.
      issueActivationToken('preflight');
      const client = await read(clientTable, clientId);
      const existingId = linkedSeller(client);
      if (existingId) {
        const sellerId = await checkSeller(existingId, clientId);
        uncertainCreates.delete(clientId);
        return { ok: true, seller_id: sellerId, activation_token: issueActivationToken(sellerId), created: false };
      }
      if (uncertainCreates.has(clientId)) throw new SellersError(409, 'CREATION_REQUIRES_VERIFICATION');
      let sellerId;
      for (let attempt = 0; attempt < 5; attempt++) {
        const candidate = generateSellerId();
        if (!validSellerId(candidate)) throw new SellersError(500, 'INVALID_GENERATED_ID');
        let rows;
        try { rows = await base('NovaPulse Sellers').select({ filterByFormula: `{Seller_id}="${candidate}"`, maxRecords: 1 }).all(); }
        catch { throw new SellersError(502, 'AIRTABLE_UNAVAILABLE'); }
        if (!rows.length) { sellerId = candidate; break; }
      }
      if (!sellerId) throw new SellersError(503, 'SELLER_ID_GENERATION_FAILED');
      // Re-read immediately before creation to observe links added during collision checks.
      const before = linkedSeller(await read(clientTable, clientId));
      if (before) {
        const resolved = await checkSeller(before, clientId);
        return { ok: true, seller_id: resolved, activation_token: issueActivationToken(resolved), created: false };
      }
      uncertainCreates.add(clientId);
      let created;
      try { created = await base('NovaPulse Sellers').create({ Seller_id: sellerId, pwa_client: [clientId] }); }
      catch { throw new SellersError(502, 'AIRTABLE_UNAVAILABLE'); }
      if (!validClientId(created?.id)) throw new SellersError(409, 'CREATION_REQUIRES_VERIFICATION');
      const after = linkedSeller(await read(clientTable, clientId));
      if (after !== created.id) throw new SellersError(409, 'SELLER_LINK_CONFLICT');
      const checked = await checkSeller(created.id, clientId);
      if (checked !== sellerId) throw new SellersError(409, 'SELLER_ID_CONFLICT');
      uncertainCreates.delete(clientId);
      return { ok: true, seller_id: sellerId, activation_token: issueActivationToken(sellerId), created: true };
    } finally {
      release();
      if (locks.get(clientId) === current) locks.delete(clientId);
    }
  }
  return { start };
}
module.exports = { createActivationStartService };
