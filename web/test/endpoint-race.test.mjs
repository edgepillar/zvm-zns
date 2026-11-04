// Execute the shipped endpoint module with explicit memory-only Vue, fetch and
// storage capabilities. These controls do not start an SDK, browser or network.
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {stripTypeScriptTypes} from 'node:module'
import {createContext, SourceTextModule, SyntheticModule} from 'node:vm'

const kind = 'zns'
const rpc = true
const source = readFileSync(new URL('../src/core/endpoint.ts', import.meta.url), 'utf8')
const alpha = 'http://alpha.invalid', beta = 'http://beta.invalid'
const urlOf = host => rpc ? host + '/rpc' : host
const selected = api => rpc ? api.endpoint.rpc : api.endpoint.url
const settle = async () => {for (let i = 0; i < 12; i++) await Promise.resolve()}

// The sole parameter-property constructor is lowered explicitly for Node's
// strip-only API. An exact inverse protects every async and request expression.
function lowerErrorConstructor(value) {
  const before = "class HttpError extends Error {\n  constructor(\n    readonly status: number,\n    readonly statusText: string,\n  ) {\n    super(`${status} ${statusText}`)\n  }\n}", after = "class HttpError extends Error {\n  readonly status: number\n  readonly statusText: string\n  constructor(status: number, statusText: string) {\n    super(`${status} ${statusText}`)\n    this.status = status\n    this.statusText = statusText\n  }\n}"
  assert.equal(value.split(before).length - 1, 1)
  const lowered = value.replace(before, after)
  assert.equal(lowered.replace(after, before), value)
  return lowered
}

async function fixture() {
  const requests = [], writes = [], saved = new Map()
  let blocked = false, tick = 0, onFetch = null, onStateWrite = null
  const context = createContext({URL, URLSearchParams,
    location: {search: '', protocol: 'http:'},
    performance: {now: () => ++tick},
    AbortSignal: {timeout: milliseconds => ({milliseconds})},
    localStorage: {getItem: key => saved.get(key) ?? null, setItem(key, value) {saved.set(key, value); writes.push({key, value})}},
    fetch(url, options) {
      if (onFetch) onFetch()
      let resolve, reject
      const promise = new Promise((yes, no) => {resolve = yes; reject = no})
      requests.push({url, options, resolve, reject, answered: false})
      return promise
    },
  })
  const dependencies = {
    vue: {reactive: value => new Proxy(value, {set(target, key, next) {const changed = !Object.is(target[key], next); target[key] = next; if (changed && onStateWrite) onStateWrite(key, next); return true}}), computed: get => ({get value() {return get()}})},
    '@zvm/web/url': {isLoopback: () => false, mixedContentBlocked: () => blocked},
    './deployment': {deploymentFor: chainId => chainId === 27 ? {registry: 'memory-only'} : null},
  }
  const module = new SourceTextModule(stripTypeScriptTypes(lowerErrorConstructor(source), {mode: 'strip'}), {
    context, initializeImportMeta(meta) {meta.env = {VITE_ZVM_NODE: alpha}},
  })
  await module.link(name => {
    const values = dependencies[name]
    assert.ok(values, 'Only declared endpoint capabilities may be linked: ' + name)
    return new SyntheticModule(Object.keys(values), function() {
      for (const [key, value] of Object.entries(values)) this.setExport(key, value)
    }, {context})
  })
  await module.evaluate({timeout: 5000})
  const api = module.namespace
  const reply = async (request, body, status = 200) => {
    assert.ok(request && !request.answered, 'Reply only to one original pending memory request')
    request.answered = true
    request.resolve({ok: status >= 200 && status < 300, status, statusText: status === 200 ? 'OK' : 'Unavailable', json: async () => body})
    await settle()
  }
  const approve = async (host, chainId = 1) => {
    const request = requests.find(row => !row.answered && row.url === (rpc ? urlOf(host) : host + '/api/info'))
    await reply(request, rpc ? {result: '0x' + chainId.toString(16)} : {l2: {chainId}})
    if (rpc) {
      const info = requests.find(row => !row.answered && row.url === host + '/api/info')
      if (info) await reply(info, {l2: {chainId}, apps: {exchange: 'memory-only'}})
    }
  }
  const reject = async request => {
    assert.ok(request && !request.answered)
    request.answered = true; request.reject(new Error('Memory-only unavailable endpoint')); await settle()
  }
  return {api, requests, writes, reply, approve, reject, block: value => {blocked = value}, reenterFetch: callback => {onFetch = callback}, observeState: callback => {onStateWrite = callback},
    async healthy(host = alpha, chainId = 1) {const pending = api.setEndpoint(urlOf(host)); await approve(host, chainId); assert.equal(await pending, true)}}
}

