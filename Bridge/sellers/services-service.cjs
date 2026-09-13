'use strict';
const { SellersError } = require('./errors.cjs');
const { createSellersService } = require('./service.cjs');
const FIELDS = ['name', 'price', 'active', 'sort_order'];
const validRecordId = id => typeof id === 'string' && /^rec[A-Za-z0-9]{14}$/.test(id);

function validateServiceFields(body, partial = false) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw new SellersError(400, 'INVALID_PAYLOAD');
  const keys = Object.keys(body);
  if (keys.some(key => !FIELDS.includes(key))) throw new SellersError(400, 'FORBIDDEN_FIELD');
  if (!keys.length || (!partial && FIELDS.some(key => !Object.hasOwn(body, key)))) throw new SellersError(400, 'INVALID_PAYLOAD');
  const fields = {};
  for (const key of keys) {
    const value = body[key];
    const valid = key === 'name' ? typeof value === 'string' && value.trim().length > 0
      : key === 'price' ? typeof value === 'string' && value.trim().length > 0
      : key === 'active' ? typeof value === 'boolean'
      : Number.isSafeInteger(value) && value >= 0;
    if (!valid) throw new SellersError(400, 'INVALID_FIELD');
    fields[key] = key === 'name' || key === 'price' ? value.trim() : value;
  }
  return fields;
}

function createSellerServicesService(base) {
  const { findUnique } = createSellersService(base);
  const owned = (record, sellerId) => Array.isArray(record.fields?.Seller)
    && record.fields.Seller.length === 1 && record.fields.Seller[0] === sellerId;
  const project = record => ({ id: record.id, name: record.fields.name,
    price: record.fields.price ?? 0, active: record.fields.active ?? false,
    sort_order: record.fields.sort_order ?? 0 });
  async function airtable(fn) {
    try {
      return await fn();
    } catch (error) {
      console.error("? AIRTABLE SERVICES ERROR:", {
        message: error?.message,
        statusCode: error?.statusCode,
        error: error?.error,
      });
      throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
    }
  }
  async function findOwned(id, seller) {
    if (!validRecordId(id)) throw new SellersError(400, 'INVALID_SERVICE_ID');

    let records;
    try {
      records = await base('Services').select({
        filterByFormula: `OR(RECORD_ID()="${id}")`,
      }).all();
    } catch (error) {
      console.error("? AIRTABLE SERVICES ERROR:", {
        message: error?.message,
        statusCode: error?.statusCode,
        error: error?.error,
      });
      throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
    }

    if (!records.length) throw new SellersError(404, 'SERVICE_NOT_FOUND');
    const record = records[0];
    if (record.id !== id || !owned(record, seller.id)) {
      throw new SellersError(403, 'FORBIDDEN');
    }

    return record;
  }
  return {
    async list(sellerId) {
      const seller = await findUnique(sellerId);
      const links = seller.fields['Services 2'] ?? [];
      if (!Array.isArray(links) || links.some(id => !validRecordId(id)) || new Set(links).size !== links.length) throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
      const ids = links, services = [];
      for (let i = 0; i < ids.length; i += 50) {
        const batch = ids.slice(i, i + 50);
        const records = await airtable(() => base('Services').select({
          filterByFormula: `OR(${batch.map(id => `RECORD_ID()="${id}"`).join(',')})`,
        }).all());
        for (const record of records) {
          if (batch.includes(record.id) && owned(record, seller.id)) services.push(project(record));
        }
      }
      return services.sort((a, b) => a.sort_order - b.sort_order || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    },
    async create(sellerId, fields) {
      const seller = await findUnique(sellerId);
      const record = await airtable(() => base('Services').create({ ...fields, Seller: [seller.id] }));
      if (!owned(record, seller.id)) throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
      return project(record);
    },
    async update(sellerId, id, fields) {
      const seller = await findUnique(sellerId);
      await findOwned(id, seller);
      const record = await airtable(() => base('Services').update(id, fields));
      if (record.id !== id || !owned(record, seller.id)) throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
      return project(record);
    },
    async remove(sellerId, id) {
      const seller = await findUnique(sellerId);
      await findOwned(id, seller);
      await airtable(() => base('Services').destroy(id));
    },
  };
}
module.exports = { createSellerServicesService, validateServiceFields };
