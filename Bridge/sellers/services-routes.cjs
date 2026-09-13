'use strict';
const { verifyActivationToken } = require('./activation-token.cjs');
const { SellersError } = require('./errors.cjs');
const { createSellerServicesService, validateServiceFields } = require('./services-service.cjs');

function registerSellerServicesRoutes(app, { base } = {}) {
  const service = createSellerServicesService(base);
  // Handle JSON parser failures forwarded by the existing global body parser,
  // exclusively for these endpoints (before Express's default HTML handler).
  app.use(/^\/seller-services(?:\/[^/]+)?\/?$/, (error, req, res, next) => {
    res.set('Cache-Control', 'no-store');
    res.set('X-Content-Type-Options', 'nosniff');
    res.status(error.type === 'entity.too.large' ? 413 : 400)
      .json({ ok: false, error: 'INVALID_PAYLOAD' });
  });
  const handle = fn => async (req, res) => {
    res.set('Cache-Control', 'no-store');
    res.set('X-Content-Type-Options', 'nosniff');
    try {
      const match = /^Bearer ([A-Za-z0-9_.-]+)$/i.exec(req.get('Authorization') || '');
      if (!match) throw new SellersError(401, 'INVALID_TOKEN');
      const { seller_id } = verifyActivationToken(match[1]);
      await fn(req, res, seller_id);
    } catch (error) {
      res.status(error instanceof SellersError ? error.status : 500)
        .json({ ok: false, error: error instanceof SellersError ? error.code : 'INTERNAL_ERROR' });
    }
  };
  app.get('/seller-services', handle(async (req, res, sellerId) => {
    res.json({ ok: true, services: await service.list(sellerId) });
  }));
  app.post('/seller-services', handle(async (req, res, sellerId) => {
    res.json({ ok: true, service: await service.create(sellerId, validateServiceFields(req.body)) });
  }));
  app.put('/seller-services/:id', handle(async (req, res, sellerId) => {
    res.json({ ok: true, service: await service.update(sellerId, req.params.id, validateServiceFields(req.body, true)) });
  }));
  app.delete('/seller-services/:id', handle(async (req, res, sellerId) => {
    if (req.body !== undefined && (!req.body || typeof req.body !== 'object' || Array.isArray(req.body) || Object.keys(req.body).length)) throw new SellersError(400, 'INVALID_PAYLOAD');
    await service.remove(sellerId, req.params.id);
    res.json({ ok: true });
  }));
}
module.exports = { registerSellerServicesRoutes };
