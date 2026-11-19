import {createHash} from 'node:crypto'
import {writeFileSync} from 'node:fs'
import {isAbsolute, relative, resolve} from 'node:path'

function portablePath(name) {
  return /^[A-Za-z0-9_@+./-]+$/.test(name) && name.split('/').every(part =>
    part && part !== '.' && part !== '..' && !part.toLowerCase().startsWith('.env')
    && !['.git', '.ssh', 'credentials', 'wallet.json'].includes(part.toLowerCase()))
}

export function sourceOrigin(id, repo, allowRelative = false) {
  const virtual = id.startsWith('\0')
  const clean = (virtual ? id.slice(1) : id).split(/[?#]/, 1)[0]
  if (clean && (isAbsolute(clean) || (allowRelative && !virtual))) {
    const path = relative(repo, resolve(repo, 'web', clean))
    if (portablePath(path) && (path.startsWith('web/node_modules/') || path.startsWith('web/src/')
        || path.startsWith('web/public/') || path.startsWith('zvm-core/web/src/') || path === 'web/index.html'
        || path === 'deployments/browser-fixture.json')) return path
  }
  if (clean.startsWith('vite/')) return '@generated/vite'
  if (clean.startsWith('rolldown:') || clean.startsWith('rolldown/')) return '@generated/rolldown'
  if (virtual && clean.startsWith('commonjs')) return '@generated/commonjs'
  return '@generated/unresolved'
}

export function distributionObserver(repo, destination) {
  if (!destination || !isAbsolute(destination)) throw new Error('Distribution evidence requires an absolute destination')
  return {
    name: 'zns-distribution-evidence',
    apply: 'build',
    generateBundle: {
      order: 'post',
      handler(_options, bundle) {
        const outputs = {}
        let sourceCount = 0
        const names = Object.keys(bundle).sort()
        if (names.length > 512) throw new Error('Distribution evidence file limit')
        for (const name of names) {
          if (!portablePath(name)) throw new Error('Distribution evidence requires portable output names')
          const output = bundle[name]
          const chunk = output.type === 'chunk'
          const source = chunk ? output.code : output.source
          const ids = chunk ? Object.keys(output.modules) : output.originalFileNames ?? []
          sourceCount += ids.length
          if (sourceCount > 8192) throw new Error('Distribution evidence source limit')
          const sources = [...new Set(ids.map(id => sourceOrigin(id, repo, !chunk)))].sort()
          outputs[name] = {
            type: output.type,
            bytes: typeof source === 'string' ? Buffer.byteLength(source) : source.byteLength,
            sha256: createHash('sha256').update(source).digest('hex'),
            sources,
          }
        }
        const data = JSON.stringify({schema: 1, outputs}) + '\n'
        if (Buffer.byteLength(data) > 1 << 20) throw new Error('Distribution evidence byte limit')
        writeFileSync(destination, data, {flag: 'wx', mode: 0o600})
      },
    },
  }
}
