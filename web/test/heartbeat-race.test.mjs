// Execute the shipped heartbeat with explicit memory-only Vue, client, clock
// and visibility capabilities. No SDK, browser, endpoint or wallet is started.
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {stripTypeScriptTypes} from 'node:module'
import {createContext, SourceTextModule, SyntheticModule} from 'node:vm'

const source = readFileSync(new URL('../src/core/chain.ts', import.meta.url), 'utf8')
const alpha = 'http://alpha.invalid/rpc', beta = 'http://beta.invalid/rpc'
const settle = async () => {for (let i = 0; i < 12; i++) await Promise.resolve()}

async function fixture() {
  const requests = [], clients = [], watches = [], intervals = [], events = new Map()
  const endpoint = {rpc: alpha, chainId: 1, health: 'ok'}, document = {hidden: false,
    addEventListener(name, callback) {if (!events.has(name)) events.set(name, []); events.get(name).push(callback)}}
  let clock = 1000, onClient = null, throwClient = false
  const context = createContext({Date: {now: () => clock}, document,
    window: {setInterval(callback, milliseconds) {intervals.push({callback, milliseconds}); return intervals.length - 1}}})
  const request = (kind, params, client) => {
    let resolve, reject
    const promise = new Promise((yes, no) => {resolve = yes; reject = no})
    requests.push({kind, params, client, resolve, reject}); return promise
  }
  const dependencies = {
    vue: {reactive: value => value, watch: (get, callback, options) => watches.push({get, callback, options})},
    './endpoint': {endpoint, reachable: {get value() {return endpoint.health === 'ok'}}},
    '@zvm/web/evm': {publicClient(chainId) {
      const client = {chainId, rpc: endpoint.rpc}; clients.push(client)
      if (onClient) onClient()
      if (throwClient) {throwClient = false; throw new Error('Memory client creation failed')}
      return {getBlockNumber: params => request('height', params, client), getBlock: params => request('block', params, client)}
    }},
  }
  const module = new SourceTextModule(stripTypeScriptTypes(source, {mode: 'strip'}) + '\nexport {poll};', {context})
  await module.link(name => {
    const values = dependencies[name]; assert.ok(values, 'Only declared heartbeat capabilities may be linked: ' + name)
    return new SyntheticModule(Object.keys(values), function() {
      for (const [key, value] of Object.entries(values)) this.setExport(key, value)
    }, {context})
  })
  await module.evaluate({timeout: 5000})
  const api = module.namespace
  const height = async (index, value) => {assert.equal(requests[index].kind, 'height'); requests[index].resolve(BigInt(value)); await settle()}
  const block = async (index, number, timestamp = BigInt(number) * 15n, fee = 2n) => {
    assert.equal(requests[index].kind, 'block'); requests[index].resolve({number: BigInt(number), timestamp: BigInt(timestamp), baseFeePerGas: fee}); await settle()
  }
  return {api, endpoint, document, requests, clients, watches, intervals, events, height, block,
    change(values) {
      const snapshot = get => {const value = get(); return Array.isArray(value) ? Array.from(value) : value}
      const before = watches.map(row => snapshot(row.get)); Object.assign(endpoint, values)
      return watches.map((row, index) => {
        const next = snapshot(row.get), old = before[index]
        const changed = Array.isArray(next) ? next.length !== old.length || next.some((value, i) => !Object.is(value, old[i])) : !Object.is(next, old)
        if (changed) return row.callback(next, old)
      })
    },
    time(value) {clock = value}, reenter(callback) {onClient = callback}, failClient() {throwClient = true},
    async reject(index, value = new Error('Memory read failed')) {requests[index].reject(value); await settle()},
    visible(hidden) {document.hidden = hidden; for (const callback of events.get('visibilitychange') ?? []) callback()},
    async tip(number, timestamp = BigInt(number) * 15n, fee = 2n) {
      const start = requests.length, pending = api.poll(); assert.equal(requests.length, start + 1)
      await height(start, number); assert.equal(requests.length, start + 2)
      await block(start + 1, number, timestamp, fee); await pending
    },
  }
}

