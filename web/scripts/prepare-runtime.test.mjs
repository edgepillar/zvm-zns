import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { prepareRuntime } from './prepare-runtime.mjs'

// These controls intentionally include a symbolic-link fixture. They run only
// in the hosted Linux lane, never inside local managed foreground scratch.
assert.equal(process.env.GITHUB_ACTIONS, 'true')
assert.equal(process.platform, 'linux'); assert.equal(process.arch, 'x64')
assert(process.env.RUNNER_TEMP && path.isAbsolute(process.env.RUNNER_TEMP))
const source = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const vendor = 'vendor/chromium-bidi-157-reviewed'
const prefix = 'node_modules/chromium-bidi/'
const manifest = JSON.parse(fs.readFileSync(path.join(source, vendor, 'manifest.json')))
const originals = new Map()
for (const [name, row] of Object.entries(manifest.effectiveMembers)) {
  if (row.original) originals.set(name, fs.readFileSync(path.join(source, name)))
}
assert.equal(originals.size, 4)
const common = new Map([
  ['package.json', fs.readFileSync(path.join(source, 'package.json'))],
  ['package-lock.json', fs.readFileSync(path.join(source, 'package-lock.json'))],
  [prefix + 'package.json', fs.readFileSync(path.join(source, prefix, 'package.json'))],
  [vendor + '/manifest.json', fs.readFileSync(path.join(source, vendor, 'manifest.json'))],
])
for (const name of Object.keys(manifest.payloads)) common.set(vendor + '/payload/' + name,
  fs.readFileSync(path.join(source, vendor, 'payload', name)))
assert([...common.values(), ...originals.values()].reduce((sum, raw) => sum + raw.length, 0) < 24 << 20)
function write(root, name, raw) {
  const file = path.join(root, name); fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, raw, { flag: 'wx', mode: 0o644 })
}
function fixture(callback) {
  const root = fs.mkdtempSync(path.join(process.env.RUNNER_TEMP, 'zns-runtime-control-'))
  assert.equal(fs.realpathSync(root), root)
  try {
    for (const [name, raw] of [...common, ...originals]) write(root, name, raw)
    callback(root)
  } finally { fs.rmSync(root, { recursive: true, force: false }) }
}
function rawUnchanged(root) {
  for (const [name, raw] of originals) assert.deepEqual(fs.readFileSync(path.join(root, name)), raw)
  for (const [name, row] of Object.entries(manifest.effectiveMembers)) {
    if (!row.original) assert(!fs.existsSync(path.join(root, name)))
  }
  assert(!fs.readdirSync(path.join(root, 'node_modules')).some(name => name.startsWith('.zns-runtime-')))
}

test('prepares all exact effective members with original manifest and lock intact', () => fixture(root => {
  const result = prepareRuntime(root)
  assert.equal(result.status, 'REVIEWED_RUNTIME_PREPARED'); assert.equal(result.changedMembers, 9)
  assert.equal(result.networkCompilerPackageManagerOrBrowserExecuted, false)
  for (const name of Object.keys(manifest.payloads)) assert.deepEqual(
    fs.readFileSync(path.join(root, prefix + name)), fs.readFileSync(path.join(root, vendor, 'payload', name)))
  assert.deepEqual(fs.readFileSync(path.join(root, 'package-lock.json')), common.get('package-lock.json'))
  assert.deepEqual(fs.readFileSync(path.join(root, prefix, 'package.json')), common.get(prefix + 'package.json'))
}))
test('a second preparation and check preserve identities without rewriting', () => fixture(root => {
  prepareRuntime(root)
  const identities = Object.keys(manifest.payloads).map(name => {
    const row = fs.statSync(path.join(root, prefix + name)); return [row.ino, row.mode, row.mtimeMs, row.ctimeMs]
  })
  assert.equal(prepareRuntime(root).changedMembers, 0)
  assert.equal(prepareRuntime(root, { checkOnly: true }).status, 'REVIEWED_RUNTIME_VERIFIED')
  assert.deepEqual(Object.keys(manifest.payloads).map(name => {
    const row = fs.statSync(path.join(root, prefix + name)); return [row.ino, row.mode, row.mtimeMs, row.ctimeMs]
  }), identities)
}))
test('check-only refuses raw members without changing them', () => fixture(root => {
  assert.throws(() => prepareRuntime(root, { checkOnly: true }), /not prepared/); rawUnchanged(root)
}))
test('unknown original bytes are preserved and refused', () => fixture(root => {
  const name = [...originals.keys()][0]; fs.appendFileSync(path.join(root, name), '\nunknown\n')
  const before = fs.readFileSync(path.join(root, name))
  assert.throws(() => prepareRuntime(root), /Unknown or partially prepared/)
  assert.deepEqual(fs.readFileSync(path.join(root, name)), before)
}))
test('mixed original/effective state is preserved and refused', () => fixture(root => {
  const name = [...originals.keys()][0]
  fs.writeFileSync(path.join(root, name), fs.readFileSync(path.join(root, vendor, 'payload', name.slice(prefix.length))))
  assert.throws(() => prepareRuntime(root), /Mixed runtime state/)
  for (const [other, raw] of originals) if (other !== name) assert.deepEqual(fs.readFileSync(path.join(root, other)), raw)
}))
test('changed vendored payload is refused before target mutation', () => fixture(root => {
  const name = Object.keys(manifest.payloads)[0]
  fs.appendFileSync(path.join(root, vendor, 'payload', name), '\nunknown\n')
  assert.throws(() => prepareRuntime(root), /Reviewed payload changed/); rawUnchanged(root)
}))
test('an unreviewed lock is refused before target mutation', () => fixture(root => {
  fs.appendFileSync(path.join(root, 'package-lock.json'), '\n')
  assert.throws(() => prepareRuntime(root), /Unreviewed application lock/); rawUnchanged(root)
}))
test('a symbolic target is refused without following it', () => fixture(root => {
  const name = [...originals.keys()][0]; const file = path.join(root, name)
  fs.unlinkSync(file); fs.symlinkSync('unowned-target', file)
  assert.throws(() => prepareRuntime(root), /Linked runtime member/)
  assert.equal(fs.readlinkSync(file), 'unowned-target'); assert(!fs.existsSync(path.join(path.dirname(file), 'unowned-target')))
}))
test('manifest traversal cannot expand the fixed replacement scope', () => fixture(root => {
  const changed = structuredClone(manifest); changed.payloads['../outside'] = Object.values(changed.payloads)[0]
  fs.writeFileSync(path.join(root, vendor, 'manifest.json'), JSON.stringify(changed))
  assert.throws(() => prepareRuntime(root)); rawUnchanged(root)
}))
test('a replacement failure restores only the known changes of this invocation', () => fixture(root => {
  const originalRename = fs.renameSync; let attempts = 0; let caught
  fs.renameSync = (...args) => {
    if (++attempts === 7) throw new Error('Declared replacement failure')
    return originalRename(...args)
  }
  try { prepareRuntime(root) } catch (error) { caught = error } finally { fs.renameSync = originalRename }
  assert.match(caught.message, /Declared replacement failure/)
  assert.equal(caught.runtimeRollbackIncomplete, false); assert(!caught.runtimeCleanupIncomplete)
  rawUnchanged(root)
}))
