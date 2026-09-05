'use strict';
// Loaded before tests/capture. Never start the production application here.
const deny = () => { throw new Error('BILLING_OFFLINE: network access forbidden'); };
for (const name of ['node:http', 'node:https']) {
  const mod = require(name);
  mod.request = deny;
  mod.get = deny;
}
const net = require('node:net');
net.connect = deny;
net.createConnection = deny;
net.Socket.prototype.connect = deny;
require('node:tls').connect = deny;
globalThis.fetch = deny;
