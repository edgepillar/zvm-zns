// Drives the built page against the ZVM, in headless Chrome, and registers for
// real.
//
//   node scripts/verify.mjs [rpc, default $ZVM_RPC] [http://localhost:47801/]
//
// A stand-in EIP-6963 wallet signs with a throwaway key, exactly as MetaMask
// would; dev key 900 funds it. Nothing under the wallet is mocked: the relayer
// posts each transaction to NoM, the deriver derives it, op-reth runs it, and
// the page reads it back. It searches a name, registers it through the page
// (commit, the minute's wait, the reveal) as the primary name, while a second
// key registers another name for the same wallet from outside the page. Then
// it edits records, makes a subname, renews, switches the primary name from
// My names, renews both in one transaction, sends one away, and checks that
// the rent was burned, that the card the page draws is the card the contract
// draws, that Karum's sell link is right, and that nothing scrolls sideways
// on a phone. It spends about 3 ZNN a run.
// Set ZNS_SHOTS to a directory to keep screenshots.

import {existsSync, mkdirSync, readFileSync} from 'node:fs'
import {join} from 'node:path'
import {prepareRuntime} from './prepare-runtime.mjs'
prepareRuntime(undefined, {checkOnly: true})
const {default: puppeteer} = await import('puppeteer-core')
import {
  createPublicClient,
  createWalletClient,
  defineChain,
  encodeFunctionData,
  http,
  keccak256,
  labelhash,
  namehash,
  parseEther,
  toBytes,
  toHex,
  zeroHash,
} from 'viem'
import {generatePrivateKey, privateKeyToAccount} from 'viem/accounts'
import {getEnsAddress} from 'viem/ens'
import {cardSvg} from '../src/core/art.ts'

const rpc = process.argv[2] ?? process.env.ZVM_RPC
if (!rpc) throw new Error("pass the node's JSON-RPC, or set ZVM_RPC")
const app = process.argv[3] ?? 'http://localhost:47801/'
const shots = process.env.ZNS_SHOTS
if (shots) mkdirSync(shots, {recursive: true})
const record = JSON.parse(readFileSync(new URL('../../deployments/zvm.json', import.meta.url), 'utf8'))
const c = record.contracts
const abi = (name) => JSON.parse(readFileSync(new URL(`../../contracts/out/${name}.json`, import.meta.url), 'utf8')).abi

const started = Date.now()
const log = (msg) => console.log(`[${((Date.now() - started) / 1000).toFixed(0).padStart(4)}s] ${msg}`)
let failed = false
const check = (ok, what) => {
  if (!ok) throw new Error(`FAILED: ${what}`)
  log(`   ok   ${what}`)
}

const chromePath = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome'].find((p) => existsSync(p))
if (!chromePath) throw new Error('no Chrome found')

const chain = defineChain({id: record.chainId, name: 'ZVM', nativeCurrency: {name: 'Zenon', symbol: 'ZNN', decimals: 18}, rpcUrls: {default: {http: [rpc]}}})
const client = createPublicClient({chain, transport: http(rpc)})
const fees = async () => ({maxFeePerGas: ((await client.getBlock()).baseFeePerGas ?? 0n) * 2n + 100_000_000_000n, maxPriorityFeePerGas: 100_000_000_000n})
const wait = async (hash) => {
  const r = await client.waitForTransactionReceipt({hash, pollingInterval: 2000, timeout: 600_000})
  if (r.status !== 'success') throw new Error(`${hash} reverted`)
  return r
}

const account = privateKeyToAccount(generatePrivateKey())
const helper = privateKeyToAccount(generatePrivateKey())
const signer = createWalletClient({account, chain, transport: http(rpc)})
const helperSigner = createWalletClient({account: helper, chain, transport: http(rpc)})
const funder = createWalletClient({account: privateKeyToAccount(keccak256(toBytes('zvm-dev-evm-900'))), chain, transport: http(rpc)})
log(`wallet ${account.address}, helper ${helper.address}`)
for (const [who, amount] of [[account.address, '4'], [helper.address, '2']]) await wait(await funder.sendTransaction({to: who, value: parseEther(amount), ...(await fees())}))
log('funded from dev key 900')

const tag = Math.random().toString(36).slice(2, 8)
const first = `verify-${tag}`
const second = `verify-${tag}-two`

// --- the stand-in wallet ----------------------------------------------------

