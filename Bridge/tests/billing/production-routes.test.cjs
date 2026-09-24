'use strict';
require('./support/offline.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createInvoiceBuilders } = require('../../billing/invoice-builders');

// Inspect source without starting the production server or contacting Airtable.
const server = fs.readFileSync(path.resolve(__dirname, '../../server.js'), 'utf8');
const removedRoutes = [
  '/test-normal-invoice', '/test-normal-xml', '/test-deposit-invoice',
  '/test-paid-deposit', '/test-balance-invoice', '/test-balance-xml',
  '/test-deposit-xml',
];

test('SEC-009: removed billing test endpoints cannot be registered', () => {
  for (const route of removedRoutes) {
    assert.ok(!server.includes(route), `Forbidden billing endpoint: ${route}`);
  }
});

test('SEC-009: no replacement /test-* endpoint in the production Bridge', () => {
  // Ban the prefix anywhere, including route arrays, mounts and forwarding URLs.
  assert.ok(!server.includes('/test-'), 'Public test endpoints must stay out of production');
});

test('SEC-009: internal invoice builders remain available without HTTP test routes', () => {
  const unavailable = () => assert.fail('Unexpected external dependency');
  const builders = createInvoiceBuilders({ base: unavailable, getSellerConfig: unavailable });
  for (const name of [
    'buildNormalInvoiceData', 'buildDepositInvoiceData',
    'buildBalanceInvoiceData', 'findPaidDepositForQuote',
  ]) {
    assert.equal(typeof builders[name], 'function', name);
  }
});
