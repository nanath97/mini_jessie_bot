'use strict';
const { pipeline } = require('node:stream');
const { SellersError } = require('./errors.cjs');
const { createSellersService } = require('./service.cjs');
const MEDIA = Object.freeze({
  avatar: { types: ['image/png', 'image/jpeg', 'image/webp'], max: 2 * 1024 * 1024, resource: 'image' },
  intro_video: { types: ['video/mp4'], max: 50 * 1024 * 1024, resource: 'video' },
  beta_video: { types: ['video/mp4'], max: 50 * 1024 * 1024, resource: 'video' },
});
const validRecordId = id => typeof id === 'string' && /^rec[A-Za-z0-9]{14}$/.test(id);
const locks = new Map();
async function airtable(fn) {
  try { return await fn(); } catch { throw new SellersError(502, 'AIRTABLE_UNAVAILABLE'); }
}
function validateMedia(files) {
  if (Object.keys(files || {}).some(key => !Object.hasOwn(MEDIA, key))) throw new SellersError(400, 'INVALID_MEDIA');
  for (const [key, spec] of Object.entries(MEDIA)) {
    if (!files?.[key]?.length) throw new SellersError(400, 'MISSING_MEDIA');
    const [file] = files[key];
    if (files[key].length !== 1 || !spec.types.includes(file.mimetype) || !Buffer.isBuffer(file.buffer)
      || file.size !== file.buffer.length || file.size === 0 || file.size > spec.max) throw new SellersError(400, 'INVALID_MEDIA');
  }
}
function createSellerMediaService({ base, cloudinary, streamifier }) {
  // Sanitize upstream errors before the existing seller resolver logs them.
  const safeBase = table => ({ select: options => ({ all: () => airtable(() => base(table).select(options).all()) }) });
  const { findUnique } = createSellersService(safeBase);
  const owned = (record, seller) => Array.isArray(record.fields?.Seller)
    && record.fields.Seller.length === 1 && record.fields.Seller[0] === seller.id;
  const project = record => Object.fromEntries(Object.keys(MEDIA).map(key => {
    const value = record.fields[key] ?? '';
    if (typeof value !== 'string') throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
    return [key, value];
  }));
  async function resolve(sellerId) {
    const seller = await findUnique(sellerId);
    if (!validRecordId(seller.id)) throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
    const links = seller.fields['Seller Media'] ?? [];
    if (!Array.isArray(links) || links.some(id => !validRecordId(id))) throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
    if (links.length > 1) throw new SellersError(409, 'MULTIPLE_SELLER_MEDIA');
    if (!links.length) return { seller, record: null };
    const records = await airtable(() => base('Seller Media').select({
      filterByFormula: `OR(RECORD_ID()="${links[0]}")`,
    }).all());
    if (records.length !== 1) throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
    const [record] = records;
    if (!record || record.id !== links[0]) throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
    if (!owned(record, seller)) throw new SellersError(403, 'FORBIDDEN');
    return { seller, record };
  }
  function upload(sellerId, key, file) {
    return new Promise((resolve, reject) => {
      const fail = () => reject(new SellersError(502, 'CLOUDINARY_UNAVAILABLE'));
      try {
        const output = cloudinary.uploader.upload_stream({
          folder: `novapulse_sellers/${sellerId}/`, public_id: key,
          resource_type: MEDIA[key].resource, overwrite: true, invalidate: true,
        }, (error, result) => {
          if (error || typeof result?.secure_url !== 'string') return fail();
          try { if (new URL(result.secure_url).protocol !== 'https:') return fail(); } catch { return fail(); }
          resolve(result.secure_url);
        });
        pipeline(streamifier.createReadStream(file.buffer), output, error => { if (error) fail(); });
      } catch { fail(); }
    });
  }
  return {
    async get(sellerId) {
      const { record } = await resolve(sellerId);
      return record ? project(record) : null;
    },
    async save(sellerId, files) {
      validateMedia(files);
      if (locks.has(sellerId)) throw new SellersError(409, 'MEDIA_UPLOAD_IN_PROGRESS');
      locks.set(sellerId, true);
      try {
        const { seller, record } = await resolve(sellerId);
        const fields = {};
        for (const key of Object.keys(MEDIA)) fields[key] = await upload(sellerId, key, files[key][0]);
        fields.updated_at = new Date().toISOString();
        // Recheck ownership and reciprocal links after potentially long uploads.
        const latest = await resolve(sellerId);
        if (latest.seller.id !== seller.id || latest.record?.id !== record?.id) throw new SellersError(409, 'SELLER_MEDIA_CHANGED');
        const saved = await airtable(() => record
          ? base('Seller Media').update(record.id, fields)
          : base('Seller Media').create({ ...fields, Seller: [seller.id] }));
        if (!saved || !validRecordId(saved.id) || (record && saved.id !== record.id) || !owned(saved, seller)) throw new SellersError(502, 'AIRTABLE_UNAVAILABLE');
        return project(saved);
      } finally { locks.delete(sellerId); }
    },
  };
}
module.exports = { createSellerMediaService, validateMedia, MEDIA };
