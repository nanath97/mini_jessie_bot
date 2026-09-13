'use strict';
const { createHash, timingSafeEqual } = require('node:crypto');
const express = require('express');
const { createSellerPackBuilder, SellerPackError } = require('./pack.cjs');
const { SellerConfigError } = require('./index.cjs');
const { ERRORS } = require('./routes.cjs');
const { PACK_ERRORS } = require('./pack-routes.cjs');
const { issuePackDownloadToken, verifyPackDownloadToken, validClientId, PackLinkError, EXPIRES_IN } = require('./pack-download-token.cjs');
const DOWNLOAD_BASE = 'https://mini-jessie-bot-1.onrender.com/seller-pack-download/';
function registerSellerPackLinkRoutes(app, { build = createSellerPackBuilder() } = {}) {
  const json = express.json({ limit: '1kb', strict: true });
  const handle = fn => async (req, res) => {
    res.set('Cache-Control', 'no-store');
    res.set('X-Content-Type-Options', 'nosniff');
    res.set('Referrer-Policy', 'no-referrer');
    try { await fn(req, res); } catch (error) {
      if (error instanceof PackLinkError) return res.status(error.status).json({ ok: false, error: error.code });
      const errors = error instanceof SellerConfigError ? ERRORS : error instanceof SellerPackError ? PACK_ERRORS : {};
      const known = Object.hasOwn(errors, error?.code);
      const [status, message] = known ? errors[error.code] : PACK_ERRORS.PACK_GENERATION_FAILED;
      return res.status(status).json({ error: known ? error.code : 'PACK_GENERATION_FAILED', message });
    }
  };
  app.post('/seller-pack-link', handle(async (req, res) => {
    const expected = process.env.SELLER_PACK_AUTOMATION_SECRET;
    if (typeof expected !== 'string' || !expected.trim() || Buffer.byteLength(expected) < 32) throw new PackLinkError(503, 'PACK_AUTOMATION_UNAVAILABLE');
    const supplied = req.get('X-NovaPulse-Automation-Token');
    const digest = value => createHash('sha256').update(value).digest();
    if (typeof supplied !== 'string' || !timingSafeEqual(digest(expected), digest(supplied))) throw new PackLinkError(403, 'FORBIDDEN');
    if (!req.is('application/json') || Object.keys(req.query).length) throw new PackLinkError(400, 'INVALID_PAYLOAD');
    await new Promise((resolve, reject) => json(req, res, error => error ? reject(new PackLinkError(400, 'INVALID_PAYLOAD')) : resolve()));
    const body = req.body;
    if (!body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).length !== 1 || !Object.hasOwn(body, 'pwaClientRecordId')) throw new PackLinkError(400, 'INVALID_PAYLOAD');
    if (!validClientId(body.pwaClientRecordId)) throw new PackLinkError(400, 'INVALID_CLIENT_ID');
    const token = issuePackDownloadToken(body.pwaClientRecordId);
    res.json({ ok: true, download_url: DOWNLOAD_BASE + token, expires_in: EXPIRES_IN });
  }));
  app.get('/seller-pack-download/:token', handle(async (req, res) => {
    const { pwa_client_record_id } = verifyPackDownloadToken(req.params.token);
    const zip = await build(pwa_client_record_id);
    res.status(200).set('Content-Disposition', 'attachment; filename="seller-pack.zip"').type('application/zip').send(zip);
  }));
}
module.exports = { registerSellerPackLinkRoutes };
