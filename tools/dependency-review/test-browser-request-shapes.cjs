'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const {distributionRoles, readOnlyParams} = require('./browser-fixture.cjs');
const call = (method, params) => ({jsonrpc: '2.0', id: 1, method, ...(params === undefined ? {} : {params})});

test('accept only complete distribution pairs in the application lane', () => {
  const baseline = {normal: '/normal', fixture: '/fixture'};
  const upgrade = {...baseline, 'upgrade-normal': '/upgrade-normal', 'upgrade-fixture': '/upgrade-fixture'};
  assert.deepEqual(distributionRoles({profile: 'baseline', distributions: baseline}), ['normal', 'fixture']);
  assert.deepEqual(distributionRoles({profile: 'application', distributions: upgrade}), Object.keys(upgrade));
  assert.throws(() => distributionRoles({profile: 'coherentCandidate', distributions: upgrade}));
  assert.throws(() => distributionRoles({profile: 'application', distributions: {...baseline, 'upgrade-normal': '/upgrade-normal'}}));
});

for (const [name, input] of [
  ['chain ID without params', call('eth_chainId')],
  ['block number without params', call('eth_blockNumber')],
  ['chain ID with an empty array', call('eth_chainId', [])],
  ['block number with an empty array', call('eth_blockNumber', [])],
  ['block with positional parameters', call('eth_getBlockByNumber', ['0x10', false])],
  ['logs with positional parameters', call('eth_getLogs', [{address: ['0x' + '0'.repeat(39) + '3', '0x' + '0'.repeat(39) + '6']}])],
  ['contract read with positional parameters', call('eth_call', [{to: '0x' + '0'.repeat(39) + '6', data: '0x'}, 'latest'])],
  ['parameterless read with a string ID', {...call('eth_chainId'), id: 'synthetic-request'}],
]) {
  test(name, () => {
    const before = JSON.stringify(input); const output = readOnlyParams(input);
    assert.deepEqual(output, input.params ?? []); assert.equal(JSON.stringify(input), before);
    if (input.params) assert.equal(output, input.params);
  });
}
for (const [name, input] of [
  ['transaction submission', call('eth_sendRawTransaction', ['0x01'])],
  ['wallet account request', call('eth_requestAccounts', [])],
  ['personal signing', call('personal_sign', [])],
  ['contract read without required parameters', call('eth_call')],
  ['null parameter structure', call('eth_blockNumber', null)],
  ['named parameter structure outside fixture scope', call('eth_blockNumber', {})],
  ['notification outside fixture scope', {jsonrpc: '2.0', method: 'eth_getLogs', params: []}],
  ['wrong protocol version', {...call('eth_chainId'), jsonrpc: '1.0'}],
]) test('reject ' + name, () => assert.throws(() => readOnlyParams(input)));
