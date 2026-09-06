'use strict';
const crypto = require('node:crypto');

// Service-to-service/admin only. This credential must never be exposed to PWA clients.
function registerFacturxRoutes(app, { service, token }) {
  function authorize(req, res, next) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    if (!token || token.length < 32) return res.status(503).json({ error: 'Factur-X unavailable' });
    const actual = crypto.createHash('sha256').update(String(req.headers.authorization || '')).digest();
    const expected = crypto.createHash('sha256').update('Bearer ' + token).digest();
    if (!crypto.timingSafeEqual(actual, expected)) return res.status(401).json({ error: 'Unauthorized' });
    next();
  }
  app.post('/internal/facturx', authorize, (req, res) => {
    const { invoice, sellerSlug, context } = req.body || {};
    const job = service.submit(invoice, sellerSlug, context);
    res.status(job.id ? 202 : 503).json(job);
  });
  app.post('/internal/facturx/payment', authorize, (req, res) => {
    const job = service.submitPayment(req.body?.paymentFields, req.body?.sellerSlug, req.body?.context);
    res.status(job.id ? 202 : 503).json(job);
  });
  app.get('/internal/facturx/:id', authorize, async (req, res) => {
    try {
      const job = await service.lookup(req.params.id);
      if (!job) return res.status(404).json({ error: 'Not found or expired' });
      if (job.state !== 'ready') return res.status(job.state === 'pending' ? 202 : 422).json({ state: job.state });
      res.setHeader('Content-Type', 'application/pdf');
      res.setHeader('Content-Disposition', 'attachment; filename="factur-x.pdf"');
      res.status(200).send(job.pdf);
    } catch { res.status(503).json({ error: 'Factur-X unavailable' }); }
  });
}
module.exports = { registerFacturxRoutes };
