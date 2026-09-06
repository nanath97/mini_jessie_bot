'use strict';
require('../../Bridge/tests/billing/support/offline.cjs');
// Preserve builder diagnostics on stderr; stdout is the JSON transport only.
console.log = (...args) => console.error(...args);
const assert = require('node:assert/strict');
const { scenarios, loadFixture } = require('../../Bridge/tests/billing/support/fixture-loader.cjs');
const { runFixture } = require('../../Bridge/tests/billing/support/run-fixture.cjs');
const builders = require('../../Bridge/billing/invoice-builders.js');
(async () => {
  const outputs = {};
  for (const scenario of scenarios) {
    const fixture = loadFixture(scenario);
    assert.ok(fixture, 'Required historical fixture missing: ' + scenario);
    const invoice = await runFixture(builders, fixture.input);
    assert.deepStrictEqual(invoice, fixture.expectedInvoice);
    outputs[scenario] = { invoice, seller_config: fixture.input.sellerConfig };
  }
  process.stdout.write(JSON.stringify(outputs));
})().catch(error => { console.error(error); process.exitCode = 1; });
