'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const express = require('express');
const { once } = require('node:events');
const { randomBytes } = require('node:crypto');
const { registerSellerConfigRoutes } = require('./routes.cjs');
const { createSellerConfigGenerator } = require('./index.cjs');
const id = n => 'rec' + String(n).padStart(14, '0');
const token = randomBytes(32).toString('hex');
function fixture() {
  const data = { 'PWA Clients': {}, 'NovaPulse Sellers': {}, Services: {} };
  for (const n of [1, 2]) {
    data['PWA Clients'][id(n)] = { id: id(n), fields: { 'NovaPulse Sellers': [id(n + 10)] } };
    data['NovaPulse Sellers'][id(n + 10)] = { id: id(n + 10), fields: { pwa_client: [id(n)], company_name: 'Seller ' + n, 'Services 2': [id(n + 20)] } };
    data.Services[id(n + 20)] = { id: id(n + 20), fields: { Seller: [id(n + 10)], active: true, name: 'Service ' + n, price: n } };
  }
  return data;
}
async function setup(t, { data = fixture(), configuredToken = token, fail, generate } = {}) {
  let reads = 0;
  const generator = createSellerConfigGenerator({ base: table => ({ async find(recordId) {
    reads++;
    if (fail) throw Object.assign(new Error('AIRTABLE_API_KEY=SECRET BASE_ID=SECRET'), { statusCode: fail });
    const record = data[table]?.[recordId];
    if (!record) throw Object.assign(new Error('secret URL'), { statusCode: 404 });
    return record;
  } }) });
  const app = express();
  registerSellerConfigRoutes(app, { generate: generate || generator.generateConfigForPwaClient, getAdminToken: () => configuredToken });
  const server = app.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  return { reads: () => reads, request: (recordId = id(1), supplied = token) => fetch('http://127.0.0.1:' + server.address().port + '/seller-config/' + recordId, {
    headers: supplied === null ? {} : { 'X-NovaPulse-Admin-Token': supplied },
  }) };
}
test('valid token: downloadable complete JSON, isolated between two sellers', async t => {
  const api = await setup(t);
  for (const n of [1, 2]) {
    const res = await api.request(id(n));
    assert.equal(res.status, 200);
    assert.equal(res.headers.get('content-disposition'), 'attachment; filename="config.json"');
    assert.match(res.headers.get('content-type'), /^application\/json/);
    assert.equal(res.headers.get('cache-control'), 'no-store');
    const c = await res.json();
    assert.equal(c.company.name, 'Seller ' + n);
    assert.deepEqual(c.services, [{ name: 'Service ' + n, price: String(n) }]);
    assert.equal(c.facturx.seller_electronic_address.scheme_id, '0225');
  }
});
for (const supplied of [null, 'incorrect']) test('missing/invalid token rejected before generation: ' + supplied, async t => {
  const api = await setup(t); const res = await api.request(id(1), supplied);
  assert.equal(res.status, 403); assert.equal(api.reads(), 0);
});
for (const configuredToken of [undefined, '', ' ']) test('unconfigured token fails closed: ' + String(configuredToken), async t => {
  const api = await setup(t, { configuredToken: configuredToken === undefined ? null : configuredToken });
  assert.equal((await api.request()).status, 403); assert.equal(api.reads(), 0);
});
test('nonexistent PWA Client returns 404', async t => {
  const api = await setup(t); assert.equal((await api.request(id(9))).status, 404);
});
test('missing seller link returns explicit 404', async t => {
  const data = fixture(); delete data['PWA Clients'][id(1)].fields['NovaPulse Sellers'];
  const api = await setup(t, { data }); const res = await api.request();
  assert.equal(res.status, 404); assert.equal((await res.json()).error, 'SELLER_NOT_FOUND');
});
test('multiple sellers return 409', async t => {
  const data = fixture(); data['PWA Clients'][id(1)].fields['NovaPulse Sellers'].push(id(12));
  const api = await setup(t, { data }); assert.equal((await api.request()).status, 409);
});
test('new seller without children still downloads successfully', async t => {
  const data = fixture(); delete data['NovaPulse Sellers'][id(11)].fields['Services 2'];
  const api = await setup(t, { data }); const res = await api.request(); assert.equal(res.status, 200);
  const c = await res.json(); assert.deepEqual(c.services, []); assert.deepEqual(c.digitalProducts, []); assert.equal(c.company.logo, '');
});
test('Airtable failure is a sanitized 502', async t => {
  const api = await setup(t, { fail: 403 }); const res = await api.request();
  assert.equal(res.status, 502); assert.equal(res.headers.get('content-disposition'), null);
  assert.doesNotMatch(await res.text(), /SECRET|BASE_ID|AIRTABLE_API_KEY/);
});
test('unexpected exception is a sanitized 500', async t => {
  const api = await setup(t, { generate: async () => { throw new Error(token); } });
  const res = await api.request(); assert.equal(res.status, 500); assert.ok(!(await res.text()).includes(token));
});
test('slug or email is rejected as invalid Record ID', async t => {
  const api = await setup(t);
  for (const value of ['seller-slug', 'client@example.com']) assert.equal((await api.request(value)).status, 400);
  assert.equal(api.reads(), 0);
});
test('foreign child cannot be downloaded', async t => {
  const data = fixture(); data.Services[id(21)].fields.Seller = [id(12)];
  const api = await setup(t, { data }); const res = await api.request(); assert.equal(res.status, 500);
  assert.doesNotMatch(await res.text(), /Service 1|Seller 2/);
});
