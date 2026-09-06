'use strict';
const policy = require('../facturx-config-fixtures/seller-policy.json');
const privateContext = require('../facturx-config-fixtures/private-context.json');
function configuredFixture(input) {
  const b2b = input.scenario.startsWith('b2b-');
  return { config: { ...structuredClone(input.sellerConfig), ...(b2b ? structuredClone(policy) : {}) },
    context: b2b ? structuredClone(privateContext) : {} };
}
module.exports = { configuredFixture };
