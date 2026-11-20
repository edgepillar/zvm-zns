import {createHash} from 'node:crypto'
import {writeFileSync} from 'node:fs'
import {isAbsolute} from 'node:path'
import {bundleOrigins, portablePath} from '../../web/scripts/bundle-origins.ts'

export function distributionObserver(repo, destination) {
  if (!destination || !isAbsolute(destination)) throw new Error('Distribution evidence requires an absolute destination')
  return {
    name: 'zns-distribution-evidence',
    apply: 'build',
    enforce: 'post',
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
          const sources = bundleOrigins(output, repo)
          sourceCount += sources.length
          if (sourceCount > 8192) throw new Error('Distribution evidence source limit')
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
