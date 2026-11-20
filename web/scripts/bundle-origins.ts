import {Buffer} from 'node:buffer'
import {isAbsolute, relative, resolve, sep} from 'node:path'

const generatedModules = new Map([
  ['\0vite/modulepreload-polyfill.js', '@generated/vite/modulepreload-polyfill'],
  ['\0vite/preload-helper.js', '@generated/vite/preload-helper'],
  ['\0commonjsHelpers.js', '@generated/vite/commonjs-helpers'],
  ['\0rolldown/runtime.js', '@generated/rolldown/runtime'],
  ['\0plugin-vue:export-helper', '@generated/vue-export-helper'],
])
const tailwindOrigin = '@generated/tailwindcss/'
const tailwindBanner = /\/\*! tailwindcss v([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)*) \| MIT License \| https:\/\/tailwindcss\.com \*\//

export function portablePath(name: string): boolean {
  return /^[A-Za-z0-9_@+./-]+$/.test(name) && name.split('/').every(part =>
    part && part !== '.' && part !== '..' && !part.toLowerCase().startsWith('.env')
    && !['.git', '.ssh', 'credentials', 'wallet.json'].includes(part.toLowerCase()))
}

export function sourceOrigin(id: string, repo: string, allowRelative = false): string {
  const generated = generatedModules.get(id)
  if (generated) return generated
  const virtual = id.startsWith('\0')
  const clean = (virtual ? id.slice(1) : id).split(/[?#]/, 1)[0]
  if (clean && (isAbsolute(clean) || (allowRelative && !virtual))) {
    const path = relative(repo, resolve(repo, 'web', clean)).split(sep).join('/')
    if (portablePath(path) && (path.startsWith('web/node_modules/') || path.startsWith('web/src/')
        || path.startsWith('web/public/') || path.startsWith('zvm-core/web/src/') || path === 'web/index.html'
        || path === 'deployments/browser-fixture.json')) return path
  }
  return '@generated/unresolved'
}

export function generatedPackageLocation(origin: string, rows: Record<string, {version: string}>): string | undefined {
  if (origin.startsWith('@generated/vite/')) return 'node_modules/vite'
  if (origin === '@generated/vue-export-helper') return 'node_modules/@vitejs/plugin-vue'
  if (origin === '@generated/rolldown/runtime') {
    const nested = 'node_modules/vite/node_modules/rolldown'
    return Object.hasOwn(rows, nested) ? nested : 'node_modules/rolldown'
  }
  if (origin.startsWith(tailwindOrigin)) {
    const location = 'node_modules/tailwindcss'
    if (rows[location]?.version !== origin.slice(tailwindOrigin.length)) {
      throw new Error('Tailwind CSS banner version differs from the lock')
    }
    return location
  }
}

type ModuleOrigins = {type: 'chunk', modules: Record<string, unknown>}
type AssetOrigins = {
  type: 'asset'
  fileName: string
  originalFileNames?: readonly string[]
  source: string | Uint8Array
}

export function bundleOrigins(output: ModuleOrigins | AssetOrigins, repo: string): string[] {
  const chunk = output.type === 'chunk'
  const ids = chunk ? Object.keys(output.modules) : output.originalFileNames ?? []
  if (ids.length > 8192) throw new Error('Distribution evidence source limit')
  const origins = new Set(ids.map(id => sourceOrigin(id, repo, !chunk)))
  if (!chunk && output.fileName.endsWith('.css')) {
    const prefix = typeof output.source === 'string' ? Buffer.from(output.source.slice(0, 1024)).subarray(0, 1024)
      : Buffer.from(output.source.subarray(0, 1024))
    const version = tailwindBanner.exec(prefix.toString('utf8'))?.[1]
    if (version) origins.add(tailwindOrigin + version)
  }
  return [...origins].sort()
}
