'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { once } = require('node:events');
const { Writable } = require('node:stream');
const express = require('express');
const MiB = 1024 * 1024;
const source = fs.readFileSync(path.join(__dirname, '../server.js'), 'utf8').replace(/\r/g, '');

// Exercise the production route without starting the bot, Airtable or background jobs.
function section(start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from);
  assert.ok(from >= 0 && to > from, 'production route markers must exist');
  return source.slice(from, to);
}

test('/upload-media multipart contracts (Cloudinary stubbed)', async t => {
  const app = express();
  const uploads = [];
  let cloudError = false;
  const context = {
    app, path, multer: require('multer'), streamifier: require('streamifier'),
    console: { log() {}, error() {} },
    cloudinary: { uploader: { upload_stream(options, done) {
      const item = { ...options, bytes: 0 }; uploads.push(item);
      return new Writable({
        write(chunk, encoding, callback) { item.bytes += chunk.length; callback(); },
        final(callback) {
          done(cloudError ? new Error('offline failure') : null, { secure_url: 'https://res.cloudinary.com/test/exact-url' });
          callback();
        },
      });
    } } },
  };
  vm.compileFunction(
    section('const MAX_MEDIA_SIZE =', '// ============================\n// PUSH CONFIGURATION') +
    section('app.post("/upload-media",', '// =======================\n// PERSISTENT HISTORY'),
    Object.keys(context),
  )(...Object.values(context));
  const server = app.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  async function call(name, mime, size = 16) {
    uploads.length = 0;
    const body = new FormData();
    if (name) body.append('file', new Blob([Buffer.alloc(size)], { type: mime }), name);
    const response = await fetch(`http://127.0.0.1:${server.address().port}/upload-media`, { method: 'POST', body });
    return { status: response.status, body: await response.json() };
  }
  const cases = [
    ['design.png', 'image/png', 'image', 21 * MiB],
    ['design.pdf', 'application/pdf', 'raw', 21 * MiB],
    ['design.svg', 'image/svg+xml', 'raw'],
    ['design.ai', 'application/postscript', 'raw'],
    ['design.eps', 'image/x-eps', 'raw'],
    ['design.psd', 'image/vnd.adobe.photoshop', 'raw'],
    ['design.zip', 'application/zip', 'raw'],
    ['clip.mp4', 'video/mp4', 'video'],
    ['design.JPG', 'application/octet-stream', 'image'],
    ['design.jpeg', 'image/jpeg', 'image'],
    ['unknown', 'image/png', 'image'],
    ['unknown', 'image/jpeg', 'image'],
    ['unknown', 'image/svg+xml', 'raw'],
    ['unknown', 'image/vnd.adobe.photoshop', 'raw'],
    ['unknown', 'application/postscript', 'raw'],
    ['misnamed.png', 'application/pdf', 'raw'],
    ['misnamed.jpg', 'application/zip', 'raw'],
    ['unknown', 'application/illustrator', 'raw'],
    ['unknown', 'video/quicktime', 'video'],
    ['legacy.doc', 'application/msword', 'raw'],
    ['legacy.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'raw'],
    ['legacy.gif', 'image/gif', 'image'],
    ['limit.pdf', 'application/pdf', 'raw', 50 * MiB],
    ['limit.mp4', 'video/mp4', 'video', 20 * MiB],
  ];
  for (const ext of ['pdf', 'svg', 'ai', 'eps', 'psd', 'zip']) {
    cases.push([`source.${ext.toUpperCase()}`, 'application/octet-stream', 'raw']);
    cases.push([`source.${ext}`, 'image/png', 'raw']);
  }
  for (const ext of ['mp4', 'mov', 'webm', 'm4v']) cases.push([`clip.${ext.toUpperCase()}`, 'application/octet-stream', 'video']);
  for (const [name, mime, resourceType, size = 16] of cases) {
    await t.test(`${name} / ${mime} / ${size} bytes -> ${resourceType}`, async () => {
      assert.deepEqual(await call(name, mime, size), { status: 200, body: {
        success: true, mediaUrl: 'https://res.cloudinary.com/test/exact-url', originalName: name, mimeType: mime, resourceType,
      } });
      assert.deepEqual(uploads, [{ folder: 'novapulse_media', resource_type: resourceType, bytes: size }]);
    });
  }
  for (const [name, mime, size, error] of [
    ['clip.mp4', 'video/mp4', 20 * MiB + 1, 'VIDEO_TOO_LARGE'],
    ['clip.MP4', 'application/octet-stream', 20 * MiB + 1, 'VIDEO_TOO_LARGE'],
    ['unknown', 'video/webm', 20 * MiB + 1, 'VIDEO_TOO_LARGE'],
    ['design.pdf', 'application/pdf', 50 * MiB + 1, 'FILE_TOO_LARGE'],
    ['clip.mp4', 'video/mp4', 78 * MiB, 'FILE_TOO_LARGE'],
  ]) await t.test(`${name} / ${mime} / ${size} bytes -> 413 ${error}`, async () => {
    assert.deepEqual(await call(name, mime, size), { status: 413, body: { success: false, error } });
    assert.equal(uploads.length, 0, 'rejected files never reach Cloudinary');
  });
  await t.test('missing file preserves 400 response', async () => {
    assert.deepEqual(await call(), { status: 400, body: { success: false, error: 'No file uploaded' } });
    assert.equal(uploads.length, 0);
  });
  await t.test('Cloudinary error preserves 500 response', async () => {
    cloudError = true;
    assert.deepEqual(await call('design.pdf', 'application/pdf'), { status: 500, body: { success: false, error: 'Cloudinary upload failed' } });
  });
});

test('/pwa/client-send-media preserves Telegram delivery', async t => {
  let handler;
  const calls = [];
  const forms = [];
  vm.runInNewContext(section('app.post("/pwa/client-send-media",', '// =======================\n// GENERATE QUOTE'), {
    app: { post(route, fn) { handler = fn; } },
    findTopicIdByEmailSlug: async () => 123, pwaRoom: () => 'room', pushPwaHistory() {},
    TELEGRAM_BOT_TOKEN: 'offline', STAFF_GROUP_ID: 'staff', Buffer,
    console: { log() {}, warn() {}, error() {} },
    axios: {
      async get(url, options) { calls.push({ method: 'get', url, options }); return { status: 200, data: Buffer.from('original bytes') }; },
      async post(url, data) { calls.push({ method: 'post', url, data }); },
    },
    FormData: class {
      append(...args) { forms.push(args); }
      getHeaders() { return { 'content-type': 'multipart/form-data' }; }
    },
  });
  for (const mediaType of ['photo', 'video', 'document']) await t.test(mediaType, async () => {
    calls.length = 0; forms.length = 0;
    let result;
    const mediaUrl = 'https://res.cloudinary.com/test/raw/exact-url';
    await handler({ body: { email: 'test@example.com', sellerSlug: 'test', mediaUrl, mediaType, fileName: 'design.psd' } }, {
      json(value) { result = value; }, status(code) { assert.fail(`unexpected status ${code}`); },
    });
    assert.equal(result.success, true);
    if (mediaType === 'document') {
      assert.equal(calls[0].url, mediaUrl);
      assert.equal(calls[0].options.responseType, 'arraybuffer');
      assert.equal(calls[1].url, 'https://api.telegram.org/botoffline/sendDocument');
      const document = forms.find(([key]) => key === 'document');
      assert.equal(document[1].toString(), 'original bytes');
      assert.equal(document[2].filename, 'design.psd');
    } else {
      assert.equal(calls.length, 1);
      assert.equal(calls[0].url, `https://api.telegram.org/botoffline/${mediaType === 'video' ? 'sendVideo' : 'sendPhoto'}`);
      assert.equal(calls[0].data[mediaType], mediaUrl);
    }
  });
});
