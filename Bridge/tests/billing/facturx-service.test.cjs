'use strict';
require('./support/offline.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { createFacturxService } = require('../../billing/facturx-service.cjs');
const { registerFacturxRoutes } = require('../../billing/facturx-routes.cjs');
const { scenarios, loadFixture } = require('./support/fixture-loader.cjs');
const { runFixture } = require('./support/run-fixture.cjs');
const builders = require('../../billing/invoice-builders.js');
const { persistedInvoiceBuilder } = require('../../billing/facturx-build.cjs');
const { createFakeAirtable, invoiceExpectations } = require('./support/fake-airtable.cjs');

for (const scenario of scenarios) test('post-persist builder dispatch '+scenario, async () => {
  const {input,expectedInvoice}=loadFixture(scenario);
  const fake=createFakeAirtable(invoiceExpectations(input));
  let captured;
  const service=createFacturxService({enabled:true,getSellerConfig:async()=>input.sellerConfig,
    buildInvoice:persistedInvoiceBuilder(fake.base),logger:{error(){}},run:async folder=>{
      captured=JSON.parse(await fs.readFile(path.join(folder,'invoice.json')));
      return {accepted:false};
    }});
  try {
    const job=service.submitPayment(input.paymentFields,input.sellerSlug);
    assert.equal(job.state,'pending');await service.drain();fake.assertDone();
    assert.deepEqual(captured,expectedInvoice);
    assert.equal((await service.lookup(job.id)).state,'failed');
  } finally {await service.close();}
});

// Unit boundary: fake worker tests orchestration, never establishes PDF/A validity.
for (const scenario of scenarios) test('service preserves builder snapshot '+scenario, async () => {
  const { input, expectedInvoice } = loadFixture(scenario);
  const invoice = await runFixture(builders, input);
  const logs = [];
  const service = createFacturxService({ enabled: true, logger: {error: (...args) => logs.push(args)},
    getSellerConfig: async slug => { assert.equal(slug, input.sellerSlug); return input.sellerConfig; },
    run: async folder => {
      assert.deepEqual(JSON.parse(await fs.readFile(path.join(folder,'invoice.json'))), expectedInvoice);
      assert.deepEqual(JSON.parse(await fs.readFile(path.join(folder,'seller.json'))), input.sellerConfig);
      await fs.mkdir(path.join(folder,'output'));
      await fs.writeFile(path.join(folder,'output/factur-x.pdf'), '%PDF-test-double');
      return {accepted:true,pdfa:{status:'pass'},cii:{accepted:true}};
    } });
  try {
    const job = service.submit(invoice, input.sellerSlug);
    assert.equal(job.state, 'pending');
    await service.drain();
    const result = await service.lookup(job.id);
    assert.equal(result.state, 'ready');
    assert.equal(result.pdf.toString(), '%PDF-test-double');
    assert.deepEqual(invoice, expectedInvoice);
    assert.deepEqual(logs, []);
  } finally { await service.close(); }
});

test('worker/config/validation errors never propagate to payment caller', async () => {
  const {input, expectedInvoice: invoice} = loadFixture('b2b-normal');
  for (const stage of ['config', 'worker', 'validation']) {
    const logs = [];
    const service = createFacturxService({ enabled:true, logger:{error: (...args)=>logs.push(args)},
      getSellerConfig: async () => { if(stage==='config') throw Error('config unavailable'); return input.sellerConfig; },
      run: async () => { if(stage==='worker') throw Error('worker unavailable'); return {accepted:false,cii:{en16931:{status:'blocked'}},pdfa:{status:'pass'}}; } });
    try {
      const job=service.submit(invoice,input.sellerSlug);
      assert.equal(job.state,'pending');
      await service.drain();
      assert.equal((await service.lookup(job.id)).state,'failed');
      assert.ok(logs.length);
    } finally { await service.close(); }
  }
});

test('disabled, bounded queue, expiry and invalid seller', async () => {
  const {input, expectedInvoice: invoice} = loadFixture('b2c-normal');
  assert.deepEqual(createFacturxService({getSellerConfig(){throw Error('forbidden');}}).submit(invoice,input.sellerSlug),{state:'disabled'});
  let clock=0;
  const service=createFacturxService({enabled:true,maxPending:1,ttlMs:1,now:()=>clock,logger:{error(){}},getSellerConfig:async()=>null,run:async()=>{throw Error('forbidden');}});
  try {
    assert.equal(service.submit(invoice,'another-seller').state,'failed');
    const job=service.submit(invoice,input.sellerSlug);
    assert.equal(service.submit(invoice,input.sellerSlug).state,'failed');
    await service.drain(); clock=2;
    assert.equal(await service.lookup(job.id),null);
    assert.equal(await service.lookup('../../invoice'),null);
  } finally {await service.close();}
});

test('download requires bearer credential and only serves ready jobs', async () => {
  const routes={}; const token='x'.repeat(64);
  const service={submit:()=>({id:'a'.repeat(64),state:'pending'}),lookup:async id=>id==='ready'?{state:'ready',pdf:Buffer.from('%PDF-test-double')}:id==='failed'?{state:'failed'}:null};
  registerFacturxRoutes({post:(p,...h)=>routes[p]=h,get:(p,...h)=>routes[p]=h},{service,token});
  async function request(id,auth) {
    const response={headers:{},setHeader(k,v){this.headers[k]=v;},status(s){this.code=s;return this;},json(v){this.body=v;return this;},send(v){this.body=v;return this;}};
    const handlers=routes['/internal/facturx/:id']; let allowed=false;
    handlers[0]({headers:{authorization:auth}},response,()=>allowed=true);
    if(allowed) await handlers[1]({params:{id}},response);
    return response;
  }
  assert.equal((await request('ready','')).code,401);
  assert.equal((await request('ready','Bearer wrong')).code,401);
  assert.equal((await request('missing','Bearer '+token)).code,404);
  assert.equal((await request('failed','Bearer '+token)).code,422);
  const ready=await request('ready','Bearer '+token);
  assert.equal(ready.code,200);
  assert.equal(ready.headers['Cache-Control'],'no-store');
  assert.equal(ready.headers['Content-Type'],'application/pdf');
});
