const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../server.js'), 'utf8');
const start = source.indexOf('app.post("/pwa/send-simple-payment",');
const end = source.indexOf('\n});', start) + 4;
assert.ok(start >= 0 && end > start);

test('simple payment forwards human text, checkout and amount; empty text retains fallback', async () => {
  for (const text of ["Voici le paiement pour l'acompte", 'Réglé à réception, merci !', '', undefined]) {
    let handler, emitted, result;
    vm.runInNewContext(source.slice(start, end), {
      app: { post(path, fn) { handler = fn; } },
      pwaRoom(email, slug) {
        assert.equal(email, 'buyer@example.test'); assert.equal(slug, 'seller');
        return 'room';
      },
      io: { to(room) {
        assert.equal(room, 'room');
        return { emit(event, payload) {
          assert.equal(event, 'simple_payment_request'); emitted = payload;
        } };
      } },
      console: { log() {}, error() {} },
    });
    await handler({ body: { email: 'buyer@example.test', sellerSlug: 'seller', text,
      checkout_url: 'https://checkout.invalid', amount: 4990 } }, {
      json(data) { result = data; }, status(code) { assert.fail(`Unexpected status ${code}`); },
    });
    assert.equal(result.success, true);
    assert.equal(emitted.text, text || '💳 Paiement requis.');
    assert.equal(emitted.checkout_url, 'https://checkout.invalid');
    assert.equal(emitted.amount, 4990);
  }
});
