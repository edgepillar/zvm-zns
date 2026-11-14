'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {read, pin} = require('./browser-source-guard.cjs');

// Only synthetic, read-only responses are available. A missing method/function
// is a failed control, never a plausible default or a forwarded RPC request.
async function fixture(input, viem) {
  const abiRaw = read(input.abi, 512 << 10).toString('utf8');
  const abi = Object.fromEntries([...abiRaw.matchAll(/^export const (\w+) = (\[.*\]) as const$/gm)]
    .map(match => [match[1], JSON.parse(match[2])]));
  const zero = '0x' + '0'.repeat(40); const hex = value => '0x' + BigInt(value).toString(16);
  const address = n => '0x' + n.toString(16).padStart(40, '0');
  const contracts = {
    [address(1)]: {abi: abi.eNSRegistryAbi, allowed: ['owner', 'resolver']},
    [address(3)]: {abi: abi.zNSRegistrarAbi, allowed: ['nameExpires']},
    [address(6)]: {abi: abi.zNSControllerAbi, allowed: ['valid', 'available', 'rentPrice']},
  };
  assert(Object.values(contracts).every(value => Array.isArray(value.abi)));
  const report = {schema: 1, synthetic: true, requests: [], rpc: [], refusals: [], staticResponses: [],
    externalUpstreamRequests: 0, walletOrSigningProviderInjected: false};
  const distributions = {};
  for (const role of ['normal', 'fixture']) {
    const root = fs.realpathSync(input.distributions[role]); assert.equal(root, input.distributions[role]);
    const files = {}; let bytes = 0;
    function visit(directory) {
      for (const name of fs.readdirSync(directory)) {
        const file = path.join(directory, name); const stat = fs.lstatSync(file);
        if (stat.isDirectory()) visit(file);
        else {
          const raw = read(file, 4 << 20); bytes += raw.length;
          assert(bytes <= 64 << 20 && Object.keys(files).length < 512);
          files[path.relative(root, file).split(path.sep).join('/')] = pin(raw);
        }
      }
    }
    visit(root); assert(files['index.html']); distributions[role] = {root, files, bytes};
  }
  function answer(call) {
    assert(call && call.jsonrpc === '2.0' && (typeof call.id === 'number' || typeof call.id === 'string'));
    assert(Array.isArray(call.params) && report.rpc.length < 1024);
    const {method, params} = call; let result; let functionName = null;
    if (method === 'eth_chainId') { assert.equal(params.length, 0); result = hex(7340469); }
    else if (method === 'eth_blockNumber') { assert.equal(params.length, 0); result = '0x10'; }
    else if (method === 'eth_getBlockByNumber') {
      assert.equal(params.length, 2); assert(['0x10', 'latest'].includes(params[0]) && params[1] === false);
      result = {number: '0x10', timestamp: hex(1700000015), hash: '0x' + '1'.repeat(64), parentHash: '0x' + '2'.repeat(64),
        nonce: '0x0000000000000000', sha3Uncles: '0x' + '0'.repeat(64), logsBloom: '0x' + '0'.repeat(512),
        transactionsRoot: '0x' + '0'.repeat(64), stateRoot: '0x' + '0'.repeat(64), receiptsRoot: '0x' + '0'.repeat(64),
        miner: zero, difficulty: '0x0', totalDifficulty: '0x0', extraData: '0x', size: '0x200', gasLimit: '0x1c9c380',
        gasUsed: '0x0', baseFeePerGas: '0x1', transactions: [], uncles: [], mixHash: '0x' + '0'.repeat(64)};
    } else if (method === 'eth_getLogs') {
      assert.equal(params.length, 1); const filter = params[0];
      assert(filter && Array.isArray(filter.address) && filter.address.length === 2
        && filter.address.every(value => [address(3), address(6)].includes(value.toLowerCase())));
      assert(BigInt(filter.fromBlock) >= 1n && BigInt(filter.toBlock) <= 16n); result = [];
    } else if (method === 'eth_call') {
      assert(params.length === 2 && ['latest', '0x10'].includes(params[1]));
      const tx = params[0]; assert(tx && !tx.value && !tx.from && typeof tx.to === 'string');
      const target = contracts[tx.to.toLowerCase()]; assert(target, 'Unknown synthetic contract');
      assert(/^0x[0-9a-f]+$/i.test(tx.data) && tx.data.length <= 4098);
      const decoded = viem.decodeFunctionData({abi: target.abi, data: tx.data}); functionName = decoded.functionName;
      assert(target.allowed.includes(functionName), 'Function outside read-only fixture scope');
      const methodABI = target.abi.find(row => row.type === 'function' && row.name === functionName);
      assert(methodABI && ['view', 'pure'].includes(methodABI.stateMutability));
      let value;
      if (['valid', 'available'].includes(functionName)) {
        assert.equal(decoded.args[0], 'source-fixture'); value = true;
      } else if (functionName === 'nameExpires') value = 0n;
      else if (['owner', 'resolver'].includes(functionName)) value = zero;
      else {
        const [label, duration] = decoded.args;
        assert(['source-fixture', 'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz', 'zzqq', 'zqq'].includes(label));
        assert(duration >= 31536000n && duration <= 315360000n && duration % 31536000n === 0n);
        value = {base: 10n ** 18n * duration / 31536000n, premium: 0n};
      }
      result = viem.encodeFunctionResult({abi: target.abi, functionName, result: value});
    } else throw new Error('Method outside read-only fixture scope');
    report.rpc.push({method, functionName, requestSha256: pin(Buffer.from(JSON.stringify(call))).sha256});
    return {jsonrpc: '2.0', id: call.id, result};
  }
  const types = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml',
    '.woff2': 'font/woff2', '.woff': 'font/woff', '.png': 'image/png', '.ico': 'image/x-icon', '.txt': 'text/plain'};
  const server = http.createServer(async (request, response) => {
    try {
      assert(report.requests.length < 2048); const url = new URL(request.url, 'http://127.0.0.1');
      report.requests.push({method: request.method, path: url.pathname});
      response.setHeader('Cache-Control', 'no-store');
      if (request.method === 'POST' && url.pathname === '/rpc') {
        const chunks = []; let length = 0;
        for await (const chunk of request) { length += chunk.length; assert(length <= 65536); chunks.push(chunk); }
        const body = JSON.parse(Buffer.concat(chunks)); const batch = Array.isArray(body);
        const calls = batch ? body : [body]; assert(calls.length > 0 && calls.length <= 32);
        const result = calls.map(answer); response.setHeader('Content-Type', 'application/json');
        response.end(JSON.stringify(batch ? result : result[0])); return;
      }
      assert.equal(request.method, 'GET');
      if (url.pathname === '/api/info') {
        response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({l2: {chainId: 7340469}})); return;
      }
      const match = /^\/(normal|fixture)\/(.*)$/.exec(url.pathname); assert(match);
      const role = match[1]; const name = match[2] || 'index.html'; const dist = distributions[role];
      assert(!name.includes('..') && !name.includes('%') && Object.hasOwn(dist.files, name), 'Unlisted static resource');
      const raw = read(path.join(dist.root, name), 4 << 20); assert.deepEqual(pin(raw), dist.files[name]);
      if (report.staticResponses.length < 1024) report.staticResponses.push({role, name, ...pin(raw)});
      else throw new Error('Static response budget');
      response.setHeader('Content-Type', types[path.extname(name)] || 'application/octet-stream'); response.end(raw);
    } catch (error) {
      report.refusals.push({type: error.name, message: 'Request outside the explicit synthetic fixture scope'});
      response.statusCode = 400; response.end('Fixture scope refusal');
    }
  });
  server.requestTimeout = 10000; server.headersTimeout = 10000; server.maxConnections = 32;
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  return {origin: 'http://127.0.0.1:' + server.address().port, report,
    async close() { server.closeAllConnections(); await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve())); },
    distributions: Object.fromEntries(Object.entries(distributions).map(([role, row]) => [role, {files: row.files, bytes: row.bytes}]))};
}
module.exports = {fixture};
