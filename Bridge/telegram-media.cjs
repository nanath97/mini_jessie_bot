'use strict';
const crypto = require('node:crypto');
const { pipeline } = require('node:stream/promises');

// Authenticated, opaque capability: no bot token or Telegram path leaves the server.
// Stable across restarts; rotating the bot token invalidates previously issued links.
function createTelegramMedia({ token, axios }) {
  const key = crypto.createHash('sha256').update(`novapulse-media-v1:${token}`).digest();
  function createUrl(fileId, fileName, type) {
    if (!token || !fileId) throw new Error('Telegram media unavailable');
    const iv = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
    const data = Buffer.concat([cipher.update(JSON.stringify({ fileId, fileName, type })), cipher.final()]);
    return '/pwa/telegram-media/' + Buffer.concat([iv, cipher.getAuthTag(), data]).toString('base64url');
  }
  async function download(req, res) {
    let media;
    try {
      const ref = req.params.reference;
      if (!token || !/^[A-Za-z0-9_-]{40,4096}$/.test(ref)) throw new Error();
      const data = Buffer.from(ref, 'base64url');
      const decipher = crypto.createDecipheriv('aes-256-gcm', key, data.subarray(0, 12));
      decipher.setAuthTag(data.subarray(12, 28));
      media = JSON.parse(Buffer.concat([decipher.update(data.subarray(28)), decipher.final()]).toString());
    } catch {
      return res.status(404).send('Media not found');
    }
    let upstream;
    try {
      const result = await axios.get(`https://api.telegram.org/bot${token}/getFile`, {
        params: { file_id: media.fileId }, timeout: 30000, maxRedirects: 0,
      });
      const filePath = result.data?.result?.file_path;
      if (!result.data?.ok || typeof filePath !== 'string' ||
          !/^[A-Za-z0-9_./-]+$/.test(filePath) || filePath.split('/').some(p => !p || p === '..' || p === '.')) {
        return res.status(502).send('Telegram file unavailable');
      }
      upstream = await axios.get(`https://api.telegram.org/file/bot${token}/${filePath}`, {
        responseType: 'stream', timeout: 30000, maxRedirects: 0, validateStatus: () => true,
        headers: req.headers.range ? { Range: req.headers.range } : {},
      });
      if (![200, 206].includes(upstream.status)) {
        upstream.data.destroy();
        return res.status(502).send('Telegram download failed');
      }
      const name = String(media.fileName || 'document').replace(/[\x00-\x1f\x7f/\\?%*:|"<>]/g, '_').slice(0, 120);
      const fallback = name.replace(/[^\x20-\x7e]/g, '_');
      const disposition = media.type === 'document' ? 'attachment' : 'inline';
      res.status(upstream.status);
      res.setHeader('Content-Disposition', `${disposition}; filename="${fallback}"; filename*=UTF-8''${encodeURIComponent(name).replace(/['()*]/g, c => '%' + c.charCodeAt(0).toString(16))}`);
      res.setHeader('Content-Type', upstream.headers['content-type'] || 'application/octet-stream');
      res.setHeader('Cache-Control', 'no-store');
      res.setHeader('X-Content-Type-Options', 'nosniff');
      for (const header of ['content-length', 'content-range', 'accept-ranges']) {
        if (upstream.headers[header]) res.setHeader(header, upstream.headers[header]);
      }
      await pipeline(upstream.data, res);
    } catch {
      // Never log Axios errors: their config/request contains the bot credential.
      upstream?.data?.destroy();
      if (res.headersSent) res.destroy();
      else res.status(502).send('Telegram media unavailable');
    }
  }
  return { createUrl, download };
}
module.exports = { createTelegramMedia };