async function evmRequest(method, params) {
  switch (method) {
    case 'eth_requestAccounts':
    case 'eth_accounts':
      return [account.address]
    case 'eth_chainId':
      return `0x${chain.id.toString(16)}`
    case 'wallet_switchEthereumChain':
    case 'wallet_addEthereumChain':
      return null
    case 'eth_sendTransaction': {
      const [tx] = params
      return signer.sendTransaction({
        to: tx.to,
        data: tx.data,
        value: tx.value ? BigInt(tx.value) : 0n,
        gas: tx.gas ? BigInt(tx.gas) : undefined,
        maxFeePerGas: tx.maxFeePerGas ? BigInt(tx.maxFeePerGas) : undefined,
        maxPriorityFeePerGas: tx.maxPriorityFeePerGas ? BigInt(tx.maxPriorityFeePerGas) : undefined,
      })
    }
    default:
      return client.request({method, params})
  }
}

// A registration waits on NoM, which can take minutes on a busy devnet.
const browser = await puppeteer.launch({executablePath: chromePath, headless: 'new', args: ['--no-sandbox', '--disable-gpu'], protocolTimeout: 900_000})
const page = await browser.newPage()
await page.setViewport({width: 1280, height: 1000, deviceScaleFactor: 1})
const problems = []
page.on('pageerror', (err) => problems.push(`page error: ${err.message}`))
page.on('console', (m) => m.type() === 'error' && !/Failed to load resource/.test(m.text()) && problems.push(`console: ${m.text()}`))
await page.exposeFunction('__evm', evmRequest)
await page.evaluateOnNewDocument((rpc) => {
  try {
    localStorage.setItem('zns.rpc', rpc)
  } catch {}
  const provider = {request: ({method, params}) => window.__evm(method, params ?? []), on() {}, removeListener() {}}
  const announce = () =>
    window.dispatchEvent(new CustomEvent('eip6963:announceProvider', {detail: Object.freeze({info: {uuid: 'zns-verify', name: 'Test wallet', icon: '', rdns: 'test.zns'}, provider})}))
  window.addEventListener('eip6963:requestProvider', announce)
}, rpc)
const shot = async (name) => shots && page.screenshot({path: join(shots, `${name}.png`), fullPage: true})
const text = (sel) => page.$eval(sel, (el) => el.textContent.replace(/\s+/g, ' ').trim())
const goto = async (hash) => {
  await page.goto(`${app}${hash}`, {waitUntil: 'networkidle2'})
}

/** Waits for every step in `scope` to execute, and fails on the first that did not. */
async function settle(scope, count) {
  await page.waitForFunction(
    (scope, count) => {
      const lis = [...document.querySelectorAll(`${scope} li[data-state]`)]
      return lis.some((l) => l.dataset.state === 'failed') || (lis.length >= count && lis.every((l) => l.dataset.state === 'done'))
    },
    {timeout: 900_000, polling: 1000},
    scope,
    count,
  )
  const failedStep = await page.$$eval(`${scope} li[data-state="failed"]`, (els) => els.map((e) => e.textContent.replace(/\s+/g, ' ').trim()))
  if (failedStep.length) throw new Error(`a step failed: ${failedStep[0]}`)
}

// The second name, registered for the wallet by another key, the way a
// friend or a script might: owner and sender differ.
async function registerFromOutside(label) {
  const controller = abi('ZNSController')
  const resolverAbi = abi('PublicResolver')
  const reg = {
    label,
    owner: account.address,
    duration: 31_536_000n,
    secret: toHex(crypto.getRandomValues(new Uint8Array(32))),
    resolver: c.PublicResolver,
    data: [encodeFunctionData({abi: resolverAbi, functionName: 'setAddr', args: [namehash(`${label}.znn`), account.address]})],
    reverseRecord: 0,
    referrer: zeroHash,
  }
  const commitment = await client.readContract({address: c.ZNSController, abi: controller, functionName: 'makeCommitment', args: [reg]})
  const r = await wait(await helperSigner.writeContract({address: c.ZNSController, abi: controller, functionName: 'commit', args: [commitment], ...(await fees())}))
  const committed = Number((await client.getBlock({blockNumber: r.blockNumber})).timestamp)
  while (Number((await client.getBlock()).timestamp) < committed + 61) await new Promise((res) => setTimeout(res, 3000))
  const price = await client.readContract({address: c.ZNSController, abi: controller, functionName: 'rentPrice', args: [label, reg.duration]})
  await wait(await helperSigner.writeContract({address: c.ZNSController, abi: controller, functionName: 'register', args: [reg], value: price.base + price.premium, ...(await fees())}))
}

const BURN = '0x000000000000000000000000000000000000dEaD'
const burnedBefore = await client.getBalance({address: BURN})

