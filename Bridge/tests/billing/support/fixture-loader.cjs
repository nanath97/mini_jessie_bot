'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const scenarios = ['b2b-normal', 'b2b-deposit', 'b2b-balance', 'b2c-normal', 'b2c-deposit', 'b2c-balance'];
const root = path.resolve(__dirname, '../fixtures');
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

function loadInputs(scenario, fixtureRoot = root) {
  assert.ok(scenarios.includes(scenario), 'Unknown billing scenario');
  const dir = path.join(fixtureRoot, scenario);
  const inputPath = path.join(dir, 'input.json');
  if (!fs.existsSync(inputPath)) {
    const otherFiles = fs.existsSync(dir) ? fs.readdirSync(dir).filter(f => f !== '.gitkeep') : [];
    assert.equal(otherFiles.length, 0, `${scenario}: incomplete fixture (missing input.json)`);
    return null;
  }
  const inputBytes = fs.readFileSync(inputPath);
  const input = JSON.parse(inputBytes);
  const manifest = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8'));
  const historicalXml = fs.readFileSync(path.join(dir, 'historical.ubl.xml'));
  assert.equal(input.scenario, scenario);
  assert.equal(
    manifest.origin,
    scenario === 'b2b-deposit' ? 'reconstructed-revalidated' : 'historical'
  );
  assert.ok(typeof manifest.source === 'string' && manifest.source.trim(), 'Historical source required');
  assert.equal(manifest.inputSha256, digest(inputBytes), 'Input fingerprint mismatch');
  assert.equal(manifest.ublSha256, digest(historicalXml), 'Historical UBL fingerprint mismatch');
  assert.ok(input.paymentFields && input.sellerConfig && input.sellerSlug);
  assert.ok(typeof input.now === 'string' && Number.isFinite(Date.parse(input.now)), 'Fixed ISO clock required');
  assert.ok(Array.isArray(input.quoteRecords) && Array.isArray(input.paidDepositRecords));
  const role = input.paymentFields['Payment Role'] || '';
  assert.equal(role, scenario.endsWith('normal') ? '' : scenario.split('-')[1]);
  return { dir, input, manifest, historicalXml };
}

function loadFixture(scenario, fixtureRoot = root) {
  const fixture = loadInputs(scenario, fixtureRoot);
  if (!fixture) return null;
  fixture.expectedInvoice = JSON.parse(fs.readFileSync(path.join(fixture.dir, 'expected.invoice.json'), 'utf8'));
  fixture.expectedXml = fs.readFileSync(path.join(fixture.dir, 'expected.ubl.xml'));
  assert.deepStrictEqual(fixture.expectedXml, fixture.historicalXml, 'Baseline must match historical UBL bytes');
  return fixture;
}
module.exports = { scenarios, root, loadInputs, loadFixture, digest };
