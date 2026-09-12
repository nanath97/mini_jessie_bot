'use strict';
const { SellersError } = require('./errors.cjs');
const { verifyClientSessionToken } = require('./client-session-token.cjs');
const { createActivationStartService } = require('./activation-start-service.cjs');
function registerActivationStartRoute(app, options) {
  const service = createActivationStartService(options);
  app.post('/seller-activation/start', async (req, res) => {
    res.set('Cache-Control', 'no-store');
    res.set('X-Content-Type-Options', 'nosniff');
    try {
      const match = /^Bearer ([A-Za-z0-9_.-]+)$/i.exec(req.get('Authorization') || '');
      if (!match) throw new SellersError(401, 'INVALID_CLIENT_TOKEN');
      const { pwa_client_record_id: clientId } = verifyClientSessionToken(match[1]);
      if (req.body !== undefined && (!req.body || typeof req.body !== 'object' || Array.isArray(req.body) || Object.keys(req.body).length)) throw new SellersError(400, 'BODY_NOT_ALLOWED');
      res.json(await service.start(clientId));
    } catch (error) {
      res.status(error instanceof SellersError ? error.status : 500).json({ ok: false, error: error instanceof SellersError ? error.code : 'INTERNAL_ERROR' });
    }
  });
}
module.exports = { registerActivationStartRoute };
