'use strict';
require('./support/offline.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createInvoiceBuilders } = require('../../billing/invoice-builders');
const { persistedInvoiceBuilder } = require('../../billing/facturx-build.cjs');

// Synthetic regression data, not a fiscal validation reference.
function setup() {
  const quote = { quote_id: 'DEV-test', total_ht: '1000', total_ttc: '1000',
    deposit_amount: '300', remaining_amount: '700', deposit_percent: '30', tva_percent: '0' };
  const deposit = { 'Quote ID': 'DEV-test', 'Payment Role': 'deposit', Status: 'Paid',
    'Invoice Number': 'NP-deposit', 'Amount Cents': 30000, 'Paid At': '2026-09-01T12:00:00Z',
    'Stripe Payment Intent ID': 'pi-deposit', 'Buyer Type': 'Particulier' };
  const config = { company: { name: 'Offline seller', vat_status: 'franchise_base', default_vat_rate: 0 } };
  const calls = [];
  const base = table => ({ select(options) {
    calls.push({table, options});
    return { async firstPage() { return [{ id: 'offline', fields: table === 'Quotes' ? quote : deposit }]; } };
  } });
  return { quote, deposit, config, base, calls,
    builders: createInvoiceBuilders({ base, getSellerConfig: async () => config }) };
}

test('bug9 28: deposit invoice stays deposit', async () => {
  const s = setup();
  const invoice = await s.builders.buildDepositInvoiceData(s.deposit, 'seller');
  assert.equal(invoice.invoice_type, 'deposit');
  assert.equal(invoice.totals.total_ttc, 300);
  assert.equal(invoice.source.quote_id, 'DEV-test');
});

test('bug9 29: balance uses the paid deposit invoice reference', async () => {
  const s = setup();
  const invoice = await persistedInvoiceBuilder(s.base)({ ...s.deposit,
    'Payment Role': 'balance', 'Amount Cents': 70000, 'Invoice Number': 'NP-balance' }, 'seller', s.config);
  assert.equal(invoice.invoice_type, 'balance');
  assert.equal(invoice.deposit_reference.invoice_number, 'NP-deposit');
  assert.equal(invoice.deposit_reference.amount, 300);
  assert.equal(invoice.totals.total_ttc, 700);
  assert.match(s.calls[1].options.filterByFormula, /\{Status\}='Paid'/);
});

test('bug9 30: wrong balance amount or missing deposit invoice is rejected', async () => {
  const s = setup();
  const fields = { ...s.deposit, 'Payment Role': 'balance', 'Amount Cents': 69999 };
  assert.equal(await s.builders.buildBalanceInvoiceData(fields, 'seller'), null);
  fields['Amount Cents'] = 70000;
  s.deposit['Invoice Number'] = '';
  assert.equal(await s.builders.buildBalanceInvoiceData(fields, 'seller'), null);
});

test('bug9 31: independent payment dispatches to normal without quote queries', async () => {
  const s = setup();
  const fields = { ...s.deposit, 'Quote ID': '', 'Payment Role': '', 'Amount Cents': 15000 };
  const invoice = await persistedInvoiceBuilder(s.base)(fields, 'seller', s.config);
  assert.equal(invoice.invoice_type, 'normal');
  assert.equal(s.calls.length, 0);
  assert.equal(await s.builders.buildBalanceInvoiceData(fields, 'seller'), null);
});
