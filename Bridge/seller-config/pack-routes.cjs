'use strict';
const { SellerConfigError } = require('./index.cjs');
const { isAdminAuthorized, readAdminToken, ERRORS } = require('./routes.cjs');
const { createSellerPackBuilder, SellerPackError } = require('./pack.cjs');
const PACK_ERRORS = Object.freeze({
  PACK_BUSY: [409, 'Un export est déjà en cours. Veuillez réessayer.'],
  INVALID_MEDIA_URL: [502, 'Média absent ou URL de livraison non autorisée.'],
  MEDIA_DOWNLOAD_FAILED: [502, 'Téléchargement média indisponible.'],
  INVALID_MEDIA_CONTENT: [502, 'Contenu média invalide.'],
  MEDIA_TOO_LARGE: [502, 'Média trop volumineux pour cet export.'],
  MEDIA_TIMEOUT: [504, 'Délai de téléchargement média dépassé.'],
  PACK_TOO_LARGE: [502, 'Configuration trop volumineuse pour cet export.'],
  PACK_GENERATION_FAILED: [500, 'Génération du pack impossible.'],
});
function registerSellerPackRoutes(app, { build = createSellerPackBuilder(), getAdminToken = readAdminToken } = {}) {
  app.get('/seller-pack/:pwaClientRecordId', async (req, res) => {
    res.set('Cache-Control', 'no-store');
    res.set('X-Content-Type-Options', 'nosniff');
    try {
      if (!isAdminAuthorized(req, getAdminToken)) return res.status(403).json({ error: 'FORBIDDEN', message: 'Forbidden' });
      // req.query/body never supply media locations, credentials or a slug.
      const zip = await build(req.params.pwaClientRecordId);
      return res.status(200).set('Content-Disposition', 'attachment; filename="seller-pack.zip"').type('application/zip').send(zip);
    } catch (error) {
      const errors = error instanceof SellerConfigError ? ERRORS : error instanceof SellerPackError ? PACK_ERRORS : {};
      const known = Object.hasOwn(errors, error?.code);
      const [status, message] = known ? errors[error.code] : PACK_ERRORS.PACK_GENERATION_FAILED;
      return res.status(status).json({ error: known ? error.code : 'PACK_GENERATION_FAILED', message });
    }
  });
}
module.exports = { registerSellerPackRoutes, PACK_ERRORS };
