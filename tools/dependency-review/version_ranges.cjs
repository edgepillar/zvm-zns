'use strict';

// Evaluate bounded data with an explicitly selected policy and reviewed SemVer.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const policies = {
  dependency: { includePrerelease: false, loose: false },
  engine: { includePrerelease: true, loose: false },
  advisory: { includePrerelease: true, loose: true },
};
const pin = raw => ({ bytes: raw.length, sha256: crypto.createHash('sha256').update(raw).digest('hex') });

function evaluate(cases, semver) {
  assert(Array.isArray(cases) && cases.length <= 16384);
  const seen = new Set();
  return cases.map(item => {
    assert(typeof item.key === 'string' && item.key.length > 0 && item.key.length <= 512 && !seen.has(item.key));
    seen.add(item.key);
    assert(Object.hasOwn(policies, item.mode), 'unreviewed range policy');
    assert(typeof item.version === 'string' && item.version.length > 0 && item.version.length <= 256);
    assert(typeof item.range === 'string' && item.range.length > 0 && item.range.length <= 4096);
    const options = policies[item.mode];
    const version = semver.valid(item.version, options);
    const range = semver.validRange(item.range, options);
    const result = { key: item.key, mode: item.mode, version: item.version, range: item.range, options,
      normalizedVersion: version, normalizedRange: range,
      status: version && range ? 'RANGE_EVALUATED' : 'UNKNOWN_INVALID_VERSION_OR_RANGE',
      matches: version && range ? semver.satisfies(version, range, options) : null };
    if (Object.hasOwn(item, 'expected')) assert.equal(result.matches, item.expected, 'range control failed');
    return result;
  });
}

function main() {
  assert.equal(process.argv.length, 4, 'requires a reviewed SemVer root and bounded JSON input');
  const root = fs.realpathSync(process.argv[2]);
  const raw = fs.readFileSync(process.argv[3]);
  assert(raw.length <= 4 * 1024 * 1024);
  const plan = JSON.parse(raw.toString('utf8'));
  const expected = plan.semverSourcePins;
  assert(expected && typeof expected === 'object' && !Array.isArray(expected));
  assert(Object.keys(expected).length > 0 && Object.keys(expected).length <= 128);
  function verify() {
    for (const [name, value] of Object.entries(expected)) {
      assert(/^[A-Za-z0-9_./-]+$/.test(name) && !name.split('/').some(part => !part || part === '.' || part === '..'));
      const file = path.join(root, name);
      assert.equal(fs.realpathSync(file), file, 'linked scanner source');
      const stat = fs.lstatSync(file);
      assert(stat.isFile() && stat.size <= 512 * 1024);
      assert.deepEqual(pin(fs.readFileSync(file)), value, 'scanner source pin differs');
    }
  }
  verify();
  assert(Object.hasOwn(expected, 'package.json') && Object.hasOwn(expected, 'LICENSE'));
  const info = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
  assert.equal(info.name, 'semver');
  assert.equal(info.version, plan.semverVersion);
  assert.equal(Object.keys(info.dependencies || {}).length, 0);
  const semver = require(root);
  const results = evaluate(plan.cases, semver);
  const sourcePins = {};
  for (const name of Object.keys(require.cache).sort()) {
    if (name === __filename) continue;
    const resolved = fs.realpathSync(name);
    assert(resolved.startsWith(root + path.sep), 'external scanner module');
    const relative = path.relative(root, resolved).split(path.sep).join('/');
    assert(Object.hasOwn(expected, relative), 'scanner module has no reviewed source pin');
    sourcePins[relative] = pin(fs.readFileSync(resolved));
    assert.deepEqual(sourcePins[relative], expected[relative]);
  }
  verify();
  process.stdout.write(JSON.stringify({ schema: 1, nodeVersion: process.version,
    nodePlatform: process.platform, nodeArchitecture: process.arch, semverVersion: info.version,
    policies, sourcePins, results, sourcePinsVerifiedBeforeAndAfter: true,
    applicationCodeExecuted: false, dependencyLifecycleScriptsExecuted: false,
    metavulnerabilityRemediationOrRuntimeReachabilityEstablished: false }) + '\n');
}

module.exports = { evaluate };
if (require.main === module) main();
