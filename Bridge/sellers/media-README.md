# Seller media

GET and POST `/seller-media` require `Authorization: Bearer <sellerActivationToken>`.
Both return HTTP 200 with `{ ok: true, media: { avatar, intro_video, beta_video } }`.
GET returns `media: null` when the seller has no reciprocal media link; missing
individual URL fields are returned as empty strings. No record IDs are exposed.

POST accepts multipart files only, exactly one each of `avatar`, `intro_video`,
`beta_video`. Text fields (including every form of seller identity) are rejected.
Avatar accepts PNG/JPEG/WebP MIME types up to 2,097,152 bytes; both videos accept
MP4 up to 52,428,800 bytes each. Empty files are rejected. MIME validation checks
the multipart declaration, not file signatures; dimensions and duration remain
frontend validations. Multer buffers files in memory with bounded file/part counts
and a global file cap; the smaller avatar cap is checked after parsing.

The signed Seller_id resolves the exact NovaPulse Sellers row through the existing
seller service. The reciprocal field `Seller Media` supplies record IDs, and
`Seller Media.Seller` must contain exactly that seller record ID. Malformed or
dangling links fail closed. Multiple links return 409 MULTIPLE_SELLER_MEDIA.

Cloudinary uses folder `novapulse_sellers/<signed Seller_id>/`, public_id `avatar`
(image), `intro_video` (video), `beta_video` (video), overwrite=true and
invalidate=true. The resulting full asset IDs are the folder plus logical name.
The existing configured Cloudinary instance is injected; no messaging uploads
or configuration changes are involved.

After all three uploads succeed, ownership and links are rechecked. No link means
create with three secure_url strings, updated_at as an ISO UTC timestamp, and
Seller: [serverResolvedRecordId]. One link means update that record's URLs and
timestamp, preserving its checked Seller relation. seller_label is not written.

Errors are `{ ok: false, error: CODE }`: 400 INVALID_MEDIA/MISSING_MEDIA;
401 INVALID_TOKEN; 403 INVALID_SCOPE/FORBIDDEN; 404 SELLER_NOT_FOUND;
409 DUPLICATE_SELLER/SELLER_ID_CONFLICT/MULTIPLE_SELLER_MEDIA/
MEDIA_UPLOAD_IN_PROGRESS/SELLER_MEDIA_CHANGED; 502 AIRTABLE_UNAVAILABLE/
CLOUDINARY_UNAVAILABLE; 503 ACTIVATION_UNAVAILABLE; unexpected failures use
500 INTERNAL_ERROR. Responses have no-store and nosniff headers. Upstream seller
lookup errors are sanitized before entering the existing resolver's logger.

## Operational limits to confirm before use

- Confirm the reciprocal field is named `Seller Media`, and `updated_at` is a
  writable Airtable date/time field accepting an ISO timestamp. No live schema
  was queried during implementation.
- Concurrent saves for the same seller are rejected within one Node process.
  Multiple processes or external Airtable writers require shared coordination
  for strict uniqueness: Airtable does not offer atomic unique create here.
- Cloudinary and Airtable do not form a transaction. A partial upload failure or
  Airtable failure can leave orphaned assets or already overwritten assets while
  Airtable still contains previous URLs. The route returns an error, never a false
  success; no rollback is attempted, since destroying stable IDs could delete
  previously valid seller media. A retry uploads to the same stable IDs.
- URLs are Cloudinary delivery URLs; endpoint authentication does not make these
  media URLs private. No new Cloudinary access-control mode is introduced.

Offline verification: `node --check sellers/media-service.cjs`,
`node --check sellers/media-routes.cjs`, `node --test sellers/media-routes.test.cjs`,
then `node --test`. Tests never call the real Airtable or Cloudinary APIs.
