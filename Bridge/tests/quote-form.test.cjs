const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '../quote.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function page() {
  function input(value = '') {
    const listeners = {};
    return { value, addEventListener(event, fn) { listeners[event] = fn; },
      type(value) { this.value = value; listeners.input(); } };
  }
  const rows = [];
  const elements = { tvaInput: input(), depositInput: input(), total: {},
    rows: { appendChild(row) { rows.push(row); } } };
  const requests = [];
  const context = vm.createContext({
    URLSearchParams, window: { location: { search: '?topic=123' } },
    document: {
      getElementById(id) { return elements[id]; },
      querySelectorAll(selector) { assert.equal(selector, '#rows tr'); return rows; },
      createElement(tag) {
        assert.equal(tag, 'tr');
        const inputs = [input(), input('1'), input('0')];
        return { inputs, children: [...inputs.map(i => ({ querySelector() { return i; } })), {}],
          querySelectorAll() { return inputs; } };
      },
    },
    async fetch(url, options) { requests.push({ url, ...options }); }, alert() {},
  });
  vm.runInContext(script, context);
  return { elements, rows, requests, context };
}

test('quote preview recalculates TTC deposit and remainder on price, quantity, VAT and deposit input', () => {
  const { elements: e, rows } = page();
  rows[0].inputs[2].type('1000');
  e.tvaInput.type('20');
  e.depositInput.type('30');
  assert.equal(e.total.innerText, 'HT : 1000.00 € | TVA : 200.00 € | TTC : 1200.00 €\nAcompte 30 % : 360.00 € | Reste à payer : 840.00 €');
  rows[0].inputs[1].type('2');
  assert.match(e.total.innerText, /Acompte 30 % : 720.00 € \| Reste à payer : 1680.00 €/);
  rows[0].inputs[2].type('500');
  assert.match(e.total.innerText, /Acompte 30 % : 360.00 € \| Reste à payer : 840.00 €/);
  e.tvaInput.type('10');
  assert.match(e.total.innerText, /Acompte 30 % : 330.00 € \| Reste à payer : 770.00 €/);
  e.depositInput.type('50');
  assert.match(e.total.innerText, /Acompte 50 % : 550.00 € \| Reste à payer : 550.00 €/);
});

test('empty, negative and excessive deposit percentages are bounded in the preview', () => {
  const { elements: e, rows } = page();
  rows[0].inputs[2].type('1000');
  e.tvaInput.type('20');
  for (const value of ['', '-10', '0']) {
    e.depositInput.type(value);
    assert.match(e.total.innerText, /Acompte 0 % : 0.00 € \| Reste à payer : 1200.00 €/);
  }
  for (const value of ['100', '150']) {
    e.depositInput.type(value);
    assert.match(e.total.innerText, /Acompte 100 % : 1200.00 € \| Reste à payer : 0.00 €/);
  }
});

test('multiple lines and fractional amounts retain two decimal places', () => {
  const { elements: e, rows, context } = page();
  rows[0].inputs[2].type('49.90');
  vm.runInContext('addRow()', context);
  rows[1].inputs[1].type('2');
  rows[1].inputs[2].type('10');
  e.tvaInput.type('20');
  e.depositInput.type('30');
  assert.equal(e.total.innerText, 'HT : 69.90 € | TVA : 13.98 € | TTC : 83.88 €\nAcompte 30 % : 25.16 € | Reste à payer : 58.72 €');
});

test('preview leaves the generate-quote payload unchanged, including raw input values', async () => {
  const { elements: e, rows, requests, context } = page();
  rows[0].inputs[0].value = 'Création';
  rows[0].inputs[2].type('1000');
  e.tvaInput.type('20');
  for (const deposit of ['30', '', '-10', '150']) {
    e.depositInput.type(deposit);
    await vm.runInContext('generate()', context);
    const request = requests.at(-1);
    assert.equal(request.url, '/generate-quote');
    assert.equal(request.method, 'POST');
    assert.deepEqual(JSON.parse(request.body), { topic: '123',
      items: [{ service: 'Création', qty: '1', price: '1000' }], tva: '20', deposit });
  }
});
