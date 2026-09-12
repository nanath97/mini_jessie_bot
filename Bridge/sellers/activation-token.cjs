'use strict';
const { createHmac, timingSafeEqual } = require('node:crypto');
const { SellersError } = require('./errors.cjs');
const validSellerId = value => typeof value === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$/.test(value);
function signingKey() {
  const secret = process.env.SELLER_ACTIVATION_SECRET;
  if (typeof secret !== 'string' || Buffer.byteLength(secret) < 32) throw new SellersError(503, 'ACTIVATION_UNAVAILABLE');
  return secret;
}
function sign(payload, secret) { return createHmac('sha256', secret).update('v1.' + payload).digest(); }
function issueActivationToken(sellerId) {
  if (!validSellerId(sellerId)) throw new SellersError(400, 'INVALID_SELLER_ID');
  const payload = Buffer.from(JSON.stringify({ seller_id: sellerId, scope: 'seller_activation', exp: Math.floor(Date.now() / 1000) + 86400 })).toString('base64url');
  return 'v1.' + payload + '.' + sign(payload, signingKey()).toString('base64url');
}
function verifyActivationToken(token) {
  if (typeof token !== 'string' || token.length > 2048) throw new SellersError(401, 'INVALID_TOKEN');
  const parts = token.split('.');
  if (parts.length !== 3 || parts[0] !== 'v1' || !/^[A-Za-z0-9_-]+$/.test(parts[1]) || !/^[A-Za-z0-9_-]{43}$/.test(parts[2])) throw new SellersError(401, 'INVALID_TOKEN');
  const signature = Buffer.from(parts[2], 'base64url');
  const expected = sign(parts[1], signingKey());
  if (signature.length !== expected.length || !timingSafeEqual(signature, expected)) throw new SellersError(401, 'INVALID_TOKEN');
  let claims;
  try { claims = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8')); }
  catch { throw new SellersError(401, 'INVALID_TOKEN'); }
  if (!claims || !validSellerId(claims.seller_id) || !Number.isSafeInteger(claims.exp) || claims.exp <= Math.floor(Date.now() / 1000)) throw new SellersError(401, 'INVALID_TOKEN');
  if (claims.scope !== 'seller_activation') throw new SellersError(403, 'INVALID_SCOPE');
  return claims;
}
module.exports = { issueActivationToken, verifyActivationToken, validSellerId };
