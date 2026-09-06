'use strict';
require('./support/offline.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { mapSellerConfig } = require('../../billing/facturx-config.cjs');
const { createFacturxService } = require('../../billing/facturx-service.cjs');
const { registerFacturxRoutes } = require('../../billing/facturx-routes.cjs');
const { scenarios, loadFixture } = require('./support/fixture-loader.cjs');
const { configuredFixture } = require('./support/facturx-config-fixture.cjs');

for (const scenario of scenarios) test('config maps without mutating invoice: '+scenario, () => {
  const {input,expectedInvoice:invoice}=loadFixture(scenario);
  const {config,context}=configuredFixture(input);
  const before=structuredClone({invoice,config,context});
  const result=mapSellerConfig(invoice,config,context);
  assert.deepEqual(result.sellerConfig.company,config.company);
  if(scenario.startsWith('b2b')) {
    assert.equal(result.context.business_process_id,config.facturx.business_process_by_type[invoice.invoice_type]);
    assert.deepEqual(result.context.buyer_electronic_address,context.buyer_electronic_address);
    assert.deepEqual(result.sellerConfig.facturx.b2b_notes,config.facturx.b2b_notes);
  } else {
    assert.deepEqual(result.context,{});
    assert.equal(result.sellerConfig.facturx,undefined);
  }
  assert.deepEqual({invoice,config,context},before);
});

for (const kind of ['normal','deposit','balance']) {
  const paths = [['config','company'],['config','facturx','seller_electronic_address','value'],
    ['config','facturx','seller_electronic_address','scheme_id'],['config','facturx','business_process_by_type',kind],
    ...['PMT','PMD','AAB'].map(c=>['config','facturx','b2b_notes',c]),['config','facturx','payment_date_convention'],
    ['context','buyer_electronic_address','value'],['context','buyer_electronic_address','scheme_id']];
  for(const path of paths) test('B2B '+kind+' refuses and logs missing '+path.join('.'),async()=>{
    const {input,expectedInvoice:invoice}=loadFixture('b2b-'+kind);
    const source=configuredFixture(input);
    let target=source; for(const key of path.slice(0,-1)) target=target[key]; delete target[path.at(-1)];
    const messages=[];let workerCalled=false;
    const service=createFacturxService({enabled:true,getSellerConfig:async()=>source.config,
      logger:{error:(...a)=>messages.push(a.join(' '))},run:async()=>{workerCalled=true;throw Error('must not run');}});
    try {
      const job=service.submit(invoice,input.sellerSlug,source.context);
      assert.equal(job.state,'pending');await service.drain();
      const result=await service.lookup(job.id);
      assert.equal(result.state,'failed');assert.equal(result.error.code,'FACTURX_CONFIG_MISSING');
      const field=path[0]==='config'?path.slice(1).join('.'):path.join('.');
      assert.ok(result.error.fields.some(v=>v.startsWith(field)));
      assert.ok(messages.some(v=>v.includes(field)));assert.equal(workerCalled,false);
      assert.equal(input.paymentFields.Status,'Paid');
    } finally {await service.close();}
  });
}

test('all missing B2B fields are collected together',()=>{
  const {input,expectedInvoice:invoice}=loadFixture('b2b-normal');
  assert.throws(()=>mapSellerConfig(invoice,input.sellerConfig,{}),error=>{
    assert.equal(error.fields.length,9);
    return error.fields.some(v=>v.includes('PMT')) && error.fields.some(v=>v.includes('buyer_electronic_address'));
  });
});
test('public buyer directory never supplies BT49 or reaches Python',()=>{
  const {input,expectedInvoice:invoice}=loadFixture('b2b-normal');const {config,context}=configuredFixture(input);
  config.facturx.buyer_electronic_addresses={['siret:'+invoice.buyer.siret]:context.buyer_electronic_address};
  assert.throws(()=>mapSellerConfig(invoice,config,{}),/context.buyer_electronic_address/);
  const result=mapSellerConfig(invoice,config,context);
  assert.equal(result.sellerConfig.facturx.buyer_electronic_addresses,undefined);
});
test('process must come from seller config even if context supplies one',()=>{
  const {input,expectedInvoice:invoice}=loadFixture('b2b-normal');const {config,context}=configuredFixture(input);
  context.business_process_id='S2';delete config.facturx.business_process_by_type.normal;
  assert.throws(()=>mapSellerConfig(invoice,config,context),/business_process_by_type.normal/);
});
test('blank values and unsupported convention/process are rejected',()=>{
  const {input,expectedInvoice:invoice}=loadFixture('b2b-normal');const {config,context}=configuredFixture(input);
  config.facturx.b2b_notes.PMD='  ';config.facturx.business_process_by_type.normal='S1';config.facturx.payment_date_convention='invoice_date';
  assert.throws(()=>mapSellerConfig(invoice,config,context),error=>error.fields.length===3);
});
test('private BT49 is forwarded only through authenticated internal payment route',()=>{
  const routes={};let received;const context={buyer_electronic_address:{value:'buyer@example.test',scheme_id:'EM'}};
  registerFacturxRoutes({post:(p,...h)=>routes[p]=h,get(){}},{token:'t'.repeat(64),service:{submitPayment:(...args)=>{received=args;return {id:'job'};}}});
  const req={headers:{authorization:'Bearer '+'t'.repeat(64)},body:{paymentFields:{Status:'Paid'},sellerSlug:'seller',context}};
  const res={setHeader(){},status(){return this;},json(){}};let allowed=false;
  const [auth,handler]=routes['/internal/facturx/payment'];auth(req,res,()=>allowed=true);assert.ok(allowed);handler(req,res);
  assert.deepEqual(received,[req.body.paymentFields,'seller',context]);
});
