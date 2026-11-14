import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const defaultRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const vendor = 'vendor/chromium-bidi-157-reviewed'
const prefix = 'node_modules/chromium-bidi/'
const allowed = [
  'out/Default/gen/src/protocol-parser/protocol-parser.js',
  'out/Default/gen/src/protocol-parser/protocol-parser.js.map',
  'out/Default/gen/src/mapperTab.js', 'out/Default/gen/src/mapperTab.js.map',
  'out/Default/gen/src/mapper.js.LEGAL.txt', 'notices/chromium-bidi/LICENSE',
  'notices/zod/LICENSE', 'notices/mitt/LICENSE', 'notices/esbuild/LICENSE.md',
].sort()
const pin = raw => ({ bytes: raw.length, sha256: crypto.createHash('sha256').update(raw).digest('hex') })
const identity = st => [st.dev, st.ino, st.mode, st.nlink, st.size, st.mtimeMs, st.ctimeMs]
function exists(file) {
  try { fs.lstatSync(file); return true } catch (error) { if (error.code === 'ENOENT') return false; throw error }
}
function inside(root, relative) {
  assert(relative && !path.isAbsolute(relative) && !relative.includes('\\'))
  assert(relative.split('/').every(part => part && part !== '.' && part !== '..'))
  let cursor = root
  for (const part of relative.split('/')) {
    cursor = path.join(cursor, part)
    if (exists(cursor)) assert(!fs.lstatSync(cursor).isSymbolicLink(), 'Linked runtime member or ancestor')
  }
  return cursor
}
function read(root, relative, limit = 16 << 20) {
  const file = inside(root, relative); const before = fs.lstatSync(file)
  assert(before.isFile() && before.nlink === 1 && before.size <= limit, 'Runtime member type, link count or byte cap')
  const raw = fs.readFileSync(file)
  assert.equal(raw.length, before.size); assert.deepEqual(identity(fs.lstatSync(file)), identity(before))
  return { raw, file, identity: identity(before), mode: before.mode & 0o777 }
}
function matches(a, b) { return a.bytes === b.bytes && a.sha256 === b.sha256 }

