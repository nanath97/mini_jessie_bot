# Offline CII first step â€” diagnostic candidates only

Target: Factur-X 1.09.2 / ZUGFeRD 2.5.2, UN/CEFACT CII D22B, EN16931.
Only expected.invoice.json is read. No UBL, raw Airtable exports, credentials,
production server imports, HTTP requests, PDFs or payment integration.

## Run from repository root

Use an isolated Python environment with requirements-facturx.txt installed before
going offline. Run `python -B -m unittest discover -s tests/facturx -v`.
Generate with:

    python -B -m billing_facturx.cli --fixtures Bridge/tests/billing/fixtures --out work/facturx-run-1

The output directory must not exist. Each scenario produces factur-x.xml and
validation.json. A validation failure, absent mandatory data, or unavailable
engine causes exit code 1. Files retained after rejection are explicitly marked
REJECTED_DIAGNOSTIC_CANDIDATE; they must not be distributed as compliant invoices.
This stage never produces a complete hybrid Factur-X document.

## Mapping and scope

- ExchangedDocument TypeCode: 380 normal/balance, 386 deposit (official code list).
- Guideline ID: urn:cen.eu:en16931:2017. No invented business-process ID.
- Source dates only; payment_date is not a contractual due date.
- One line/one tax breakdown is the supported initial domain, matching fixtures.
- Monetary values are rendered using Decimal without recomputing or rounding.
  Consistency checks compare supplied values; they do not repair them.
- Seller/buyer identifiers: legal SIREN scheme 0002, establishment SIRET 0009.
  The buyer field named siret contains a 9-digit SIREN in the B2B fixtures.
- Seller tax identifier is emitted only from vat_number (VA) or an explicitly
  supplied tax_registration_id (FC), or the existing nine-digit seller SIREN
  repeated in BT-32 under BR-FR-CO-16: country FR, no VAT number, category E
  and VATEX-FR-FRANCHISE. BT-30/SIRET are preserved; no VAT number is fabricated.
- Quote ID: AdditionalReferencedDocument, TypeCode 916 (BG-24).
- Balance: preserve its own remaining-amount totals; InvoiceReferencedDocument
  carries the preceding deposit invoice number/date. No second deposit deduction.
- Category E, VATEX-FR-FRANCHISE and exemption text come from source.
- No invented conditions, payment means, regulatory process code or routing ID.
- B2C generation/validation is diagnostic only, not the French B2B mandate.

## Official artifacts

Copied unchanged from the user's local France_RFE-1.4.0.03 distribution,
FNFE_RFE_INVOICE/Factur-X/EN16931. UPSTREAM.md explicitly records the update to
Factur-X 1.09.2; XSD imports include 1.09.2 in their filenames. SHA-256 hashes
are pinned in validation/artifacts.lock.json, with the upstream Apache license.
Release description: https://www.ferd-net.de/en/downloads/publications/details/zugferd-252-english

XSD uses lxml; compiled official Schematron uses SaxonC-HE, local code lists and
file-only URI access. Missing tools are BLOCKED, never silently skipped/passed.
SVRL errors and warnings are reported; no rules firing is an error.

## BT-32 confirmed mapping

French XP Z12-012, BR-FR-CO-16 (Franchise en base), states that a seller
without a VAT number must repeat its SIREN in BT-32. Official DGFiP publication:
https://www.impots.gouv.fr/sites/default/files/media/1_metier/2_professionnel/EV/2_gestion/290_facturation_electronique/specification_externes_b2b/afnor/norme-afnor-factures.pdf
The indexed official text was consulted on 2026-09-05; direct PDF retrieval
returned 404. This is a French mapping rule, not an assertion that the French
Schematron executable itself enforces the SIREN repetition.

The packaged Factur-X 1.09.2 FACTUR-X_EN16931.sch, BR-E-02 and the SellerTradeParty
SpecifiedTaxRegistration rules confirm this CII binding:
/rsm:CrossIndustryInvoice/rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty/ram:SpecifiedTaxRegistration/ram:ID[@schemeID="FC"]

This adapter copies the supplied SIREN verbatim into that element only under the
conditions above, keeps the existing BT-30 and SIRET mappings and never generates
BT-31. The original JSON remains untouched. B2C is still diagnostic only.

## Remaining validation blocker and exact local commands

SaxonC is unavailable in the Codex runner; attempts to install the pinned wheel
returned no matching distribution. XSD and unit tests are executable, but neither
EN16931 nor BR-FR has been executed here. Do not infer Schematron compliance.

After applying the patch from the jessie_bot repository root, run in PowerShell
(Python 3.12 x64 must be installed; package installation requires network, the
subsequent tests and validations do not):

```powershell
Set-Location -LiteralPath 'C:\Users\epicn\Desktop\NOVA PULSE_fr\Code\jessie_bot'
py -3.12 -m venv .venv-facturx
if ($LASTEXITCODE -ne 0) { throw 'venv failed' }
& .\.venv-facturx\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r .\requirements-facturx.txt
if ($LASTEXITCODE -ne 0) { throw 'dependency installation failed' }
& .\.venv-facturx\Scripts\python.exe -B -m unittest discover -s .\tests\facturx -v
if ($LASTEXITCODE -ne 0) { throw 'CII tests failed' }
npm --prefix .\Bridge run test:billing:historical
if ($LASTEXITCODE -ne 0) { throw 'historical tests failed' }
$ciiOutput = Join-Path 'work' ('facturx-' + [guid]::NewGuid().ToString('N'))
& .\.venv-facturx\Scripts\python.exe -B -m billing_facturx.cli --fixtures .\Bridge\tests\billing\fixtures --out $ciiOutput
$ciiExit = $LASTEXITCODE
Get-Content -LiteralPath (Join-Path $ciiOutput 'summary.json')
if ($ciiExit -ne 0) { throw 'CII validation rejected or blocked: inspect summary.json and scenario SVRL reports' }
```

For each of the six inputs, the CLI executes XSD, then official EN16931 XSLT,
then BR-FR CII XSLT, and retains SVRL reports. Both rule sets run even when the
first reports failures. Missing engine, runtime error or failed rules return
exit code 1; no missing data is filled to make validation succeed.

## Explicit French historical overlays

The CLI enriches only the three confirmed B2B snapshots via
`tests/facturx/french-fixtures/*.json`. Each overlay is bound to the invoice ID
and SHA-256 of its unchanged expected.invoice.json. No builder or historical
snapshot is modified. S2 and endpoints are explicit fixture data, never defaults.
PMT is the B2B 40 EUR recovery notice. PMD/AAB are explicitly stored historical
test wording; the generic PMD wording does not establish a complete contractual
penalty rate and must not become a production seller default.

The due date is the UTC calendar date of the timezone-aware historical
payment_date (convert to UTC, then take date). For these confirmed S2 invoices
this implements BR-FR-CO-09. It is not a general contractual due-date inference.
No date is inferred for B2C. ApplicableHeaderTradeDelivery remains empty because
the official XSD requires it; its warning is retained.

B2B acceptance requires XSD + EN16931 + BR-FR PASS. B2C acceptance requires
XSD + EN16931 PASS; BR-FR findings remain visible but are not an acceptance gate.
B2C always carries `diagnostic only` scope, and no B2B 40 EUR note is injected.
This supersedes the earlier all-scenarios BR-FR requirement described above.
