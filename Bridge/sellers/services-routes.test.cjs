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
      async destroy(id) { fail('destroy'); writes.push({ operation: 'destroy', id }); rows = rows.filter(row => row.id !== id); return { id, deleted: true }; },
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
  await t.test('production ID: HTTP GET -> DELETE returned ID -> GET empty', async () => {
    reset();
    const id = 'recyA3vKd9zkeEos0';
    assert.equal(/^rec[A-Za-z0-9]{14}$/.test(id), true);
    rows = [{ id, fields: { ...payload, name: 'Service test NovaPulse', price: '10 EUR', Seller: ['recSellerA0000000'] } }];
    const before = await call('GET');
    assert.equal(before.status, 200);
    assert.deepEqual(before.data.services, [{ id, name: 'Service test NovaPulse', price: '10 EUR', active: true, sort_order: 0 }]);
    assert.deepEqual(await call('DELETE', undefined, before.data.services[0].id), { status: 200, data: { ok: true } });
    assert.deepEqual(writes, [{ operation: 'destroy', id }]);
    assert.deepEqual(await call('GET'), { status: 200, data: { ok: true, services: [] } });
  });
  await t.test('installed Airtable SDK: compare GET and DELETE reads at transport boundary', async t => {
    const Airtable = require('airtable');
    const encode = require('airtable/lib/object_to_query_param_string');
    const sdk = new Airtable({ apiKey: 'local-test-only' }).base('app00000000000000');
    const id = 'recyA3vKd9zkeEos0', sellerId = 'recSellerA0000000';
    let stored, scenario, requests;
    // Keep the real SDK select/all/Record/destroy code; replace only network I/O.
    sdk('Services')._base.runAction = (method, path, params, body, done) => {
      requests.push({ method, path, params: { ...params }, body });
      if (path === '/NovaPulse%20Sellers') {
        return done(null, {}, { records: [{ id: sellerId, fields: { Seller_id: 'seller-a', 'Services 2': stored ? [id] : [] } }] });
      }
      if (method === 'get' && path === '/Services') {
        if (scenario === 'error') return done(Object.assign(new Error('PRIVATE DETAIL'), { statusCode: 403, error: 'NOT_AUTHORIZED' }));
        return done(null, {}, { records: stored ? [stored] : [] });
      }
      if (method === 'delete' && path === '/Services/' + id) {
        stored = undefined;
        return done(null, {}, { id, deleted: true });
      }
      return done(new Error('Unexpected SDK request'));
    };
    const sdkApp = express(); sdkApp.use(express.json()); registerSellerServicesRoutes(sdkApp, { base: sdk });
    const sdkServer = sdkApp.listen(0, '127.0.0.1'); await once(sdkServer, 'listening');
    t.after(() => new Promise(resolve => { sdkServer.close(resolve); sdkServer.closeAllConnections(); }));
    const request = async (method, suffix = '') => {
      const response = await fetch('http://127.0.0.1:' + sdkServer.address().port + '/seller-services' + suffix, { method, headers: { Authorization: 'Bearer ' + token } });
      const data = await response.json();
      assert.ok(!JSON.stringify(data).includes('PRIVATE DETAIL'));
      return { status: response.status, data };
    };
    const restore = () => {
      scenario = 'ok'; requests = [];
      stored = { id, fields: { name: 'Service test NovaPulse', price: '10 EUR', active: true, sort_order: 0, Seller: [sellerId] } };
    };
    restore();
    const before = await request('GET');
    assert.equal(before.status, 200);
    assert.equal(before.data.services[0].id, id);
    assert.deepEqual(await request('DELETE', '/' + before.data.services[0].id), { status: 200, data: { ok: true } });
    const reads = requests.filter(entry => entry.path === '/Services');
    assert.equal(reads.length, 2);
    assert.deepEqual(reads[0], reads[1]);
    assert.deepEqual(reads[0], { method: 'get', path: '/Services', params: { filterByFormula: 'OR(RECORD_ID()="recyA3vKd9zkeEos0")' }, body: null });
    assert.equal(new URLSearchParams(encode(reads[0].params)).get('filterByFormula'), reads[0].params.filterByFormula);
    assert.deepEqual(await request('GET'), { status: 200, data: { ok: true, services: [] } });
    for (const [label, expected] of [['foreign', 403], ['multiple', 403], ['missing', 404], ['unexpected', 403], ['error', 502]]) {
      await t.test('production ID ' + label, async () => {
        restore();
        if (label === 'foreign') stored.fields.Seller = ['recSellerB0000000'];
        if (label === 'multiple') stored.fields.Seller = [sellerId, sellerId];
        if (label === 'missing') stored = undefined;
        if (label === 'unexpected') stored.id = 'recOther000000000';
        if (label === 'error') scenario = 'error';
        const result = await request('DELETE', '/' + id);
        assert.deepEqual(result, { status: expected, data: { ok: false, error: expected === 404 ? 'SERVICE_NOT_FOUND' : expected === 502 ? 'AIRTABLE_UNAVAILABLE' : 'FORBIDDEN' } });
        assert.equal(requests.some(entry => entry.method === 'delete'), false);
      });
    }
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
