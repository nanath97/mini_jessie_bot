'use strict';

require('./support/offline.cjs');

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { scenarios, loadFixture } = require('./support/fixture-loader.cjs');
const { buildUblInvoiceXml } = require('../../billing/ubl');
const legacy = require('./reference/legacy-billing.cjs');

function applyHistoricalWhitespaceException(xml, scenario) {
  if (scenario !== 'b2b-normal' && scenario !== 'b2b-balance') {
    return xml;
  }

  const supplierStart = xml.indexOf('<cac:AccountingSupplierParty>');
  const supplierEnd = xml.indexOf('</cac:AccountingSupplierParty>');

  assert.ok(
    supplierStart !== -1 && supplierEnd !== -1,
    `${scenario}: seller block not found`
  );

  const before = xml.slice(0, supplierStart);
  const supplier = xml.slice(supplierStart, supplierEnd);
  const after = xml.slice(supplierEnd);

  const needle = '</cbc:EndpointID>\n    \n\n      ';
  const replacement = '</cbc:EndpointID>\n\n      ';
  const first = supplier.indexOf(needle);

  assert.ok(
    first !== -1,
    `${scenario}: expected exact 5-byte historical whitespace exception not found`
  );

  assert.equal(
    supplier.indexOf(needle, first + needle.length),
    -1,
    `${scenario}: historical whitespace exception must occur exactly once in seller block`
  );

  const normalizedSupplier =
    supplier.slice(0, first) +
    replacement +
    supplier.slice(first + needle.length);

  return before + normalizedSupplier + after;
}

for (const scenario of scenarios) {
  test(`historical UBL bytes: ${scenario}`, t => {
    const fixture = loadFixture(scenario);

    if (!fixture) {
      return t.skip('Historical inputs and validated outputs not supplied');
    }

    const currentXml = buildUblInvoiceXml(fixture.expectedInvoice);
    const legacyXml = legacy.buildUblInvoiceXml(fixture.expectedInvoice);

    assert.deepStrictEqual(
      Buffer.from(applyHistoricalWhitespaceException(currentXml, scenario), 'utf8'),
      fixture.expectedXml
    );

    assert.deepStrictEqual(
      Buffer.from(applyHistoricalWhitespaceException(legacyXml, scenario), 'utf8'),
      fixture.expectedXml
    );
  });
}

test('UBL missing invoice keeps its existing exception', () => {
  assert.throws(
    () => buildUblInvoiceXml(null),
    { message: 'Invoice data manquante' }
  );
});
