import assert from 'node:assert/strict'
import {mkdtemp} from 'node:fs/promises'
import {createRequire} from 'node:module'
import {resolve} from 'node:path'
import {test} from 'node:test'
import {createContext, SourceTextModule} from 'node:vm'
import {createServer} from 'vite'

const require = createRequire(import.meta.url)
const version = require('vite/package.json').version
assert.equal(version, '7.3.8')
assert.equal(typeof SourceTextModule, 'function')
const base = process.env.ZNS_VITE_CONTROL_TMPDIR
assert.ok(base, 'a hosted job-owned fixture directory is required')
const names = ['plain', 'both\'"quotes', 'tick`back\\slash', 'line\nreturn\r', 'separators\u2028\u2029', 'literal-${label}']
const observed = []

async function moduleFrom(result) {
  const code = typeof result === 'string' ? result : result?.code
  assert.equal(typeof code, 'string')
  assert.ok(Buffer.byteLength(code) < 16 * 1024)
  const context = createContext(Object.create(null), {codeGeneration: {strings: false, wasm: false}})
  const module = new SourceTextModule(code, {context})
  assert.deepEqual(module.dependencySpecifiers, [])
  await module.link(() => { throw new Error('generated stubs must not import modules') })
  return module
}

for (const production of [false, true]) {
  for (const kind of ['browser-external', 'optional-peer']) {
    await test(`${production ? 'production' : 'development'} ${kind} keeps benign names as text`, async () => {
      const previous = process.env.NODE_ENV
      process.env.NODE_ENV = production ? 'production' : 'development'
      let server
      try {
        const root = await mkdtemp(resolve(base, 'vite-virtual-module-'))
        server = await createServer({
          root, configFile: false, envDir: false, logLevel: 'silent',
          server: {middlewareMode: true, ws: false, watch: null},
          optimizeDeps: {noDiscovery: true, include: []},
        })
        assert.equal(server.httpServer, null)
        assert.equal(server.config.server.ws, false)
        assert.equal(server.config.server.middlewareMode, true)
        assert.equal(server.config.isProduction, production)
        for (const name of names) {
          const peer = `peer-${name}`, parent = `parent-${name}`
          const id = kind === 'browser-external' ? `__vite-browser-external:${name}` : `__vite-optional-peer-dep:${peer}:${parent}:false`
          const module = await moduleFrom(await server.environments.client.pluginContainer.load(id))
          if (kind === 'browser-external') {
            await module.evaluate({timeout: 1000})
            const value = module.namespace.default
            if (production) assert.deepEqual(Object.keys(value), [])
            else assert.throws(() => value.sample, {
              name: 'Error',
              message: `Module "${name}" has been externalized for browser compatibility. Cannot access "${name}.sample" in client code.  See https://vite.dev/guide/troubleshooting.html#module-externalized-for-browser-compatibility for more details.`,
            })
          } else {
            await assert.rejects(module.evaluate({timeout: 1000}), {
              name: 'Error',
              message: `Could not resolve "${peer}" imported by "${parent}".${production ? '' : ' Is it installed?'}`,
            })
          }
          observed.push({production, kind})
        }
      } finally {
        await server?.close()
        if (previous === undefined) delete process.env.NODE_ENV
        else process.env.NODE_ENV = previous
      }
    })
  }
}
assert.equal(observed.length, 24)
console.log('# ZNS_VITE_VIRTUAL_MODULE_RESULT ' + JSON.stringify({
  version, branches: 4, namesPerBranch: names.length, cases: observed.length,
  actualInstalledPluginLoadUsed: true, generatedModulesHadNoImports: true,
  generatedModulesEvaluatedWithVmTimeoutMs: 1000,
  httpRequestsOrListenCallsPerformed: false, browserRuntimeQualified: false,
  optimizerPrebundlePathExecuted: false,
}))
