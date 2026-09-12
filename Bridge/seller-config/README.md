# Configuration depuis un client PWA

Entrée backend : `generateConfigForPwaClient(pwaClientRecordId)`. Aucun usage de seller_id ni de seller_slug pour résoudre un client ou cloisonner les données. Le JSON public conserve sa structure. Aucun appel réel ni changement de schéma Airtable n'a été effectué pour cette modification.

## Liaisons et lectures

Les valeurs des champs liés sont des tableaux de Record IDs. Airtable crée automatiquement le lien réciproque : https://support.airtable.com/articles/3370222027-linking-records-in-airtable . Ces liens suffisent ; aucun champ formule RECORD_ID() ou lookup supplémentaire n'est nécessaire.

Le module lit exclusivement des enregistrements individuels avec `table.find(recordId)` :

1. `PWA Clients` par le Record ID d'entrée.
2. Le seul Record ID contenu dans son champ réciproque `NovaPulse Sellers`.
3. Vérification que `NovaPulse Sellers.pwa_client` contient exactement le client demandé.
4. Lecture des IDs présents dans les champs réciproques `Services 2`, `Digital Products`, `Seller Media` du profil vendeur.
5. Vérification que chaque champ enfant `Seller` contient exactement le Record ID du profil courant, y compris pour les éléments inactifs.
6. Omission des services/produits inactifs et tri par `sort_order` croissant (absent : 0, égalité : Record ID), uniquement parmi les enregistrements liés déjà vérifiés.

Aucun parcours de table, aucune comparaison aux libellés affichés des liens, aucun fallback. Les anciens champs seller_id peuvent subsister et même être identiques entre clients : ils sont ignorés.

Les noms réciproques ci-dessus sont des valeurs par défaut à vérifier dans l'interface Airtable : ils peuvent avoir été renommés. Les quatre liens avant confirmés sont `NovaPulse Sellers.pwa_client`, `Services.Seller`, `Digital Products.Seller`, `Seller Media.Seller`. Si leurs champs réciproques portent d'autres noms, passer leurs noms exacts avec `reverseLinks` (voir ci-dessous). Ne pas créer de nouveaux liens parallèles ; utiliser les réciproques des liens existants. Le module ne tente pas de deviner un champ alternatif.

## Cardinalités et erreurs

- Un client doit avoir exactement un profil vendeur lié.
- Ce profil doit avoir exactement ce client dans pwa_client.
- Chaque service, produit ou média doit avoir exactement ce vendeur dans Seller.
- Services et produits : champ réciproque absent ou tableau vide → tableau JSON vide. Si tous les éléments liés sont inactifs, le tableau généré est également vide.
- Médias : champ réciproque absent ou tableau vide → logo et médias internes vides. Plusieurs lignes restent une erreur. Si la ligne liée n'a pas d'avatar, logo vaut une chaîne vide.
- Record ID invalide, lien dupliqué, enregistrement introuvable, réponse étrangère ou erreur réseau : échec complet, sans JSON partiel ni repli vers un autre profil.

Le module ne crée ni profil ni slug. Le passage PWA Client → NovaPulse Seller → slug final conserve les Record IDs comme références. L'identité d'entrée ne constitue pas une autorisation : un futur appel depuis une route devra contrôler les droits du client authentifié. Les lectures Airtable ne sont pas une transaction ; une modification simultanée des liens peut faire échouer les contrôles et nécessiter de relancer la génération.

## Premier test réel

