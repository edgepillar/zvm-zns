// The chain's heartbeat.
//
// One NoM momentum orders exactly one ZVM block, so this chain does not have a
// mempool that drains continuously: it has a beat, measured at about fifteen
// seconds on the devnets. Everything that looks slow about a purchase here follows
// from that, so the beat is tracked once, in one place, and drawn under the
// header where a person can see what they are waiting for.

import {reactive, watch} from 'vue'
import {endpoint, reachable} from './endpoint'
import {publicClient} from '@zvm/web/evm'

export interface ChainState {
  chainId: number | null
  head: number | null
  /** Unix seconds of the head block. */
  timestamp: number | null
  baseFee: bigint | null
  /** Measured seconds between the last few blocks, not the nominal ten. */
  interval: number
  /** Wall clock (ms) when the head last changed. */
  landedAt: number
  /** Wall clock (ms) of the last poll, and the gap to the next: the pulse
   *  under the header fills across it. */
  polledAt: number
  pollMs: number
  error: string | null
}

export const chain = reactive<ChainState>({
  chainId: null,
  head: null,
  timestamp: null,
  baseFee: null,
  interval: 15,
  landedAt: Date.now(),
  polledAt: Date.now(),
  pollMs: 60_000,
  error: null,
})

/** Called once per new block, by whoever wants to refresh on the beat. */
const onBlockListeners = new Set<(head: number) => void>()

export function onBlock(fn: (head: number) => void): () => void {
  onBlockListeners.add(fn)
  return () => onBlockListeners.delete(fn)
}

let timer: number | undefined
let lastSeen: number | null = null
let started = false
let generation = 0
let reading: {generation: number; promise?: Promise<void>} | null = null
const gaps: number[] = []

// A hidden tab does not poll. Every page refreshes on the beat, so a
// background tab left open all day was one block read every three seconds plus
// each page's own refetch on every block, for a screen nobody was looking at.
// Coming back polls at once, and the listeners catch the page up.
const hidden = () => typeof document !== 'undefined' && document.hidden

function poll(): Promise<void> | undefined {
  if (!reachable.value || endpoint.chainId === null || hidden()) return
  const selected = generation
  if (reading?.generation === selected) return reading.promise
  const rpc = endpoint.rpc, chainId = endpoint.chainId
  const current = () => generation === selected && endpoint.rpc === rpc &&
    endpoint.chainId === chainId && reachable.value && !hidden()
  const owner: {generation: number; promise?: Promise<void>} = {generation: selected}
  reading = owner
  owner.promise = read(chainId, current).finally(() => {
    if (reading === owner) reading = null
  })
  return owner.promise
}

async function read(chainId: number, current: () => boolean): Promise<void> {
  try {
    const client = publicClient(chainId)
    if (!current()) return
    // The height first, and the block only when it moved. cacheTime 0 because
    // viem otherwise caches the height for its polling interval.
    const number = await client.getBlockNumber({cacheTime: 0})
    if (!current()) return
    chain.polledAt = Date.now()
    if (!current()) return
    chain.chainId = chainId
    if (!current()) return
    chain.error = null
    if (!current()) return
    if (Number(number) === lastSeen) return
    const block = await client.getBlock({blockNumber: number})
    if (!current()) return
    const head = Number(block.number)
    chain.baseFee = block.baseFeePerGas ?? null
    if (!current()) return
    if (head !== lastSeen) {
      // Blocks carry NoM's own timestamps, so the gap between two of them is
      // the momentum cadence rather than this browser's clock drift. A poll
      // a minute apart sees several blocks at once; the gap is per block.
      if (chain.timestamp && block.timestamp && lastSeen !== null && head > lastSeen) {
        const gap = (Number(block.timestamp) - chain.timestamp) / Math.max(1, head - lastSeen)
        if (gap > 0 && gap < 120) {
          gaps.push(gap)
          if (gaps.length > 8) gaps.shift()
          chain.interval = gaps.reduce((a, b) => a + b, 0) / gaps.length
        }
      }
      if (!current()) return
      lastSeen = head
      if (!current()) return
      chain.head = head
      if (!current()) return
      chain.timestamp = Number(block.timestamp)
      if (!current()) return
      chain.landedAt = Date.now()
      if (!current()) return
      for (const fn of onBlockListeners) {
        if (!current()) break
        fn(head)
      }
    }
  } catch (err: any) {
    if (current()) chain.error = err?.shortMessage ?? err?.message ?? String(err)
  }
}

export function startChainPolling(intervalMs = 60_000) {
  if (started || timer !== undefined) return
  started = true
  chain.pollMs = intervalMs
  poll()
  timer = window.setInterval(poll, intervalMs)
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      generation++
      reading = null
    } else poll()
  })
}

// A new node is a new chain until proven otherwise: drop what the old one said
// rather than showing its head height under the new endpoint's name.
watch(
  () => [endpoint.rpc, endpoint.chainId, endpoint.health],
  () => {
    generation++
    reading = null
    lastSeen = null
    gaps.length = 0
    chain.chainId = null
    chain.head = null
    chain.timestamp = null
    chain.baseFee = null
    chain.interval = 15
    chain.landedAt = Date.now()
    chain.polledAt = Date.now()
    chain.error = null
    return poll()
  },
  {flush: 'sync'},
)
