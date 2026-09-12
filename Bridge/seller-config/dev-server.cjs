'use strict';

// Development entry point only. Never import the Bridge server or its environment.
const express = require('express');
const { readSellerConfigEnv } = require('./env.cjs');
const { registerSellerConfigRoutes } = require('./routes.cjs');

// Explicitly read only the dedicated local file, regardless of shell variables.
const local = readSellerConfigEnv({ env: {} });
for (const key of ['AIRTABLE_API_KEY', 'AIRTABLE_BASE_ID', 'SELLER_CONFIG_ADMIN_TOKEN']) {
  if (typeof local[key] !== 'string' || !local[key].trim()) {
    process.stderr.write(`Variable requise dans seller-config/.env : ${key}\n`);
    process.exit(1);
  }
  process.env[key] = local[key];
}

const app = express();
registerSellerConfigRoutes(app);
const server = app.listen(10001, '127.0.0.1', () => {
  process.stdout.write('seller-config local : http://127.0.0.1:10001 (Ctrl+C pour arrêter)\n');
});
server.on('error', () => {
  process.stderr.write('Impossible de démarrer seller-config sur le port local 10001.\n');
  process.exitCode = 1;
});
