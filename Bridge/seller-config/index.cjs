'use strict';

class SellerConfigError extends Error {
  constructor(code, message) { super(message); this.name = 'SellerConfigError'; this.code = code; }
}

const TABLES = Object.freeze({ seller: 'NovaPulse Sellers', services: 'Services', products: 'Digital Products', media: 'Seller Media' });
const str = value => {
  if (Array.isArray(value)) {
    if (value.length > 1) throw new Error('Champ scalaire contenant plusieurs valeurs lookup.');
    return str(value[0]);
  }
  return value == null ? '' : String(value);
};
const validId = value => typeof value === 'string' && /^rec[A-Za-z0-9]{14}$/.test(value);
const REVERSE_LINKS = Object.freeze({ seller: 'NovaPulse Sellers', services: 'Services 2', products: 'Digital Products', media: 'Seller Media' });
// Airtable attachment fields and URL fields are both supported.
const mediaUrl = value => Array.isArray(value) ? str(value[0]?.url) : str(value);

function defaultBase() {
  const { AIRTABLE_API_KEY, AIRTABLE_BASE_ID } = require('./env.cjs').readSellerConfigEnv();
  const baseId = AIRTABLE_BASE_ID;
  if (!AIRTABLE_API_KEY || !baseId) throw new Error('AIRTABLE_API_KEY et AIRTABLE_BASE_ID sont nécessaires.');
  const Airtable = require('airtable');
  return new Airtable({ apiKey: AIRTABLE_API_KEY }).base(baseId);
}

