'use strict';
require('./support/offline.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { createInvoiceBuilders } = require('../../billing/invoice-builders');
const { createFakeAirtable, invoiceExpectations } = require('./support/fake-airtable.cjs');
const { scenarios, loadFixture } = require('./support/fixture-loader.cjs');
const provenance = require('./reference/provenance.json');
const digest = text => crypto.createHash('sha256').update(text).digest('hex');

test('all extracted function bodies match pre-extraction SHA-256', () => {
  const sources = ['../../billing/invoice-builders.js', '../../billing/ubl.js', './reference/legacy-billing.cjs'].map(p => fs.readFileSync(path.resolve(__dirname, p), 'utf8'));
  for (const [name, hash] of Object.entries(provenance.functions)) {
    for (const source of [sources[name.includes('Xml') ? 1 : 0], sources[2]]) {
      const body = source.match(new RegExp('^(?:async )?function ' + name + '\\b[\\s\\S]*?^}', 'm'));
      assert.ok(body, name);
      assert.equal(digest(body[0]), hash, name);
    }
  }
});

test('network is blocked for fetch and socket connections', () => {
  assert.throws(() => fetch('https://example.invalid'), /BILLING_OFFLINE/);
  assert.throws(() => require('node:https').get('https://example.invalid'), /BILLING_OFFLINE/);
  assert.throws(() => require('node:net').connect(443, 'example.invalid'), /BILLING_OFFLINE/);
});

test('fake Airtable enforces exact queries and returns isolated records', async () => {
  const expected = { table: 'Quotes', options: { maxRecords: 1 }, records: [{ id: 'unit-only', fields: {} }] };
  const fake = createFakeAirtable([expected]);
  const result = await fake.base('Quotes').select({ maxRecords: 1 }).firstPage();
  result[0].fields.modified = true;
  assert.deepStrictEqual(expected.records[0].fields, {});
  fake.assertDone();
  assert.throws(() => fake.base('Quotes').select({ maxRecords: 1 }), /Unexpected/);
  assert.throws(() => createFakeAirtable([expected]).base('Other').select({ maxRecords: 1 }));
  const vmOptions = require('node:vm').runInNewContext('({maxRecords: 1})');
  const vmFake = createFakeAirtable([expected]);
  await vmFake.base('Quotes').select(vmOptions).firstPage();
  vmFake.assertDone();
});

test('invalid payment roles retain null results without accessing dependencies', async t => {
  t.mock.method(console, 'error', () => {});
  let calls = 0;
  const unavailable = () => { calls++; throw new Error('Unexpected dependency'); };
  const api = createInvoiceBuilders({ base: unavailable, getSellerConfig: unavailable });
  assert.equal(await api.buildNormalInvoiceData({ 'Quote ID': 'unit-only' }, 'unit-only'), null);
  assert.equal(await api.buildDepositInvoiceData({}, 'unit-only'), null);
  assert.equal(await api.buildBalanceInvoiceData({}, 'unit-only'), null);
  assert.equal(await api.findPaidDepositForQuote(''), null);
  assert.equal(calls, 0);
});

test('seller failure preserves existing null result', async t => {
  t.mock.method(console, 'error', () => {});
  const api = createInvoiceBuilders({ base() { assert.fail('Unexpected Airtable call'); }, async getSellerConfig() { throw new Error('unit failure'); } });
  assert.equal(await api.buildNormalInvoiceData({}, 'unit-only'), null);
});

test('deposit lookup preserves exact Airtable formula and empty-result behavior', async t => {
  t.mock.method(console, 'log', () => {});
  const expectations = invoiceExpectations({ paymentFields: { 'Quote ID': 'unit-only', 'Payment Role': 'balance' }, quoteRecords: [], paidDepositRecords: [] });
  const fake = createFakeAirtable([expectations[1]]);
  const api = createInvoiceBuilders({ base: fake.base, getSellerConfig() { assert.fail('Unexpected seller lookup'); } });
  assert.equal(await api.findPaidDepositForQuote(' unit-only '), null);
  fake.assertDone();
});

test('Airtable errors retain existing null result', async t => {
  t.mock.method(console, 'error', () => {});
  const expectation = invoiceExpectations({ paymentFields: { 'Quote ID': 'unit-only', 'Payment Role': 'balance' }, quoteRecords: [], paidDepositRecords: [] })[1];
  expectation.error = 'unit failure';
  const fake = createFakeAirtable([expectation]);
  const api = createInvoiceBuilders({ base: fake.base, getSellerConfig() { assert.fail(); } });
  assert.equal(await api.findPaidDepositForQuote('unit-only'), null);
  fake.assertDone();
});

test('fixture loader never creates missing historical references', () => {
  for (const scenario of scenarios) {
    const dir = path.join(__dirname, 'fixtures', scenario);
    const before = fs.readdirSync(dir);
    loadFixture(scenario);
    assert.deepStrictEqual(fs.readdirSync(dir), before);
  }
});
