'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const express = require('express');
const { createSellerPackBuilder, LIMITS } = require('./pack.cjs');
const { registerSellerPackRoutes } = require('./pack-routes.cjs');
const { SellerConfigError } = require('./index.cjs');
const id = 'rec00000000000001';
const token = 'offline-admin-token';
const jpeg = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 0xff, 0xd9]);
const mp4 = Buffer.from([0, 0, 0, 16, 0x66, 0x74, 0x79, 0x70, 0x69, 0x73, 0x6f, 0x6d, 0, 0, 0, 0]);
function fixture() {
  return { config: { company: { name: 'Seller', logo: 'https://res.cloudinary.com/demo/image/upload/v1/avatar.png' }, services: [], digitalProducts: [] }, media: {
    avatar: 'https://res.cloudinary.com/demo/image/upload/v1/avatar.png',
    intro_video: 'https://res.cloudinary.com/demo/video/upload/v1/intro.mp4',
    beta_video: 'https://res.cloudinary.com/demo/video/upload/v1/beta.mp4',
  } };
}
function setupBuilder({ result = fixture(), fail, limits = LIMITS, generate } = {}) {
  const reads = [], downloads = [];
  const build = createSellerPackBuilder({ limits, generate: async clientId => {
    reads.push(clientId); if (generate) return generate(clientId); return result;
  }, fetchMedia: async (url, options) => {
    downloads.push({ url, options });
    assert.equal(options.redirect, 'error'); assert.ok(options.signal instanceof AbortSignal);
    if (fail === 'network') throw new Error('SECRET credentials');
    if (fail === 'timeout') return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('SECRET abort')), { once: true }));
    if (fail === 'headers-size') return new Response(jpeg, { headers: { 'content-type': 'image/jpeg', 'content-length': String(limits.avatar + 1) } });
    if (fail === 'body-timeout') return new Response(new ReadableStream({ pull() { return new Promise(() => {}); } }), { headers: { 'content-type': 'image/jpeg' } });
    const avatar = url.includes('/image/upload/');
    const bytes = fail === 'empty' ? Buffer.alloc(0) : fail === 'signature' ? Buffer.from('not media') : avatar ? jpeg : mp4;
    return new Response(bytes, { status: fail === 'status' ? 404 : fail === 'redirect' ? 302 : 200,
      headers: { 'content-type': fail === 'mime' ? 'text/html' : avatar ? 'image/jpeg' : 'video/mp4' } });
  } });
  return { build, reads, downloads, result };
}
// Independently read the standard ZIP central directory and local STORE entries.
function unzip(bytes) {
  const end = bytes.length - 22;
  assert.equal(bytes.readUInt32LE(end), 0x06054b50);
  const count = bytes.readUInt16LE(end + 10);
  let cursor = bytes.readUInt32LE(end + 16);
  const files = {};
  for (let i = 0; i < count; i++) {
    assert.equal(bytes.readUInt32LE(cursor), 0x02014b50);
    assert.equal(bytes.readUInt16LE(cursor + 10), 0);
    const size = bytes.readUInt32LE(cursor + 24);
    const nameLength = bytes.readUInt16LE(cursor + 28), extraLength = bytes.readUInt16LE(cursor + 30), commentLength = bytes.readUInt16LE(cursor + 32);
    const name = bytes.toString('utf8', cursor + 46, cursor + 46 + nameLength);
    const local = bytes.readUInt32LE(cursor + 42);
    assert.equal(bytes.readUInt32LE(local), 0x04034b50);
    const start = local + 30 + bytes.readUInt16LE(local + 26) + bytes.readUInt16LE(local + 28);
    files[name] = bytes.subarray(start, start + size);
    assert.equal(require('buffer-crc32').unsigned(files[name]), bytes.readUInt32LE(cursor + 16));
    cursor += 46 + nameLength + extraLength + commentLength;
  }
  return files;
}
async function server(t, options = {}) {
  const builder = setupBuilder(options);
  const app = express();
  registerSellerPackRoutes(app, { build: builder.build, getAdminToken: () => Object.hasOwn(options, 'configured') ? options.configured : token });
  const listener = app.listen(0, '127.0.0.1'); await once(listener, 'listening');
  t.after(() => new Promise(resolve => { listener.close(resolve); listener.closeAllConnections(); }));
  return { ...builder, request: (suffix = id, supplied = token) => fetch(`http://127.0.0.1:${listener.address().port}/seller-pack/${suffix}`, {
    headers: supplied === null ? {} : { 'X-NovaPulse-Admin-Token': supplied },
  }) };
}
test('ZIP has exactly config.json, JPEG avatar and both videos; source result unchanged', async t => {
  const api = await server(t); const original = structuredClone(api.result);
  const response = await api.request(id + '?avatar=http://127.0.0.1&intro_video=https://evil.test&sellerSlug=other');
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('content-disposition'), 'attachment; filename="seller-pack.zip"');
  assert.equal(response.headers.get('content-type'), 'application/zip');
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  const files = unzip(Buffer.from(await response.arrayBuffer()));
  assert.deepEqual(Object.keys(files), ['seller-pack/config.json', 'seller-pack/avatar.jpg', 'seller-pack/Intro.mp4', 'seller-pack/beta-video.mp4']);
  assert.deepEqual(JSON.parse(files['seller-pack/config.json']), original.config);
  assert.deepEqual(files['seller-pack/avatar.jpg'], jpeg);
  assert.deepEqual(files['seller-pack/Intro.mp4'], mp4);
  assert.deepEqual(files['seller-pack/beta-video.mp4'], mp4);
  assert.deepEqual(api.result, original);
  assert.deepEqual(api.reads, [id]);
  assert.deepEqual(api.downloads.map(x => x.url), [original.media.avatar.replace('/image/upload/', '/image/upload/f_jpg/'), original.media.intro_video, original.media.beta_video]);
});
for (const supplied of [null, 'wrong']) test('auth before generation/download: ' + supplied, async t => {
  const api = await server(t); assert.equal((await api.request(id, supplied)).status, 403);
  assert.deepEqual(api.reads, []); assert.deepEqual(api.downloads, []);
});
for (const configured of [undefined, '', ' ']) test('missing configured admin secret fails closed: ' + String(configured), async t => {
  const api = await server(t, { configured }); assert.equal((await api.request()).status, 403); assert.deepEqual(api.reads, []);
});
test('invalid client before generator or network', async t => {
  const api = await server(t); assert.equal((await api.request('seller-slug')).status, 400); assert.deepEqual(api.reads, []); assert.deepEqual(api.downloads, []);
});
for (const [fail, code, status] of [['network', 'MEDIA_DOWNLOAD_FAILED', 502], ['status', 'MEDIA_DOWNLOAD_FAILED', 502], ['redirect', 'MEDIA_DOWNLOAD_FAILED', 502], ['mime', 'INVALID_MEDIA_CONTENT', 502], ['signature', 'INVALID_MEDIA_CONTENT', 502], ['empty', 'INVALID_MEDIA_CONTENT', 502], ['headers-size', 'MEDIA_TOO_LARGE', 502], ['timeout', 'MEDIA_TIMEOUT', 504], ['body-timeout', 'MEDIA_TIMEOUT', 504]]) {
  test('sanitized download failure: ' + fail, async t => {
    const api = await server(t, { fail, limits: { ...LIMITS, timeoutMs: 30 } });
    const response = await api.request(); assert.equal(response.status, status);
    assert.equal(response.headers.get('content-disposition'), null);
    const data = await response.json(); assert.equal(data.error, code); assert.doesNotMatch(JSON.stringify(data), /SECRET|cloudinary|credentials/);
  });
}
for (const [field, value] of [['avatar', 'http://res.cloudinary.com/demo/image/upload/a'], ['avatar', 'https://127.0.0.1/a'], ['intro_video', 'https://res.cloudinary.com.evil.test/demo/video/upload/a'], ['beta_video', 'https://user:pass@res.cloudinary.com/demo/video/upload/a'], ['beta_video', 'https://res.cloudinary.com:444/demo/video/upload/a'], ['beta_video', 'https://res.cloudinary.com/demo/video/fetch/https://evil.test'], ['beta_video', '']]) test('reject unsafe media URL before any download: ' + field + value, async () => {
  const result = fixture(); result.media[field] = value;
  const api = setupBuilder({ result }); await assert.rejects(api.build(id), { code: 'INVALID_MEDIA_URL' }); assert.deepEqual(api.downloads, []);
});
test('stream size is enforced without Content-Length, including videos', async () => {
  for (const limits of [{ ...LIMITS, avatar: jpeg.length - 1 }, { ...LIMITS, video: mp4.length - 1 }]) {
    await assert.rejects(setupBuilder({ limits }).build(id), { code: 'MEDIA_TOO_LARGE' });
  }
});
test('inclusive size boundaries are accepted', async () => {
  const api = setupBuilder({ limits: { ...LIMITS, avatar: jpeg.length, video: mp4.length } });
  assert.equal(Object.keys(unzip(await api.build(id))).length, 4);
});
test('configuration and ZIP have independent size caps', async () => {
  const api = setupBuilder({ limits: { ...LIMITS, config: 1 } });
  await assert.rejects(api.build(id), { code: 'PACK_TOO_LARGE' }); assert.deepEqual(api.downloads, []);
  await assert.rejects(setupBuilder({ limits: { ...LIMITS, zip: 1 } }).build(id), { code: 'PACK_GENERATION_FAILED' });
});
for (const error of [new SellerConfigError('AIRTABLE_ERROR', 'SECRET'), new Error('SECRET')]) test('generator failures remain JSON and never download: ' + error.name, async t => {
  const api = await server(t, { generate: async () => { throw error; } });
  const response = await api.request(); assert.equal(response.status, error instanceof SellerConfigError ? 502 : 500);
  assert.equal(response.headers.get('content-disposition'), null); assert.doesNotMatch(await response.text(), /SECRET/); assert.deepEqual(api.downloads, []);
});
test('one build at a time and lock released on success', async () => {
  let release;
  const api = setupBuilder({ generate: () => new Promise(resolve => { release = resolve; }) });
  const first = api.build(id); await assert.rejects(api.build(id), { code: 'PACK_BUSY' });
  release(fixture()); await first;
  const next = api.build(id); release(fixture()); await next;
});
test('lock released after failure', async () => {
  let calls = 0;
  const api = setupBuilder({ generate: async () => { if (++calls === 1) throw new Error('failure'); return fixture(); } });
  await assert.rejects(api.build(id)); assert.equal(Object.keys(unzip(await api.build(id))).length, 4);
});
