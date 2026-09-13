'use strict';
const { ZipFile } = require('yazl');
const { createSellerConfigGenerator, SellerConfigError } = require('./index.cjs');

const MIB = 1024 * 1024;
const LIMITS = Object.freeze({ avatar: 2 * MIB, video: 50 * MIB, config: MIB, zip: 104 * MIB, timeoutMs: 60000 });
class SellerPackError extends Error {
  constructor(code) { super(code); this.code = code; }
}
function mediaLocation(value, avatar) {
  let url;
  try { url = new URL(value); } catch { throw new SellerPackError('INVALID_MEDIA_URL'); }
  const type = avatar ? 'image' : 'video';
  if (url.protocol !== 'https:' || url.hostname !== 'res.cloudinary.com' || url.port || url.username || url.password
    || url.search || url.hash || !new RegExp(`^/[A-Za-z0-9_-]+/${type}/upload/.+`).test(url.pathname)) {
    throw new SellerPackError('INVALID_MEDIA_URL');
  }
  // Cloudinary delivery transformation; never rename PNG/WebP bytes as JPEG.
  if (avatar) url.pathname = url.pathname.replace('/image/upload/', '/image/upload/f_jpg/');
  return url.href;
}
async function download(url, avatar, fetchMedia, limits) {
  const controller = new AbortController();
  let timer, reader;
  const timeout = new Promise((resolve, reject) => {
    timer = setTimeout(() => { controller.abort(); reject(new SellerPackError('MEDIA_TIMEOUT')); }, limits.timeoutMs);
  });
  try {
    return await Promise.race([timeout, (async () => {
      const response = await fetchMedia(url, { signal: controller.signal, redirect: 'error' });
      if (response.status !== 200 || !response.body) throw new SellerPackError('MEDIA_DOWNLOAD_FAILED');
      const mime = (response.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
      if (mime !== (avatar ? 'image/jpeg' : 'video/mp4')) throw new SellerPackError('INVALID_MEDIA_CONTENT');
      const max = avatar ? limits.avatar : limits.video;
      const declared = response.headers.get('content-length');
      if (declared !== null && (!/^\d+$/.test(declared) || Number(declared) > max)) throw new SellerPackError('MEDIA_TOO_LARGE');
      reader = response.body.getReader();
      const chunks = []; let size = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > max) throw new SellerPackError('MEDIA_TOO_LARGE');
        chunks.push(Buffer.from(value));
      }
      const data = Buffer.concat(chunks, size);
      const valid = avatar
        ? size >= 5 && data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff && data[size - 2] === 0xff && data[size - 1] === 0xd9
        : size >= 12 && data.toString('ascii', 4, 8) === 'ftyp';
      if (!valid || (declared !== null && Number(declared) !== size)) throw new SellerPackError('INVALID_MEDIA_CONTENT');
      return data;
    })()]);
  } catch (error) {
    throw error instanceof SellerPackError ? error : new SellerPackError('MEDIA_DOWNLOAD_FAILED');
  } finally {
    clearTimeout(timer);
    controller.abort();
    if (reader) void reader.cancel().catch(() => {});
  }
}
async function archive(entries, max) {
  const zip = new ZipFile();
  const chunks = []; let size = 0;
  return new Promise((resolve, reject) => {
    const fail = () => { zip.outputStream.destroy(); reject(new SellerPackError('PACK_GENERATION_FAILED')); };
    zip.on('error', fail);
    zip.outputStream.on('error', fail);
    zip.outputStream.on('data', chunk => {
      size += chunk.length;
      if (size > max) return fail();
      chunks.push(chunk);
    });
    zip.outputStream.on('end', () => resolve(Buffer.concat(chunks, size)));
    try {
      for (const [name, data] of entries) zip.addBuffer(data, 'seller-pack/' + name, { compress: false });
      zip.end();
    } catch { fail(); }
  });
}
function createSellerPackBuilder({
  generate = createSellerConfigGenerator().generatePwaClientResult,
  fetchMedia = globalThis.fetch, limits = LIMITS,
} = {}) {
  let busy = false;
  return async function build(pwaClientRecordId) {
    if (!/^rec[A-Za-z0-9]{14}$/.test(pwaClientRecordId || '')) throw new SellerConfigError('INVALID_CLIENT_ID', 'Record ID invalide.');
    if (busy) throw new SellerPackError('PACK_BUSY');
    busy = true;
    try {
      const result = await generate(pwaClientRecordId);
      if (!result?.config?.company) throw new SellerPackError('PACK_GENERATION_FAILED');
      // Preserve the generator contract: no invented slug or extra video keys.
      const config = Buffer.from(JSON.stringify(result.config, null, 2) + '\n');
      if (config.length > limits.config) throw new SellerPackError('PACK_TOO_LARGE');
      // Validate ALL URLs before the first network request.
      const sources = [mediaLocation(result.media?.avatar, true), mediaLocation(result.media?.intro_video, false), mediaLocation(result.media?.beta_video, false)];
      const entries = [['config.json', config]];
      for (const [index, name] of ['avatar.jpg', 'Intro.mp4', 'beta-video.mp4'].entries()) {
        entries.push([name, await download(sources[index], index === 0, fetchMedia, limits)]);
      }
      return await archive(entries, limits.zip);
    } finally { busy = false; }
  };
}
module.exports = { createSellerPackBuilder, SellerPackError, LIMITS };
