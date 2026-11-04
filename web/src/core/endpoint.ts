// Which ZVM node this page reads.
//
// There is no backend here: this is a static bundle, so the node is a setting,
// and the setting is an RPC URL because that is what people have to hand. ZNS
// needs nothing but the RPC: every name, record and price is read from the
// contracts, and the history from their logs. A ZVM node also serves an API
// beside its RPC (the URL with `/rpc` taken off); when there is one, its
// explorer is where a transaction link goes.
//
// The zvm node answers with `Access-Control-Allow-Origin: *`, so a
// cross-origin read needs nothing from whoever runs it.

import {computed, reactive} from 'vue'

import {isLoopback, mixedContentBlocked} from '@zvm/web/url'
import {deploymentFor} from './deployment'

/** The part of the node's /api/info this page reads. */
export interface ChainInfo {
  l2?: {chainId: number}
}

export {isLoopback, mixedContentBlocked}

const KEY = 'zns.rpc'

export interface Preset {
  label: string
  url: string
  note: string
}

// The node this build reads, and any others its picker offers, come from the
// environment (see .env.example), so no node is written into the source.
// VITE_ZVM_NODE is a ZVM node's base URL, its JSON-RPC at /rpc; a local
// zvm-devnet's is http://localhost:47080/zvm. VITE_ZVM_PRESETS
// adds more to the picker, as comma-separated `label=url` pairs.
const NODE = (import.meta.env.VITE_ZVM_NODE as string).replace(/\/+$/, '')

export const DEFAULT_RPC = `${NODE}/rpc`

/** Somewhere to start. Any of them can be replaced with a pasted URL. */
export const PRESETS: Preset[] = [
  {label: 'This build\'s node', url: DEFAULT_RPC, note: new URL(DEFAULT_RPC).host},
  ...((import.meta.env.VITE_ZVM_PRESETS as string | undefined) ?? '')
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => {
      const i = p.indexOf('=')
      const url = i < 0 ? p : p.slice(i + 1).trim()
      return {label: i < 0 ? url : p.slice(0, i).trim(), url, note: url}
    }),
]

export type Health = 'idle' | 'checking' | 'ok' | 'error'

export interface EndpointState {
  /** The RPC the app talks to. Resolved, so it is what actually answered. */
  rpc: string
  health: Health
  /** What went wrong, written for the person who has to fix it. */
  error: string | null
  /** A second line naming the fix, when there is a specific one. */
  hint: string | null
  /** Round trip to eth_chainId, in ms. */
  latency: number | null
  chainId: number | null
  /** The node's API, when the RPC is a zvm node's. */
  apiBase: string | null
  /** The node's /api/info, when it has an API. */
  info: ChainInfo | null
}

export const endpoint = reactive<EndpointState>({
  rpc: initial(),
  health: 'idle',
  error: null,
  hint: null,
  latency: null,
  chainId: null,
  apiBase: null,
  info: null,
})

/** Accepts what people paste: a bare host, a host:port, or a full RPC URL. */
export function normalize(input: string): string {
  let s = input.trim()
  if (!s) return ''
  if (!/^https?:\/\//i.test(s)) s = `http://${s}`
  try {
    const u = new URL(s)
    return `${u.protocol}//${u.host}${u.pathname.replace(/\/+$/, '')}${u.search}`
  } catch {
    return ''
  }
}

function initial(): string {
  // A link can carry the node, so an item page can be shared with the chain it
  // was read from: ?rpc=http://host:49000/rpc
  try {
    const q = new URLSearchParams(location.search)
    const fromQuery = q.get('rpc') ?? q.get('node') ?? q.get('endpoint')
    if (fromQuery) {
      const url = normalize(fromQuery)
      if (url) {
        save(url)
        return url
      }
    }
  } catch {
    /* no query, or no location */
  }
  try {
    const saved = localStorage.getItem(KEY)
    if (saved) return saved
  } catch {
    /* storage can be blocked */
  }
  return DEFAULT_RPC
}

function save(url: string) {
  try {
    localStorage.setItem(KEY, url)
  } catch {
    /* storage can be blocked; the endpoint still works for this tab */
  }
}

export const rpcUrl = () => endpoint.rpc

/** The node's API base. Throws where a page needs one and there is none. */
export function base(): string {
  if (!endpoint.apiBase) throw new Error('This node has no API.')
  return endpoint.apiBase
}

/** Points the app at a different node and re-checks it. */
export async function setEndpoint(input: string): Promise<boolean> {
  const url = normalize(input)
  selectionGeneration++
  checking = null
  if (!url) {
    fail('That is not a URL.', `Try ${DEFAULT_RPC}`)
    return false
  }
  endpoint.health = 'checking'
  clearChain()
  endpoint.rpc = url
  save(url)
  return check()
}

class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly statusText: string,
  ) {
    super(`${status} ${statusText}`)
  }
}

async function chainIdOf(url: string, timeoutMs: number): Promise<number> {
  const res = await fetch(url, {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({jsonrpc: '2.0', id: 1, method: 'eth_chainId', params: []}),
    signal: AbortSignal.timeout(timeoutMs),
  })
  if (!res.ok) throw new HttpError(res.status, res.statusText)
  const body = await res.json()
  const id = Number(body?.result)
  if (!Number.isFinite(id) || id <= 0) throw new Error('not an EVM RPC')
  return id
}

