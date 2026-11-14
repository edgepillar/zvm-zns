'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');

const hash = raw => crypto.createHash('sha256').update(raw).digest('hex');
function read(file, limit) {
  const before = fs.lstatSync(file);
  assert(before.isFile() && !before.isSymbolicLink() && before.nlink === 1 && before.size <= limit);
  const raw = fs.readFileSync(file); const after = fs.lstatSync(file);
  for (const key of ['dev', 'ino', 'size', 'mtimeMs', 'ctimeMs']) assert.equal(after[key], before[key]);
  assert.equal(raw.length, before.size); return raw;
}

async function main() {
  assert.equal(process.argv.length, 3);
  const plan = JSON.parse(read(process.argv[2], 2 * 1024 * 1024));
  assert.equal(plan.schema, 1); assert(plan.integrities.length > 0 && plan.integrities.length <= 512);
  const requested = new Set(plan.integrities); assert.equal(requested.size, plan.integrities.length);
  for (const value of requested) assert(/^sha512-[A-Za-z0-9+/]{86}==$/.test(value));
  const npmRoot = fs.realpathSync(plan.npmRoot); const cache = fs.realpathSync(plan.cacheRoot);
  const npmRaw = read(path.join(npmRoot, 'package.json'), 65536); const npm = JSON.parse(npmRaw);
  assert.equal(npm.name, 'npm'); assert.equal(npm.version, plan.npmVersion);
  const selected = createRequire(path.join(npmRoot, 'package.json'));
  const entry = selected.resolve('cacache'); assert(entry.startsWith(npmRoot + path.sep));
  const entryRaw = read(entry, 1024 * 1024);
  const cacache = selected('cacache'); const index = {}; let entries = 0;
  for await (const row of cacache.ls.stream(cache)) {
    entries++; assert(entries <= 8192);
    if (!requested.has(row.integrity)) continue;
    const relative = path.relative(cache, row.path);
    assert(relative && !path.isAbsolute(relative) && !relative.split(path.sep).some(p => !p || p === '.' || p === '..'));
    assert(Number.isInteger(row.size) && row.size > 0 && row.size <= 32 * 1024 * 1024);
    const value = {cacheRelative: relative.split(path.sep).join('/'), bytes: row.size};
    if (index[row.integrity]) assert.deepEqual(index[row.integrity], value);
    else index[row.integrity] = value;
  }
  assert.equal(Object.keys(index).length, requested.size, 'Current-job cache is missing a selected publication; no fallback fetch is permitted');
  assert.deepEqual(read(entry, 1024 * 1024), entryRaw);
  process.stdout.write(JSON.stringify({schema: 1, npmVersion: npm.version, nodeVersion: process.version,
    toolPins: {'npm/package.json': {bytes: npmRaw.length, sha256: hash(npmRaw)},
      'npm/cacache-entry': {bytes: entryRaw.length, sha256: hash(entryRaw)}},
    API: 'npm-bundled cacache.ls.stream', entriesObserved: entries, index,
    cacheAPIIsNotIndependentNpmToolchainAuthentication: true, cacheVerifyCleanOrMutationRequested: false,
    historicalCacheFallbackOrAdditionalTransport: false}) + '\n');
}

main().catch(error => { process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1; });
