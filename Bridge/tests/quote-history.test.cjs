const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../server.js'), 'utf8');
const start = source.indexOf('app.get("/pwa/history",');
const end = source.indexOf('\n});', start) + 4;
assert.ok(start > 0 && end > start);
const record = (id, status = 'pending') => ({fields: {quote_id: id, status, pdf_url: id + '.pdf', created_at: '2026-09-20T12:00:00Z'}});
async function history(quotes, memory) {
  let handler, result;
  vm.runInNewContext(source.slice(start, end), {
    app: {get(path, fn) { handler = fn; }},
    normEmail: s => s, normSlug: s => s, pwaRoom: () => 'room', missedCounts: {},
    console: {log() {}, error() {}}, pwaHistoryStore: {room: memory},
    tableMessages: {select: () => ({all: async () => []})},
    tablePaymentLinks: {select: () => ({firstPage: async () => []})},
    base(name) { assert.equal(name, 'Quotes'); return {select: () => ({all: async () => quotes})}; },
  });
  await handler({query: {email: 'client@example.com', sellerSlug: 'ceo', topicId: '1'}}, {
    json(data) { result = data; }, status(code) { assert.fail('Unexpected status ' + code); },
  });
  assert.equal(result.success, true);
  return result.history;
}

test('Quotes is canonical despite legacy memory copies, including accepted status', async () => {
  const items = await history([record('q1', 'accepted')], [
    {isQuote: true, quoteId: 'q1', quoteStatus: 'pending'},
    {quoteId: 'q1'}, {isQuote: true},
  ]);
  assert.equal(items.length, 1);
  assert.equal(items[0].quoteId, 'q1'); assert.equal(items[0].isQuote, true);
  assert.equal(items[0].quoteStatus, 'accepted'); assert.equal(items[0].url, 'q1.pdf');
});

test('different quotes and repeated ordinary media remain in history', async () => {
  const normal = {mediaType: 'document', url: 'q1.pdf', fileName: 'quote.pdf', ts: Date.now()};
  const items = await history([record('q1'), record('q2')], [normal, normal]);
  assert.equal(items.length, 4);
  assert.equal(items.filter(m => m.isQuote).length, 2);
  assert.equal(items.filter(m => !m.isQuote).length, 2);
});

test('creation still emits quote metadata without writing another memory copy', () => {
  const start = source.indexOf('io.to(room).emit("admin_media",{', source.indexOf('app.post("/generate-quote"'));
  const end = source.indexOf('console.log("📄 Quote sent to PWA:', start);
  assert.ok(start > 0 && end > start);
  const emitted = [];
  vm.runInNewContext(source.slice(start, end), {
    room: 'room', quoteId: 'q1', quoteUrl: 'q1.pdf',
    io: {to: () => ({emit(event, data) { assert.equal(event, 'admin_media'); emitted.push(data); }})},
    pushPwaHistory() { assert.fail('Quotes must not be stored in memory'); },
  });
  assert.equal(emitted.length, 1); assert.equal(emitted[0].quoteId, 'q1');
  assert.equal(emitted[0].isQuote, true); assert.equal(emitted[0].quoteStatus, 'pending');
});
