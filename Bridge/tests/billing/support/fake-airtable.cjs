'use strict';
const assert = require('node:assert/strict');

// Exact ordered expectations: no formula interpretation or permissive fallback.
function createFakeAirtable(expectations = []) {
  const pending = structuredClone(expectations);
  const calls = [];
  function base(table) {
    return {
      select(options) {
        const expected = pending.shift();
        calls.push({ table, options: structuredClone(options) });
        assert.ok(expected, `Unexpected Airtable request: ${table}`);
        assert.equal(table, expected.table);
        assert.deepStrictEqual(calls[calls.length - 1].options, expected.options);
        return {
          async firstPage() {
            if (expected.error) throw new Error(expected.error);
            return structuredClone(expected.records);
          }
        };
      }
    };
  }
  return {
    base,
    calls,
    assertDone() { assert.equal(pending.length, 0, 'Unused Airtable expectations'); }
  };
}

function invoiceExpectations(input) {
  const quoteId = String(input.paymentFields['Quote ID'] || '').trim();
  const role = String(input.paymentFields['Payment Role'] || '').trim();
  if (!quoteId) return [];
  const expectations = [{
    table: 'Quotes',
    options: { filterByFormula: `{quote_id}='${quoteId}'`, maxRecords: 1 },
    records: input.quoteRecords
  }];
  if (role === 'balance') expectations.push({
    table: 'Payment Links',
    options: {
      filterByFormula: `AND(
          {Quote ID}='${quoteId}',
          {Payment Role}='deposit',
          {Status}='Paid'
        )`,
      maxRecords: 1
    },
    records: input.paidDepositRecords
  });
  return expectations;
}
module.exports = { createFakeAirtable, invoiceExpectations };