try {
  const outside = registerFromOutside(second).then(() => log(`   ..   ${second}.znn registered from outside the page`))

  // --- search, then register through the page -------------------------------
  await goto('#/')
  await page.waitForSelector('[data-testid=search]')
  await page.type('[data-testid=search]', first.toUpperCase())
  await page.waitForSelector('[data-testid=result]', {timeout: 30_000})
  const result = await text('[data-testid=result]')
  check(result.includes(`${first}.znn`) && /Available/.test(result) && /1 ZNN/.test(result), `searching finds ${first}.znn available at 1 ZNN: "${result}"`)
  await shot('01-search')

  await page.click('[data-testid=connect]')
  await page.waitForFunction(() => [...document.querySelectorAll('dialog button')].some((b) => b.textContent.includes('Test wallet')), {timeout: 20_000})
  await page.evaluate(() => [...document.querySelectorAll('dialog button')].find((b) => b.textContent.includes('Test wallet')).click())
  await page.waitForFunction(() => !/Connect wallet/.test(document.querySelector('[data-testid=connect]').textContent), {timeout: 20_000})
  check(true, 'the wallet connects')

  await page.click('[data-testid=result]')
  await page.waitForSelector('[data-testid=register-go]', {timeout: 30_000})
  await page.waitForFunction(() => /ZNN/.test(document.querySelector('[data-testid=total]').textContent) && !/-/.test(document.querySelector('[data-testid=total]').textContent.replace(/ZNN/, '')), {timeout: 30_000})
  check((await text('[data-testid=total]')) === '1 ZNN', `a year costs 1 ZNN: ${await text('[data-testid=total]')}`)
  check(await page.$eval('[data-testid=primary]', (el) => el.checked), 'a wallet with no primary name gets this one by default')
  await page.click('[data-testid=register-go]')
  log('   ..   registering: commit, a minute, reveal')
  await page.waitForFunction(() => document.querySelector('[data-testid=register] li[data-state="waiting"]'), {timeout: 600_000})
  check(true, 'the commitment executed and the page waits the minute')
  await shot('02-waiting')
  await settle('[data-testid=register]', 3)
  check(true, `${first}.znn registered through the page`)
  await page.waitForSelector('[data-testid=expires]', {timeout: 120_000})
  await page.waitForFunction((a) => document.querySelector('[data-testid=addr]')?.textContent.toLowerCase() === a.toLowerCase(), {timeout: 120_000}, account.address)
  check(true, 'the name page shows it registered, pointing at the wallet')
  await page.waitForFunction((n) => document.querySelector('[data-testid=wallet-name]')?.textContent === n, {timeout: 120_000}, `${first}.znn`)
  check(true, 'the wallet button now reads as the primary name')
  await shot('03-registered')

  // --- the card, the contract's and the page's ----------------------------
  const id = BigInt(labelhash(first))
  const uri = await client.readContract({address: c.ZNSRegistrar, abi: abi('ZNSRegistrar'), functionName: 'tokenURI', args: [id]})
  const meta = JSON.parse(Buffer.from(uri.split(',')[1], 'base64').toString())
  const onChain = Buffer.from(meta.image.split(',')[1], 'base64').toString()
  const expires = Number(await client.readContract({address: c.ZNSRegistrar, abi: abi('ZNSRegistrar'), functionName: 'nameExpires', args: [id]}))
  check(onChain === cardSvg(first, expires), 'the card the page draws is byte for byte the card the contract draws')
  check(meta.name === `${first}.znn`, 'the token names itself')

  // --- records ----------------------------------------------------------------
  await page.click('[data-testid=edit]')
  await page.waitForSelector('[data-testid=text-description]', {visible: true})
  await page.type('[data-testid=text-description]', 'verified by a script')
  await page.type('[data-testid=text-url]', 'zenon.network')
  await page.click('[data-testid=save-records]')
  await settle('dialog[open]', 1)
  await page.waitForFunction(() => document.body.textContent.includes('verified by a script'), {timeout: 120_000})
  check(true, 'records saved in one transaction and shown')

  // --- a subname -------------------------------------------------------------
  await page.keyboard.press('Escape')
  await page.click('[data-testid=new-sub]')
  await page.waitForSelector('[data-testid=sub-label]', {visible: true})
  await page.type('[data-testid=sub-label]', 'pay')
  await page.click('[data-testid=sub-go]')
  await settle('dialog[open]', 2)
  await page.waitForFunction((n) => [...document.querySelectorAll('a')].some((a) => a.textContent === n), {timeout: 120_000}, `pay.${first}.znn`)
  const ens = createPublicClient({chain: {...chain, contracts: {ensUniversalResolver: {address: c.UniversalResolver}}}, transport: http(rpc)})
  const sub = await getEnsAddress(ens, {name: `pay.${first}.znn`})
  check(sub?.toLowerCase() === account.address.toLowerCase(), `pay.${first}.znn exists, is listed, and resolves through the universal resolver`)

  // --- renew --------------------------------------------------------------
  await page.keyboard.press('Escape')
  await page.click('[data-testid=renew]')
  await page.waitForSelector('[data-testid=renew-go]', {visible: true})
  await page.waitForFunction(() => !document.querySelector('[data-testid=renew-go]').disabled, {timeout: 30_000})
  await page.click('[data-testid=renew-go]')
  await settle('dialog[open]', 1)
  const renewed = Number(await client.readContract({address: c.ZNSRegistrar, abi: abi('ZNSRegistrar'), functionName: 'nameExpires', args: [id]}))
  check(renewed === expires + 31_536_000, 'renewing added a year')
  const sell = await page.$eval('[data-testid=sell]', (a) => a.href)
  check(sell.endsWith(`/item/${c.ZNSRegistrar}/${id}?list=1`), `Sell on Karum links to the item with the listing form open: ${sell}`)

  // --- My names: switch the primary name, renew both ------------------------
  await outside
  await goto('#/names')
  await page.waitForFunction((n) => document.querySelector('[data-testid=inventory]')?.textContent.includes(n), {timeout: 120_000}, `${second}.znn`)
  check(true, 'My names lists the name registered from outside the page')
  await page.click(`[data-testid="primary-${second}"]`)
  await page.waitForFunction((n) => document.querySelector('[data-testid=wallet-name]')?.textContent === n, {timeout: 600_000}, `${second}.znn`)
  check(true, `the primary name switched to ${second}.znn from My names`)
  await shot('04-my-names')

  for (const label of [first, second]) await page.click(`input[aria-label="Select ${label}.znn"]`)
  await page.click('[data-testid=bulk-renew]')
  await page.waitForFunction(() => !document.querySelector('[data-testid=bulk-renew-go]').disabled, {timeout: 30_000})
  await page.click('[data-testid=bulk-renew-go]')
  await settle('dialog[open]', 1)
  const both = await Promise.all([first, second].map((l) => client.readContract({address: c.ZNSRegistrar, abi: abi('ZNSRegistrar'), functionName: 'nameExpires', args: [BigInt(labelhash(l))]})))
  check(Number(both[0]) === renewed + 31_536_000, 'both names renewed in one transaction')
  await page.keyboard.press('Escape')

  // --- send one away -----------------------------------------------------------
  await goto(`#/name/${first}.znn`)
  await page.waitForSelector('[data-testid=send]', {timeout: 60_000})
  await page.click('[data-testid=send]')
  await page.waitForSelector('dialog[open] input', {visible: true})
  await page.type('dialog[open] input', helper.address)
  await page.evaluate(() => [...document.querySelectorAll('dialog[open] button')].find((b) => b.textContent.trim() === 'Send').click())
  await settle('dialog[open]', 1)
  const owner = await client.readContract({address: c.ENSRegistry, abi: abi('ENSRegistry'), functionName: 'owner', args: [namehash(`${first}.znn`)]})
  check(owner.toLowerCase() === helper.address.toLowerCase(), 'sending moved the token and control of its records together')

  // --- the rent was burned -------------------------------------------------
  const burned = (await client.getBalance({address: BURN})) - burnedBefore
  check(burned >= parseEther('3.99'), `the rent went to the burn address: ${Number(burned) / 1e18} ZNN over this run (other burns land there too)`)
  check((await client.getBalance({address: c.ZNSController})) === 0n, 'the controller holds nothing')

  // --- pages that only read --------------------------------------------------
  await goto(`#/address/${account.address}`)
  await page.waitForFunction((n) => document.querySelector('[data-testid=profile-name]')?.textContent === n, {timeout: 60_000}, `${second}.znn`)
  check(true, 'the address page shows the primary name')
  await page.setViewport({width: 400, height: 860, deviceScaleFactor: 1})
  for (const hash of ['#/', `#/name/${second}.znn`, '#/names', '#/explore', '#/about']) {
    await goto(hash)
    await new Promise((r) => setTimeout(r, 1500))
    const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    check(wide <= 0, `no sideways scroll at 400px on ${hash}`)
  }
  await shot('05-phone')
  check(problems.length === 0, `no page errors${problems.length ? `: ${problems.join('; ')}` : ''}`)
} catch (err) {
  failed = true
  console.error(err)
  await shot('failure')
} finally {
  await browser.close()
}
log(failed ? 'FAILED' : 'passed')
process.exit(failed ? 1 : 0)
