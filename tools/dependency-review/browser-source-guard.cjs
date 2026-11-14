'use strict';

// Return the native resolver/loader results unchanged while checking raw source
// pins. The hosted browser worker deliberately permits its own process/profile
// writes; this source observer is not an operating-system sandbox.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {isBuiltin, registerHooks} = require('node:module');
const {fileURLToPath, pathToFileURL} = require('node:url');
const {describeLoad, controls} = require('./node-consumer-formats.cjs');
const hash = raw => crypto.createHash('sha256').update(raw).digest('hex');
const pin = raw => ({bytes: raw.length, sha256: hash(raw)});
function read(file, limit = 16 << 20) {
  const a = fs.lstatSync(file);
  assert(a.isFile() && a.nlink === 1 && a.size <= limit);
  const raw = fs.readFileSync(file); const b = fs.lstatSync(file);
  for (const key of ['dev', 'ino', 'mode', 'nlink', 'size', 'mtimeMs', 'ctimeMs']) assert.equal(a[key], b[key]);
  assert.equal(raw.length, a.size); return raw;
}
async function sourceGuard(input) {
  assert(process.execArgv.includes('--experimental-import-meta-resolve'));
  const {resolveProfile} = await import(pathToFileURL(input.resolver).href);
  const root = fs.realpathSync(input.root); assert.equal(root, input.root);
  const lock = JSON.parse(read(path.join(root, 'package-lock.json'), 2 << 20));
  const plan = JSON.parse(read(input.plan, 65536));
  assert.equal(hash(read(path.join(root, 'package-lock.json'), 2 << 20)), plan.profiles[input.profile].lockSha256);
  const inventory = JSON.parse(read(input.inventory));
  assert.equal(inventory.lockSha256, plan.profiles.candidate.lockSha256);
  const changed = JSON.parse(read(input.changedSources, 2 << 20));
  const sources = {...inventory.sources};
  for (const [key, value] of Object.entries(changed.publications)) {
    if (sources[key]) assert.deepEqual(sources[key].filePins, value.filePins);
    sources[key] = value;
  }
  const locations = Object.keys(lock.packages).filter(Boolean).sort((a, b) => b.length - a.length);
  const loaded = new Map(); let comparisons = 0; let violations = 0;
  function member(file) {
    assert(file.startsWith(root + path.sep));
    const relative = path.relative(root, file).split(path.sep).join('/');
    assert(relative && !relative.split('/').some(p => !p || p === '.' || p === '..'));
    const location = locations.find(p => relative.startsWith(p + '/')); assert(location);
    const selected = lock.packages[location]; assert(selected.integrity && !selected.link && !selected.inBundle);
    const publication = sources[selected.integrity]; assert(publication, 'Unbound browser worker publication');
    const name = relative.slice(location.length + 1); const expected = publication.filePins[name];
    assert(expected, 'Unbound browser worker member');
    return {relative, location, member: name, integrity: selected.integrity, expected, publication};
  }
  function verified(file) {
    const row = member(file); let cursor = root;
    for (const part of row.relative.split('/')) { cursor = path.join(cursor, part); assert(!fs.lstatSync(cursor).isSymbolicLink()); }
    assert.deepEqual(pin(read(path.join(root, row.location, 'package.json'), 2 << 20)), row.publication.filePins['package.json']);
    const raw = read(file); assert.deepEqual(pin(raw), row.expected); return {row, raw};
  }
  const formatControls = controls();
  const hook = registerHooks({
    resolve(specifier, context, next) {
      const result = next(specifier, context);
      if (!isBuiltin(result.url)) {
        try { assert(result.url.startsWith('file:')); member(fileURLToPath(result.url)); }
        catch (error) { violations++; throw error; }
      }
      return result;
    },
    load(url, context, next) {
      if (isBuiltin(url)) return next(url, context);
      try {
        const file = fileURLToPath(url); const {row, raw} = verified(file);
        const result = next(url, context); const format = describeLoad(file, context, result);
        assert(result.source !== null && result.source !== undefined);
        assert.deepEqual(Buffer.from(result.source), raw); comparisons++;
        assert(loaded.size < 4096 || loaded.has(row.relative), 'Loaded browser source member budget');
        loaded.set(row.relative, {location: row.location, member: row.member, integrity: row.integrity, ...row.expected, ...format});
        return result;
      } catch (error) { violations++; throw error; }
    },
  });
  return {
    resolve: name => resolveProfile(name, pathToFileURL(path.join(root, 'package.json')).href),
    finish() {
      for (const [name, row] of loaded) assert.deepEqual(pin(read(path.join(root, name))), {bytes: row.bytes, sha256: row.sha256});
      assert.equal(violations, 0); assert(comparisons >= loaded.size && loaded.size > 0); hook.deregister();
      return {loadedMembers: [...loaded.values()], exactLoaderSourceComparisons: comparisons,
        sourceGuardViolations: violations, loaderFormatControls: formatControls,
        nativeResolutionAndUnmodifiedLoadResultsPreserved: true, sourcePinsRecheckedAfterBrowserClosure: true};
    },
  };
}
module.exports = {sourceGuard, read, pin};
