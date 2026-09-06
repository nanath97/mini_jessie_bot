'use strict';
const { createInvoiceBuilders } = require('./invoice-builders');

// All quote/deposit queries and calculations remain in the original builders.
function persistedInvoiceBuilder(base) {
  return async (fields, sellerSlug, config) => {
    const builders = createInvoiceBuilders({ base, getSellerConfig: async () => config });
    const role = fields['Payment Role'] || '';
    const name = { '': 'buildNormalInvoiceData', deposit: 'buildDepositInvoiceData', balance: 'buildBalanceInvoiceData' }[role];
    if (!name) throw new Error('Unsupported persisted payment role');
    return builders[name](fields, sellerSlug);
  };
}
module.exports = { persistedInvoiceBuilder };
