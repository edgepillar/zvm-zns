import {createHash} from 'node:crypto'
import {existsSync, lstatSync, readFileSync, readdirSync, realpathSync} from 'node:fs'
import {dirname, join} from 'node:path'
import type {Plugin} from 'vite'
import {bundleOrigins, generatedPackageLocation, portablePath, stylesheetChunkInputs} from './bundle-origins'

const indexFile = 'notices/npm/index.json'
const noticeName = /^(LICENSE|LICENCE|COPYING|NOTICE|COPYRIGHT|OFL|UNLICENSE)/i
const packageName = /^(?:@[a-z0-9_.-]+\/)?[a-z0-9_.-]+$/
const versionText = /^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)*$/

type LockRow = {name?: string, version: string, resolved?: string, integrity?: string}
type PickedPackage = {name: string, version: string, license?: string}
type NoticeFile = {member: string, file: string, bytes: number, sha256: string}
type PackageNotices = {location: string, name: string, version: string, license: string | null, notices: NoticeFile[]}

function readBounded(root: string, relative: string, limit: number): Buffer {
  if (!portablePath(relative)) throw new Error('Invalid browser notice path')
  let current = root
  for (const part of relative.split('/')) {
    current = join(current, part)
    if (lstatSync(current).isSymbolicLink()) throw new Error('Browser notice input is a symbolic link')
  }
  const before = lstatSync(current, {bigint: true})
  if (!before.isFile() || before.size > BigInt(limit)) throw new Error('Browser notice input exceeds its bounds')
  const raw = readFileSync(current)
  const after = lstatSync(current, {bigint: true})
  if (before.dev !== after.dev || before.ino !== after.ino || before.size !== after.size
    || before.mtimeNs !== after.mtimeNs || before.ctimeNs !== after.ctimeNs
    || BigInt(raw.byteLength) !== before.size) throw new Error('Browser notice input changed during the build')
  return raw
}

function digest(raw: Buffer): string {
  return createHash('sha256').update(raw).digest('hex')
}

export function browserNotices(directory: string): Plugin {
  return {
    name: 'zns-browser-notices',
    apply: 'build',
    enforce: 'post',
    generateBundle: {
      order: 'post',
      handler(_options, bundle) {
        const web = realpathSync(directory)
        const lock = JSON.parse(readBounded(web, 'package-lock.json', 2 << 20).toString()) as {
          lockfileVersion: number, packages: Record<string, LockRow>
        }
        if (lock.lockfileVersion !== 3) throw new Error('Browser notices require an npm v3 lock file')
        const locations = Object.keys(lock.packages).filter(path => path.startsWith('node_modules/') && portablePath(path))
        if (locations.length > 512) throw new Error('Browser notices lock location limit')
        locations.sort((a, b) => b.length - a.length || (a < b ? -1 : 1))
        const repo = dirname(web)
        const outputs = Object.values(bundle)
        const reported = new Set(outputs.flatMap(output => bundleOrigins(output, repo)))
        const selected = new Set<string>()
        for (const origin of reported) {
          const generatedLocation = generatedPackageLocation(origin, lock.packages)
          if (generatedLocation) selected.add(generatedLocation)
          if (!origin.startsWith('web/node_modules/')) continue
          const path = origin.slice(4)
          const location = locations.find(candidate => path.startsWith(candidate + '/'))
          if (!location) throw new Error('A browser origin has no dependency lock row')
          selected.add(location)
        }
        const styleEntryEmitted = outputs.some(output => {
          if (output.type !== 'chunk') return false
          const stylesheet = stylesheetChunkInputs(output, repo)
          return stylesheet !== undefined && stylesheet.sources.includes('web/src/style.css')
            && bundle[stylesheet.file]?.type === 'asset'
        })
        if (styleEntryEmitted && /^[ \t]*@import[ \t]+(['"])tailwindcss\1[ \t]*;/m
          .test(readBounded(web, 'src/style.css', 1 << 20).toString())) {
          selected.add('node_modules/tailwindcss')
        }
        if (selected.size > 128) throw new Error('Browser notice package limit')

        const existing = new Map<string, string>()
        const publicNotices = join(web, 'public/notices')
        for (const entry of readdirSync(publicNotices, {withFileTypes: true}).sort((a, b) => a.name < b.name ? -1 : 1)) {
          if (!entry.isFile()) continue
          const path = 'notices/' + entry.name
          const sha256 = digest(readBounded(web, 'public/' + path, 1 << 20))
          if (!existing.has(sha256)) existing.set(sha256, path)
        }
        const pending = new Map<string, Buffer>()
        const packages: PackageNotices[] = []
        let payload = 0
        let files = 0
        for (const location of [...selected].sort()) {
          const row = lock.packages[location]
          const pkg = JSON.parse(readBounded(web, location + '/package.json', 1 << 20).toString()) as PickedPackage
          const name = row.name ?? location.split('node_modules/').at(-1)
          if (!name || !packageName.test(name) || !versionText.test(row.version)
              || pkg.name !== name || pkg.version !== row.version
              || row.resolved !== 'https://registry.npmjs.org/' + name + '/-/' + name.split('/').at(-1) + '-' + row.version + '.tgz'
              || !/^sha512-[A-Za-z0-9+/]{86}==$/.test(row.integrity ?? '')) {
            throw new Error('Browser notice package identity differs from the lock')
          }
          const notices: NoticeFile[] = []
          for (const entry of readdirSync(join(web, location), {withFileTypes: true}).sort((a, b) => a.name < b.name ? -1 : 1)) {
            if (!noticeName.test(entry.name) || !entry.isFile()) continue
            const raw = readBounded(web, location + '/' + entry.name, 1 << 20)
            const sha256 = digest(raw)
            let file = existing.get(sha256)
            if (!file) {
              file = 'notices/npm/' + name + '@' + pkg.version + '/' + entry.name
              if (pending.has(file) || bundle[file] || existsSync(join(web, 'public', file))) throw new Error('Browser notice output collision')
              payload += raw.byteLength
              if (payload > 2 << 20 || pending.size >= 256) throw new Error('Browser notice output limit')
              existing.set(sha256, file)
              pending.set(file, raw)
            }
            if (++files > 512) throw new Error('Browser notice record limit')
            notices.push({member: entry.name, file, bytes: raw.byteLength, sha256})
          }
          packages.push({location, name, version: pkg.version, license: pkg.license ?? null, notices})
        }
        if (bundle[indexFile] || existsSync(join(web, 'public', indexFile))) throw new Error('Browser notice index already exists')
        const index = JSON.stringify({schema: 1, packages}, null, 2) + '\n'
        if (Buffer.byteLength(index) > 256 << 10) throw new Error('Browser notice index limit')
        for (const [fileName, source] of pending) this.emitFile({type: 'asset', fileName, source})
        this.emitFile({type: 'asset', fileName: indexFile, source: index})
      },
    },
  }
}