Variables : `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `SELLER_CONFIG_ADMIN_TOKEN`. `process.env` a toujours priorité. En développement, le module lit facultativement `seller-config/.env` pour les valeurs manquantes, sans modifier process.env ni lire de .env parent. En production (`NODE_ENV=production`) ou sur Render (`RENDER=true`), aucun fichier .env n’est lu ni requis. L’ancien alias `BASE_ID` reste accepté uniquement dans le fichier local pour compatibilité. `TABLE_NAME` n’est pas utilisé. Le jeton Airtable doit autoriser la lecture des cinq tables. Le .env local est ignoré par Git et n’a pas été modifié.

Depuis Bridge, remplacer la valeur ci-dessous par le véritable Record ID d'un client PWA dont le profil vendeur est lié (les collections enfants peuvent être vides) :

```powershell
node seller-config/index.cjs recXXXXXXXXXXXXXX
```

Le résultat JSON est affiché sur stdout, sans écriture de fichier ni modification Airtable. Les erreurs sont résumées sur stderr sans URL de requête ni credentials ; code de sortie 1.

Usage backend :

```js
const { generateConfigForPwaClient } = require('./seller-config/index.cjs');
const config = await generateConfigForPwaClient('recXXXXXXXXXXXXXX');
```

Si les champs réciproques sont renommés :

```js
const { createSellerConfigGenerator } = require('./seller-config/index.cjs');
const generator = createSellerConfigGenerator({
  reverseLinks: {
    seller: 'Nom exact du lien réciproque dans PWA Clients',
    services: 'Nom exact du lien réciproque Services dans NovaPulse Sellers',
    products: 'Nom exact du lien réciproque Digital Products dans NovaPulse Sellers',
    media: 'Nom exact du lien réciproque Seller Media dans NovaPulse Sellers',
  },
});
const { config, media, pwaClientRecordId, sellerRecordId } =
  await generator.generatePwaClientResult('recXXXXXXXXXXXXXX');
console.log(JSON.stringify(config, null, 2));
```

L'option `base` permet aussi d'injecter une instance SDK backend ou une doublure de test. Les lookups scalaires à une valeur sont acceptés ; plusieurs valeurs provoquent une erreur. Les médias acceptent une URL ou la première pièce jointe Airtable, sans copie physique. Les vidéos restent dans le résultat interne `media`, hors JSON. `meta.validated` reste la constante true demandée.

## Tests hors ligne

```powershell
node --test seller-config/generator.test.cjs
```

24 tests vérifient deux clients et deux vendeurs, les lectures limitées aux liens, les anciens identifiants identiques ignorés, les liens multiples/étrangers/vides, les enregistrements absents, le mapping, le tri, les médias, les erreurs réseau et les noms réciproques personnalisés. Le faux client n'expose aucune méthode de lecture globale ou de mutation.

`pwa-client.example.json` est l'exemple complet fictif contrôlé par les tests. Il remplace l'ancien exemple novapulse-ceo et ne représente aucun vendeur réel.

## Route de téléchargement protégée

`GET /seller-config/:pwaClientRecordId` est monté juste après la création d'Express dans `server.js`, avant les routes métier, par `registerSellerConfigRoutes`. Aucun autre comportement du serveur n'est modifié.

Ajouter `SELLER_CONFIG_ADMIN_TOKEN` avec un secret long et aléatoire dans `seller-config/.env` pour le développement. Sur Render, cette variable peut être définie dans l'environnement du service ; elle a priorité sur la valeur du fichier dédié. Une valeur absente ou vide interdit l'accès. Le fichier .env existant n'a pas été modifié automatiquement et aucun secret n'est fourni par le code.

Le client doit envoyer `X-NovaPulse-Admin-Token`. La comparaison utilise des empreintes SHA-256 comparées en temps constant. Ce secret donne un accès administratif à tous les profils : le conserver côté administration, jamais dans la PWA ni dans l'URL. L'ouverture directe d'un lien dans la barre d'adresse n'envoie pas ce header et reçoit donc 403.

Succès : HTTP 200, `Content-Type: application/json`, `Content-Disposition: attachment; filename="config.json"`, `Cache-Control: no-store`. Le serveur sérialise en mémoire et n'écrit aucun fichier. Erreurs JSON sans header de téléchargement :

| Statut | Cas |
|---|---|
| 403 | Token absent, incorrect ou non configuré côté serveur |
| 400 | Identifiant d'entrée invalide, notamment slug ou email |
| 404 | Client/enregistrement lié introuvable, ou profil vendeur absent |
| 409 | Lien multiple alors qu'un seul enregistrement est attendu |
| 502 | Erreur de lecture Airtable, hors enregistrement introuvable |
| 500 | Autre erreur de génération ou incohérence des données |

Les réponses d'erreur sont fixes : aucun message brut Airtable, token, clé ou identifiant de base n'est journalisé par cette route.

Depuis Bridge, pour tester seulement cette route sans lancer les autres services du Bridge, ouvrir un terminal :

```powershell
node -e "const app=require('express')();require('./seller-config/routes.cjs').registerSellerConfigRoutes(app);app.listen(10000,'127.0.0.1')"
```

Dans un second terminal PowerShell, saisir le même token que celui configuré sur le serveur sans le placer dans l'historique :

```powershell
$adminSecret = Read-Host 'Token administration' -AsSecureString
$adminCredential = [System.Net.NetworkCredential]::new('', $adminSecret)
Invoke-WebRequest -Uri 'http://127.0.0.1:10000/seller-config/recbp4DCJy9DuN30j' -Headers @{ 'X-NovaPulse-Admin-Token' = $adminCredential.Password } -OutFile './config.json'
Remove-Variable adminCredential, adminSecret
```

Cette commande sauvegarde le téléchargement sur le poste client, pas sur le serveur. Pour tester le Bridge complet, utiliser son démarrage habituel avec ses variables existantes ; son port par défaut est 10000, surchargeable par PORT.

Après déploiement : `https://<service-bridge>.onrender.com/seller-config/<pwaClientRecordId>`, avec le même header et HTTPS. Aucun déploiement n'a été réalisé dans ce chantier. Sur Render, définir directement les trois variables dans l’environnement du service. Aucun fichier .env ne doit être déployé.

