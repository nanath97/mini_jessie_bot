'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { once } = require('node:events');
const { readFileSync } = require('node:fs');
const { createRequire } = require('node:module');
const express = require('express');
const { issueClientSessionToken, verifyClientSessionToken } = require('./client-session-token.cjs');
const { verifyActivationToken } = require('./activation-token.cjs');
const { registerActivationStartRoute } = require('./activation-start-routes.cjs');
const A = 'rec00000000000001', B = 'rec00000000000002', S = 'rec00000000000003';
function fake() {
  const clients = new Map([A, B].map(id => [id, { id, fields: {} }]));
  const sellers = new Map(); const writes = []; let fail = false, omitLink = false;
  const base = table => {
    assert.ok(['PWA Clients', 'NovaPulse Sellers'].includes(table));
    const rows = table === 'PWA Clients' ? clients : sellers;
    return {
      async find(id) { if (fail) throw Error('private upstream detail'); if (!rows.has(id)) throw { statusCode: 404 }; return structuredClone(rows.get(id)); },
      select({ filterByFormula }) { return { async all() { const id = /^\{Seller_id\}="([A-Za-z0-9_-]+)"$/.exec(filterByFormula)[1]; return [...rows.values()].filter(row => row.fields.Seller_id === id); } }; },
      async create(fields) { assert.equal(table, 'NovaPulse Sellers'); writes.push(structuredClone(fields)); const id = 'rec' + String(100 + writes.length).padStart(14, '0'); const row = { id, fields }; sellers.set(id, row); if (!omitLink) clients.get(fields.pwa_client[0]).fields['NovaPulse Sellers'] = [id]; return row; },
    };
  };
  return { base, clients, sellers, writes, fail(value) { fail = value; }, omitLink(value) { omitLink = value; } };
}
test('client session and activation start', async t => {
  for (const name of ['PWA_CLIENT_SESSION_SECRET', 'SELLER_ACTIVATION_SECRET']) {
    const prior = process.env[name]; process.env[name] = crypto.randomBytes(32).toString('hex');
    t.after(() => { if (prior === undefined) delete process.env[name]; else process.env[name] = prior; });
  }
  const signed = claims => { const payload = Buffer.from(JSON.stringify(claims)).toString('base64url'); return 'v1.' + payload + '.' + crypto.createHmac('sha256', process.env.PWA_CLIENT_SESSION_SECRET).update('v1.' + payload).digest('base64url'); };
  async function setup(options = {}) {
    const db = fake(); const app = express(); app.use(express.json()); registerActivationStartRoute(app, { base: db.base, ...options });
    const server = app.listen(0, '127.0.0.1'); await once(server, 'listening');
    t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
    const call = async (token = issueClientSessionToken(A), body) => { const res = await fetch('http://127.0.0.1:' + server.address().port + '/seller-activation/start', { method: 'POST', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) }); return { status: res.status, data: await res.json(), cache: res.headers.get('cache-control') }; };
    return { db, call };
  }
  await t.test('session claims last 24 hours', () => { const claims = verifyClientSessionToken(issueClientSessionToken(A)); assert.equal(claims.pwa_client_record_id, A); assert.equal(claims.scope, 'pwa_client_session'); assert.ok(Math.abs(claims.exp - Math.floor(Date.now()/1000) - 86400) <= 1); });
  for (const [name, token, status] of [
    ['missing', '', 401], ['invalid', 'invalid', 401],
    ['tampered', issueClientSessionToken(A).slice(0, -5) + 'aaaaa', 401],
    ['expired', signed({ pwa_client_record_id: A, scope: 'pwa_client_session', exp: 1 }), 401],
    ['scope', signed({ pwa_client_record_id: A, scope: 'other', exp: Math.floor(Date.now()/1000)+100 }), 403],
  ]) await t.test(name, async () => { const {db, call} = await setup(); assert.equal((await call(token)).status, status); assert.equal(db.writes.length, 0); });
  await t.test('missing client 404', async () => { const {db,call}=await setup(); db.clients.delete(A); assert.equal((await call()).status,404); assert.equal(db.writes.length,0); });
  await t.test('create minimal seller, reuse sequentially and isolate clients', async () => {
    const {db,call}=await setup(); const first=await call(); assert.equal(first.status,200); assert.equal(first.cache,'no-store'); assert.equal(first.data.created,true); assert.match(first.data.seller_id,/^sel_[a-f0-9]{32}$/);
    assert.deepEqual(db.writes,[{Seller_id:first.data.seller_id,pwa_client:[A]}]); assert.equal(verifyActivationToken(first.data.activation_token).seller_id,first.data.seller_id);
    assert.deepEqual(Object.keys(first.data).sort(),['activation_token','created','ok','seller_id']);
    const second=await call(); assert.equal(second.data.created,false); assert.equal(second.data.seller_id,first.data.seller_id); assert.equal(db.writes.length,1);
    const other=await call(issueClientSessionToken(B)); assert.equal(other.status,200); assert.notEqual(other.data.seller_id,first.data.seller_id); assert.deepEqual(db.writes[1].pwa_client,[B]);
  });
  await t.test('concurrent requests create once',async()=>{const {db,call}=await setup();const results=await Promise.all([call(),call(),call()]);assert.ok(results.every(r=>r.status===200));assert.equal(new Set(results.map(r=>r.data.seller_id)).size,1);assert.equal(db.writes.length,1);});
  await t.test('multiple reciprocal sellers reject without writes',async()=>{const {db,call}=await setup();db.clients.get(A).fields['NovaPulse Sellers']=[S,B];assert.equal((await call()).status,409);assert.equal(db.writes.length,0);});
  for (const owners of [undefined,[],[B],[A,B]]) await t.test('invalid seller owner '+JSON.stringify(owners),async()=>{const {db,call}=await setup();db.clients.get(A).fields['NovaPulse Sellers']=[S];db.sellers.set(S,{id:S,fields:{Seller_id:'sel_existing',pwa_client:owners}});assert.equal((await call()).status,409);assert.equal(db.writes.length,0);});
  await t.test('existing empty seller ID rejects without creating',async()=>{const {db,call}=await setup();db.clients.get(A).fields['NovaPulse Sellers']=[S];db.sellers.set(S,{id:S,fields:{pwa_client:[A]}});assert.equal((await call()).status,409);assert.equal(db.writes.length,0);});
  await t.test('collision regenerates ID',async()=>{let n=0;const {db,call}=await setup({generateSellerId:()=>++n===1?'sel_taken':'sel_new'});db.sellers.set(S,{id:S,fields:{Seller_id:'sel_taken',pwa_client:[B]}});const result=await call();assert.equal(result.status,200);assert.equal(result.data.seller_id,'sel_new');assert.equal(n,2);});
  await t.test('untrusted body identities rejected',async()=>{const {db,call}=await setup();for(const key of ['seller_id','sellerSlug','email','topic_id','pwa_client_record_id','pwa_client'])assert.equal((await call(undefined,{[key]:B})).status,400);assert.equal(db.writes.length,0);});
  await t.test('upstream errors sanitized',async()=>{const {db,call}=await setup();db.fail(true);const result=await call();assert.equal(result.status,502);assert.equal(result.data.error,'AIRTABLE_UNAVAILABLE');});
  await t.test('unconfirmed creation blocks blind retry',async()=>{const {db,call}=await setup();db.omitLink(true);assert.equal((await call()).status,409);assert.equal((await call()).status,409);assert.equal(db.writes.length,1);});
  await t.test('verified email handler issues session only for actual record',async()=>{
    const source=readFileSync(require.resolve('../server.js'),'utf8'); const start=source.indexOf('app.post("/pwa/verify-login-code"'); const end=source.indexOf('\n});',start)+4;
    let handler; const pwaLoginCodes=new Map(); const email='client@example.com', sellerSlug='coach-test';
    const fields={email,seller_slug:sellerSlug}; let rows=[{id:A,fields}];
    const tablePWA={select(options){assert.equal(options.maxRecords,2);return{async firstPage(){return rows;}};}};
    const getLoginCodeKey=(e,s)=>e+'|'+s;
    new Function('app','normEmail','normSlug','getLoginCodeKey','pwaLoginCodes','tablePWA','crypto','require','console',source.slice(start,end))({post(path,fn){handler=fn;}},v=>v,v=>v,getLoginCodeKey,pwaLoginCodes,tablePWA,crypto,createRequire(require.resolve('../server.js')),{log(){},error(){}});
    const seed=()=>pwaLoginCodes.set(getLoginCodeKey(email,sellerSlug),{codeHash:crypto.createHash('sha256').update('123456').digest('hex'),expiresAt:Date.now()+60000,attempts:0});
    async function run(code){const response={statusCode:200,status(n){this.statusCode=n;return this;},set(){return this;},json(data){this.data=data;return this;}};await handler({body:{email,sellerSlug,code,pwa_client_record_id:B}},response);return response;}
    seed();const result=await run('123456');assert.equal(result.statusCode,200);assert.equal(result.data.success,true);assert.equal(result.data.verified,true);assert.deepEqual(result.data.clientData,fields);assert.equal(verifyClientSessionToken(result.data.client_session_token).pwa_client_record_id,A);
    assert.equal((await run('123456')).statusCode,401);seed();assert.equal((await run('wrong')).statusCode,401);
    seed();rows=[{id:A,fields},{id:B,fields}];assert.equal((await run('123456')).statusCode,409);
  });
  await t.test('missing client secret fails closed',async()=>{const token=issueClientSessionToken(A);const {db,call}=await setup();const saved=process.env.PWA_CLIENT_SESSION_SECRET;delete process.env.PWA_CLIENT_SESSION_SECRET;try{assert.equal((await call(token)).status,503);assert.equal(db.writes.length,0);}finally{process.env.PWA_CLIENT_SESSION_SECRET=saved;}});
});
