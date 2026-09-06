# Seller configuration mapping (a81b8b6)

The sole seller source remains getSellerConfig(sellerSlug), reading the published
`/sellers/<sellerSlug>/config.json`. The corresponding PWA files are under
`C:\Users\epicn\Desktop\novapulse-pwa\public\sellers\`.
No profile file, builder, amount calculation, authentication or storage changes
are included here.

`company` is passed unchanged from the fetched config to the existing builder
and adapter. For B2B the helper requires the seller endpoint (BT-34), process
for the current invoice_type (BT-23), PMT/PMD/AAB and the explicit date convention.
All missing/invalid policy field paths are collected and logged before Python
runs. A failed job never propagates an exception to the payment caller.
The Python adapter retains its other checks (seller consistency, amounts, dates).

## Shape to add later in each public seller config

The following nulls deliberately fail validation. Replace them with confirmed
seller values; this is a schema illustration, not usable default configuration.

```json
{
  "facturx": {
    "seller_electronic_address": {"value": null, "scheme_id": null},
    "business_process_by_type": {"normal": null, "deposit": null, "balance": null},
    "b2b_notes": {"PMT": null, "PMD": null, "AAB": null},
    "payment_date_convention": null
  }
}
```

Values must be nonempty strings. The current adapter supports only explicitly
confirmed S2 paid services and the explicitly confirmed paid_at_utc_date
convention. These constants are allowed values, never defaults. No SIREN/email
is converted into a routing endpoint. Each seller must supply their own policy;
fixture contents are not commercial policy. Only the current invoice type's
process is required. B2C does not require or inherit the B2B policy fields.

## BT-49 is private transaction data

The only accepted source is `context.buyer_electronic_address`, with explicit
`value` and `scheme_id`. Existing direct callers use `service.submit(invoice,
sellerSlug, context)`. The authenticated internal payment endpoint now forwards
its optional `body.context` to `service.submitPayment(fields, sellerSlug,
context)`. The helper passes this value unchanged to the existing adapter.
The company contact email, buyer email, SIREN/SIRET and obsolete public
facturx.buyer_electronic_addresses map are never used as fallbacks. A strict
allowlist also excludes that public map from the seller JSON sent to Python.
BT-23 comes from seller policy; a conflicting explicit context process is refused.

The existing Python post-persist notifier transmits only paymentFields and
sellerSlug. It currently provides NO BT-49. Thus a B2B call without additional
explicit private context is intentionally refused. This patch neither invents
an Airtable field nor changes that notifier or invents a private data store.
The future private-data producer must provide the explicit context on this same
internal contract. Missing BT-49 is not repaired by public configuration.

## Offline tests

`node --test Bridge/tests/billing/facturx-config.test.cjs Bridge/tests/billing/facturx-service.test.cjs`

For the six existing end-to-end scenarios, use the unchanged E2E command with
FACTURX_PYTHON and FACTURX_VERAPDF configured:
`node Bridge/tests/billing/facturx-e2e.cjs`.

New seller-policy.json and private-context.json under tests/billing are separate
test-only inputs derived from the previously confirmed historical overlays.
The shared helper attaches company from each historical input without altering
any historical file. The public-shaped fixture contains no buyer directory.
E2E still compares generated XML bytes to the original CII references and requires
all applicable validators. Missing SaxonC is BLOCKED, never PASS.
