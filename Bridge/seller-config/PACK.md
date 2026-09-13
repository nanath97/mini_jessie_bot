# Export manuel seller-pack

`GET /seller-pack/:pwaClientRecordId` utilise exactement la même authentification
que `/seller-config/:pwaClientRecordId` : header `X-NovaPulse-Admin-Token`, secret
`SELLER_CONFIG_ADMIN_TOKEN`, comparaison SHA-256 en temps constant. Le helper est
partagé par les deux routes. L'autorisation précède génération et téléchargements.
Ne jamais mettre le token dans une URL ou dans la PWA.

Le builder appelle une fois `generatePwaClientResult(pwaClientRecordId)` : aucun
second resolver, aucun scan Airtable, aucune écriture Airtable. Les trois sources
sont exclusivement `result.media.avatar`, `intro_video`, `beta_video`. Les paramètres
query/body sont ignorés. Aucun slug n'est déduit des anciens champs seller_slug :
le slug présent dans PWA Clients concerne le contexte client, pas nécessairement
le nouvel espace vendeur. Le résultat du générateur ne fournit pas de slug fiable.

## Archive et installation

HTTP 200, `Content-Type: application/zip`,
`Content-Disposition: attachment; filename="seller-pack.zip"`,
`Cache-Control: no-store`, `X-Content-Type-Options: nosniff`.

```text
seller-pack/
  config.json
  avatar.jpg
  Intro.mp4
  beta-video.mp4
```

La conversion avatar en JPEG via Cloudinary a été explicitement retenue par Nathan.
On ajoute `f_jpg/` dans le chemin de livraison `image/upload/`, puis on vérifie le
MIME JPEG et ses marqueurs binaires. Il ne s'agit pas de renommer un PNG en JPG.
Référence : https://cloudinary.com/documentation/transformation_reference#f_format

Extraire puis copier **le contenu** de seller-pack dans le dossier
`public/sellers/<slug réel déjà attribué>/` de la PWA. Ne pas copier un sous-dossier
seller-pack supplémentaire. Le slug et la publication restent des étapes manuelles.
La PWA charge directement `/sellers/<slug>/avatar.jpg`, `Intro.mp4` et
`beta-video.mp4`, indépendamment de config.json.

Le JSON exporté est strictement celui du générateur : `company.logo` reste son URL
Cloudinary, faute de slug fiable pour construire un chemin absolu local. Une URL
relative comme avatar.jpg ne serait pas résolue relativement au fichier JSON par
le navigateur. Aucune clé vidéo n'est ajoutée. Aucune mutation du résultat source.
Le pack contient les trois médias localement mais **ne rend pas tous les liens du
config autonomes** : company.logo et les images/liens de produits restent distants.
Les autres ressources statiques de la PWA (notamment logos/*.svg) ne sont pas incluses.

## Réseau, ressources et erreurs

- HTTPS uniquement, hôte exact `res.cloudinary.com`, chemin image/upload ou
  video/upload selon le média. Aucun user/password, query, fragment ou port non
  standard. Les domaines Cloudinary personnalisés ne sont pas acceptés.
- Redirections interdites (`redirect: error`), y compris vers un autre hôte.
  Aucun appel à une URL fournie dans la requête HTTP; aucun header admin ou secret
  Cloudinary/Airtable n'est transmis aux téléchargements.
- Trois téléchargements séquentiels, délai maximal de 60 secondes chacun couvrant
  headers et lecture du corps, puis abort. Un seul build simultané par builder
  (une instance montée en production); les suivants reçoivent 409 PACK_BUSY.
- Avatar JPEG : 2 MiB; chaque MP4 : 50 MiB. Vérification de Content-Length s'il
  existe et comptage réel des octets même sans cet en-tête. Corps vide refusé.
  MIME strict et contrôle de signature JPEG/boîte ftyp MP4. Pas de décodage complet,
  ni nouvelle vérification de durée/dimensions.
- Config : 1 MiB; ZIP : 104 MiB. Les plafonds de médias totalisent 102 MiB.
  Buffers temporaires en mémoire, sans disque Render; mémoire de pointe supérieure
  au ZIP (médias, fragments et buffers assemblés), de l'ordre de quelques centaines
  de MiB au maximum des tailles autorisées. Prévoir cette marge dans l'instance.
- ZIP via yazl 3.3.1 (nouvelle dépendance, aucune bibliothèque ZIP préexistante),
  entrées STORE sans recompression coûteuse de JPEG/MP4. Noms fixes sans chemin
  fourni par le client. CRC et structure ZIP contrôlés par les tests.
- Toute la génération finit avant l'ajout des headers ZIP. Échec : JSON fixe
  `{ "error": "CODE", "message": "message nettoyé" }`, aucun ZIP partiel.

Codes HTTP : 403 FORBIDDEN; 400 INVALID_CLIENT_ID; 404 RECORD_NOT_FOUND ou
SELLER_NOT_FOUND; 409 LINK_CONFLICT ou PACK_BUSY; 502 AIRTABLE_ERROR,
INVALID_MEDIA_URL, MEDIA_DOWNLOAD_FAILED, INVALID_MEDIA_CONTENT, MEDIA_TOO_LARGE,
PACK_TOO_LARGE; 504 MEDIA_TIMEOUT; 500 PACK_GENERATION_FAILED.

Les trois médias sont obligatoires pour un pack, même si le générateur config seul
accepte une collection média vide. Un échec de conversion Cloudinary (par exemple
transformation non autorisée par le compte) entraîne une erreur propre, sans
fallback vers un fichier au format incorrect.

## Téléchargement manuel

Après démarrage de `node seller-config/dev-server.cjs`, dans un autre PowerShell :

```powershell
$adminSecret = Read-Host 'Token administration' -AsSecureString
$adminCredential = [System.Net.NetworkCredential]::new('', $adminSecret)
Invoke-WebRequest -Uri 'http://127.0.0.1:10001/seller-pack/recXXXXXXXXXXXXXX' -Headers @{ 'X-NovaPulse-Admin-Token' = $adminCredential.Password } -OutFile './seller-pack.zip'
Remove-Variable adminCredential, adminSecret
```

Remplacer le Record ID par celui du vrai PWA Client. Sur le Bridge déployé, utiliser
`https://mini-jessie-bot-1.onrender.com/seller-pack/<pwaClientRecordId>` avec le même
header, seulement après déploiement autorisé. Cette commande écrit sur le poste
de Nathan, pas sur Render. Une barre d'adresse seule ne transmet pas le header.

Tests sans réseau externe :

```powershell
node --test seller-config/env.test.cjs seller-config/generator.test.cjs seller-config/routes.test.cjs
node --test seller-config/pack.test.cjs
node --test
```