// This first-party helper performs no network, compiler, package-manager or
// browser operation. All nine effective files are committed, bounded payloads.
export function prepareRuntime(root = defaultRoot, { checkOnly = false } = {}) {
  root = path.resolve(root); assert.equal(fs.realpathSync(root), root, 'Runtime root must be physical')
  assert.equal(typeof checkOnly, 'boolean')
  const manifestRow = read(root, vendor + '/manifest.json', 128 << 10)
  const manifest = JSON.parse(manifestRow.raw)
  assert.equal(manifest.schema, 1); assert.equal(manifest.kind, 'REVIEWED_LOCAL_DERIVATIVE_PAYLOAD_SET')
  assert.equal(manifest.publication.location, prefix.slice(0, -1))
  assert.equal(manifest.publication.selection.name, 'chromium-bidi')
  assert.equal(manifest.publication.selection.version, '157.0.8090-0')
  assert.equal(manifest.registryArtifactOrPublisherAuthenticationClaimed, false)
  assert.deepEqual(Object.keys(manifest.payloads).sort(), allowed)
  assert.deepEqual(Object.keys(manifest.effectiveMembers).sort(), allowed.map(name => prefix + name).sort())
  const lock = read(root, 'package-lock.json', 2 << 20)
  assert.equal(pin(lock.raw).sha256, manifest.baseLockSha256, 'Unreviewed application lock; review it before preparing runtime bytes')
  const locked = JSON.parse(lock.raw); const rootManifest = read(root, 'package.json', 1 << 20)
  const app = JSON.parse(rootManifest.raw)
  assert.equal(app.name, locked.packages[''].name); assert.equal(app.version, locked.packages[''].version)
  for (const scope of ['dependencies', 'devDependencies', 'optionalDependencies']) {
    assert.deepEqual(app[scope] ?? {}, locked.packages[''][scope] ?? {}, 'Application declarations differ from the reviewed lock')
  }
  const row = locked.packages[prefix.slice(0, -1)]
  for (const key of ['version', 'resolved', 'integrity']) assert.equal(row[key], manifest.publication.selection[key])
  const packageRow = read(root, prefix + 'package.json', 1 << 20)
  assert.deepEqual(pin(packageRow.raw), manifest.originalPackageManifest, 'Unreviewed installed package manifest')
  const packageJson = JSON.parse(packageRow.raw)
  assert.equal(packageJson.name, 'chromium-bidi'); assert.equal(packageJson.version, '157.0.8090-0')
  const inputs = []; let payloadBytes = 0; let rawCount = 0; let effectiveCount = 0
  for (const name of allowed) {
    const effective = manifest.effectiveMembers[prefix + name]
    assert.equal(effective.registryIntegrityCoversEffectiveBytes, false)
    assert.deepEqual(effective.effective, manifest.payloads[name])
    assert(['REVIEWED_LOCAL_DERIVATIVE', 'RETAINED_ORIGINAL_NOTICE'].includes(effective.kind))
    const payload = read(root, vendor + '/payload/' + name)
    assert.deepEqual(pin(payload.raw), effective.effective, 'Reviewed payload changed')
    payloadBytes += payload.raw.length; assert(payloadBytes <= 5 << 20)
    const target = inside(root, prefix + name)
    const before = exists(target) ? read(root, prefix + name) : null
    const actual = before ? pin(before.raw) : null
    if (actual && matches(actual, effective.effective)) effectiveCount++
    else {
      assert(effective.original ? actual && matches(actual, effective.original) : actual === null,
        'Unknown or partially prepared runtime bytes; preserve them and use a reviewed fresh install')
      rawCount++
    }
    inputs.push({ name, effective, payload, target, before })
  }
  assert(rawCount === 9 || effectiveCount === 9, 'Mixed runtime state; preparation refuses to adopt partial or unknown bytes')
  const result = { schema: 1, status: 'REVIEWED_RUNTIME_VERIFIED', package: 'chromium-bidi', version: '157.0.8090-0',
    effectiveMembers: 9, changedMembers: 0, payloadBytes, manifest: pin(manifestRow.raw),
    registryIntegrityCoversEffectiveBytes: false, networkCompilerPackageManagerOrBrowserExecuted: false }
  if (effectiveCount === 9) return result
  assert(!checkOnly, 'Reviewed runtime is not prepared; run npm run prepare:runtime')

  // Prepare every new file before the first replacement. Replacements are
  // individually atomic; this is not a power-loss-atomic nine-file transaction.
  const stageRoot = fs.mkdtempSync(inside(root, 'node_modules') + path.sep + '.zns-runtime-')
  const stageIdentity = identity(fs.lstatSync(stageRoot)); const staged = []; const replaced = []
  let primaryError
  try {
    for (const [i, item] of inputs.entries()) {
      const file = path.join(stageRoot, String(i)); const fd = fs.openSync(file, 'wx', item.before?.mode ?? 0o644)
      try { fs.writeFileSync(fd, item.payload.raw); fs.fchmodSync(fd, item.before?.mode ?? 0o644); fs.fsyncSync(fd) } finally { fs.closeSync(fd) }
      const info = fs.lstatSync(file)
      assert(info.isFile() && info.nlink === 1)
      staged.push({ file, identity: identity(info) })
    }
    assert.deepEqual(read(root, vendor + '/manifest.json', 128 << 10).raw, manifestRow.raw)
    assert.deepEqual(read(root, 'package-lock.json', 2 << 20).raw, lock.raw)
    assert.deepEqual(read(root, 'package.json', 1 << 20).raw, rootManifest.raw)
    assert.deepEqual(read(root, prefix + 'package.json', 1 << 20).raw, packageRow.raw)
    for (const item of inputs) {
      assert.deepEqual(read(root, vendor + '/payload/' + item.name).raw, item.payload.raw)
      if (item.before) assert.deepEqual(read(root, prefix + item.name).identity, item.before.identity)
      else assert(!exists(item.target), 'Runtime target appeared during preparation')
    }
    for (const [i, item] of inputs.entries()) {
      const parts = (prefix + item.name).split('/').slice(0, -1); let parent = root
      for (const part of parts) {
        parent = path.join(parent, part)
        if (!exists(parent)) fs.mkdirSync(parent, { mode: 0o755 })
        assert(fs.lstatSync(parent).isDirectory() && !fs.lstatSync(parent).isSymbolicLink())
      }
      if (item.before) assert.deepEqual(read(root, prefix + item.name).identity, item.before.identity)
      else assert(!exists(item.target))
      assert.deepEqual(identity(fs.lstatSync(staged[i].file)), staged[i].identity)
      fs.renameSync(staged[i].file, item.target)
      replaced.push({ item, identity: identity(fs.lstatSync(item.target)) })
    }
    for (const item of inputs) assert.deepEqual(pin(read(root, prefix + item.name).raw), item.effective.effective)
    assert.deepEqual(read(root, vendor + '/manifest.json', 128 << 10).raw, manifestRow.raw)
    assert.deepEqual(read(root, 'package-lock.json', 2 << 20).raw, lock.raw)
    assert.deepEqual(read(root, 'package.json', 1 << 20).raw, rootManifest.raw)
    assert.deepEqual(read(root, prefix + 'package.json', 1 << 20).raw, packageRow.raw)
    for (const item of inputs) assert.deepEqual(read(root, vendor + '/payload/' + item.name).raw, item.payload.raw)
    result.status = 'REVIEWED_RUNTIME_PREPARED'; result.changedMembers = 9
    return result
  } catch (error) {
    primaryError = error
    // Restore only known files this invocation replaced, and only while their
    // current identities and bytes still match this invocation's outputs.
    let rollbackIncomplete = false
    for (const { item, identity: expected } of replaced.reverse()) {
      try {
        const current = read(root, prefix + item.name)
        assert.deepEqual(current.identity, expected); assert.deepEqual(pin(current.raw), item.effective.effective)
        if (item.before) {
          const backup = path.join(stageRoot, 'restore-' + inputs.indexOf(item))
          fs.writeFileSync(backup, item.before.raw, { flag: 'wx', mode: item.before.mode })
          fs.chmodSync(backup, item.before.mode)
          const info = identity(fs.lstatSync(backup)); staged.push({ file: backup, identity: info })
          fs.renameSync(backup, item.target)
        } else fs.unlinkSync(item.target)
      } catch { rollbackIncomplete = true }
    }
    error.runtimeRollbackIncomplete = rollbackIncomplete
    throw error
  } finally {
    // Never recursively remove a directory or adopt an unexpected file.
    let cleanupIncomplete = false
    for (const item of staged) {
      if (!exists(item.file)) continue
      try {
        assert.deepEqual(identity(fs.lstatSync(item.file)), item.identity); fs.unlinkSync(item.file)
      } catch { cleanupIncomplete = true }
    }
    try {
      const current = fs.lstatSync(stageRoot)
      assert(current.isDirectory() && current.dev === stageIdentity[0] && current.ino === stageIdentity[1])
      fs.rmdirSync(stageRoot)
    } catch { cleanupIncomplete = true }
    if (cleanupIncomplete) {
      if (primaryError) primaryError.runtimeCleanupIncomplete = true
      else throw new Error('Prepared bytes retained, but owned staging cleanup is incomplete')
    }
  }
}

if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  try {
    assert(process.argv.length === 2 || (process.argv.length === 3 && process.argv[2] === '--check'))
    process.stdout.write(JSON.stringify(prepareRuntime(defaultRoot, { checkOnly: process.argv[2] === '--check' })) + '\n')
  } catch (error) {
    process.stderr.write(String(error.stack || error) + '\n')
    if (error.runtimeRollbackIncomplete !== undefined) process.stderr.write('runtimeRollbackIncomplete=' + error.runtimeRollbackIncomplete + '\n')
    if (error.runtimeCleanupIncomplete) process.stderr.write('runtimeCleanupIncomplete=true\n')
    process.exitCode = 1
  }
}
