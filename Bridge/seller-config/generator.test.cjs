'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createSellerConfigGenerator } = require('./index.cjs');
const rid = n => 'rec' + String(n).padStart(14, '0');
function fixture() {
  const data = { 'PWA Clients': {}, 'NovaPulse Sellers': {}, Services: {}, 'Digital Products': {}, 'Seller Media': {} };
  for (const offset of [0, 100]) {
    const client = rid(offset + 1), seller = rid(offset + 2);
    const add = (table, n, fields) => { const id = rid(offset + n); data[table][id] = { id, fields }; };
    add('PWA Clients', 1, { 'NovaPulse Sellers': [seller], email: 'client@example.com' });
    add('NovaPulse Sellers', 2, { pwa_client: [client], 'Services 2': [rid(offset + 3), rid(offset + 4), rid(offset + 7)], 'Digital Products': [rid(offset + 5)], 'Seller Media': [rid(offset + 6)], company_name: 'Entreprise fictive ' + offset, siren: '123456789', email: ['client@example.com'], default_vat_rate: 20 });
    add('Services', 3, { Seller: [seller], active: true, name: 'Conseil ' + offset, price: 90, sort_order: 2 });
    add('Services', 4, { Seller: [seller], active: true, name: 'Diagnostic ' + offset, price: 0, sort_order: 1 });
    add('Services', 7, { Seller: [seller], active: false, name: 'Inactif ' + offset });
    add('Digital Products', 5, { Seller: [seller], active: true, title: 'Guide ' + offset, price: 19, image: [{ url: 'https://example.com/guide.png' }], payment_link: 'https://example.com/guide' });
    add('Seller Media', 6, { Seller: [seller], avatar: [{ url: 'https://example.com/avatar-' + offset + '.png' }], intro_video: 'https://example.com/intro.mp4' });
    // Deliberate collisions: neither legacy field may influence ownership.
    for (const table of Object.values(data)) for (const row of Object.values(table)) Object.assign(row.fields, { seller_id: 'same-legacy-value', seller_slug: '' });
  }
  return data;
}
function api(data = fixture(), options = {}) {
  const reads = [];
  const base = table => ({ async find(id) {
    reads.push([table, id]);
    if (options.fail) throw Object.assign(new Error('SECRET request credentials'), { statusCode: options.fail });
    const row = data[table]?.[id];
    if (!row) throw Object.assign(new Error('missing'), { statusCode: 404 });
    return structuredClone(row);
  } }); // No select/list/mutation API: table scans or writes fail the tests.
  return { ...createSellerConfigGenerator({ base, reverseLinks: options.reverseLinks }), reads };
}
test('two clients: isolated record reads, mapping, sorting and identical legacy identifiers', async () => {
  for (const offset of [0, 100]) {
    const generator = api();
    const result = await generator.generatePwaClientResult(rid(offset + 1));
    const c = result.config;
    assert.equal(result.sellerRecordId, rid(offset + 2));
    assert.equal(c.company.name, 'Entreprise fictive ' + offset);
    assert.equal(c.company.email, 'client@example.com');
    assert.equal(c.company.logo, 'https://example.com/avatar-' + offset + '.png');
    assert.deepEqual(c.services, [{ name: 'Diagnostic ' + offset, price: '0' }, { name: 'Conseil ' + offset, price: '90' }]);
    assert.deepEqual(c.digitalProducts, [{ title: 'Guide ' + offset, description: '', price: '19', image: 'https://example.com/guide.png', paymentLink: 'https://example.com/guide' }]);
    assert.deepEqual(c.facturx.seller_electronic_address, { value: '123456789', scheme_id: '0225' });
    assert.equal(result.media.intro_video, 'https://example.com/intro.mp4');
    assert.deepEqual(Object.keys(c), ['company', 'facturx', 'meta', 'services', 'digitalProducts', 'buttonText', 'calendly', 'phone']);
    assert.equal(generator.reads.length, 7);
    assert.ok(generator.reads.every(([, id]) => Number(id.slice(3)) > offset && Number(id.slice(3)) < offset + 8));
    if (!offset) assert.deepEqual(c, require('./pwa-client.example.json'));
  }
});
test('invalid input rejected before reading Airtable', async () => {
  const generator = api();
  for (const input of [null, '', 'novapulse-ceo', ' rec00000000000001', 'rec\"injection', rid(1) + '\n']) await assert.rejects(generator.generateConfigForPwaClient(input), /invalide/);
  assert.equal(generator.reads.length, 0);
});
test('missing client, seller or child is an explicit error', async () => {
  for (const [table, id] of [['PWA Clients', 1], ['NovaPulse Sellers', 2], ['Services', 3], ['Digital Products', 5], ['Seller Media', 6]]) {
    const data = fixture(); delete data[table][rid(id)];
    await assert.rejects(api(data).generateConfigForPwaClient(rid(1)), /introuvable/);
  }
});
test('zero or multiple seller profiles rejected before reading any seller', async () => {
  for (const value of [undefined, [], [rid(2), rid(102)]]) {
    const data = fixture(); data['PWA Clients'][rid(1)].fields['NovaPulse Sellers'] = value;
    const generator = api(data);
    await assert.rejects(generator.generateConfigForPwaClient(rid(1)), /absent|non unique/);
    assert.equal(generator.reads.length, 1);
  }
});
for (const [table, id, field, expected, other] of [
  ['NovaPulse Sellers', 2, 'pwa_client', 1, 101], ['Services', 3, 'Seller', 2, 102], ['Digital Products', 5, 'Seller', 2, 102], ['Seller Media', 6, 'Seller', 2, 102],
]) test(table + ': rejects foreign, missing, duplicate and multiple ownership', async () => {
  for (const links of [[rid(other)], [], undefined, [rid(expected), rid(other)], [rid(expected), rid(expected)], 'invalid']) {
    const data = fixture(); data[table][rid(id)].fields[field] = links;
    await assert.rejects(api(data).generateConfigForPwaClient(rid(1)), /Cloisonnement|absent|non unique|dupliqués/);
  }
});
test('reciprocal link pointing to foreign child is rejected', async () => {
  for (const [field, id] of [['Services 2', 103], ['Digital Products', 105], ['Seller Media', 106]]) {
    const data = fixture(); data['NovaPulse Sellers'][rid(2)].fields[field] = [rid(id)];
    await assert.rejects(api(data).generateConfigForPwaClient(rid(1)), /Cloisonnement/);
  }
});
for (const field of ['Services 2', 'Digital Products', 'Seller Media']) {
  for (const absent of [false, true]) test(field + (absent ? ' omitted' : ' empty') + ': empty output without child reads', async () => {
    const data = fixture();
    if (absent) delete data['NovaPulse Sellers'][rid(2)].fields[field];
    else data['NovaPulse Sellers'][rid(2)].fields[field] = [];
    const generator = api(data);
    const result = await generator.generatePwaClientResult(rid(1));
    if (field === 'Services 2') assert.deepEqual(result.config.services, []);
    if (field === 'Digital Products') assert.deepEqual(result.config.digitalProducts, []);
    if (field === 'Seller Media') {
      assert.equal(result.config.company.logo, '');
      assert.deepEqual(result.media, { avatar: '', intro_video: '', beta_video: '' });
    }
    assert.ok(generator.reads.every(([table]) => table !== (field === 'Services 2' ? 'Services' : field)));
    assert.equal(result.config.company.name, 'Entreprise fictive 0');
  });
}
test('new seller with no child fields reads only client and seller, without foreign fallback', async () => {
  const data = fixture();
  for (const field of ['Services 2', 'Digital Products', 'Seller Media']) delete data['NovaPulse Sellers'][rid(2)].fields[field];
  const generator = api(data);
  const c = await generator.generateConfigForPwaClient(rid(1));
  assert.deepEqual(c.services, []); assert.deepEqual(c.digitalProducts, []); assert.equal(c.company.logo, '');
  assert.deepEqual(generator.reads, [['PWA Clients', rid(1)], ['NovaPulse Sellers', rid(2)]]);
});
test('malformed child collections remain errors', async () => {
  for (const field of ['Services 2', 'Digital Products', 'Seller Media']) {
    for (const value of [null, '', {}, [rid(3), rid(3)]]) {
      const data = fixture(); data['NovaPulse Sellers'][rid(2)].fields[field] = value;
      await assert.rejects(api(data).generateConfigForPwaClient(rid(1)), /absent|dupliqués/);
    }
  }
});
test('multiple media remain an explicit error', async () => {
  const data = fixture(); data['NovaPulse Sellers'][rid(2)].fields['Seller Media'].push(rid(106));
  await assert.rejects(api(data).generateConfigForPwaClient(rid(1)), /non unique/);
});
test('inactive records still checked for ownership before omission', async () => {
  const data = fixture(); data.Services[rid(7)].fields.Seller = [rid(102)];
  await assert.rejects(api(data).generateConfigForPwaClient(rid(1)), /Cloisonnement/);
});
test('inactive catalogues yield empty arrays; optional fields keep template defaults', async () => {
  const data = fixture();
  for (const row of Object.values(data.Services)) row.fields.active = false;
  data['Digital Products'][rid(5)].fields.active = false;
  delete data['NovaPulse Sellers'][rid(2)].fields.default_vat_rate;
  delete data['Seller Media'][rid(6)].fields.avatar;
  const c = await api(data).generateConfigForPwaClient(rid(1));
  assert.deepEqual(c.services, []); assert.deepEqual(c.digitalProducts, []);
  assert.equal(c.company.logo, ''); assert.equal(c.company.country, 'FR'); assert.equal(c.company.default_vat_rate, 0);
});
test('renamed reciprocal fields supported explicitly', async () => {
  const data = fixture(); const fields = data['PWA Clients'][rid(1)].fields;
  fields.Profile = fields['NovaPulse Sellers']; delete fields['NovaPulse Sellers'];
  assert.equal((await api(data, { reverseLinks: { seller: 'Profile' } }).generateConfigForPwaClient(rid(1))).company.name, 'Entreprise fictive 0');
});
test('network errors never expose credentials or produce partial JSON', async () => {
  await assert.rejects(api(fixture(), { fail: 403 }).generateConfigForPwaClient(rid(1)), error => {
    assert.match(error.message, /HTTP 403/); assert.doesNotMatch(error.message, /SECRET/); return true;
  });
});
test('wrong returned record ID is rejected', async () => {
  const data = fixture(); data['PWA Clients'][rid(1)].id = rid(101);
  await assert.rejects(api(data).generateConfigForPwaClient(rid(1)), /incohérente/);
});
test('invalid VAT and multi-value scalar lookups rejected', async () => {
  const data = fixture(); data['NovaPulse Sellers'][rid(2)].fields.default_vat_rate = 'invalid';
  await assert.rejects(api(data).generateConfigForPwaClient(rid(1)), /default_vat_rate/);
  delete data['NovaPulse Sellers'][rid(2)].fields.default_vat_rate;
  data['NovaPulse Sellers'][rid(2)].fields.email = ['a', 'b'];
  await assert.rejects(api(data).generateConfigForPwaClient(rid(1)), /lookup/);
});
