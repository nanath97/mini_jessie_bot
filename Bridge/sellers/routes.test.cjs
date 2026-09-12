'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { randomBytes, createHmac } = require('node:crypto');
const { once } = require('node:events');
const express = require('express');
const { registerSellersRoutes } = require('./routes.cjs');
const { issueActivationToken } = require('./activation-token.cjs');
test('activation routes: authentication, validation and update-only isolation', async t => {
  const prior = process.env.SELLER_ACTIVATION_SECRET;
  process.env.SELLER_ACTIVATION_SECRET = randomBytes(32).toString('hex');
  t.after(() => { if (prior === undefined) delete process.env.SELLER_ACTIVATION_SECRET; else process.env.SELLER_ACTIVATION_SECRET = prior; });
  const admin = randomBytes(32).toString('hex'); let mode = 'ok', writes = [], reads = 0;
  const base = table => { assert.equal(table, 'NovaPulse Sellers'); return {
    select(options) { reads++; assert.deepEqual(options, { filterByFormula: '{Seller_id}="seller-a"', maxRecords: 2 }); return { async all() {
      if (mode === 'error') throw new Error('SECRET');
      const row = { id: 'recA', fields: { Seller_id: 'seller-a', activation_status: 'pending', config_generated: false } };
      if (mode === 'label-only' || mode === 'empty-id') {
        const other = { id: 'recOther', fields: { Seller_id: mode === 'empty-id' ? '' : 'seller-b', seller_label: 'seller-a', seller_id: 'seller-a' } };
        return [other].filter(record => record.fields.Seller_id === 'seller-a');
      }
      return mode === 'missing' ? [] : mode === 'duplicate' ? [row, { ...row, id: 'recB' }] : [row];
    } }; },
    async update(id, fields) { writes.push({ id, fields }); },
  }; }; // No create method exists in this fake.
  const app = express(); app.use(express.json()); registerSellersRoutes(app, { base, getAdminToken: () => admin });
  const server = app.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  const url = 'http://127.0.0.1:' + server.address().port;
  const call = (method, path, body, headers = {}) => fetch(url + path, { method, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
  const auth = () => ({ Authorization: 'Bearer ' + issueActivationToken('seller-a') });
  const payload = { company_name: 'A', email: 'a@example.com', country: 'FR', default_vat_rate: '20', calendly: 'https://calendly.com/seller-a/meeting' };
  const signed = claims => { const encoded = Buffer.from(JSON.stringify(claims)).toString('base64url'); return 'v1.' + encoded + '.' + createHmac('sha256', process.env.SELLER_ACTIVATION_SECRET).update('v1.' + encoded).digest('base64url'); };
  await t.test('wrong admin token: 403, no Airtable read', async () => { const before=reads; assert.equal((await call('POST','/admin/seller-activation-token',{seller_id:'seller-a'},{'X-NovaPulse-Admin-Token':'wrong'})).status,403); assert.equal(reads,before); });
  for (const [m,status] of [['missing',404],['label-only',404],['empty-id',404],['duplicate',409],['ok',200]]) await t.test('admin issue '+m,async()=>{mode=m;const res=await call('POST','/admin/seller-activation-token',{seller_id:'seller-a'},{'X-NovaPulse-Admin-Token':admin});assert.equal(res.status,status);if(status===200){const data=await res.json();assert.equal(data.expires_in,86400);assert.ok(data.activation_token.startsWith('v1.'));assert.equal(res.headers.get('cache-control'),'no-store');}assert.equal(writes.length,0);});
  for (const [label,headers,status] of [
    ['missing',{},401],['invalid',{Authorization:'Bearer invalid'},401],
    ['tampered',{Authorization:'Bearer '+issueActivationToken('seller-a').replace('v1.','v2.')},401],
    ['expired',{Authorization:'Bearer '+signed({seller_id:'seller-a',scope:'seller_activation',exp:1})},401],
    ['scope',{Authorization:'Bearer '+signed({seller_id:'seller-a',scope:'other',exp:Math.floor(Date.now()/1000)+100})},403],
  ]) await t.test('PUT token '+label,async()=>{assert.equal((await call('PUT','/sellers',payload,headers)).status,status);assert.equal(writes.length,0);});
  await t.test('contradictory seller_id: 403',async()=>{assert.equal((await call('PUT','/sellers',{...payload,seller_id:'seller-b'},auth())).status,403);});
  for (const [m,status] of [['missing',404],['label-only',404],['empty-id',404],['duplicate',409],['error',502]]) await t.test('PUT lookup '+m,async()=>{mode=m;const res=await call('PUT','/sellers',payload,auth());assert.equal(res.status,status);assert.ok(!(await res.text()).includes('SECRET'));assert.equal(writes.length,0);});
  mode='ok';
  await t.test('invalid payloads rejected',async()=>{for(const bad of [{...payload,email:'bad'},{...payload,country:''},{...payload,default_vat_rate:-1},{...payload,company_name:{}},{...payload,calendly:'javascript:alert(1)'},{...payload,activation_status:'active'},{...payload,config_generated:true},{...payload,pwa_client:['recB']}])assert.equal((await call('PUT','/sellers',bad,auth())).status,400);assert.equal(writes.length,0);});
  await t.test('identifier and relationship fields cannot be written', async () => {
    for (const field of ['Seller_id', 'seller_label', 'pwa_client', 'Seller Media', 'Services', 'Services 2', 'Digital Products', 'activation_status', 'config_generated']) {
      assert.equal((await call('PUT', '/sellers', { ...payload, [field]: 'forbidden' }, auth())).status, 400);
    }
    assert.equal(writes.length, 0);
  });
  await t.test('valid update only modifies whitelisted fields of token seller',async()=>{const res=await call('PUT','/sellers',payload,auth());assert.equal(res.status,200);assert.deepEqual(await res.json(),{ok:true,seller_id:'seller-a'});assert.deepEqual(writes,[{id:'recA',fields:{...payload,default_vat_rate:20}}]);});
  await t.test('missing signing secret fails closed',async()=>{delete process.env.SELLER_ACTIVATION_SECRET;assert.equal((await call('POST','/admin/seller-activation-token',{seller_id:'seller-a'},{'X-NovaPulse-Admin-Token':admin})).status,503);});
});