test('the current heartbeat uses the captured client and exact height before publishing a block', async () => {
  const f = await fixture(), seen = []; f.api.onBlock(head => seen.push(head)); f.time(3000); await f.tip(12, 180, 7n)
  assert.deepEqual({...f.requests[0].params}, {cacheTime: 0}); assert.deepEqual({...f.requests[1].params}, {blockNumber: 12n})
  assert.equal(f.clients.length, 1); assert.deepEqual(f.clients[0], {chainId: 1, rpc: alpha})
  assert.deepEqual({...f.api.chain}, {chainId: 1, head: 12, timestamp: 180, baseFee: 7n, interval: 15, landedAt: 3000, polledAt: 3000, pollMs: 60_000, error: null})
  assert.deepEqual(seen, [12])
})
test('an unchanged height needs no second block body and preserves the accepted block', async () => {
  const f = await fixture(), seen = []; f.api.onBlock(head => seen.push(head)); await f.tip(12)
  f.api.chain.error = 'Earlier error'; const pending = f.api.poll(); await f.height(2, 12); await pending
  assert.equal(f.requests.length, 3); assert.equal(f.api.chain.head, 12); assert.equal(f.api.chain.error, null); assert.deepEqual(seen, [12])
})
test('repeated timer or focus polls share one complete current read', async () => {
  const f = await fixture(), pending = f.api.poll()
  for (let i = 0; i < 100; i++) assert.equal(f.api.poll(), pending)
  assert.equal(f.requests.length, 1); await f.height(0, 12)
  for (let i = 0; i < 100; i++) assert.equal(f.api.poll(), pending)
  assert.equal(f.requests.length, 2); await f.block(1, 12); await pending
  const next = f.api.poll(); await f.height(2, 12); await next; assert.equal(f.requests.length, 3)
})
test('client creation cannot reenter the same heartbeat and start a duplicate read', async () => {
  const f = await fixture(); f.reenter(() => f.api.poll()); const pending = f.api.poll()
  assert.equal(f.clients.length, 1); assert.equal(f.requests.length, 1)
  await f.height(0, 12); await f.block(1, 12); await pending
})
test('a late old-endpoint height cannot start a block read or replace the new tip', async () => {
  const f = await fixture(), old = f.api.poll(); const [next] = f.change({rpc: beta, chainId: 2})
  await f.height(1, 20); await f.block(2, 20, 300, 9n); await next; await f.height(0, 10); await old
  assert.equal(f.requests.length, 3); assert.equal(f.api.chain.head, 20); assert.equal(f.api.chain.chainId, 2); assert.equal(f.api.chain.baseFee, 9n)
})
test('a late old-endpoint block cannot replace a newer accepted block', async () => {
  const f = await fixture(), seen = []; f.api.onBlock(head => seen.push(head)); const old = f.api.poll(); await f.height(0, 10)
  const [next] = f.change({rpc: beta, chainId: 2}); await f.height(2, 20); await f.block(3, 20, 300, 9n); await next
  await f.block(1, 10, 150, 1n); await old
  assert.equal(f.api.chain.head, 20); assert.equal(f.api.chain.timestamp, 300); assert.equal(f.api.chain.baseFee, 9n); assert.deepEqual(seen, [20])
})
test('an old height failure cannot overwrite the new endpoint success', async () => {
  const f = await fixture(), old = f.api.poll(); const [next] = f.change({rpc: beta, chainId: 2})
  await f.height(1, 20); await f.block(2, 20); await next; await f.reject(0); await old
  assert.equal(f.api.chain.error, null); assert.equal(f.api.chain.head, 20)
})
test('an old block failure cannot overwrite the new endpoint success', async () => {
  const f = await fixture(), old = f.api.poll(); await f.height(0, 10)
  const [next] = f.change({rpc: beta, chainId: 2}); await f.height(2, 20); await f.block(3, 20); await next; await f.reject(1); await old
  assert.equal(f.api.chain.error, null); assert.equal(f.api.chain.head, 20)
})
test('an old finally cannot release a newer pending read', async () => {
  const f = await fixture(), old = f.api.poll(); const [next] = f.change({rpc: beta, chainId: 2})
  await f.height(0, 10); await old; assert.equal(f.api.poll(), next); assert.equal(f.requests.length, 2)
  await f.height(1, 20); await f.block(2, 20); await next
})
test('an A-to-B-to-A endpoint change still refuses both older generations', async () => {
  const f = await fixture(), old = f.api.poll(); const [middle] = f.change({rpc: beta, chainId: 2}); const [last] = f.change({rpc: alpha, chainId: 1})
  await f.height(2, 30); await f.block(3, 30); await last
  await f.height(1, 20); await middle; await f.height(0, 10); await old
  assert.equal(f.api.chain.head, 30); assert.equal(f.api.chain.chainId, 1); assert.equal(f.requests.length, 4)
})
test('health loss clears metadata and invalidates a pending height before recovery', async () => {
  const f = await fixture(), old = f.api.poll(); f.change({health: 'checking'})
  assert.equal(f.api.chain.chainId, null); assert.equal(f.api.chain.head, null); assert.equal(f.api.chain.timestamp, null); assert.equal(f.api.chain.baseFee, null)
  await f.height(0, 10); await old; assert.equal(f.requests.length, 1)
  const [next] = f.change({health: 'ok'}); await f.height(1, 20); await f.block(2, 20); await next; assert.equal(f.api.chain.head, 20)
})
test('health loss also refuses a block that was already pending', async () => {
  const f = await fixture(), old = f.api.poll(); await f.height(0, 10); f.change({health: 'error'})
  await f.block(1, 10); await old; assert.equal(f.api.chain.head, null); assert.equal(f.api.chain.chainId, null)
})
test('a same-chain RPC change clears the old chain identity and cadence synchronously', async () => {
  const f = await fixture(); await f.tip(1, 10); await f.tip(2, 20); assert.equal(f.api.chain.interval, 10)
  f.time(4000); const [next] = f.change({rpc: beta})
  assert.equal(f.api.chain.chainId, null); assert.equal(f.api.chain.head, null); assert.equal(f.api.chain.interval, 15); assert.equal(f.api.chain.landedAt, 4000)
  await f.height(4, 100); await f.block(5, 100, 3000); await next; assert.equal(f.api.chain.interval, 15)
  assert.equal(f.watches[0].options.flush, 'sync'); assert.deepEqual(Array.from(f.watches[0].get()), [beta, 1, 'ok'])
})
test('a chain-id change at the same RPC invalidates the old client', async () => {
  const f = await fixture(), old = f.api.poll(); const [next] = f.change({chainId: 2})
  assert.deepEqual(f.clients[1], {chainId: 2, rpc: alpha}); await f.height(1, 20); await f.block(2, 20); await next; await f.height(0, 10); await old
  assert.equal(f.api.chain.chainId, 2); assert.equal(f.api.chain.head, 20)
})
test('a hidden document starts no reads and visibility restoration polls the current tip', async () => {
  const f = await fixture(); f.document.hidden = true; f.api.startChainPolling(); f.intervals[0].callback(); assert.equal(f.clients.length, 0)
  f.visible(false); assert.equal(f.requests.length, 1); await f.height(0, 10); await f.block(1, 10); assert.equal(f.api.chain.head, 10)
})
test('becoming hidden refuses pending block publication until a fresh visible poll', async () => {
  const f = await fixture(); f.api.startChainPolling(); await f.height(0, 10); f.visible(true); await f.block(1, 10)
  assert.equal(f.api.chain.head, null); f.visible(false); await f.height(2, 20); await f.block(3, 20); assert.equal(f.api.chain.head, 20)
})
test('polling starts once even when the timer capability returns zero', async () => {
  const f = await fixture(); f.api.startChainPolling(); f.api.startChainPolling(1)
  assert.equal(f.intervals.length, 1); assert.equal(f.intervals[0].milliseconds, 60_000); assert.equal(f.events.get('visibilitychange').length, 1)
  assert.equal(f.requests.length, 1); await f.height(0, 10); await f.block(1, 10)
})
test('a current height failure stays visible and a later successful read recovers', async () => {
  const f = await fixture(), pending = f.api.poll(); await f.reject(0, {shortMessage: 'Current height unavailable'}); await pending
  assert.equal(f.api.chain.error, 'Current height unavailable'); await f.tip(10); assert.equal(f.api.chain.error, null)
})
test('a current block failure preserves the previous block until a successful retry', async () => {
  const f = await fixture(); await f.tip(10); const pending = f.api.poll(); await f.height(2, 11); await f.reject(3, new Error('Current block unavailable')); await pending
  assert.equal(f.api.chain.head, 10); assert.equal(f.api.chain.error, 'Current block unavailable'); await f.tip(11); assert.equal(f.api.chain.head, 11)
})
test('a client construction failure releases the read slot for the next poll', async () => {
  const f = await fixture(); f.failClient(); await f.api.poll(); assert.equal(f.requests.length, 0); assert.equal(f.api.chain.error, 'Memory client creation failed')
  await f.tip(10); assert.equal(f.api.chain.error, null)
})
test('the initial genesis height zero is read once and then deduplicated', async () => {
  const f = await fixture(), seen = []; f.api.onBlock(head => seen.push(head)); await f.tip(0, 0, 0n)
  assert.equal(f.api.chain.head, 0); assert.equal(f.api.chain.timestamp, 0); assert.equal(f.api.chain.baseFee, 0n); assert.deepEqual(seen, [0])
  const next = f.api.poll(); await f.height(2, 0); await next; assert.equal(f.requests.length, 3)
})
test('a newly read lower canonical height remains observable after a rollback', async () => {
  const f = await fixture(), seen = []; f.api.onBlock(head => seen.push(head)); await f.tip(12); await f.tip(10)
  assert.equal(f.api.chain.head, 10); assert.equal(f.api.chain.timestamp, 150); assert.deepEqual(seen, [12, 10])
})
test('cadence keeps the original eight valid gaps and ignores negative or long gaps', async () => {
  const f = await fixture(); let timestamp = 10; await f.tip(1, timestamp)
  for (let gap = 1; gap <= 10; gap++) {timestamp += gap; await f.tip(gap + 1, timestamp)}
  assert.equal(f.api.chain.interval, 6.5)
  timestamp += 120; await f.tip(12, timestamp); assert.equal(f.api.chain.interval, 6.5)
  timestamp -= 1; await f.tip(13, timestamp); assert.equal(f.api.chain.interval, 6.5)
  timestamp += 20; await f.tip(14, timestamp); assert.equal(f.api.chain.interval, 8.625)
})
test('detaching a block listener prevents subsequent notifications', async () => {
  const f = await fixture(), seen = []; const off = f.api.onBlock(head => seen.push(head)); await f.tip(10); off(); await f.tip(11)
  assert.deepEqual(seen, [10])
})

