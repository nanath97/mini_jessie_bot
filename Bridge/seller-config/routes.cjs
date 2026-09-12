'use strict';
const { createHash, timingSafeEqual } = require('node:crypto');
const { generateConfigForPwaClient, SellerConfigError } = require('./index.cjs');

function readAdminToken() {
  return require('./env.cjs').readSellerConfigEnv().SELLER_CONFIG_ADMIN_TOKEN;
}

const ERRORS = Object.freeze({
  INVALID_CLIENT_ID: [400, 'Record ID PWA Client invalide.'],
  RECORD_NOT_FOUND: [404, 'Enregistrement demandé ou lié introuvable.'],
  SELLER_NOT_FOUND: [404, 'Aucun profil vendeur lié à ce client.'],
  LINK_CONFLICT: [409, 'Plusieurs enregistrements liés alors qu’un seul est attendu.'],
  AIRTABLE_ERROR: [502, 'Lecture Airtable indisponible.'],
});

function registerSellerConfigRoutes(app, {
  generate = generateConfigForPwaClient, getAdminToken = readAdminToken,
} = {}) {
  app.get('/seller-config/:pwaClientRecordId', async (req, res) => {
    res.set('Cache-Control', 'no-store');
    res.set('X-Content-Type-Options', 'nosniff');
    try {
      const expected = getAdminToken();
      const supplied = req.get('X-NovaPulse-Admin-Token');
      const digest = value => createHash('sha256').update(value).digest();
      if (typeof expected !== 'string' || !expected.trim() || typeof supplied !== 'string' ||
          !timingSafeEqual(digest(expected), digest(supplied))) {
        return res.status(403).json({ error: 'FORBIDDEN', message: 'Forbidden' });
      }
      const config = await generate(req.params.pwaClientRecordId);
      // Serialize fully before adding download headers; no filesystem writes.
      const json = JSON.stringify(config, null, 2) + '\n';
      return res.status(200).set('Content-Disposition', 'attachment; filename="config.json"')
        .type('application/json').send(json);
    } catch (error) {
      const known = error instanceof SellerConfigError && Object.hasOwn(ERRORS, error.code);
      const [status, message] = known ? ERRORS[error.code] : [500, 'Génération de configuration impossible.'];
      // Never log or serialize upstream errors, request headers, tokens or base IDs.
      return res.status(status).json({ error: known ? error.code : 'CONFIG_GENERATION_FAILED', message });
    }
  });
}

module.exports = { registerSellerConfigRoutes };
