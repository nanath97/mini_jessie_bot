# Dynamic adapter — offline, outside production

Base: `14278e8`. No server import, network access, fixture defaults, amount
calculation, or deployment integration. `adapt_invoice(invoice, seller_config,
context)` accepts the JSON object returned by an existing invoice builder and
the config already obtained by its caller. It returns an independent CII/PDF
input. It never fetches a configuration itself.

## Source contract

| Source | Destination |
| --- | --- |
| Builder invoice_type normal/deposit/balance | Existing CII 380/386/380 and PDF title |
| invoice_number, invoice_date, currency | CII document identity and settlement currency |
| seller from getSellerConfig(...).company | Seller party, contact, legal and fiscal identifiers |
| buyer from Payment Links (balance: existing paid-deposit fallback) | Buyer party; Entreprise/Particulier selects scope |
| lines, tax, totals | Existing CII/PDF fields, unchanged values and types |
| quote.quote_id | Existing referenced document 916 |
| deposit_reference.invoice_number/invoice_date | Existing preceding-invoice reference |
| source payment/quote IDs | Preserved in input, not promoted to regulatory identifiers |
| context.business_process_id | BT-23; explicitly confirmed S2 only in this first paid-service integration |
| seller_config.facturx.seller_electronic_address {value,scheme_id} | Seller BT-34 |
| context.buyer_electronic_address {value,scheme_id} | Buyer BT-49 |
| seller_config.facturx.b2b_notes {PMT,PMD,AAB} | Explicit IncludedNote subject/content, also shown in PDF |
| invoice.payment_date + explicit paid_at_utc_date convention | B2B S2 payment_terms.due_date, UTC calendar date |

No due date is inferred from invoice_date. The UTC convention requires
`seller_config.facturx.payment_date_convention = "paid_at_utc_date"`.
Contact email/SIREN/SIRET never becomes a routing address automatically. The
existing CII fiscal identifier mapping is reused without changing its meaning.
The supplied seller country and SIREN must agree with the invoice snapshot;
other identity/address fields remain those of the builder snapshot.

B2B missing fields raise AdapterError with paths before any output is written.
Only the existing paid invoices (payable_amount = 0), one line and one VAT
breakdown supported by the CII engine are supported. Other business processes
and unpaid invoices require a separate extension. B2C uses the unchanged invoice,
has no automatic B2B notes/endpoints, and remains diagnostic only. Unknown buyer
types fail. A supplied B2C regulatory context is rejected, not silently ignored.

## Available versus missing data

The six locally archived inputs provide seller company, buyer, payments, dates,
lines, totals, quote and deposit references. These are real historical exports;
the current remote seller config was not queried. None contains the explicit
facturx policy/context above. UBL's hardcoded S2, endpoint inference and legal
placeholders are not treated as real configuration.

For B2B, obtain/confirm the seller endpoint, buyer endpoint, per-transaction
business process, PMT/PMD/AAB commercial wording, and payment-date convention
before using real dynamic data. Do not copy historical PMD wording into a real
commercial policy without confirmation. The three B2C inputs need no such B2B
supplement. Tests deliberately load confirmed historical overlays into a private
test config; these supplements are NEVER imported by the dynamic module.

## Tests and six test outputs (repository root, PowerShell)

Use the existing isolated Python environment with requirements-facturx.txt and
requirements-facturx-pdf.txt installed; no new dependency is added. Node must be
on PATH. Dependency installation is separate from offline tests.

```powershell
$py = '.\Bridge\.venv-facturx\Scripts\python.exe'
& $py -m unittest discover -s tests/facturx_dynamic -v
& $py -m unittest discover -s tests/facturx_pdf -v
& $py -m unittest discover -s tests/facturx -v
npm --prefix Bridge run test:billing:historical
& $py tests/facturx_dynamic/generate.py --out work/facturx-dynamic-local --verapdf 'C:\Users\epicn\verapdf\verapdf.bat'
```

The output directory must not exist. The generator executes the three builders
against fake Airtable with networking blocked, asserts each result equals its
historical snapshot, adapts with test-only supplements, and compares every CII
byte to the previously validated reference before generating any output. It
writes six scenario directories containing factur-x.xml, factur-x.pdf and
validation.json plus available validator reports. Existing histories are read
only. XML embedding remains byte-for-byte. The command runs XSD, EN16931,
BR-FR (required B2B only), and veraPDF. Missing validators are BLOCKED, never
PASS; exit code 2 means the new validation is not fully accepted, even when
historical XML bytes match. Six fixture outputs do not certify arbitrary future
data. Read each validation.json.

## Dynamic local invocation (explicit input files, no historical dependency)

```powershell
& $py -m billing_facturx_dynamic.cli --invoice invoice-from-builder.json --seller-config seller-config.json --context transaction-context.json --out work/dynamic-invoice --verapdf 'C:\Users\epicn\verapdf\verapdf.bat'
```

For B2C omit --context. Output filenames are fixed, so invoice identifiers cannot
control filesystem paths. Validation failures produce diagnostic candidates with
accepted=false; they must not be sent as accepted invoices.

The only existing-file change is PDF rendering of tax identifiers: FC comes
from the same CII helper instead of unconditionally labelling SIREN as FC; actual
VA identifiers are displayed when present. The six franchise fixtures retain
their existing rendering content. CII, builders, UBL and production are unchanged.