async function infoOf(apiBase: string): Promise<ChainInfo | null> {
  try {
    const res = await fetch(`${apiBase}/api/info`, {signal: AbortSignal.timeout(8000)})
    if (!res.ok) return null
    return (await res.json()) as ChainInfo
  } catch {
    return null
  }
}

let selectionGeneration = 0
let checking: {url: string; generation: number; promise: Promise<boolean>} | null = null

/** Asks the node for its chain id and its deployment, and classifies the failure when it does not answer. */
export function check(): Promise<boolean> {
  const url = endpoint.rpc, generation = selectionGeneration
  if (checking?.url === url && checking.generation === generation) return checking.promise
  let selectedURL = url
  const current = () => selectionGeneration === generation && endpoint.rpc === selectedURL
  // Own the promise before fetch or a reactive observer can reenter check.
  let accept!: (value: boolean) => void
  let decline!: (reason: unknown) => void
  const completed = new Promise<boolean>((resolve, reject) => {accept = resolve; decline = reject})
  const promise = completed.finally(() => {
    if (checking?.promise === promise) checking = null
  })
  checking = {url, generation, promise}
  const selectRPC = (candidate: string) => {
    if (!current()) return false
    selectedURL = candidate
    if (checking?.promise === promise) checking.url = candidate
    endpoint.rpc = candidate
    return current()
  }
  void run(url, current, selectRPC).then(accept, decline)
  return promise
}

async function run(url: string, current: () => boolean, selectRPC: (candidate: string) => boolean): Promise<boolean> {
  endpoint.health = 'checking'
  clearChain()
  endpoint.error = null
  endpoint.hint = null

  if (mixedContentBlocked(url)) {
    fail(
      `This page is served over HTTPS and cannot reach ${hostOf(url)} over plain HTTP.`,
      'Use an HTTPS address, or http://localhost, which browsers allow from an HTTPS page.',
    )
    return false
  }

  // A zvm node serves its RPC at /rpc. Someone who pasted a host and no path
  // meant that, or an op-reth at the root; try both rather than making them
  // guess which.
  const bare = new URL(url).pathname.replace(/\/+$/, '') === ''
  const candidates = bare ? [`${url}/rpc`, url] : [url]
  const started = performance.now()
  let last: unknown = null
  for (const candidate of candidates) {
    try {
      const chainId = await chainIdOf(candidate, 8000)
      if (!current()) return false
      const apiBase = /\/rpc$/.test(candidate) ? candidate.replace(/\/rpc$/, '') : null
      const info = apiBase ? await infoOf(apiBase) : null
      if (!current()) return false
      if (!selectRPC(candidate)) return false
      save(candidate)
      if (!current()) return false
      endpoint.chainId = chainId
      if (!current()) return false
      endpoint.latency = Math.round(performance.now() - started)
      if (!current()) return false
      endpoint.apiBase = info ? apiBase : null
      if (!current()) return false
      endpoint.info = info
      if (!current()) return false
      endpoint.health = 'ok'
      if (!current()) return false
      endpoint.error = null
      if (!current()) return false
      endpoint.hint = null
      if (!current()) return false
      return true
    } catch (err) {
      if (!current()) return false
      last = err
    }
  }
  if (!current()) return false
  describe(last, url)
  return false
}

function describe(err: any, url: string) {
  if (err?.name === 'TimeoutError') {
    fail(`${hostOf(url)} did not answer within 8 seconds.`, 'The node may be starting up, or the port may be firewalled.')
    return
  }
  if (err instanceof HttpError) {
    fail(`${hostOf(url)} answered ${err.status} ${err.statusText}.`, 'Check the path. A ZVM node serves JSON-RPC at /rpc on its explorer port.')
    return
  }
  if (err?.message === 'not an EVM RPC') {
    fail(`${hostOf(url)} answered, but not like an EVM node.`, 'Point this at the ZVM RPC rather than the NoM RPC.')
    return
  }
  // A cross-origin failure is opaque by design: the browser will not say
  // whether it was DNS, a refused connection, CORS, or Chrome's local network
  // check. Naming the likely causes beats repeating "failed to fetch".
  fail(
    `Could not reach ${hostOf(url)}.`,
    isLoopback(url)
      ? 'Start the node, or check the port. If it is running, your browser may be asking you to allow access to local network devices.'
      : 'Check the node is running and reachable, and that it allows requests from this page.',
  )
}

export function hostOf(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

function clearChain() {
  endpoint.latency = null
  endpoint.chainId = null
  endpoint.apiBase = null
  endpoint.info = null
}

function fail(error: string, hint: string | null) {
  endpoint.health = 'error'
  endpoint.error = error
  endpoint.hint = hint
  clearChain()
}

export const reachable = computed(() => endpoint.health === 'ok')

/** Reachable, and ZNS is deployed on the chain it serves. */
export const hasZns = computed(() => reachable.value && !!deploymentFor(endpoint.chainId))

/** The node's explorer page for a path, for "view on the node" links. */
export const explorerUrl = (path: string) => (endpoint.apiBase ? `${endpoint.apiBase}${path}` : null)
