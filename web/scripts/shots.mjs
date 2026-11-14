// Screenshots of the built page, for eyeballing a change.
//   node scripts/shots.mjs <outdir> [http://localhost:47801/] [path ...]
import {existsSync, mkdirSync} from 'node:fs'
import {join} from 'node:path'
import {prepareRuntime} from './prepare-runtime.mjs'
prepareRuntime(undefined, {checkOnly: true})
const {default: puppeteer} = await import('puppeteer-core')

const out = process.argv[2]
const app = process.argv[3] ?? 'http://localhost:47801/'
const paths = process.argv.slice(4).length ? process.argv.slice(4) : ['#/', '#/name/zenon.znn', '#/explore', '#/about']
mkdirSync(out, {recursive: true})
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome'].find((p) => existsSync(p))
const browser = await puppeteer.launch({executablePath: chrome, headless: 'new', args: ['--no-sandbox']})
const page = await browser.newPage()
page.on('pageerror', (e) => console.log('pageerror', e.message))
page.on('console', (m) => m.type() === 'error' && console.log('console', m.text()))
await page.evaluateOnNewDocument(() => localStorage.removeItem('zns.rpc'))
for (const [i, p] of paths.entries()) {
  for (const [w, h] of [[1280, 900], [400, 860]]) {
    await page.setViewport({width: w, height: h})
    await page.goto(app + p, {waitUntil: 'networkidle0'})
    await new Promise((r) => setTimeout(r, 2500))
    await page.screenshot({path: join(out, `${i}-${w}.png`), fullPage: true})
    const sideways = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    if (sideways) console.log(`${p} at ${w}px scrolls sideways`)
  }
}
await browser.close()
