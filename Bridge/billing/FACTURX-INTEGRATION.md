# Factur-X post-persistence integration on 41240d8

`main.py` registers `stripe_webhook.py` as the handler forwarded to by Bridge.
The checkout hook runs after the successful PATCH of Payment Links (200/201),
before returning record_id. The off-session hook runs only in the successful
Payment Links POST branch (200/201); existing-record handling is unchanged.
Both hand the actual response object to a bounded daemon-thread notifier.
Parsing, HTTP and generation never block the handler. No new invoice numbers,
payment writes or calculations are performed by the hook.

The server changes only import/instantiate the service and register internal
routes. The notifier transmits response.fields without supplements to
POST /internal/facturx/payment. The Bridge worker loads real seller config and
selects the unchanged builder by Payment Role. Only the builder's existing quote
and paid-deposit reads occur. JSON timezone/date values come from the persisted
Airtable response, never repaired by the hook. Missing dates, buyer fields or
policy cause an explicit failure, including incomplete off-session buyer data.

## Runtime settings (not set by this patch)

- FACTURX_ENABLED=true to opt in; default disabled.
- FACTURX_BRIDGE_URL in Python: HTTPS Bridge base URL or HTTP loopback only.
- FACTURX_SERVICE_TOKEN: dedicated high-entropy bearer secret, at least 32
  characters, for trusted backend/admin clients only. Never put it in the PWA,
  query string, download URL or logs. Use TLS or a private local connection.
- FACTURX_PYTHON: Python executable in the existing isolated environment with
  requirements-facturx-pdf.txt installed, including SaxonC.
- FACTURX_VERAPDF: veraPDF executable/batch path.
- FACTURX_STORAGE_DIR: private local temp directory; default OS temp.

No dependency installation or deployment is performed automatically.

## Input and seller policy

POST /internal/facturx with Authorization: Bearer <service-token> and JSON
{invoice, sellerSlug, context}. The trusted caller supplies the unchanged builder
object, not a client-created invoice. The seller_slug must match the invoice.
The service calls the existing getSellerConfig(sellerSlug) for real seller policy.

B2B requires config.facturx.seller_electronic_address, b2b_notes.PMT/PMD/AAB and
payment_date_convention=paid_at_utc_date, as specified by the existing adapter.
context.buyer_electronic_address must be explicit. context.business_process_id
may be supplied per transaction; otherwise it must be explicitly configured in
config.facturx.business_process_by_type[normal|deposit|balance]. Only the existing
adapter's paid S2 service scope is supported. No invoice SIREN/contact email is
silently converted to a routing address. B2C receives no artificial B2B context.

For the post-persist endpoint, the seller config supplies
facturx.buyer_electronic_addresses["siret:<exact buyer.siret>"] or, when no SIRET
exists, ["email:<lowercase trimmed buyer.email>"], each {value, scheme_id}.
These are explicit configuration mappings; a key is never itself converted into
an endpoint. business_process_by_type supplies the confirmed S2 process.
No live configuration or Airtable schema was changed by this patch.

Returns 202 with an opaque random job id. GET /internal/facturx/:id requires the
same backend credential: 202 pending, 422 failed, 404 unknown/expired, 200 PDF.
This is not yet buyer-session authentication or a customer download link.

## Failure and storage behavior

One worker runs at a time; at most four jobs are pending and 100 jobs retained.
Submit is synchronous/non-throwing, including configuration/worker failures.
Errors are logged; the worker cannot reject the originating payment operation.
Full subprocess tracebacks and credentials are not logged. Generation timeout
is 180 seconds. Environment secrets for Stripe/Airtable/mail are not inherited
by Python. Arguments are passed without shell interpolation.

Only accepted CII + veraPDF PASS outputs are downloadable. Missing validators
are BLOCKED and never bypassed. Input/config and intermediate files are deleted
after the worker finishes. Accepted PDFs are retained in memory for one hour;
expired jobs are discarded on activity. A restart loses them. This is temporary
storage, not statutory archiving or a durable queue. A future caller needs a
retry mechanism for process interruption. No public static directory is used.

## Offline verification (from repository root)

```powershell
node --check Bridge/server.js
node --test Bridge/tests/billing/facturx-service.test.cjs
$env:FACTURX_PYTHON = (Resolve-Path '.\Bridge\.venv-facturx\Scripts\python.exe').Path
$env:FACTURX_VERAPDF = 'C:\Users\epicn\verapdf\verapdf.bat'
node Bridge/tests/billing/facturx-e2e.cjs
npm --prefix Bridge run test:billing:historical
```

The E2E harness runs actual builders against fake Airtable, the queue, JSON file
transport, actual Python adapter/CII/PDF/validators and authenticated download
handlers, without starting the production server or opening network sockets.
Explicit historical supplements exist only inside this test. Every produced XML
is checked byte-for-byte against its historical CII reference. Unit tests use a
fake PDF worker and make no PDF/A compliance claim. E2E exit 2 means validators
blocked; exit 1 means failure; exit 0 means all six accepted/downloaded.

Python post-persist tests (no production imports, Stripe or Airtable calls):
`python -m unittest discover -s tests/facturx_postpersist -v`.
They execute the actual handler functions from their AST with mocked dependencies,
including success, failed persistence, off-session duplicate and scheduling errors.
The thread queue is best-effort and not durable; shutdown may lose a notification.
The returned job id is logged server-side (no token), retrievable through the
protected internal download endpoint. It is not yet sent to a PWA customer.
