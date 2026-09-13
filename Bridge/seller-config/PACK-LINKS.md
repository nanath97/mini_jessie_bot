# Liens temporaires de téléchargement

Variables à ajouter manuellement sur Render :

- `SELLER_PACK_LINK_SECRET` : secret HMAC aléatoire indépendant, au moins 32 octets,
  uniquement sur Render. Ne jamais le transmettre à Airtable.
- `SELLER_PACK_AUTOMATION_SECRET` : autre secret aléatoire indépendant, au moins
  32 octets, sur Render et dans les secrets Airtable Automation.

Aucun fichier env n'est créé/modifié par le code. Ni SELLER_CONFIG_ADMIN_TOKEN
ni SELLER_ACTIVATION_SECRET ne sont utilisés par ce mécanisme.

## Création depuis Airtable Automation

POST `https://mini-jessie-bot-1.onrender.com/seller-pack-link`

Headers : `Content-Type: application/json` et
`X-NovaPulse-Automation-Token: <SELLER_PACK_AUTOMATION_SECRET>`.

Body exact : `{ "pwaClientRecordId": "recXXXXXXXXXXXXXX" }`.
Tout champ supplémentaire ou query est refusé. JSON limité à 1 KiB, lu après
authentification. Cette route ne lit pas Airtable et ne génère pas de ZIP : elle
valide le format de l'ID, pas l'existence du client.

Réponse 200 : `{ "ok": true, "download_url": "https://mini-jessie-bot-1.onrender.com/seller-pack-download/<token>", "expires_in": 86400 }`.
Utiliser download_url dans le lien de l'email. Aucun header admin n'est nécessaire
pour ouvrir ce lien. Aucune automation/email n'a été créée ou envoyée ici.

## Token et téléchargement

Format `v1.<payload JSON base64url>.<HMAC-SHA256 base64url>`.
Le HMAC porte sur `v1.<payload>`.
Payload : `{ "pwa_client_record_id": "rec...", "exp": <Unix secondes + 86400>, "scope": "seller_pack_download" }`.
Le payload est lisible, pas chiffré; il ne contient aucun secret.

GET `/seller-pack-download/:token` vérifie signature en temps constant, ID,
expiration et scope avant le builder. L'identité query/body est ignorée.
La réponse ZIP et les limites réseau/mémoire sont celles du seller-pack existant.
Le serveur principal injecte le même builder dans les deux routes de téléchargement,
conservant une seule génération simultanée. La route admin existante conserve
son authentification et son contrat.

Headers : `Content-Type: application/zip`,
`Content-Disposition: attachment; filename="seller-pack.zip"`,
`Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`.

Erreurs de lien : `{ "ok": false, "error": "CODE" }` avec 400 INVALID_PAYLOAD/
INVALID_CLIENT_ID, 401 INVALID_TOKEN (dont expiration), 403 FORBIDDEN/INVALID_SCOPE,
503 PACK_LINK_UNAVAILABLE/PACK_AUTOMATION_UNAVAILABLE (secret absent ou trop court).
Les erreurs du builder conservent ses statuts et JSON nettoyés, sans header ZIP.

Le lien est un accès transmissible au pack pendant 24 heures, réutilisable et sans
révocation individuelle en V1. Rotation du secret HMAC invalide tous les anciens
liens. Les scanners de liens email peuvent lancer une génération; ce n'est pas
un mécanisme single-use. Le code ne journalise ni URL ni token. Les éventuels logs
d'accès de Render/proxy restent à configurer séparément pour masquer le chemin
`/seller-pack-download/*` si ces logs sont activés.

Tests sans réseau externe : `node --test seller-config/pack-link.test.cjs`.
