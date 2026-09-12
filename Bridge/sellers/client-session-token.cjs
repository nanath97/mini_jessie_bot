'use strict';
const { createHmac, timingSafeEqual } = require('node:crypto');
const { SellersError } = require('./errors.cjs');
const validClientId = value => typeof value === 'string' && /^rec[A-Za-z0-9]{14}$/.test(value);
function secret() {
  const value = process.env.PWA_CLIENT_SESSION_SECRET;
  if (typeof value !== 'string' || Buffer.byteLength(value) < 32) throw new SellersError(503, 'CLIENT_SESSION_UNAVAILABLE');
  return value;
}
const signature = payload => createHmac('sha256', secret()).update('v1.' + payload).digest();
function issueClientSessionToken(recordId) {
  if (!validClientId(recordId)) throw new SellersError(500, 'INVALID_VERIFIED_CLIENT');
  const payload = Buffer.from(JSON.stringify({ pwa_client_record_id: recordId, scope: 'pwa_client_session', exp: Math.floor(Date.now() / 1000) + 86400 })).toString('base64url');
  return 'v1.' + payload + '.' + signature(payload).toString('base64url');
}
function verifyClientSessionToken(token) {
  if (typeof token !== 'string' || token.length > 2048) throw new SellersError(401, 'INVALID_CLIENT_TOKEN');
  const parts = token.split('.');
  if (parts.length !== 3 || parts[0] !== 'v1' || !/^[A-Za-z0-9_-]+$/.test(parts[1]) || !/^[A-Za-z0-9_-]{43}$/.test(parts[2])) throw new SellersError(401, 'INVALID_CLIENT_TOKEN');
  const actual = Buffer.from(parts[2], 'base64url'), expected = signature(parts[1]);
  if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) throw new SellersError(401, 'INVALID_CLIENT_TOKEN');
  let claims;
  try { claims = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8')); }
  catch { throw new SellersError(401, 'INVALID_CLIENT_TOKEN'); }
  if (!claims || !validClientId(claims.pwa_client_record_id) || !Number.isSafeInteger(claims.exp) || claims.exp <= Math.floor(Date.now() / 1000)) throw new SellersError(401, 'INVALID_CLIENT_TOKEN');
  if (claims.scope !== 'pwa_client_session') throw new SellersError(403, 'INVALID_CLIENT_SCOPE');
  return claims;
}
module.exports = { issueClientSessionToken, verifyClientSessionToken, validClientId };
