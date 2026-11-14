'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {isBuiltin, registerHooks, syncBuiltinESMExports} = require('node:module');
const {fileURLToPath, pathToFileURL} = require('node:url');
const {describeLoad, controls: formatControls} = require('./node-consumer-formats.cjs');

const hash = raw => crypto.createHash('sha256').update(raw).digest('hex');
const pin = raw => ({bytes: raw.length, sha256: hash(raw)});
function read(file, limit) {
  const before = fs.lstatSync(file);
  assert(before.isFile() && !before.isSymbolicLink() && before.nlink === 1 && before.size <= limit);
  const raw = fs.readFileSync(file); const after = fs.lstatSync(file);
  for (const key of ['dev', 'ino', 'size', 'mtimeMs', 'ctimeMs']) assert.equal(after[key], before[key]);
  assert.equal(raw.length, before.size); return raw;
}
const json = (file, limit) => JSON.parse(read(file, limit));

async function main() {
  assert.equal(process.argv.length, 3);
  const input = json(process.argv[2], 65536);
  assert.equal(input.schema, 1); assert(['baseline', 'candidate'].includes(input.profile));
  assert.equal(process.platform, 'linux'); assert.equal(process.arch, 'x64');
  const glibc = process.report.getReport().header.glibcVersionRuntime;
  assert(typeof glibc === 'string' && glibc);
  assert(process.permission, 'Read-only filesystem and child-process permission profile is required');
  assert.equal(process.permission.has('fs.write', input.root), false);
  assert.equal(process.permission.has('child'), false); assert.equal(process.permission.has('worker'), false);
  const root = fs.realpathSync(input.root); assert.equal(root, input.root);
  assert(process.execArgv.includes('--experimental-import-meta-resolve'));
  const {resolveProfile} = await import(pathToFileURL(input.resolver).href);
  const anchor = pathToFileURL(path.join(root, 'package.json')).href;
  const inventory = json(input.inventory, 16 * 1024 * 1024);
  const changed = json(input.changedSources, 2 * 1024 * 1024);
  const planRaw = read(input.plan, 65536); const plan = JSON.parse(planRaw);
  const loaderFormatControls = formatControls();
  const lockRaw = read(path.join(root, 'package-lock.json'), 2 * 1024 * 1024); const lock = JSON.parse(lockRaw);
  assert.equal(hash(lockRaw), plan.profiles[input.profile].lockSha256);
  assert.equal(inventory.lockSha256, plan.profiles.candidate.lockSha256);
  const sources = {};
  for (const [integrity, value] of Object.entries(inventory.sources)) sources[integrity] = value;
  for (const [integrity, value] of Object.entries(changed.publications)) {
    if (sources[integrity]) assert.deepEqual(sources[integrity].filePins, value.filePins);
    else sources[integrity] = value;
  }
  const locations = Object.keys(lock.packages).filter(Boolean).sort((a, b) => b.length - a.length);
  const loaded = new Map(); const builtins = new Set(); const missing = new Map();
  let violations = 0; let loaderSourceMatches = 0; let requestedIO = 0;
  function member(file, table = sources) {
    assert(file.startsWith(root + path.sep));
    const relative = path.relative(root, file).split(path.sep).join('/');
    assert(relative && !relative.split('/').some(part => !part || part === '.' || part === '..'));
    const location = locations.find(value => relative.startsWith(value + '/')); assert(location);
    const selected = lock.packages[location]; assert(selected.integrity && !selected.inBundle && !selected.link);
    const publication = table[selected.integrity]; assert(publication, 'Runtime source publication is not bound');
    const name = relative.slice(location.length + 1); const expected = publication.filePins[name];
    assert(expected, 'Runtime source member is not bound');
    return {relative, location, member: name, integrity: selected.integrity, expected, publication};
  }
  function verified(file) {
    const value = member(file); let cursor = root;
    for (const part of value.relative.split('/')) { cursor = path.join(cursor, part); assert(!fs.lstatSync(cursor).isSymbolicLink()); }
    const manifestPath = path.join(root, value.location, 'package.json');
    assert.deepEqual(pin(read(manifestPath, 2 * 1024 * 1024)), value.publication.filePins['package.json']);
    const raw = read(file, 16 * 1024 * 1024); assert.deepEqual(pin(raw), value.expected);
    return {value, raw};
  }
  // Source-only refusal controls run before any selected package is imported.
  let refusals = 0;
  const pptrLocation = 'node_modules/puppeteer-core';
  const pptr = sources[lock.packages[pptrLocation].integrity]; assert(pptr);
  const known = Object.keys(pptr.filePins).find(name => name.endsWith('.js')); assert(known);
  for (const action of [
    () => member(path.join(root, '..', 'outside.js')),
    () => member(path.join(root, pptrLocation, 'unrecorded-source.js')),
    () => member(path.join(root, pptrLocation, known), {}),
    () => assert.deepEqual(pin(read(path.join(root, pptrLocation, known), 16 * 1024 * 1024)), {bytes: 0, sha256: '0'.repeat(64)}),
  ]) { assert.throws(action); refusals++; }
  // These guards record unexpected use of common network entry points. They are
  // observation controls, not a network sandbox or a browser security claim.
  const refuseIO = () => { requestedIO++; throw new Error('Network or process operation is outside the Node import/default-argument scope'); };
  for (const [moduleName, methods] of [
    ['node:http', ['request', 'get']], ['node:https', ['request', 'get']],
    ['node:net', ['connect', 'createConnection', 'createServer']], ['node:tls', ['connect', 'createServer']],
    ['node:dns', ['lookup', 'resolve', 'resolve4', 'resolve6']],
    ['node:child_process', ['spawn', 'spawnSync', 'exec', 'execSync', 'execFile', 'execFileSync', 'fork']],
  ]) { const module = require(moduleName); for (const name of methods) module[name] = refuseIO; }
  globalThis.fetch = refuseIO; syncBuiltinESMExports();
  const hook = registerHooks({
    resolve(specifier, context, nextResolve) {
      let result;
      try { result = nextResolve(specifier, context); }
      catch (error) {
        if (error.code === 'MODULE_NOT_FOUND' || error.code === 'ERR_MODULE_NOT_FOUND') {
          assert(missing.size < 1024 && String(specifier).length <= 2048);
          const request = path.isAbsolute(specifier) ? '<absolute request omitted>' : String(specifier);
          missing.set(request, error.code);
        }
        throw error;
      }
      if (isBuiltin(result.url)) { builtins.add(result.url); return result; }
      try { assert(result.url.startsWith('file:')); member(fileURLToPath(result.url)); }
      catch (error) { violations++; throw error; }
      return result;
    },
    load(url, context, nextLoad) {
      if (isBuiltin(url)) return nextLoad(url, context);
      try {
        const file = fileURLToPath(url); const {value, raw} = verified(file);
        const result = nextLoad(url, context);
        const formatEvidence = describeLoad(file, context, result);
        assert(result.source !== null && result.source !== undefined, 'Synchronous loader did not expose source bytes');
        const actual = typeof result.source === 'string' ? Buffer.from(result.source) : Buffer.from(result.source);
        assert.deepEqual(actual, raw); loaderSourceMatches++;
        loaded.set(value.relative, {location: value.location, member: value.member, integrity: value.integrity,
          ...value.expected, ...formatEvidence});
        return result;
      } catch (error) { violations++; throw error; }
    },
  });
  const entry = resolveProfile('puppeteer-core', anchor); const module = await import(entry);
  const puppeteer = module.default; assert(puppeteer);
  const methods = ['launch', 'connect', 'defaultArgs', 'executablePath'];
  for (const name of methods) assert.equal(typeof puppeteer[name], 'function');
  const adapter = await import(resolveProfile('puppeteer-core/internal/bidi/BidiOverCdp.js', anchor));
  assert.equal(typeof adapter.connectBidiOverCdp, 'function');
  const bidi = await import(resolveProfile('chromium-bidi', anchor));
  assert.equal(typeof bidi.BidiMapper.BidiServer.createAndStart, 'function');
  const options = [];
  for (const caller of plan.callers) {
    const raw = read(path.join(input.repo, caller.path), 64 * 1024); assert.deepEqual(pin(raw), caller.sourcePin);
    const source = raw.toString('utf8');
    const matches = [...source.matchAll(/^const browser = await puppeteer\.launch\((\{[^\r\n]*\})\)\s*$/gm)];
    assert.equal(matches.length, 1); assert.equal(hash(Buffer.from(matches[0][1])), caller.expressionSha256);
    const expression = matches[0][1]; assert(expression.length <= 2048);
    const context = vm.createContext({chrome: '/qualified/browser-not-launched', chromePath: '/qualified/browser-not-launched'},
      {codeGeneration: {strings: false, wasm: false}});
    const inputOptions = new vm.Script('(' + expression + ')', {filename: 'tracked-launch-options.js'}).runInContext(context, {timeout: 100});
    assert.deepEqual(Object.keys(inputOptions).sort(), caller.expectedKeys);
    const before = JSON.stringify(inputOptions);
    const argv = await puppeteer.defaultArgs(inputOptions);
    assert.equal(JSON.stringify(inputOptions), before); assert(Array.isArray(argv) && argv.length <= 256 && argv.every(value => typeof value === 'string' && value.length <= 4096));
    assert(argv.includes('--headless=new'));
    for (const value of caller.requiredCallerFlags) assert(argv.includes(value));
    assert.equal(inputOptions.headless, 'new'); assert.equal(inputOptions.executablePath, '/qualified/browser-not-launched');
    if (caller.protocolTimeout !== null) assert.equal(inputOptions.protocolTimeout, caller.protocolTimeout);
    options.push({path: caller.path, options: JSON.parse(before), argv, inputUnchanged: true,
      actualPuppeteerDefaultArgsExecuted: true, publicDefaultArgsResultAwaited: true, browserLaunchExecuted: false});
  }
  assert.equal(options.length, 2); assert.equal(violations, 0); assert.equal(requestedIO, 0);
  assert(loaded.size > 0 && loaderSourceMatches >= loaded.size);
  for (const [name, row] of loaded) assert.deepEqual(pin(read(path.join(root, name), 16 * 1024 * 1024)), {bytes: row.bytes, sha256: row.sha256});
  hook.deregister();
  const packageRaw = read(path.join(root, pptrLocation, 'package.json'), 65536); const manifest = JSON.parse(packageRaw);
  assert.equal(manifest.version, plan.profiles[input.profile].puppeteer);
  process.stdout.write(JSON.stringify({schema: 1, status: 'ACTUAL_NODE_ENTRIES_AND_TRACKED_CALLER_DEFAULT_ARGS_QUALIFIED_BROWSER_NOT_RUN',
    profile: input.profile, nodeVersion: process.version, nodePlatform: process.platform, nodeArchitecture: process.arch,
    libc: 'glibc', puppeteerVersion: manifest.version, planPin: pin(planRaw),
    sourceGuardRefusals: refusals, packageAPIObservations: 3, trackedCallerOptionCases: 2,
    loaderFormatControls,
    observedPublicMethods: methods, options, loadedMembers: [...loaded.values()], builtinModules: [...builtins].sort(),
    missingModuleResolutions: [...missing].map(([request, code]) => ({request, code})),
    exactLoaderSourceComparisons: loaderSourceMatches, sourceGuardViolations: violations, requestedNetworkOrProcessOperations: requestedIO,
    actualInstalledPackageCodeExecuted: true, actualNodeResolutionPreserved: true,
    moduleResolution: 'NATIVE_ESM_IMPORT_CONDITIONS_WITH_RECORDED_PARENT_URL',
    originalEmbeddedMapperMemberLoaded: [...loaded.values()].some(row => row.location.endsWith('/chromium-bidi') && row.member.endsWith('/mapperTab.js')),
    nodeValidatorEntryLoaded: [...loaded.values()].some(row => row.location.endsWith('/chromium-bidi') && row.member.endsWith('/protocol-parser.js')),
    rootZodMemberLoaded: [...loaded.values()].some(row => row.location === 'node_modules/zod'),
    baselineOrRawCandidateSourcesModified: false, browserOrCDPOrProtocolHandlersOrApplicationScriptsExecuted: false,
    fundedVerificationOrWalletSigningOrLiveChainExecuted: false, processAndFilesystemWritePermissionGranted: false,
    instrumentationIsNotUninstrumentedOrBrowserCompatibility: true, proposalAdopted: false, productionGate: 'NO_GO'}) + '\n');
}

main().catch(error => { process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1; });
