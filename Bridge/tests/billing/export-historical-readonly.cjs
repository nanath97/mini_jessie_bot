'use strict';

// Node.js 24. Aucune dépendance externe.
// Sources distantes : Airtable et configuration vendeur uniquement.
// Sorties locales : historical-import/raw/*.json uniquement.

const fs = require('node:fs/promises');
const path = require('node:path');

const SELLER_SLUG = 'coach-matthieu';

const INVOICES = [
  'NP-2026-000006',
  'NP-2026-000007',
  'NP-2026-000008',
  'NP-2026-000009',
  'NP-2026-000010',
  'NP-2026-000011',
];

const QUOTES = [
  'DEV-1787470286216',
  'DEV-1787507060544',
];

const OUTPUT_DIR = path.join(
  __dirname,
  'historical-import',
  'raw'
);

async function readJson(url, headers = {}) {
  const response = await fetch(url, {
    method: 'GET',
    headers,
    redirect: 'error',
    signal: AbortSignal.timeout(30000),
  });

  if (!response.ok) {
    // Ne pas afficher les en-têtes ni le corps de l'erreur.
    throw new Error(
      `Lecture refusée : HTTP ${response.status} sur ${url.hostname}`
    );
  }

  return response.json();
}

async function readRecords(apiKey, baseId, table, field, values) {
  const records = [];
  const offsets = new Set();
  let offset;

  do {
    const url = new URL(
      `https://api.airtable.com/v0/` +
      `${encodeURIComponent(baseId)}/${encodeURIComponent(table)}`
    );

    url.searchParams.set(
      'filterByFormula',
      `OR(${values.map(value => `{${field}}='${value}'`).join(',')})`
    );
    url.searchParams.set('pageSize', '100');

    if (offset) {
      url.searchParams.set('offset', offset);
    }

    const page = await readJson(url, {
      Authorization: `Bearer ${apiKey}`,
    });

    if (!Array.isArray(page.records)) {
      throw new Error(`Réponse inattendue pour ${table}`);
    }

    for (const record of page.records) {
      if (
        typeof record.id !== 'string' ||
        !record.fields ||
        typeof record.fields !== 'object' ||
        Array.isArray(record.fields)
      ) {
        throw new Error(`Enregistrement invalide dans ${table}`);
      }

      // Champs conservés tels que renvoyés par Airtable :
      // aucune conversion, aucun ajout, aucune valeur par défaut.
      records.push({
        id: record.id,
        fields: record.fields,
      });
    }

    offset = page.offset;

    if (offset !== undefined) {
      if (typeof offset !== 'string' || offsets.has(offset)) {
        throw new Error(`Pagination invalide pour ${table}`);
      }
      offsets.add(offset);
    }
  } while (offset);

  // Ne pas sélectionner arbitrairement un doublon.
  for (const value of values) {
    const matches = records.filter(
      record => record.fields[field] === value
    );

    if (matches.length !== 1) {
      throw new Error(
        `${table} : ${value} correspond à ${matches.length} enregistrement(s)`
      );
    }
  }

  if (records.length !== values.length) {
    throw new Error(`Nombre inattendu d'enregistrements dans ${table}`);
  }

  return records;
}

async function main() {
  const apiKey = process.env.AIRTABLE_API_KEY;
  const baseId = process.env.AIRTABLE_BASE_ID;

  if (!apiKey || !baseId) {
    throw new Error(
      'AIRTABLE_API_KEY et AIRTABLE_BASE_ID doivent être définies.'
    );
  }

  const names = [
    'payment-links.json',
    'quotes.json',
    'seller-config.json',
  ];

  // Refuser tout écrasement d'un export existant.
  for (const name of names) {
    try {
      await fs.lstat(path.join(OUTPUT_DIR, name));
    } catch (error) {
      if (error.code === 'ENOENT') continue;
      throw error;
    }
    throw new Error(`Export déjà présent : ${name}`);
  }

  const payments = await readRecords(
    apiKey,
    baseId,
    'Payment Links',
    'Invoice Number',
    INVOICES
  );

  const quotes = await readRecords(
    apiKey,
    baseId,
    'Quotes',
    'quote_id',
    QUOTES
  );

  const configUrl = new URL(
    `https://app.nova-pulse.app/sellers/` +
    `${encodeURIComponent(SELLER_SLUG)}/config.json`
  );

  // Aucun en-tête Airtable transmis à cet hébergement.
  const sellerConfig = await readJson(configUrl);

  if (
    !sellerConfig ||
    typeof sellerConfig !== 'object' ||
    !sellerConfig.company
  ) {
    throw new Error('Configuration vendeur invalide');
  }

  // Vérification en lecture seule des liens connus.
  for (const [invoice, quoteId, role] of [
    ['NP-2026-000006', QUOTES[0], 'deposit'],
    ['NP-2026-000007', QUOTES[0], 'balance'],
    ['NP-2026-000010', QUOTES[1], 'deposit'],
    ['NP-2026-000011', QUOTES[1], 'balance'],
  ]) {
    const record = payments.find(
      payment => payment.fields['Invoice Number'] === invoice
    );

    if (
      record.fields['Quote ID'] !== quoteId ||
      record.fields['Payment Role'] !== role ||
      record.fields.Status !== 'Paid'
    ) {
      throw new Error(`Lien ou statut inattendu pour ${invoice}`);
    }
  }

  for (const quote of quotes) {
    if (quote.fields.seller_slug !== SELLER_SLUG) {
      throw new Error(`Vendeur inattendu pour le devis ${quote.id}`);
    }
  }

  // Toutes les lectures doivent réussir avant la première écriture locale.
  await fs.mkdir(OUTPUT_DIR, { recursive: true });

  const exports = [
    [names[0], payments],
    [names[1], quotes],
    [names[2], sellerConfig],
  ];

  for (const [name, data] of exports) {
    await fs.writeFile(
      path.join(OUTPUT_DIR, name),
      JSON.stringify(data, null, 2) + '\n',
      { encoding: 'utf8', flag: 'wx' }
    );
  }

  console.log('Export terminé : 6 paiements, 2 devis, 1 configuration.');
  console.log(`Dossier : ${OUTPUT_DIR}`);
}

main().catch(error => {
  console.error(`Export interrompu : ${error.message}`);
  process.exitCode = 1;
});
