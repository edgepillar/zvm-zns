import {isAbsolute, relative, resolve, sep} from 'node:path'

export function portablePath(name: string): boolean {
  return /^[A-Za-z0-9_@+./-]+$/.test(name) && name.split('/').every(part =>
    part && part !== '.' && part !== '..' && !part.toLowerCase().startsWith('.env')
    && !['.git', '.ssh', 'credentials', 'wallet.json'].includes(part.toLowerCase()))
}

export function sourceOrigin(id: string, repo: string, allowRelative = false): string {
  const virtual = id.startsWith('\0')
  const clean = (virtual ? id.slice(1) : id).split(/[?#]/, 1)[0]
  if (clean && (isAbsolute(clean) || (allowRelative && !virtual))) {
    const path = relative(repo, resolve(repo, 'web', clean)).split(sep).join('/')
    if (portablePath(path) && (path.startsWith('web/node_modules/') || path.startsWith('web/src/')
        || path.startsWith('web/public/') || path.startsWith('zvm-core/web/src/') || path === 'web/index.html'
        || path === 'deployments/browser-fixture.json')) return path
  }
  if (clean.startsWith('vite/')) return '@generated/vite'
  if (clean.startsWith('rolldown:') || clean.startsWith('rolldown/')) return '@generated/rolldown'
  if (virtual && clean.startsWith('commonjs')) return '@generated/commonjs'
  return '@generated/unresolved'
}

type ModuleOrigins = {type: 'chunk', modules: Record<string, unknown>}
type AssetOrigins = {type: 'asset', originalFileNames?: readonly string[]}

export function bundleOrigins(output: ModuleOrigins | AssetOrigins, repo: string): string[] {
  const chunk = output.type === 'chunk'
  const ids = chunk ? Object.keys(output.modules) : output.originalFileNames ?? []
  if (ids.length > 8192) throw new Error('Distribution evidence source limit')
  return [...new Set(ids.map(id => sourceOrigin(id, repo, !chunk)))].sort()
}
