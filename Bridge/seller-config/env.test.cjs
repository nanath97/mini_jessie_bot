'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { readSellerConfigEnv } = require('./env.cjs');
function localFile(t, content) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'seller-config-env-'));
  const file = path.join(dir, '.env');
  if (content !== undefined) fs.writeFileSync(file, content);
  t.after(() => { if (fs.existsSync(file)) fs.unlinkSync(file); fs.rmdirSync(dir); });
  return file;
}
const values = { AIRTABLE_API_KEY: 'fake-key', AIRTABLE_BASE_ID: 'fake-base', SELLER_CONFIG_ADMIN_TOKEN: 'fake-token' };
const content = Object.entries(values).map(([k, v]) => k + '=' + v).join('\n');
test('local .env provides all three variables without mutating environment', t => {
  const env = {};
  assert.deepEqual(readSellerConfigEnv({ env, envPath: localFile(t, content) }), values);
  assert.deepEqual(env, {});
});
test('process.env alone works without any .env file', t => {
  for (const k of Object.keys(values)) { const original = process.env[k]; t.after(() => { if (original === undefined) delete process.env[k]; else process.env[k] = original; }); process.env[k] = values[k]; }
  assert.deepEqual(readSellerConfigEnv({ envPath: localFile(t) }), values);
});
test('process environment takes precedence over local file, including empty values', t => {
  assert.deepEqual(readSellerConfigEnv({ env: values, envPath: localFile(t, content.replaceAll('fake', 'local')) }), values);
  assert.equal(readSellerConfigEnv({ env: { SELLER_CONFIG_ADMIN_TOKEN: '' }, envPath: localFile(t, content) }).SELLER_CONFIG_ADMIN_TOKEN, '');
});
for (const production of [{ NODE_ENV: 'production' }, { RENDER: 'true' }]) test('production/Render never reads local file: ' + JSON.stringify(production), t => {
  const envPath = localFile(t, content);
  // A directory cannot be read as a dotenv file: success proves the read is skipped.
  assert.deepEqual(readSellerConfigEnv({ env: { ...production, ...values }, envPath: path.dirname(envPath) }), values);
  assert.deepEqual(readSellerConfigEnv({ env: production, envPath }), { AIRTABLE_API_KEY: undefined, AIRTABLE_BASE_ID: undefined, SELLER_CONFIG_ADMIN_TOKEN: undefined });
});
test('missing local .env is optional', t => {
  assert.deepEqual(readSellerConfigEnv({ env: {}, envPath: localFile(t) }), { AIRTABLE_API_KEY: undefined, AIRTABLE_BASE_ID: undefined, SELLER_CONFIG_ADMIN_TOKEN: undefined });
});
test('existing BASE_ID alias is local-only and canonical variable wins', t => {
  const envPath = localFile(t, 'BASE_ID=legacy-local');
  assert.equal(readSellerConfigEnv({ env: {}, envPath }).AIRTABLE_BASE_ID, 'legacy-local');
  assert.equal(readSellerConfigEnv({ env: { AIRTABLE_BASE_ID: 'canonical' }, envPath }).AIRTABLE_BASE_ID, 'canonical');
  assert.equal(readSellerConfigEnv({ env: { NODE_ENV: 'production', BASE_ID: 'legacy' }, envPath }).AIRTABLE_BASE_ID, undefined);
});
