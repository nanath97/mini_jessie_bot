# Billing extraction tests

No historical inputs or validated XML files have been supplied. The six fixture
directories intentionally contain only .gitkeep. Synthetic values in dependency
unit tests are not invoices and are not EN16931/BR-FR validation references.

Run from Bridge:

    node --check server.js
    npm run test:billing
    npm run test:billing:historical

The ordinary suite explicitly skips missing historical comparisons. The strict
historical gate fails until all six fixtures are complete, then runs the suite.
Tests load only billing modules, never server.js, and block network connections.
Node 24 is the tested local runtime (built-in test runner and Date mock timers).
No Node dependencies are added and production runtime settings are unchanged.

## Historical fixture contract

Each directory must receive input.json, historical.ubl.xml and manifest.json.
input.json contains scenario, sellerSlug, sellerConfig, paymentFields,
quoteRecords, paidDepositRecords and now (a fixed ISO date/time). Preserve original
Airtable field names and scalar types. Records have the original {id, fields}
shape. Use empty record arrays only where the scenario does not query that table.

manifest.json must contain origin="historical", source (a traceable description),
inputSha256 (SHA-256 of the exact input.json bytes) and ublSha256 (SHA-256 of the
exact historical.ubl.xml bytes). Record the validator versions and original
reports under validation/ when available. A hash records provenance/integrity;
it is not evidence of EN16931 or BR-FR compliance. Anonymized inputs/XML must be
revalidated before being described as validated references.

Before changing any historical reference, retain its original provenance.
The capture command uses only the frozen pre-extraction implementation and
requires its output to equal historical.ubl.xml byte for byte. It never generates
validation reports and never overwrites expected files:

    node ../tools/billing/capture-baseline.cjs --all

Or pass one scenario name. Capture creates expected.invoice.json and
expected.ubl.xml only after preflight succeeds for all requested scenarios.
It does not run during tests. Missing, malformed, partial or mismatched input
causes an explicit failure. All comparisons retain original whitespace and
numeric/string distinctions. No schema validator is installed in this step.

## Scope

invoice-builders.js contains the original three builders and paid-deposit lookup
inside createInvoiceBuilders({base, getSellerConfig}). ubl.js contains the original
generator and escapeXml. Tests check function-source SHA-256 against the original
server.js extraction. No calculations, Airtable queries, error behavior or XML
templates are rewritten. Future CII/PDF/Factur-X work is not included.