Suite complète :

```powershell
node --test seller-config/env.test.cjs seller-config/generator.test.cjs seller-config/routes.test.cjs
```

45 tests : 7 tests de configuration environnement, 24 tests du générateur et 14 tests HTTP sur un serveur Express local éphémère avec Airtable simulé, sans exécution du Bridge complet, sans appel Airtable réel et sans écriture de configuration sur disque.

## Serveur de développement isolé

Depuis Bridge :

```powershell
node seller-config/dev-server.cjs
```

Écoute uniquement sur `127.0.0.1:10001`. Ce point d'entrée de développement charge exclusivement `seller-config/.env`, par chemin relatif au module, et utilise ses trois variables à la place des éventuelles valeurs héritées du shell. Il refuse de démarrer si l'une manque. Il ne charge pas server.js ni le .env principal, et monte uniquement la route seller-config. Ctrl+C arrête le serveur. Le comportement de production reste inchangé.

Dans un second terminal, la commande suivante suppose que le token est déjà disponible dans `$env:SELLER_CONFIG_ADMIN_TOKEN` :

```powershell
Invoke-WebRequest `
  -Uri "http://localhost:10001/seller-config/recbp4DCJy9DuN30j" `
  -Headers @{ "X-NovaPulse-Admin-Token" = $env:SELLER_CONFIG_ADMIN_TOKEN } `
  -OutFile "./config.json"
```

Le chargement du .env par Node ne renseigne pas l'environnement du terminal PowerShell. Si le token n'y est pas défini, utiliser la saisie sécurisée montrée plus haut (`Read-Host -AsSecureString`) et `$adminCredential.Password` dans le header, en adaptant le port à 10001. Le fichier téléchargé est écrit par le client PowerShell uniquement.

Vérification effectuée : démarrage isolé sur 10001 et refus HTTP 403 sans token, puis arrêt du processus de test. Aucun appel Airtable n'est nécessaire pour cette vérification.
