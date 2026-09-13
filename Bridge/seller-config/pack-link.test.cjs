'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { randomBytes, createHmac } = require('node:crypto');
const { once } = require('node:events');
const http = require('node:http');
const express = require('express');
const { issuePackDownloadToken, verifyPackDownloadToken } = require('./pack-download-token.cjs');
const { registerSellerPackLinkRoutes } = require('./pack-link-routes.cjs');
const { registerSellerPackRoutes } = require('./pack-routes.cjs');
const { SellerPackError } = require('./pack.cjs');
const { SellerConfigError } = require('./index.cjs');
const id = 'rec00000000000001';
test('temporary seller pack links: isolated secrets, strict payload, signed download (offline)', async t => {
  const keys = ['SELLER_PACK_LINK_SECRET', 'SELLER_PACK_AUTOMATION_SECRET'];
  const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]));
  const linkSecret = randomBytes(32).toString('hex'), automation = randomBytes(32).toString('hex'), admin = randomBytes(32).toString('hex');
  process.env.SELLER_PACK_LINK_SECRET = linkSecret; process.env.SELLER_PACK_AUTOMATION_SECRET = automation;
  t.after(() => { for (const key of keys) { if (previous[key] === undefined) delete process.env[key]; else process.env[key] = previous[key]; } });
  let builds = [], failure;
  const zip = Buffer.from('offline ZIP stub');
  const build = async client => { builds.push(client); if (failure) throw failure; return zip; };
  const app = express();
  registerSellerPackLinkRoutes(app, { build });
  registerSellerPackRoutes(app, { build, getAdminToken: () => admin });
  const listener = app.listen(0, '127.0.0.1'); await once(listener, 'listening');
  t.after(() => new Promise(resolve => { listener.close(resolve); listener.closeAllConnections(); }));
  const origin = 'http://127.0.0.1:' + listener.address().port;
  const post = (body = { pwaClientRecordId: id }, supplied = automation, extra = {}, suffix = '') => fetch(origin + '/seller-pack-link' + suffix, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...(supplied === null ? {} : { 'X-NovaPulse-Automation-Token': supplied }), ...extra }, body: JSON.stringify(body),
  });
  const get = (token, suffix = '') => fetch(origin + '/seller-pack-download/' + token + suffix);
  const signed = claims => { const payload = Buffer.from(JSON.stringify(claims)).toString('base64url'); return 'v1.' + payload + '.' + createHmac('sha256', linkSecret).update('v1.' + payload).digest('base64url'); };
  const claims = () => ({ pwa_client_record_id: id, exp: Math.floor(Date.now() / 1000) + 86400, scope: 'seller_pack_download' });
  async function checkError(response, status, code) {
    assert.equal(response.status, status); assert.equal(response.headers.get('content-disposition'), null);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    const text = await response.text();
    for (const secret of [linkSecret, automation, admin, 'PRIVATE']) assert.ok(!text.includes(secret));
    if (code) assert.equal(JSON.parse(text).error, code);
  }
  for (const supplied of [null, 'wrong', admin]) await t.test('creation rejects missing/wrong/admin credential ' + String(supplied).slice(0, 5), async () => {
    await checkError(await post(undefined, supplied), 403, 'FORBIDDEN'); assert.equal(builds.length, 0);
  });
  await t.test('missing automation configuration fails closed', async () => {
    delete process.env.SELLER_PACK_AUTOMATION_SECRET;
    await checkError(await post(), 503, 'PACK_AUTOMATION_UNAVAILABLE');
    process.env.SELLER_PACK_AUTOMATION_SECRET = automation;
  });
  for (const body of [null, [], {}, { pwaClientRecordId: id, seller_id: 'x' }, { pwaClientRecordId: id, sellerSlug: 'x' }, { pwaClientRecordId: id, url: 'https://evil.test' }, { pwaClientRecordId: id, extra: true }]) await t.test('strict creation payload ' + JSON.stringify(body), async () => {
    await checkError(await post(body), 400, 'INVALID_PAYLOAD'); assert.equal(builds.length, 0);
  });
  for (const value of ['bad', id + '\n', null, 42]) await t.test('invalid client ' + value, async () => { await checkError(await post({ pwaClientRecordId: value }), 400, 'INVALID_CLIENT_ID'); });
  await t.test('reject query parameters', async () => { await checkError(await post(undefined, automation, {}, '?baseUrl=https://evil.test'), 400, 'INVALID_PAYLOAD'); });
  await t.test('invalid JSON and oversized JSON sanitized after auth', async () => {
    for (const body of ['{bad', JSON.stringify({ pwaClientRecordId: 'x'.repeat(2000) })]) {
      const response = await fetch(origin + '/seller-pack-link', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-NovaPulse-Automation-Token': automation }, body });
      await checkError(response, 400, 'INVALID_PAYLOAD');
    }
    const response = await fetch(origin + '/seller-pack-link', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{bad' });
    await checkError(response, 403, 'FORBIDDEN');
  });
  let valid;
  await t.test('creation yields fixed HTTPS URL and exact 24h expiry; no build', async () => {
    const before = Math.floor(Date.now() / 1000);
    const response = await post(undefined, automation, { Host: 'evil.test', 'X-Forwarded-Host': 'evil.test', 'X-Forwarded-Proto': 'http' });
    assert.equal(response.status, 200); const data = await response.json();
    assert.deepEqual(Object.keys(data), ['ok', 'download_url', 'expires_in']);
    assert.equal(data.ok, true); assert.equal(data.expires_in, 86400);
    const url = new URL(data.download_url); assert.equal(url.origin, 'https://mini-jessie-bot-1.onrender.com');
    assert.ok(url.pathname.startsWith('/seller-pack-download/v1.')); valid = url.pathname.split('/').pop();
    const decoded = verifyPackDownloadToken(valid);
    assert.equal(decoded.pwa_client_record_id, id); assert.equal(decoded.scope, 'seller_pack_download');
    assert.ok(decoded.exp >= before + 86400 && decoded.exp <= Math.floor(Date.now() / 1000) + 86400);
    assert.deepEqual(Object.keys(decoded), ['pwa_client_record_id', 'exp', 'scope']); assert.equal(builds.length, 0);
    for (const secret of [linkSecret, automation, admin]) assert.ok(!data.download_url.includes(secret));
  });
  const invalidTokens = () => [
    ['malformed', 'invalid', 401], ['tampered', valid.slice(0, -5) + 'aaaaa', 401],
    ['expired', signed({ ...claims(), exp: Math.floor(Date.now() / 1000) - 1 }), 401],
    ['expiry boundary', signed({ ...claims(), exp: Math.floor(Date.now() / 1000) }), 401],
    ['scope', signed({ ...claims(), scope: 'seller_activation' }), 403],
    ['client', signed({ ...claims(), pwa_client_record_id: 'bad' }), 401],
  ];
  for (const [label, token, status] of invalidTokens()) await t.test('download refuses ' + label + ' before build', async () => {
    assert.throws(() => verifyPackDownloadToken(token));
    await checkError(await get(token), status); assert.equal(builds.length, 0);
  });
  await t.test('missing signing secret fails closed for issue and verify', async () => {
    delete process.env.SELLER_PACK_LINK_SECRET;
    assert.throws(() => issuePackDownloadToken(id), { code: 'PACK_LINK_UNAVAILABLE' });
    assert.throws(() => verifyPackDownloadToken(valid), { code: 'PACK_LINK_UNAVAILABLE' });
    await checkError(await post(), 503, 'PACK_LINK_UNAVAILABLE');
    await checkError(await get(valid), 503, 'PACK_LINK_UNAVAILABLE'); assert.equal(builds.length, 0);
    process.env.SELLER_PACK_LINK_SECRET = linkSecret;
  });
  await t.test('automation token cannot access admin route', async () => {
    const response = await fetch(origin + '/seller-pack/' + id, { headers: { 'X-NovaPulse-Admin-Token': automation, 'X-NovaPulse-Automation-Token': automation } });
    await checkError(response, 403, 'FORBIDDEN'); assert.equal(builds.length, 0);
  });
  await t.test('valid token downloads repeatedly, ignores query identity, preserves ZIP headers', async () => {
    for (let i = 0; i < 2; i++) {
      const response = await get(valid, '?pwaClientRecordId=rec00000000000002&seller_id=other&sellerSlug=other&url=https://evil.test');
      assert.equal(response.status, 200); assert.equal(response.headers.get('content-type'), 'application/zip');
      assert.equal(response.headers.get('content-disposition'), 'attachment; filename="seller-pack.zip"');
      assert.equal(response.headers.get('cache-control'), 'no-store'); assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
      assert.equal(response.headers.get('referrer-policy'), 'no-referrer');
      assert.deepEqual(Buffer.from(await response.arrayBuffer()), zip);
    }
    assert.deepEqual(builds, [id, id]);
  });
  await t.test('GET body cannot override verified client identity', async () => {
    const body = JSON.stringify({ pwaClientRecordId: 'rec00000000000002', seller_id: 'other' });
    const status = await new Promise((resolve, reject) => {
      const request = http.request(origin + '/seller-pack-download/' + valid, { method: 'GET', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } }, response => { response.resume(); response.on('end', () => resolve(response.statusCode)); });
      request.on('error', reject); request.end(body);
    });
    assert.equal(status, 200); assert.equal(builds.at(-1), id);
  });
  for (const error of [new Error('PRIVATE'), new SellerPackError('MEDIA_TIMEOUT'), new SellerConfigError('RECORD_NOT_FOUND', 'PRIVATE')]) await t.test('builder error sanitized ' + error.code, async () => {
    failure = error; await checkError(await get(valid), error.code === 'MEDIA_TIMEOUT' ? 504 : error.code === 'RECORD_NOT_FOUND' ? 404 : 500); failure = undefined;
  });
});