test('a current successful selection preserves the original read and normalized endpoint', async () => {
  const f = await fixture(); await f.healthy(beta, 27)
  assert.equal(selected(f.api), urlOf(beta)); assert.equal(f.api.endpoint.chainId, 27)
  assert.equal(f.api.endpoint.health, 'ok'); assert.equal(f.api.reachable.value, true)
  assert.equal(f.api.endpoint.error, null); assert.equal(f.api.endpoint.hint, null)
  assert.equal(f.writes.at(-1).value, urlOf(beta))
  assert.ok(f.api.endpoint.latency >= 0)
  assert.equal(f.requests[0].options.signal.milliseconds, 8000)
  if (rpc) {
    assert.deepEqual(JSON.parse(f.requests[0].options.body), {jsonrpc: '2.0', id: 1, method: 'eth_chainId', params: []})
    assert.equal(f.api.endpoint.apiBase, beta); assert.equal(f.api.endpoint.info.l2.chainId, 27)
  }
})
test('concurrent checks of the same selection share one pending request', async () => {
  const f = await fixture(), first = f.api.check(), again = f.api.check()
  assert.equal(first, again); assert.equal(f.requests.length, 1)
  await f.approve(alpha); assert.equal(await first, true)
  const later = f.api.check(); assert.notEqual(later, first)
  await f.approve(alpha, 2); assert.equal(await later, true)
})
test('a new selection starts independently and refuses the older successful reply', async () => {
  const f = await fixture(), old = f.api.setEndpoint(urlOf(alpha)), next = f.api.setEndpoint(urlOf(beta))
  assert.equal(f.requests.length, 2)
  await f.approve(beta, 2); assert.equal(await next, true)
  await f.approve(alpha, 1); assert.equal(await old, false)
  assert.equal(selected(f.api), urlOf(beta)); assert.equal(f.api.endpoint.chainId, 2)
  assert.equal(f.api.endpoint.health, 'ok'); assert.equal(f.writes.at(-1).value, urlOf(beta))
})
test('an old failure cannot overwrite a newer healthy selection', async () => {
  const f = await fixture(), old = f.api.setEndpoint(urlOf(alpha)), next = f.api.setEndpoint(urlOf(beta))
  await f.approve(beta, 2); await next; await f.reject(f.requests[0]); assert.equal(await old, false)
  assert.equal(f.api.endpoint.health, 'ok'); assert.equal(f.api.endpoint.chainId, 2); assert.equal(f.api.endpoint.error, null)
})
test('an older finally cannot clear the current in-flight check', async () => {
  const f = await fixture(), old = f.api.setEndpoint(urlOf(alpha)), next = f.api.setEndpoint(urlOf(beta))
  await f.approve(alpha); await old
  const again = f.api.check(); assert.equal(f.requests.length, 2)
  await f.approve(beta, 2); assert.equal(await next, true); assert.equal(await again, true)
})
test('an A-to-B-to-A selection refuses both obsolete generations', async () => {
  const f = await fixture(), first = f.api.setEndpoint(urlOf(alpha)), middle = f.api.setEndpoint(urlOf(beta)), last = f.api.setEndpoint(urlOf(alpha))
  assert.equal(f.requests.length, 3)
  await f.reply(f.requests[2], rpc ? {result: '0x3'} : {l2: {chainId: 3}})
  if (rpc) await f.reply(f.requests[3], {l2: {chainId: 3}})
  assert.equal(await last, true)
  await f.reply(f.requests[1], rpc ? {result: '0x2'} : {l2: {chainId: 2}})
  await f.reply(f.requests[0], rpc ? {result: '0x1'} : {l2: {chainId: 1}})
  assert.equal(await first, false); assert.equal(await middle, false)
  assert.equal(f.api.endpoint.chainId, 3); assert.equal(selected(f.api), urlOf(alpha))
  assert.equal(f.requests.length, rpc ? 4 : 3)
})
test('invalid input immediately clears the old deployment and invalidates pending success', async () => {
  const f = await fixture(); await f.healthy(alpha, 1)
  const old = f.api.check(); assert.equal(await f.api.setEndpoint(''), false)
  assert.equal(f.api.endpoint.chainId, null); assert.equal(f.api.endpoint.latency, null)
  assert.equal(f.api.endpoint.health, 'error'); const error = f.api.endpoint.error
  if (rpc) {assert.equal(f.api.endpoint.apiBase, null); assert.equal(f.api.endpoint.info, null)}
  await f.approve(alpha, 2); assert.equal(await old, false)
  assert.equal(f.api.endpoint.health, 'error'); assert.equal(f.api.endpoint.error, error); assert.equal(f.api.endpoint.chainId, null)
})
test('invalid input also refuses a pending failure', async () => {
  const f = await fixture(), old = f.api.check(); await f.api.setEndpoint('')
  const error = f.api.endpoint.error; await f.reject(f.requests[0]); assert.equal(await old, false)
  assert.equal(f.api.endpoint.error, error)
})
test('starting a recheck clears previously established chain and deployment state', async () => {
  const f = await fixture(); await f.healthy(alpha, 1)
  const pending = f.api.check()
  assert.equal(f.api.endpoint.health, 'checking'); assert.equal(f.api.endpoint.chainId, null); assert.equal(f.api.endpoint.latency, null)
  if (rpc) {assert.equal(f.api.endpoint.apiBase, null); assert.equal(f.api.endpoint.info, null)}
  await f.approve(alpha, 2); assert.equal(await pending, true); assert.equal(f.api.endpoint.chainId, 2)
})
test('a repeated explicit selection is a new generation even for the same URL', async () => {
  const f = await fixture(), old = f.api.setEndpoint(urlOf(alpha)), next = f.api.setEndpoint(urlOf(alpha))
  assert.equal(f.requests.length, 2)
  await f.reply(f.requests[1], rpc ? {result: '0x2'} : {l2: {chainId: 2}})
  if (rpc) await f.reply(f.requests[2], {l2: {chainId: 2}})
  await next; await f.reply(f.requests[0], rpc ? {result: '0x1'} : {l2: {chainId: 1}})
  assert.equal(await old, false); assert.equal(f.api.endpoint.chainId, 2)
})
test('a current request failure remains unavailable rather than preserving old chain metadata', async () => {
  const f = await fixture(); await f.healthy(alpha)
  const pending = f.api.setEndpoint(urlOf(beta)); await f.reject(f.requests.at(-1)); assert.equal(await pending, false)
  assert.equal(f.api.endpoint.health, 'error'); assert.equal(f.api.endpoint.chainId, null); assert.equal(f.api.endpoint.latency, null)
  assert.ok(f.api.endpoint.error); if (rpc) assert.equal(f.api.endpoint.apiBase, null)
})
test('mixed-content refusal performs no new fetch and clears the old chain metadata', async () => {
  const f = await fixture(); await f.healthy(alpha); const count = f.requests.length
  f.block(true); assert.equal(await f.api.setEndpoint(urlOf(beta)), false)
  assert.equal(f.requests.length, count); assert.equal(f.api.endpoint.health, 'error'); assert.equal(f.api.endpoint.chainId, null)
})
test('an HTTP failure is classified only for the current selection', async () => {
  const f = await fixture(), pending = f.api.setEndpoint(urlOf(beta))
  await f.reply(f.requests[0], {}, 503); assert.equal(await pending, false)
  assert.equal(f.api.endpoint.chainId, null); assert.match(f.api.endpoint.error, /503/)
})
test('a non-node response cannot establish endpoint health', async () => {
  const f = await fixture(), pending = f.api.setEndpoint(urlOf(beta))
  await f.reply(f.requests[0], {}); assert.equal(await pending, false)
  assert.equal(f.api.endpoint.health, 'error'); assert.equal(f.api.endpoint.chainId, null)
})
if (rpc) {
  test('an old API-info response cannot replace a newly selected deployment', async () => {
    const f = await fixture(), old = f.api.setEndpoint(urlOf(alpha))
    await f.reply(f.requests[0], {result: '0x1'}); const oldInfo = f.requests[1]
    const next = f.api.setEndpoint(urlOf(beta)); await f.approve(beta, 2); await next
    await f.reply(oldInfo, {l2: {chainId: 1}, apps: {exchange: 'obsolete'}})
    assert.equal(await old, false); assert.equal(f.api.endpoint.info.l2.chainId, 2); assert.equal(f.api.endpoint.apiBase, beta)
  })
  test('an obsolete failed bare-host candidate cannot start a fallback request', async () => {
    const f = await fixture(), old = f.api.setEndpoint(alpha), next = f.api.setEndpoint(urlOf(beta))
    await f.approve(beta, 2); await next; const count = f.requests.length
    await f.reject(f.requests[0]); assert.equal(await old, false); assert.equal(f.requests.length, count)
    assert.equal(f.api.endpoint.chainId, 2)
  })
  test('the current bare-host selection preserves both original candidates and canonical RPC persistence', async () => {
    const f = await fixture(), pending = f.api.setEndpoint(beta)
    assert.equal(f.requests[0].url, beta + '/rpc'); await f.reject(f.requests[0]); assert.equal(f.requests[1].url, beta)
    await f.reply(f.requests[1], {result: '0x2'}); assert.equal(await pending, true)
    assert.equal(f.api.endpoint.rpc, beta); assert.equal(f.writes.at(-1).value, beta); assert.equal(f.api.endpoint.apiBase, null)
  })
  test('a reachable RPC with an unavailable optional API preserves its read-only RPC capability', async () => {
    const f = await fixture(), pending = f.api.setEndpoint(urlOf(beta))
    await f.reply(f.requests[0], {result: '0x2'}); await f.reject(f.requests[1]); assert.equal(await pending, true)
    assert.equal(f.api.endpoint.chainId, 2); assert.equal(f.api.endpoint.apiBase, null); assert.equal(f.api.endpoint.info, null)
  })
}

