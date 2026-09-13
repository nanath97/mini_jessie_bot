'use strict';
const { verifyActivationToken } = require('./activation-token.cjs');
const { SellersError } = require('./errors.cjs');
const { createSellerMediaService, MEDIA } = require('./media-service.cjs');

function registerSellerMediaRoutes(app, { base, cloudinary, multer = require('multer'), streamifier = require('streamifier') } = {}) {
  const service = createSellerMediaService({ base, cloudinary, streamifier });
  const upload = multer({
    storage: multer.memoryStorage(),
    // Busboy marks a file truncated when it reaches its limit; allow the
    // inclusive 50 MiB boundary, then validate the exact per-field limits.
    limits: { fileSize: 50 * 1024 * 1024 + 1, files: 3, fields: 0, parts: 4 },
    fileFilter(req, file, done) {
      const spec = Object.hasOwn(MEDIA, file.fieldname) && MEDIA[file.fieldname];
      done(spec && spec.types.includes(file.mimetype) ? null : new SellersError(400, 'INVALID_MEDIA'), Boolean(spec));
    },
  }).fields(Object.keys(MEDIA).map(name => ({ name, maxCount: 1 })));
  const headers = res => { res.set('Cache-Control', 'no-store'); res.set('X-Content-Type-Options', 'nosniff'); };
  const failure = (res, error) => res.status(error instanceof SellersError ? error.status : 500)
    .json({ ok: false, error: error instanceof SellersError ? error.code : 'INTERNAL_ERROR' });
  app.use(/^\/seller-media\/?$/, (error, req, res, next) => {
    headers(res); failure(res, new SellersError(400, 'INVALID_MEDIA'));
  });
  const handle = fn => async (req, res) => {
    headers(res);
    try {
      const match = /^Bearer ([A-Za-z0-9_.-]+)$/i.exec(req.get('Authorization') || '');
      if (!match) throw new SellersError(401, 'INVALID_TOKEN');
      const { seller_id } = verifyActivationToken(match[1]);
      await fn(req, res, seller_id);
    } catch (error) { failure(res, error); }
  };
  app.get('/seller-media', handle(async (req, res, sellerId) => {
    res.json({ ok: true, media: await service.get(sellerId) });
  }));
  app.post('/seller-media', handle(async (req, res, sellerId) => {
    if (!req.is('multipart/form-data')) throw new SellersError(400, 'INVALID_MEDIA');
    await new Promise((resolve, reject) => upload(req, res, error => error
      ? reject(new SellersError(400, 'INVALID_MEDIA')) : resolve()));
    if (Object.keys(req.body || {}).length) throw new SellersError(400, 'INVALID_MEDIA');
    res.json({ ok: true, media: await service.save(sellerId, req.files) });
  }));
}
module.exports = { registerSellerMediaRoutes };
