'use strict';
require('./support/offline.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { scenarios, loadFixture } = require('./support/fixture-loader.cjs');
const { runFixture } = require('./support/run-fixture.cjs');
const builders = require('../../billing/invoice-builders.js');
const { createFacturxService, pythonRunner } = require('../../billing/facturx-service.cjs');
const { registerFacturxRoutes } = require('../../billing/facturx-routes.cjs');
const { persistedInvoiceBuilder } = require('../../billing/facturx-build.cjs');
const { createFakeAirtable, invoiceExpectations } = require('./support/fake-airtable.cjs');
const root = path.resolve(__dirname, '../../..');

(async () => {
  assert.ok(process.env.FACTURX_PYTHON, 'Set FACTURX_PYTHON to the isolated Python executable');
  const worker = pythonRunner({root,python:process.env.FACTURX_PYTHON,verapdf:process.env.FACTURX_VERAPDF});
  let pass=0, fail=0, blocked=0;
  for (const scenario of scenarios) {
    const fixture=loadFixture(scenario), input=fixture.input;
    const invoice=await runFixture(builders,input);
    const config=structuredClone(input.sellerConfig), context={};
    if(scenario.startsWith('b2b')) {
      // Confirmed test-only supplements, never production defaults.
      const overlay=JSON.parse(await fs.readFile(path.join(root,'tests/facturx/french-fixtures',scenario+'.json'),'utf8'));
      config.facturx={seller_electronic_address:overlay.seller_endpoint,
        b2b_notes:Object.fromEntries(overlay.notes.map(n=>[n.subject_code,n.content])),
        payment_date_convention:'paid_at_utc_date',business_process_by_type:{[invoice.invoice_type]:overlay.business_process_id}};
      context.buyer_electronic_address=overlay.buyer_endpoint;
      const key=invoice.buyer.siret ? 'siret:'+invoice.buyer.siret : 'email:'+invoice.buyer.email.trim().toLowerCase();
      config.facturx.buyer_electronic_addresses={[key]:overlay.buyer_endpoint};
    }
    let report;
    const fake=createFakeAirtable(invoiceExpectations(input));
    const service=createFacturxService({enabled:true,buildInvoice:persistedInvoiceBuilder(fake.base),getSellerConfig:async slug=>{assert.equal(slug,input.sellerSlug);return config;},
      run:async folder=>{
        report=await worker(folder);
        const ref=path.join(root,'tests/facturx_pdf/fixtures',scenario==='b2b-normal'?'':scenario,'factur-x.xml');
        assert.deepEqual(await fs.readFile(path.join(folder,'output/factur-x.xml')),await fs.readFile(ref));
        return report;
      }});
    try {
      const routes={};const token='offline-test-service-token-never-use-live';
      registerFacturxRoutes({post:(p,...h)=>routes[p]=h,get:(p,...h)=>routes[p]=h},{service,token});
      const response=()=>({setHeader(){},status(code){this.code=code;return this;},json(body){this.body=body;return this;},send(body){this.body=body;return this;}});
      const req={headers:{authorization:'Bearer '+token},body:{paymentFields:input.paymentFields,sellerSlug:input.sellerSlug}};
      const submitted=response();let authorized=false;
      routes['/internal/facturx/payment'][0](req,submitted,()=>authorized=true);assert.ok(authorized);
      routes['/internal/facturx/payment'][1](req,submitted);assert.equal(submitted.code,202);
      await service.drain();
      fake.assertDone();
      const downloaded=response();req.params={id:submitted.body.id};
      routes['/internal/facturx/:id'][0](req,downloaded,()=>{});
      await routes['/internal/facturx/:id'][1](req,downloaded);
      if(report?.accepted) {assert.equal(downloaded.code,200);assert.ok(downloaded.body.subarray(0,5).equals(Buffer.from('%PDF-')));pass++;console.log(scenario,'PASS');}
      else if(report && [report.pdfa,report.cii.en16931,report.cii.br_fr].some(v=>v?.status==='blocked')) {assert.equal(downloaded.code,422);blocked++;console.log(scenario,'BLOCKED: validators unavailable; download refused',report.pdfa);}
      else {fail++;console.error(scenario,'FAIL');}
    } catch(error) {fail++;console.error(scenario,error.message);}
    finally {await service.close();}
  }
  console.log(JSON.stringify({pass,fail,blocked}));process.exitCode=fail?1:blocked?2:0;
})().catch(error=>{console.error(error);process.exitCode=1;});
