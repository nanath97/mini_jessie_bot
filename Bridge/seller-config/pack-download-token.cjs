'use strict';
const { createHmac, timingSafeEqual } = require('node:crypto');
const EXPIRES_IN = 86400;
const validClientId = value => typeof value === 'string' && value.length === 17 && /^rec[A-Za-z0-9]{14}$/.test(value);
class PackLinkError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}
function signingKey() {
  const secret = process.env.SELLER_PACK_LINK_SECRET;
  if (typeof secret !== 'string' || !secret.trim() || Buffer.byteLength(secret) < 32) throw new PackLinkError(503, 'PACK_LINK_UNAVAILABLE');
  return secret;
}
const sign = (payload, secret) => createHmac('sha256', secret).update('v1.' + payload).digest();
function issuePackDownloadToken(pwaClientRecordId) {
  if (!validClientId(pwaClientRecordId)) throw new PackLinkError(400, 'INVALID_CLIENT_ID');
  const payload = Buffer.from(JSON.stringify({ pwa_client_record_id: pwaClientRecordId,
    exp: Math.floor(Date.now() / 1000) + EXPIRES_IN, scope: 'seller_pack_download' })).toString('base64url');
  return 'v1.' + payload + '.' + sign(payload, signingKey()).toString('base64url');
}
function verifyPackDownloadToken(token) {
  const secret = signingKey();
  if (typeof token !== 'string' || token.length > 2048) throw new PackLinkError(401, 'INVALID_TOKEN');
  const parts = token.split('.');
  if (parts.length !== 3 || parts[0] !== 'v1' || !/^[A-Za-z0-9_-]+$/.test(parts[1]) || !/^[A-Za-z0-9_-]{43}$/.test(parts[2])) throw new PackLinkError(401, 'INVALID_TOKEN');
  const signature = Buffer.from(parts[2], 'base64url');
  const expected = sign(parts[1], secret);
  if (signature.toString('base64url') !== parts[2] || signature.length !== expected.length || !timingSafeEqual(signature, expected)) throw new PackLinkError(401, 'INVALID_TOKEN');
  let claims;
  try { claims = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8')); } catch { throw new PackLinkError(401, 'INVALID_TOKEN'); }
  if (!claims || !validClientId(claims.pwa_client_record_id) || !Number.isSafeInteger(claims.exp) || claims.exp <= Math.floor(Date.now() / 1000)) throw new PackLinkError(401, 'INVALID_TOKEN');
  if (claims.scope !== 'seller_pack_download') throw new PackLinkError(403, 'INVALID_SCOPE');
  return claims;
}
module.exports = { issuePackDownloadToken, verifyPackDownloadToken, validClientId, PackLinkError, EXPIRES_IN };
