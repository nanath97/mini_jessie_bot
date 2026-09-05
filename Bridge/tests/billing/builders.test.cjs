'use strict';
require('./support/offline.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { scenarios, loadFixture } = require('./support/fixture-loader.cjs');
const { runFixture } = require('./support/run-fixture.cjs');
const current = require('../../billing/invoice-builders');
const legacy = require('./reference/legacy-billing.cjs');

for (const scenario of scenarios) test(`historical invoice: ${scenario}`, async t => {
  const fixture = loadFixture(scenario);
  if (!fixture) return t.skip('Historical inputs and validated outputs not supplied');
  t.mock.timers.enable({ apis: ['Date'], now: Date.parse(fixture.input.now) });
  const before = await runFixture(legacy, fixture.input);
  const after = await runFixture(current, fixture.input);
  assert.deepStrictEqual(before, fixture.expectedInvoice);
  assert.deepStrictEqual(after, fixture.expectedInvoice);
  const expectedType = scenario.startsWith('b2b') ? 'Entreprise' : 'Particulier';
  assert.equal(after.buyer.type, expectedType);
});
