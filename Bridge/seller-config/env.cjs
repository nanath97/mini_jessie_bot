'use strict';
const fs = require('node:fs');
const path = require('node:path');

function readSellerConfigEnv({ env = process.env, envPath = path.join(__dirname, '.env') } = {}) {
  let local = {};
  if (env.NODE_ENV !== 'production' && env.RENDER !== 'true') {
    try { local = require('dotenv').parse(fs.readFileSync(envPath)); }
    catch (error) {
      if (error.code !== 'ENOENT') throw new Error('Impossible de lire le fichier local seller-config/.env.');
    }
  }
  return {
    AIRTABLE_API_KEY: env.AIRTABLE_API_KEY ?? local.AIRTABLE_API_KEY,
    // Keep the existing local BASE_ID alias; production uses AIRTABLE_BASE_ID only.
    AIRTABLE_BASE_ID: env.AIRTABLE_BASE_ID ?? local.AIRTABLE_BASE_ID ?? local.BASE_ID,
    SELLER_CONFIG_ADMIN_TOKEN: env.SELLER_CONFIG_ADMIN_TOKEN ?? local.SELLER_CONFIG_ADMIN_TOKEN,
  };
}

module.exports = { readSellerConfigEnv };