test('a synchronous fetch callback shares the already-owned current promise', async () => {
  const f = await fixture(); let nested
  f.reenterFetch(() => {nested = f.api.check()})
  const pending = f.api.check(); assert.equal(nested, pending); assert.equal(f.requests.length, 1)
  await f.approve(alpha, 27); assert.equal(await pending, true)
})
test('ZNS readiness still depends on the selected chain deployment', async () => {
  const f = await fixture(); await f.healthy(alpha, 27); assert.equal(f.api.hasZns.value, true)
  await f.healthy(beta, 2); assert.equal(f.api.reachable.value, true); assert.equal(f.api.hasZns.value, false)
})
test('the original optional API explorer contract remains distinct from RPC health', async () => {
  const f = await fixture(), pending = f.api.setEndpoint(urlOf(beta))
  await f.reply(f.requests[0], {result: '0x2'}); await f.reject(f.requests[1]); assert.equal(await pending, true)
  assert.equal(f.api.explorerUrl('/tx/example'), null); assert.throws(() => f.api.base(), /no API/)
  assert.equal(f.api.endpoint.info, null); assert.equal(f.api.reachable.value, true)
})
test('canonical bare-host resolution still shares the owned promise during a reactive URL callback', async () => {
  const f = await fixture(); let nested
  f.observeState(key => {if (key === 'rpc') nested = f.api.check()})
  const pending = f.api.setEndpoint(beta); await f.approve(beta, 2)
  assert.equal(await pending, true); assert.equal(await nested, true)
  assert.equal(f.requests.length, 2); assert.equal(f.api.endpoint.rpc, urlOf(beta))
})
test('a reactive new selection during health publication refuses the older completion', async () => {
  const f = await fixture(); let next
  f.observeState((key, value) => {if (key === 'health' && value === 'ok' && !next) next = f.api.setEndpoint(urlOf(beta))})
  const old = f.api.setEndpoint(urlOf(alpha)); await f.approve(alpha, 1)
  assert.equal(await old, false); assert.equal(f.api.endpoint.rpc, urlOf(beta)); assert.equal(f.api.endpoint.chainId, null)
  assert.equal(f.api.endpoint.health, 'checking'); await f.approve(beta, 2); assert.equal(await next, true)
  assert.equal(f.api.endpoint.chainId, 2)
})
