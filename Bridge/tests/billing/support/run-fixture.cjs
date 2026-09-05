'use strict';
const assert = require('node:assert/strict');
const { createFakeAirtable, invoiceExpectations } = require('./fake-airtable.cjs');
async function runFixture(api, input) {
  const airtable = createFakeAirtable(invoiceExpectations(input));
  let sellerCalls = 0;
  const builders = api.createInvoiceBuilders({
    base: airtable.base,
    async getSellerConfig(slug) {
      sellerCalls++;
      assert.equal(slug, input.sellerSlug);
      return structuredClone(input.sellerConfig);
    }
  });
  const role = input.scenario.split('-')[1];
  const name = { normal: 'buildNormalInvoiceData', deposit: 'buildDepositInvoiceData', balance: 'buildBalanceInvoiceData' }[role];
  const invoice = await builders[name](structuredClone(input.paymentFields), input.sellerSlug);
  assert.ok(invoice, 'Invoice builder failed');
  assert.equal(sellerCalls, 1);
  airtable.assertDone();
  return invoice;
}
module.exports = { runFixture };