test('ZNS preserves its minute default and original pulse timing on an unchanged height', async () => {
  const f = await fixture(); f.time(2000); f.api.startChainPolling()
  await f.height(0, 12); await f.block(1, 12); assert.equal(f.api.chain.polledAt, 2000)
  assert.equal(f.api.chain.pollMs, 60_000); assert.equal(f.intervals[0].milliseconds, 60_000)
  f.time(4000); const next = f.api.poll(); await f.height(2, 12); await next
  assert.equal(f.api.chain.polledAt, 4000); assert.equal(f.requests.length, 3)
})
test('an explicit original ZNS poll period is selected once', async () => {
  const f = await fixture(); f.api.startChainPolling(17_000); f.api.startChainPolling(1)
  assert.equal(f.api.chain.pollMs, 17_000); assert.equal(f.intervals.length, 1)
  assert.equal(f.intervals[0].milliseconds, 17_000); await f.height(0, 1); await f.block(1, 1)
})
test('ZNS averages timestamps over the original number of skipped blocks', async () => {
  const f = await fixture(); await f.tip(12, 180); await f.tip(16, 240)
  assert.equal(f.api.chain.interval, 15); await f.tip(20, 360); assert.equal(f.api.chain.interval, 22.5)
})
test('a lower canonical height with a newer timestamp does not invent a cadence gap', async () => {
  const f = await fixture(); await f.tip(12, 180); await f.tip(10, 190)
  assert.equal(f.api.chain.head, 10); assert.equal(f.api.chain.timestamp, 190); assert.equal(f.api.chain.interval, 15)
})
test('hide and immediate restore starts a fresh read and refuses the earlier visible request', async () => {
  const f = await fixture(); f.api.startChainPolling(); const old = f.api.poll()
  f.visible(true); f.visible(false); const current = f.api.poll(); assert.equal(f.requests.length, 2)
  await f.height(0, 10); await old; assert.equal(f.requests.length, 2); assert.equal(f.api.chain.head, null)
  await f.height(1, 20); await f.block(2, 20); await current; assert.equal(f.api.chain.head, 20)
})
test('an earlier listener cannot publish the obsolete head to later listeners after a context change', async () => {
  const f = await fixture(), seen = []
  f.api.onBlock(head => {if (head === 12) f.change({rpc: beta, chainId: 2})})
  f.api.onBlock(head => seen.push(head)); await f.tip(12); assert.deepEqual(seen, [])
  await f.height(2, 20); await f.block(3, 20); assert.deepEqual(seen, [20])
})
test('synchronous client creation cannot start a second ZNS timer', async () => {
  const f = await fixture(); f.reenter(() => f.api.startChainPolling()); f.api.startChainPolling()
  assert.equal(f.intervals.length, 1); assert.equal(f.requests.length, 1)
  await f.height(0, 12); await f.block(1, 12)
})
test('context reset clears pulse ownership while retaining the configured ZNS period', async () => {
  const f = await fixture(); f.api.startChainPolling(17_000); await f.height(0, 12); await f.block(1, 12)
  f.time(5000); f.change({health: 'checking'}); assert.equal(f.api.chain.polledAt, 5000)
  assert.equal(f.api.chain.pollMs, 17_000); assert.equal(f.api.chain.chainId, null); assert.equal(f.api.chain.head, null)
})
