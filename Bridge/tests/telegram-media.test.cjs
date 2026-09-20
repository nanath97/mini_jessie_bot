'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { Readable } = require('node:stream');
const express = require('express');
const { createTelegramMedia } = require('../telegram-media.cjs');
const source = fs.readFileSync(require('node:path').join(__dirname, '../server.js'), 'utf8');
const token = 'secret-bot-token';
async function serve(t, handler, route) {
  const app = express(); app.get(route, handler);
  const server = app.listen(0, '127.0.0.1');
  await require('node:events').once(server, 'listening');
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  return `http://127.0.0.1:${server.address().port}`;
}
test('Telegram proxy: original bytes, Unicode filename, range, errors and forged references', async t => {
  let failure = '', calls = [];
  const axios = { async get(url, options) {
    calls.push({url, options});
    if (url.endsWith('/getFile')) {
      if (failure === 'getFile') throw new Error(token);
      return { data: { ok: failure !== 'missing', result: { file_path: 'documents/file.pdf' } } };
    }
    if (failure === 'download') throw new Error(token);
    return { status: failure === 'status' ? 404 : options.headers.Range ? 206 : 200,
      headers: { 'content-type': 'application/pdf' }, data: Readable.from(['PDF bytes']) };
  } };
  const proxy = createTelegramMedia({token, axios});
  const url = proxy.createUrl('file-id', 'contrat été.pdf', 'document');
  assert.ok(!url.includes(token)); assert.ok(!url.includes('file-id'));
  // Links remain valid across server restarts with the same credential.
  const base = await serve(t, createTelegramMedia({token, axios}).download, '/pwa/telegram-media/:reference');
  let response = await fetch(base + url);
  assert.equal(response.status, 200); assert.equal(await response.text(), 'PDF bytes');
  assert.ok(response.headers.get('content-disposition').includes("filename*=UTF-8''contrat%20%C3%A9t%C3%A9.pdf"));
  assert.equal(calls[0].options.params.file_id, 'file-id');
  assert.equal(calls[1].options.maxRedirects, 0);
  response = await fetch(base + proxy.createUrl('video-id', 'clip.mp4', 'video'), { headers: { Range: 'bytes=0-8' } });
  assert.equal(response.status, 206); assert.ok(response.headers.get('content-disposition').startsWith('inline;')); await response.text();
  response = await fetch(base + proxy.createUrl('photo-id', 'photo.jpg', 'photo'));
  assert.equal(response.status, 200); assert.ok(response.headers.get('content-disposition').startsWith('inline;')); await response.text();
  for (failure of ['getFile', 'missing', 'download', 'status']) {
    response = await fetch(base + url); assert.equal(response.status, 502);
    assert.ok(!(await response.text()).includes(token));
  }
  calls = [];
  response = await fetch(base + url.slice(0, -8) + 'AAAAAAAA');
  assert.equal(response.status, 404); assert.equal(calls.length, 0);
});
test('webhook emits and stores only internal URLs for document/photo/video; paywall is preserved', () => {
  const block = source.slice(source.indexOf('  // D) Telegram media'), source.indexOf('} // ← ferme le if(supergroup topic)'));
  const proxy = createTelegramMedia({token, axios: {}});
  for (const [type, media] of [['document', {file_id:'id',file_name:'original.pdf'}], ['video', {file_id:'vid',file_name:'clip.mp4'}], ['photo', [{file_id:'pic'}]]]) {
    for (const paywall of [false, true]) {
      const emitted = [], history = [];
      vm.runInNewContext(block, {
        isPaywallCommand: paywall, message: { [type]: media, caption: 'caption' }, room:'room', telegramMedia: proxy,
        io: { to() { return { emit(event, data) { assert.equal(event, 'admin_media'); emitted.push(data); } }; } },
        pushPwaHistory(room, data) { history.push(data); },
      });
      assert.equal(emitted.length, paywall ? 0 : 1);
      if (!paywall) {
        assert.equal(emitted[0].type, type); assert.equal(history[0].url, emitted[0].url);
        assert.ok(emitted[0].url.startsWith('/pwa/telegram-media/'));
        assert.ok(!JSON.stringify([emitted,history]).includes(token));
        assert.equal(emitted[0].fileName, type === 'photo' ? 'photo' : media.file_name);
      }
    }
  }
});
test('Cloudinary download works; unrelated URLs and hostname tricks remain forbidden', async t => {
  let handler, calls = 0;
  vm.runInNewContext(source.slice(source.indexOf('app.get("/pwa/download",'), source.indexOf('// PUSH SUBSCRIPTION')), {
    app: { get(path, fn) { handler = fn; } }, URL, console,
    axios: { async get(url, options) { calls++; assert.equal(options.maxRedirects, 0); return {
      status: 200, headers: { 'content-type': 'application/pdf' }, data: Readable.from(['cloud bytes']),
    }; } },
  });
  const base = await serve(t, handler, '/pwa/download');
  const response = await fetch(base + '/pwa/download?url=' + encodeURIComponent('https://res.cloudinary.com/demo/raw/file.pdf') + '&name=original.pdf');
  assert.equal(response.status, 200); assert.equal(await response.text(), 'cloud bytes');
  assert.ok(response.headers.get('content-disposition').includes('original.pdf'));
  for (const url of ['https://example.com/file', 'https://api.telegram.org/file/botsecret/file', 'https://evil.test/res.cloudinary.com/file', 'https://res.cloudinary.com.evil.test/file', 'http://res.cloudinary.com/file', 'https://user:pass@res.cloudinary.com/file']) {
    assert.equal((await fetch(base + '/pwa/download?url=' + encodeURIComponent(url))).status, 403);
  }
  assert.equal(calls, 1);
});
