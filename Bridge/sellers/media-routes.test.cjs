'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const { Writable } = require('node:stream');
const express = require('express');
const { issueActivationToken } = require('./activation-token.cjs');
const { registerSellerMediaRoutes } = require('./media-routes.cjs');
const { validateMedia, MEDIA } = require('./media-service.cjs');

test('seller media HTTP contracts and security (offline)', async t => {
  const prior = process.env.SELLER_ACTIVATION_SECRET;
  process.env.SELLER_ACTIVATION_SECRET = require('node:crypto').randomBytes(32).toString('hex');
  t.after(() => { if (prior === undefined) delete process.env.SELLER_ACTIVATION_SECRET; else process.env.SELLER_ACTIVATION_SECRET = prior; });
  const sellerId = 'sel_abc123', sellerRecordId = 'rec00000000000001', mediaId = 'rec00000000000002';
  const urls = { avatar: 'https://res.cloudinary.com/test/avatar', intro_video: 'https://res.cloudinary.com/test/intro_video', beta_video: 'https://res.cloudinary.com/test/beta_video' };
  let mode, seller, row, reads, writes, uploads;
  const reset = () => {
    mode = ''; reads = []; writes = []; uploads = [];
    seller = { id: sellerRecordId, fields: { Seller_id: sellerId, 'Seller Media': [] } };
    row = { id: mediaId, fields: { ...urls, Seller: [sellerRecordId], seller_label: 'private' } };
  };
  const fail = at => { if (mode === at) throw new Error('PRIVATE ' + process.env.SELLER_ACTIVATION_SECRET); };
  const base = table => {
    if (table === 'NovaPulse Sellers') return { select(options) {
      assert.deepEqual(options, { filterByFormula: `{Seller_id}="${sellerId}"`, maxRecords: 2 });
      return { async all() { reads.push('seller'); fail('seller'); return mode === 'missing' ? [] : [seller]; } };
    } };
    assert.equal(table, 'Seller Media');
    return {
      select(options) {
        assert.deepEqual(options, { filterByFormula: 'OR(RECORD_ID()="rec00000000000002")' });
        return { async all() {
          reads.push('media'); fail('read');
          return mode === 'dangling' ? [] : mode === 'multiple-results' ? [row, row] : [row];
        } };
      },
      async create(fields) { fail('create'); writes.push({ op: 'create', fields }); row = { id: mediaId, fields }; seller.fields['Seller Media'] = [mediaId]; return row; },
      async update(id, fields) { assert.equal(id, mediaId); fail('update'); writes.push({ op: 'update', fields }); row.fields = { ...row.fields, ...fields }; return row; },
    };
  };
  const cloudinary = { uploader: { upload_stream(options, done) {
    uploads.push(options);
    if (mode === 'cloud-throw') throw new Error('PRIVATE');
    return new Writable({ write(chunk, encoding, callback) { callback(mode === 'stream' ? new Error('PRIVATE') : null); }, final(callback) {
      if (mode === 'ownership-change') row.fields.Seller = ['rec00000000000003'];
      if (mode === 'cloud') done(new Error('PRIVATE'));
      else done(null, { secure_url: mode === 'bad-url' ? 'http://unsafe.test/a' : urls[options.public_id] });
      callback();
    } });
  } } };
  const app = express(); registerSellerMediaRoutes(app, { base, cloudinary });
  const server = app.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  const token = issueActivationToken(sellerId);
  function form({ omit, mime, size, extra, duplicate } = {}) {
    const data = new FormData();
    for (const [key, spec] of Object.entries(MEDIA)) {
      if (omit === key) continue;
      data.append(key, new Blob([Buffer.alloc(size?.[key] ?? 8)], { type: mime?.[key] ?? spec.types[0] }), key);
      if (duplicate === key) data.append(key, new Blob(['x'], { type: spec.types[0] }), key);
    }
    if (extra) data.append(extra, 'rec00000000000003');
    return data;
  }
  async function call(method, body, auth = token) {
    const response = await fetch(`http://127.0.0.1:${server.address().port}/seller-media`, {
      method, headers: auth === null ? {} : { Authorization: 'Bearer ' + auth }, ...(method === 'POST' ? { body: body ?? form() } : {}),
    });
    const text = await response.text();
    assert.ok(!text.includes('PRIVATE')); assert.ok(!text.includes(token)); assert.ok(!text.includes(process.env.SELLER_ACTIVATION_SECRET));
    assert.equal(response.headers.get('cache-control'), 'no-store');
    assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
    return { status: response.status, data: JSON.parse(text) };
  }
  const error = (status, code) => ({ status, data: { ok: false, error: code } });
  for (const method of ['GET', 'POST']) {
    for (const auth of [null, 'invalid', token.slice(0, -3) + 'xxx']) await t.test(method + ' absent/invalid token ' + String(auth).slice(0, 7), async () => {
      reset(); assert.deepEqual(await call(method, undefined, auth), error(401, 'INVALID_TOKEN')); assert.equal(reads.length, 0); assert.equal(uploads.length, 0);
    });
    for (const [scenario, status, code] of [['missing', 404, 'SELLER_NOT_FOUND'], ['seller', 502, 'AIRTABLE_UNAVAILABLE'], ['read', 502, 'AIRTABLE_UNAVAILABLE'], ['dangling', 502, 'AIRTABLE_UNAVAILABLE']]) await t.test(method + ' ' + scenario, async () => {
      reset(); mode = scenario; seller.fields['Seller Media'] = [mediaId];
      assert.deepEqual(await call(method), error(status, code)); assert.equal(uploads.length, 0); assert.equal(writes.length, 0);
    });
    for (const owners of [[], ['rec00000000000003'], [sellerRecordId, 'rec00000000000003']]) await t.test(method + ' rejects ownership ' + owners.length, async () => {
      reset(); seller.fields['Seller Media'] = [mediaId]; row.fields.Seller = owners;
      assert.deepEqual(await call(method), error(403, 'FORBIDDEN')); assert.equal(uploads.length, 0); assert.equal(writes.length, 0);
    });
    await t.test(method + ' multiple links', async () => {
      reset(); seller.fields['Seller Media'] = [mediaId, mediaId];
      assert.deepEqual(await call(method), error(409, 'MULTIPLE_SELLER_MEDIA')); assert.deepEqual(reads, ['seller']); assert.equal(uploads.length, 0);
    });
    await t.test(method + ' malformed link', async () => {
      reset(); seller.fields['Seller Media'] = ['invalid']; assert.deepEqual(await call(method), error(502, 'AIRTABLE_UNAVAILABLE')); assert.deepEqual(reads, ['seller']);
    });
    for (const scenario of ['multiple-results', 'wrong-record-id']) await t.test(method + ' rejects ' + scenario, async () => {
      reset(); mode = scenario; seller.fields['Seller Media'] = [mediaId];
      if (scenario === 'wrong-record-id') row.id = 'rec00000000000003';
      assert.deepEqual(await call(method), error(502, 'AIRTABLE_UNAVAILABLE'));
      assert.equal(uploads.length, 0); assert.equal(writes.length, 0);
    });
  }
  await t.test('GET select().all() uses exact OR(RECORD_ID()="rec00000000000002") formula', async () => {
    reset(); seller.fields['Seller Media'] = [mediaId];
    assert.deepEqual(await call('GET'), { status: 200, data: { ok: true, media: urls } });
    assert.deepEqual(reads, ['seller', 'media']);
  });
  await t.test('GET empty without media table scan', async () => { reset(); assert.deepEqual(await call('GET'), { status: 200, data: { ok: true, media: null } }); assert.deepEqual(reads, ['seller']); });
  await t.test('GET exact projection', async () => { reset(); seller.fields['Seller Media'] = [mediaId]; assert.deepEqual(await call('GET'), { status: 200, data: { ok: true, media: urls } }); });
  for (const key of Object.keys(MEDIA)) {
    await t.test('POST missing ' + key, async () => { reset(); assert.deepEqual(await call('POST', form({ omit: key })), error(400, 'MISSING_MEDIA')); assert.equal(uploads.length, 0); });
    await t.test('POST wrong MIME ' + key, async () => { reset(); assert.deepEqual(await call('POST', form({ mime: { [key]: 'text/plain' } })), error(400, 'INVALID_MEDIA')); assert.equal(uploads.length, 0); });
    await t.test('POST oversize ' + key, async () => { reset(); assert.deepEqual(await call('POST', form({ size: { [key]: MEDIA[key].max + 1 } })), error(400, 'INVALID_MEDIA')); assert.equal(uploads.length, 0); });
  }
  for (const key of ['seller_id', 'Seller_id', 'Seller', 'sellerRecordId', 'sellerSlug', 'email']) await t.test('POST rejects identity ' + key, async () => { reset(); assert.deepEqual(await call('POST', form({ extra: key })), error(400, 'INVALID_MEDIA')); assert.equal(uploads.length, 0); assert.equal(writes.length, 0); });
  await t.test('POST duplicate file', async () => { reset(); assert.deepEqual(await call('POST', form({ duplicate: 'avatar' })), error(400, 'INVALID_MEDIA')); assert.equal(uploads.length, 0); });
  for (const existing of [false, true]) await t.test('POST ' + (existing ? 'update' : 'create') + ' and stable Cloudinary paths', async () => {
    reset(); if (existing) seller.fields['Seller Media'] = [mediaId];
    assert.deepEqual(await call('POST'), { status: 200, data: { ok: true, media: urls } });
    assert.equal(writes.length, 1); assert.equal(writes[0].op, existing ? 'update' : 'create');
    assert.deepEqual(writes[0].fields, { ...urls, updated_at: writes[0].fields.updated_at, ...(existing ? {} : { Seller: [sellerRecordId] }) });
    assert.equal(new Date(writes[0].fields.updated_at).toISOString(), writes[0].fields.updated_at);
    assert.deepEqual(uploads, Object.entries(MEDIA).map(([key, spec]) => ({ folder: `novapulse_sellers/${sellerId}/`, public_id: key, resource_type: spec.resource, overwrite: true, invalidate: true })));
    assert.deepEqual(await call('GET'), { status: 200, data: { ok: true, media: urls } });
    assert.equal((await call('POST')).status, 200); assert.equal(writes[1].op, 'update');
  });
  for (const scenario of ['cloud', 'cloud-throw', 'stream', 'bad-url', 'create', 'update', 'ownership-change']) await t.test('POST failure ' + scenario, async () => {
    reset(); mode = scenario; if (['update', 'ownership-change'].includes(mode)) seller.fields['Seller Media'] = [mediaId];
    assert.deepEqual(await call('POST'), error(scenario === 'ownership-change' ? 403 : 502, scenario === 'ownership-change' ? 'FORBIDDEN' : ['create', 'update'].includes(mode) ? 'AIRTABLE_UNAVAILABLE' : 'CLOUDINARY_UNAVAILABLE'));
    assert.equal(writes.length, 0);
    mode = ''; row.fields.Seller = [sellerRecordId]; assert.equal((await call('POST')).status, 200, 'lock released after failure');
  });
});

test('validation accepts all allowed MIME types and inclusive size boundaries', () => {
  const files = Object.fromEntries(Object.entries(MEDIA).map(([key, spec]) => [key, [{ mimetype: spec.types[0], size: spec.max, buffer: Buffer.alloc(spec.max) }]]));
  for (const mimetype of MEDIA.avatar.types) { files.avatar[0].mimetype = mimetype; assert.doesNotThrow(() => validateMedia(files)); }
  files.avatar[0].size = 0; assert.throws(() => validateMedia(files), { code: 'INVALID_MEDIA' });
});
