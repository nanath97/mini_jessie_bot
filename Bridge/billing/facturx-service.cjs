'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { execFile } = require('node:child_process');

function pythonRunner({ python, root, verapdf, timeout = 180000 }) {
  return async (folder) => {
    const args = ['-m', 'billing_facturx_dynamic.cli', '--invoice', path.join(folder, 'invoice.json'),
      '--seller-config', path.join(folder, 'seller.json'), '--context', path.join(folder, 'context.json'),
      '--out', path.join(folder, 'output')];
    if (verapdf) args.push('--verapdf', verapdf);
    await new Promise((resolve, reject) => execFile(python, args, {
      cwd: root, timeout, windowsHide: true, shell: false, maxBuffer: 2 * 1024 * 1024,
      // Do not pass Stripe, Airtable, SMTP or service credentials to the renderer.
      env: Object.fromEntries(['PATH','Path','SYSTEMROOT','SystemRoot','WINDIR','TEMP','TMP','LANG','JAVA_HOME','COMSPEC','ComSpec','PATHEXT','USERPROFILE','OS'].filter(k => process.env[k]).map(k => [k, process.env[k]])),
    }, (error, stdout, stderr) => {
      if (!error) return resolve();
      // The CLI returns 2 for a validation failure; preserve its report below.
      if (error.code === 2) return resolve();
      const detail = String(stderr || '').split(/\r?\n/).filter(line => /AdapterError:|required|confirmation required|conflicts with/.test(line)).join(' ').slice(0, 1500);
      reject(new Error(detail || 'Factur-X worker failed or timed out'));
    }));
    return JSON.parse(await fs.readFile(path.join(folder, 'output', 'validation.json'), 'utf8'));
  };
}

function createFacturxService({ getSellerConfig, buildInvoice, run, logger = console, storage = os.tmpdir(),
  enabled = false, ttlMs = 3600000, maxJobs = 100, maxPending = 4, now = Date.now }) {
  const jobs = new Map();
  let directory;
  let tail = Promise.resolve();
  let pending = 0;
  const log = (error) => { try { logger.error('[Factur-X]', error.message); } catch {} };
  async function cleanup() {
    for (const [id, job] of jobs) if (job.state !== 'pending' && job.expires <= now()) {
      if (job.folder) await fs.rm(job.folder, { recursive: true, force: true });
      jobs.delete(id);
    }
  }
  async function generate(job, invoice, slug, context, paymentFields) {
    try {
      const config = await getSellerConfig(slug);
      if (!config?.company) throw new Error('Missing real seller configuration');
      if (paymentFields) {
        invoice = await buildInvoice(paymentFields, slug, config);
        if (!invoice) throw new Error('Persisted invoice builder failed');
        if (invoice.buyer?.type === 'Entreprise') {
          const buyer = invoice.buyer;
          const key = buyer.siret ? 'siret:' + buyer.siret : 'email:' + String(buyer.email || '').trim().toLowerCase();
          context.buyer_electronic_address = config.facturx?.buyer_electronic_addresses?.[key];
        }
      }
      // Process defaults must be explicit seller policy, never historical values.
      if (invoice.buyer?.type === 'Entreprise' && !context.business_process_id) {
        context.business_process_id = config.facturx?.business_process_by_type?.[invoice.invoice_type];
      }
      if (!directory) {
        await fs.mkdir(storage, { recursive: true });
        directory = await fs.mkdtemp(path.join(path.resolve(storage), 'novapulse-facturx-'));
      }
      job.folder = await fs.mkdtemp(path.join(directory, 'job-'));
      for (const [name, value] of [['invoice', invoice], ['seller', config], ['context', context]]) {
        await fs.writeFile(path.join(job.folder, name + '.json'), JSON.stringify(value), { mode: 0o600, flag: 'wx' });
      }
      const report = await run(job.folder);
      if (report.accepted !== true || report.pdfa?.status !== 'pass' || report.cii?.accepted !== true) {
        throw new Error('Validation rejected/blocked: ' + JSON.stringify({ mandatory: report.cii?.mandatory_data, xsd: report.cii?.xsd?.status, en16931: report.cii?.en16931?.status, br_fr: report.cii?.br_fr?.status, pdfa: report.pdfa?.status }));
      }
      const pdf = await fs.readFile(path.join(job.folder, 'output', 'factur-x.pdf'));
      if (!pdf.subarray(0, 5).equals(Buffer.from('%PDF-'))) throw new Error('Invalid PDF output');
      job.pdf = pdf;
      job.state = 'ready';
    } catch (error) {
      job.state = 'failed'; log(error);
    } finally {
      job.expires = now() + ttlMs;
      if (job.folder) {
        try { await fs.rm(job.folder, { recursive: true, force: true }); } catch (error) { log(error); }
      }
      pending--;
    }
  }
  function submit(invoice, slug, context = {}, paymentFields = null) {
    // No exception or worker rejection is allowed to reach a payment caller.
    try {
      if (!enabled) return { state: 'disabled' };
      for (const [id, job] of jobs) if (job.state !== 'pending' && job.expires <= now()) jobs.delete(id);
      if (typeof slug !== 'string' || !slug || (!paymentFields && (!invoice || invoice.seller?.seller_slug !== slug || !invoice.invoice_number || !invoice.payment_date))) {
        throw new Error('Missing/mismatched built invoice seller, invoice number or payment date');
      }
      if (paymentFields && (paymentFields.Status !== 'Paid' || !paymentFields['Invoice Number'] || !paymentFields['Paid At'])) throw new Error('Persisted paid invoice fields required');
      if (pending >= maxPending || jobs.size >= maxJobs) throw new Error('Factur-X queue capacity reached');
      const data = structuredClone(invoice), ctx = structuredClone(context);
      const persisted = paymentFields ? structuredClone(paymentFields) : null;
      if (JSON.stringify({ data, ctx, persisted }).length > 1024 * 1024) throw new Error('Factur-X input too large');
      const id = crypto.randomBytes(32).toString('hex');
      const job = { state: 'pending', expires: Infinity };
      jobs.set(id, job); pending++;
      tail = tail.then(() => generate(job, data, slug, ctx, persisted)).catch(log);
      return { id, state: 'pending' };
    } catch (error) { log(error); return { state: 'failed' }; }
  }
  async function lookup(id) {
    await cleanup();
    if (!/^[a-f0-9]{64}$/.test(String(id))) return null;
    const job = jobs.get(id);
    return job ? { state: job.state, pdf: job.pdf } : null;
  }
  // Tests / orderly shutdown only; payment callers never wait for rendering.
  async function close() {
    await tail;
    if (directory) await fs.rm(directory, { recursive: true, force: true });
    jobs.clear();
  }
  return { submit, submitPayment: (fields, slug) => fields && typeof fields === 'object' ? submit(null, slug, {}, fields) : { state: 'failed' }, lookup, drain: () => tail, close };
}

module.exports = { createFacturxService, pythonRunner };
