'use strict';
const { createHash, timingSafeEqual } = require('node:crypto');
const { readSellerConfigEnv } = require('../seller-config/env.cjs');
const { SellersError } = require('./errors.cjs');
const { issueActivationToken, verifyActivationToken, validSellerId } = require('./activation-token.cjs');
const { createSellersService, validateFields } = require('./service.cjs');
function registerSellersRoutes(app, { base, getAdminToken = () => readSellerConfigEnv().SELLER_CONFIG_ADMIN_TOKEN } = {}) {
  const service = createSellersService(base);
  const handle = fn => async (req, res) => {
    res.set('Cache-Control', 'no-store');
    res.set('X-Content-Type-Options', 'nosniff');
    try { await fn(req, res); }
    catch (error) { res.status(error instanceof SellersError ? error.status : 500).json({ ok: false, error: error instanceof SellersError ? error.code : 'INTERNAL_ERROR' }); }
  };
  app.post('/admin/seller-activation-token', handle(async (req, res) => {
    const expected = getAdminToken(), supplied = req.get('X-NovaPulse-Admin-Token');
    const digest = value => createHash('sha256').update(value).digest();
    if (typeof expected !== 'string' || !expected.trim() || typeof supplied !== 'string' || !timingSafeEqual(digest(expected), digest(supplied))) throw new SellersError(403, 'FORBIDDEN');
    const sellerId = req.body?.seller_id;
    if (!validSellerId(sellerId)) throw new SellersError(400, 'INVALID_SELLER_ID');
    await service.findUnique(sellerId);
    res.json({ ok: true, seller_id: sellerId, activation_token: issueActivationToken(sellerId), expires_in: 86400 });
  }));
  app.put('/sellers', handle(async (req, res) => {
    const match = /^Bearer ([A-Za-z0-9_.-]+)$/i.exec(req.get('Authorization') || '');
    if (!match) throw new SellersError(401, 'INVALID_TOKEN');
    const { seller_id: sellerId } = verifyActivationToken(match[1]);
    const fields = validateFields(req.body, sellerId);
    res.json(await service.update(sellerId, fields));
  }));
}
module.exports = { registerSellersRoutes };
