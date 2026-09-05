'use strict';
const { scenarios, loadFixture } = require('./support/fixture-loader.cjs');
const { spawnSync } = require('node:child_process');
const missing = scenarios.filter(scenario => !loadFixture(scenario));
if (missing.length) {
  console.error('Historical regression gate BLOCKED. Missing: ' + missing.join(', '));
  process.exitCode = 1;
} else {
  const result = spawnSync(process.execPath, ['--require', './tests/billing/support/offline.cjs', '--test', 'tests/billing/builders.test.cjs', 'tests/billing/ubl.test.cjs', 'tests/billing/dependencies.test.cjs'], { stdio: 'inherit' });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
}
