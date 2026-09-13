'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const { randomBytes } = require('node:crypto');
const express = require('express');
const { issueActivationToken } = require('./activation-token.cjs');
const { registerSellerServicesRoutes } = require('./services-routes.cjs');

test('seller services CRUD security', async t => {
  const prior = process.env.SELLER_ACTIVATION_SECRET;
  process.env.SELLER_ACTIVATION_SECRET = randomBytes(32).toString('hex');
  t.after(() => { if (prior === undefined) delete process.env.SELLER_ACTIVATION_SECRET; else process.env.SELLER_ACTIVATION_SECRET = prior; });
  const payload = { name: 'Consultation', price: '20 EUR', active: true, sort_order: 0 };
  let mode, rows, writes, reads;
  const reset = () => {
    mode = 'ok'; writes = []; reads = 0;
    rows = [
      { id: 'recZ0000000000000', fields: { ...payload, Seller: ['recSellerA0000000'], sort_order: 2 } },
      { id: 'recB0000000000000', fields: { ...payload, Seller: ['recSellerA0000000'], active: false } },
      { id: 'recA0000000000000', fields: { ...payload, Seller: ['recSellerA0000000'] } },
      { id: 'recOther000000000', fields: { ...payload, Seller: ['recSellerB0000000'] } },
      { id: 'recMulti000000000', fields: { ...payload, Seller: ['recSellerA0000000', 'recSellerB0000000'] } },
      { id: 'recNone0000000000', fields: { ...payload } },
    ];
  };
  reset();
  const fail = operation => { if (mode === operation) throw new Error('AIRTABLE PRIVATE DETAIL ' + process.env.SELLER_ACTIVATION_SECRET); };
  const base = table => {
    if (table === 'NovaPulse Sellers') return { select(options) {
      reads++;
      assert.deepEqual(options, { filterByFormula: '{Seller_id}="seller-a"', maxRecords: 2 });
      return { async all() {
        fail('seller');
        const seller = { id: 'recSellerA0000000', fields: { Seller_id: 'seller-a', 'Services 2': rows.map(row => row.id) } };
        return mode === 'missing' ? [] : mode === 'duplicate' ? [seller, seller] : [seller];
      } };
    } };
    assert.equal(table, 'Services');
    return {
      select(options) {
        reads++; assert.ok(options.filterByFormula);
        const ids = [...options.filterByFormula.matchAll(/RECORD_ID\(\)="(rec[A-Za-z0-9]+)"/g)].map(match => match[1]);
        assert.ok(ids.length);
        assert.equal(options.filterByFormula, `OR(${ids.map(id => `RECORD_ID()="${id}"`).join(',')})`);
        return { async all() { fail('read'); return rows.filter(row => ids.includes(row.id)); } };
      },
      async create(fields) { fail('create'); writes.push({ operation: 'create', fields }); return { id: 'recNew00000000000', fields }; },
      async update(id, fields) { fail('update'); writes.push({ operation: 'update', id, fields }); const row = rows.find(row => row.id === id); row.fields = { ...row.fields, ...fields }; return row; },
      async destroy(id) { fail('destroy'); writes.push({ operation: 'destroy', id }); return { id, deleted: true }; },
    };
  };
  const app = express(); app.use(express.json()); registerSellerServicesRoutes(app, { base });
  const server = app.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  const token = issueActivationToken('seller-a');
  const call = async (method, body, id = '', auth = token) => {
    const response = await fetch('http://127.0.0.1:' + server.address().port + '/seller-services' + (id ? '/' + id : ''), {
      method, headers: { 'Content-Type': 'application/json', ...(auth === null ? {} : { Authorization: 'Bearer ' + auth }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const text = await response.text();
    assert.ok(!text.includes(process.env.SELLER_ACTIVATION_SECRET));
    assert.ok(!text.includes('PRIVATE DETAIL'));
    assert.equal(response.headers.get('cache-control'), 'no-store');
    return { status: response.status, data: JSON.parse(text) };
  };
  for (const method of ['GET', 'POST', 'PUT', 'DELETE']) {
    for (const auth of [null, 'invalid', token.slice(0, -2) + 'xx']) await t.test(method + ' rejects missing/invalid token ' + String(auth).slice(0, 8), async () => {
      reset(); assert.equal((await call(method, method === 'POST' || method === 'PUT' ? payload : undefined, method === 'PUT' || method === 'DELETE' ? 'recA0000000000000' : '', auth)).status, 401);
      assert.equal(reads, 0); assert.equal(writes.length, 0);
    });
    for (const [failure, status] of [['missing', 404], ['duplicate', 409], ['seller', 502]]) await t.test(method + ' seller ' + failure, async () => {
      reset(); mode = failure;
      assert.equal((await call(method, method === 'POST' || method === 'PUT' ? payload : undefined, method === 'PUT' || method === 'DELETE' ? 'recA0000000000000' : '')).status, status);
      assert.equal(writes.length, 0);
    });
  }
  await t.test('GET isolates ownership and sorts by order then ID, preserving inactive', async () => {
    reset(); const result = await call('GET'); assert.equal(result.status, 200);
    assert.deepEqual(result.data, { ok: true, services: [
      { id: 'recA0000000000000', ...payload }, { id: 'recB0000000000000', ...payload, active: false }, { id: 'recZ0000000000000', ...payload, sort_order: 2 },
    ] });
  });
  await t.test('empty reciprocal links never queries Services', async () => {
    reset(); rows = []; assert.deepEqual((await call('GET')).data, { ok: true, services: [] }); assert.equal(reads, 1);
  });
  await t.test('duplicate Services 2 links fail before querying Services', async () => {
    reset(); rows.push(rows[0]);
    const result = await call('GET');
    assert.equal(result.status, 502);
    assert.deepEqual(result.data, { ok: false, error: 'AIRTABLE_UNAVAILABLE' });
    assert.equal(reads, 1);
    assert.equal(writes.length, 0);
  });
  for (const method of ['POST', 'PUT']) {
    await t.test(method + ' invalid payloads and forbidden fields', async () => {
      reset();
      const invalid = [null, [], {}, { ...payload, name: ' ' }, { ...payload, price: '' }, { ...payload, price: '   ' }, { ...payload, price: 2 }, { ...payload, active: 1 }, { ...payload, sort_order: -1 }, { ...payload, sort_order: 1.2 }];
      for (const key of ['Seller_id', 'seller_id', 'sellerRecordId', 'Seller', 'pwa_client', 'Services 2', 'unexpected']) invalid.push({ ...payload, [key]: 'recOther000000000' });
      for (const body of invalid) assert.equal((await call(method, body, method === 'PUT' ? 'recA0000000000000' : '')).status, 400);
      assert.equal(writes.length, 0);
    });
  }
  await t.test('POST requires complete payload and links token seller automatically', async () => {
    reset(); assert.equal((await call('POST', { name: 'Only' })).status, 400);
    const result = await call('POST', { ...payload, active: false });
    assert.equal(result.status, 200); assert.deepEqual(result.data, { ok: true, service: { id: 'recNew00000000000', ...payload, active: false } });
    assert.deepEqual(writes, [{ operation: 'create', fields: { ...payload, active: false, Seller: ['recSellerA0000000'] } }]);
  });
  for (const method of ['PUT', 'DELETE']) {
    for (const id of ['recOther000000000', 'recMulti000000000', 'recNone0000000000']) await t.test(method + ' denies ownership ' + id, async () => {
      reset(); assert.equal((await call(method, method === 'PUT' ? payload : undefined, id)).status, 403); assert.equal(writes.length, 0);
    });
    await t.test(method + ' missing service', async () => { reset(); assert.equal((await call(method, method === 'PUT' ? payload : undefined, 'recMissing0000000')).status, 404); assert.equal(writes.length, 0); });
  }
  await t.test('PUT partial update retains fields and supports active false/true', async () => {
    reset();
    for (const active of [false, true]) {
      const result = await call('PUT', { active }, 'recA0000000000000'); assert.equal(result.status, 200);
      assert.deepEqual(result.data, { ok: true, service: { id: 'recA0000000000000', ...payload, active } });
    }
    assert.deepEqual(writes.map(write => write.fields), [{ active: false }, { active: true }]);
  });
  await t.test('DELETE own service and reject supplied identity', async () => {
    reset(); assert.equal((await call('DELETE', { Seller: ['recSellerB0000000'] }, 'recA0000000000000')).status, 400);
    assert.equal(writes.length, 0); assert.deepEqual((await call('DELETE', undefined, 'recA0000000000000')).data, { ok: true });
    assert.deepEqual(writes, [{ operation: 'destroy', id: 'recA0000000000000' }]);
  });
  for (const [failure, method, id] of [['read', 'GET', ''], ['read', 'PUT', 'recA0000000000000'], ['read', 'DELETE', 'recA0000000000000'], ['create', 'POST', ''], ['update', 'PUT', 'recA0000000000000'], ['destroy', 'DELETE', 'recA0000000000000']]) await t.test('sanitized Airtable failure ' + failure + method, async () => {
    reset(); mode = failure; const result = await call(method, method === 'POST' || method === 'PUT' ? payload : undefined, id);
    assert.equal(result.status, 502); assert.deepEqual(result.data, { ok: false, error: 'AIRTABLE_UNAVAILABLE' }); assert.equal(writes.length, 0);
  });
});