function createSellerConfigGenerator({ base, reverseLinks = {} } = {}) {
  const links = { ...REVERSE_LINKS, ...reverseLinks };
  async function generatePwaClientResult(pwaClientRecordId) {
    if (!validId(pwaClientRecordId)) throw new SellerConfigError('INVALID_CLIENT_ID', 'Record ID PWA Client invalide (rec suivi de 14 caractères alphanumériques attendu).');
    const source = base || defaultBase();
    async function readRecord(table, id) {
      if (!validId(id)) throw new Error('Record ID lié invalide dans ' + table);
      let record;
      try { record = await source(table).find(id); }
      catch (error) {
        const status = Number.isInteger(error?.statusCode) ? ' (HTTP ' + error.statusCode + ')' : '';
        throw new SellerConfigError(error?.statusCode === 404 ? 'RECORD_NOT_FOUND' : 'AIRTABLE_ERROR', error?.statusCode === 404
          ? 'Enregistrement introuvable dans ' + table
          : 'Échec de lecture Airtable dans ' + table + status);
      }
      if (!record || record.id !== id || !record.fields) throw new Error('Réponse incohérente dans ' + table);
      return record;
    }
    function linkedIds(record, field, { single = false, allowEmpty = false } = {}) {
      const ids = record.fields[field];
      // Airtable omits empty fields; only reciprocal child collections are optional.
      if (allowEmpty && (ids === undefined || (Array.isArray(ids) && ids.length === 0))) return [];
      if (!Array.isArray(ids) || !ids.length) throw new Error('Lien absent ou vide : ' + field + ' dans ' + record.id);
      if (ids.some(id => !validId(id)) || new Set(ids).size !== ids.length) throw new Error('Liens invalides ou dupliqués : ' + field);
      if (single && ids.length !== 1) throw new SellerConfigError('LINK_CONFLICT', 'Lien non unique : ' + field + ' dans ' + record.id);
      return ids;
    }
    function assertOwner(record, field, parentId) {
      const [owner] = linkedIds(record, field, { single: true });
      if (owner !== parentId) throw new Error('Cloisonnement violé : ' + field + ' dans ' + record.id);
    }
    const client = await readRecord('PWA Clients', pwaClientRecordId);
    if (client.fields[links.seller] === undefined || (Array.isArray(client.fields[links.seller]) && !client.fields[links.seller].length)) {
      throw new SellerConfigError('SELLER_NOT_FOUND', 'Profil vendeur absent pour ce client.');
    }
    const [sellerRecordId] = linkedIds(client, links.seller, { single: true });
    const sellerRecord = await readRecord(TABLES.seller, sellerRecordId);
    assertOwner(sellerRecord, 'pwa_client', pwaClientRecordId);
    const seller = sellerRecord.fields;
    async function readChildren(kind, active = false) {
      const ids = linkedIds(sellerRecord, links[kind], { single: kind === 'media', allowEmpty: true });
      const records = [];
      // Follow only explicit reciprocal links, never enumerate an entire table.
      for (const id of ids) {
        const record = await readRecord(TABLES[kind], id);
        assertOwner(record, 'Seller', sellerRecordId);
        records.push(record);
      }
      return records.filter(record => !active || record.fields.active === true)
        .sort((a, b) => (Number(a.fields.sort_order) || 0) - (Number(b.fields.sort_order) || 0) || a.id.localeCompare(b.id))
        .map(record => record.fields);
    }
    const services = await readChildren('services', true);
    const products = await readChildren('products', true);
    const [media = {}] = await readChildren('media');
    const vat = seller.default_vat_rate == null || seller.default_vat_rate === '' ? 0 : Number(seller.default_vat_rate);
    if (!Number.isFinite(vat) || vat < 0) throw new Error('default_vat_rate invalide.');
    const company = { name: str(seller.company_name) };
    for (const key of ['legal_name', 'legal_status', 'siren', 'siret', 'address', 'postal_code', 'city']) company[key] = str(seller[key]);
    Object.assign(company, {
      country: str(seller.country) || 'FR', email: str(seller.email), phone: str(seller.phone),
      vat_status: str(seller.vat_status), default_vat_rate: vat, vat_number: str(seller.vat_number), logo: mediaUrl(media.avatar),
    });
    const config = {
      company,
      facturx: {
        seller_electronic_address: { value: company.siren, scheme_id: '0225' },
        business_process_by_type: { normal: 'S2', deposit: 'S2', balance: 'S2' },
        payment_date_convention: 'paid_at_utc_date',
        b2b_notes: {
          PMT: 'Indemnité forfaitaire pour frais de recouvrement : 40 EUR en cas de retard de paiement.',
          PMD: "Pénalités de retard exigibles dès le jour suivant la date d'échéance, au taux de refinancement semestriel de la BCE en vigueur majoré de 10 points.",
          AAB: 'Escompte pour paiement anticipé : néant.',
        },
      },
      meta: { validated: true },
      services: services.map(row => ({ name: str(row.name), price: str(row.price) })),
      digitalProducts: products.map(row => ({ title: str(row.title), description: str(row.description), price: str(row.price), image: mediaUrl(row.image), paymentLink: str(row.payment_link) })),
      buttonText: '📋 Voir les services et prestations', calendly: str(seller.calendly), phone: company.phone,
    };
    return { pwaClientRecordId, sellerRecordId, config, media: { avatar: company.logo, intro_video: mediaUrl(media.intro_video), beta_video: mediaUrl(media.beta_video) } };
  }
  return { generatePwaClientResult, async generateConfigForPwaClient(pwaClientRecordId) { return (await generatePwaClientResult(pwaClientRecordId)).config; } };
}

module.exports = { SellerConfigError, createSellerConfigGenerator, generateConfigForPwaClient: pwaClientRecordId => createSellerConfigGenerator().generateConfigForPwaClient(pwaClientRecordId) };

if (require.main === module) {
  module.exports.generateConfigForPwaClient(process.argv[2]).then(config => {
    process.stdout.write(JSON.stringify(config, null, 2) + '\n');
  }).catch(error => {
    // Avoid printing SDK errors that could contain request details or credentials.
    process.stderr.write(`Génération impossible : ${error.safeMessage || (error instanceof Error && !error.statusCode ? error.message : 'échec de lecture Airtable')}\n`);
    process.exitCode = 1;
  });
}
