# Activation vendeur bêta — backend uniquement

Routes montées dans server.js après express.json et l'initialisation de la base Airtable existante. Table utilisée : NovaPulse Sellers. Champ texte de recherche : Seller_id (S majuscule). Aucun fichier frontend, média, config.json ou schéma Airtable modifié.

## Configuration

Définir SELLER_ACTIVATION_SECRET dans l'environnement du processus : secret aléatoire dédié d'au moins 32 octets. Le module de signature lit uniquement process.env ; il ne charge aucun .env. Le secret n'est jamais retourné ni journalisé. Ne pas réutiliser SELLER_CONFIG_ADMIN_TOKEN ou FACTURX_SERVICE_TOKEN. Une absence ou longueur insuffisante produit 503.

Le contrôle administrateur réutilise SELLER_CONFIG_ADMIN_TOKEN via le chargeur seller-config/env.cjs et le même mécanisme SHA-256 + timingSafeEqual que seller-config/routes.cjs. Les accès Airtable utilisent la base déjà initialisée du Bridge (AIRTABLE_API_KEY, AIRTABLE_BASE_ID).

## Token

Format propriétaire versionné : v1.<payload JSON encodé base64url>.<HMAC-SHA256 encodé base64url>.

La signature couvre exactement v1.<payload>. Ce n'est pas un JWT. Le payload contient seller_id, scope="seller_activation" et exp (secondes Unix, création + 86400). Il est signé, pas chiffré. Le token est réutilisable pendant 24 heures ; aucune révocation individuelle n'est implémentée. Changer le secret invalide tous les tokens existants.

## POST /admin/seller-activation-token

Header X-NovaPulse-Admin-Token obligatoire. Body JSON : {"seller_id":"mon-seller-id"}.

Recherche exactement un vendeur par Seller_id avant émission : zéro → 404, plusieurs → 409. Réponse 200 : {"ok":true,"seller_id":"mon-seller-id","activation_token":"...","expires_in":86400}. Token admin incorrect/absent/non configuré → 403.

Identifiants autorisés : 1 à 128 caractères, premier caractère alphanumérique puis lettres ASCII, chiffres, tirets et underscores. Ce contrat évite aussi l'injection dans la formule Airtable. Les résultats sont comparés strictement à l'identifiant demandé ; aucun fallback.

## PUT /sellers

Header Authorization: Bearer <activation_token>.

Signature et expiration invalides → 401 ; scope incorrect → 403. seller_id est extrait uniquement des claims signés. Si présent dans le body, il doit être identique, sinon 403 ; il n'est jamais écrit.

Liste exclusive des champs modifiables : company_name, legal_name, legal_status, siren, siret, address, postal_code, city, country, email, phone, vat_status, vat_number, default_vat_rate, calendly.

country et email valides sont requis à chaque appel. Les autres champs omis restent inchangés. Chaînes limitées à 2000 caractères et espaces externes supprimés. default_vat_rate accepte un nombre ou une chaîne numérique non vide et est converti en nombre fini positif ou nul. Calendly peut être vide ; sinon URL HTTPS sur calendly.com sans identifiants ni port non standard. Les champs inconnus/sensibles sont refusés avec 400, notamment activation_status, config_generated, created_at, updated_at, pwa_client.

Nouvelle recherche du seller_id signé dans le champ Airtable Seller_id : zéro → 404 ; plusieurs → 409 ; exactement un → update du Record ID trouvé, puis 200 {"ok":true,"seller_id":"..."}. Aucun create, aucun upsert créateur. Erreur Airtable → 502 avec code fixe, erreur inattendue → 500 sans détail interne. Cache-Control: no-store sur les réponses des routes.

updated_at n'est pas écrit : aucune convention correspondante n'a été trouvée dans le serveur inspecté. activation_status et config_generated ne changent pas. Les écritures concurrentes ne créent pas de doublons puisque la route ne crée jamais ; les modifications manuelles concurrentes du schéma ou de l'identité restent hors transaction Airtable.

## Vérification

node --test sellers/routes.test.cjs seller-config/env.test.cjs seller-config/generator.test.cjs seller-config/routes.test.cjs
node --check server.js

Tests HTTP sur Express éphémère et Airtable simulé : aucun accès à la base réelle et aucun démarrage du Bridge complet. Le faux Airtable n'offre pas de méthode create.

Les prospects avec Seller_id vide sont ignorés lors de la recherche. Aucun fallback vers seller_label, seller_slug, email, topic_id ou l’ancien champ seller_id. Le token et le body admin gardent la clé seller_id en minuscules. Seller_id et les champs de liaison sont interdits dans le payload de mise à jour.
