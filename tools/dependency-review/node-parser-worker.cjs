'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {nameChecked, readArchive, readInstalled, sha} = require('./verified-package-sources.cjs');

const fixture = `(() => {
  const parser = globalThis.__parser;
  const InvalidArgument = globalThis.__invalidArgument;
  const z = globalThis.__zod;
  const rows = [];
  const inventory = [];
  for (const [namespace, value] of Object.entries(parser)) {
    if (!value || typeof value !== 'object') continue;
    for (const [name, fn] of Object.entries(value)) {
      if (typeof fn !== 'function') continue;
      const route = namespace + '.' + name;
      inventory.push(route);
      let error;
      try { fn(null); } catch (caught) { error = caught; }
      if (!(error instanceof InvalidArgument) || error.error !== 'invalid argument') throw new Error('Malformed route did not preserve protocol error: ' + route);
      const envelope = error.toErrorResponse(7);
      if (envelope.type !== 'error' || envelope.id !== 7 || envelope.error !== 'invalid argument' || !envelope.message) throw new Error('Malformed protocol error envelope');
      rows.push({route, control: 'null-parameters', success: false, protocolError: error.error, errorEnvelopeVerified: true});
    }
  }
  const samples = [
    ['Browser', 'parseCreateUserContextParameters', {}],
    ['Network', 'parseAddInterceptParameters', {phases: ['beforeRequestSent']}],
    ['Script', 'parseEvaluateParams', {expression: '1 + 1', target: {context: 'context-one'}, awaitPromise: false}],
    ['BrowsingContext', 'parseNavigateParams', {context: 'context-one', url: 'https://example.invalid/', wait: 'none'}],
    ['Session', 'parseSubscribeParams', {events: ['log.entryAdded']}],
    ['Emulation', 'parseSetLocaleOverrideParams', {locale: 'en-US'}],
    ['Input', 'parsePerformActionsParams', {context: 'context-one', actions: []}],
    ['Storage', 'parseGetCookiesParams', {}],
    ['Cdp', 'parseGetSessionRequest', {context: 'context-one'}],
    ['Permissions', 'parseSetPermissionsParams', {descriptor: {name: 'geolocation'}, state: 'granted', origin: 'https://example.invalid'}],
    ['Bluetooth', 'parseSimulateAdapterParams', {context: 'context-one', state: 'absent'}],
    ['DigitalCredentials', 'parseSetVirtualWalletBehaviorParams', {action: 'decline', context: 'context-one'}],
    ['WebModule', 'parseInstallParams', {extensionData: {type: 'path', path: '/controlled/example'}}],
  ];
  if (globalThis.__profile === 'candidate') samples.push(
    ['Emulation', 'parseSetMediaFeaturesOverrideParams', {features: null}],
    ['Emulation', 'parseSetTextLayoutModeOverrideParams', {textLayoutMode: null}],
    ['Emulation', 'parseSetViewportMetaOverrideParams', {viewportMeta: null}],
  );
  for (const [namespace, name, parameters] of samples) {
    const before = JSON.stringify(parameters);
    const output = parser[namespace][name](parameters);
    if (JSON.stringify(parameters) !== before) throw new Error('Parser mutated input parameters');
    const expected = JSON.parse(before);
    if (namespace === 'Script' && globalThis.__profile === 'candidate') expected.userActivation = false;
    if (JSON.stringify(output) !== JSON.stringify(expected)) throw new Error('Reviewed valid output differs: ' + namespace + '.' + name);
    rows.push({route: namespace + '.' + name, control: 'valid-parameters', success: true, inputUnchanged: true, output});
  }
  const schema = z.object({value: z.string()});
  const valid = parser.parseObject({value: 'ok', ignored: 1}, schema);
  if (JSON.stringify(valid) !== JSON.stringify({value: 'ok'})) throw new Error('Direct parser stripping differs');
  rows.push({route: 'parseObject', control: 'valid-direct-schema', success: true, output: valid});
  let error;
  try { parser.parseObject({value: 1}, schema); } catch (caught) { error = caught; }
  if (!(error instanceof InvalidArgument) || error.error !== 'invalid argument' || !error.message.includes('"value"')) throw new Error('Direct parser did not retain nested issue path');
  rows.push({route: 'parseObject', control: 'invalid-direct-schema', success: false, protocolError: error.error, nestedIssuePathRetained: true});
  return JSON.stringify({profile: globalThis.__profile, inventory: inventory.sort(), controls: rows,
    validNamespaceCases: samples.length, malformedNamespaceCases: inventory.length, directSchemaCases: 2});
})()`;

const calibration = `(() => {
  const parser = globalThis.__parser;
  const schema = globalThis.__zod.object({value: globalThis.__zod.string()});
  const output = parser.parseObject({value: 'ok'}, schema);
  if (JSON.stringify(output) !== JSON.stringify({value: 'ok'})) throw new Error('Legacy override positive calibration failed');
  let error;
  try { parser.parseObject({value: 1}, schema); } catch (caught) { error = caught; }
  if (!(error instanceof TypeError) || error instanceof globalThis.__invalidArgument) throw new Error('Legacy override error-shape incompatibility not observed');
  return JSON.stringify({controls: 2, validDirectParseSucceeded: true,
    invalidDirectParseRaisedTypeError: true, protocolInvalidArgumentPreserved: false,
    unsupportedOverrideAccepted: false});
})()`;

async function loadProfile(mapper, zod, mapperPlan, zodPlan, profile, entry) {
  const context = vm.createContext(Object.create(null), {codeGeneration: {strings: false, wasm: false}});
  const cache = new Map();
  function moduleFor(packageName, name) {
    nameChecked(name); assert(['mapper', 'zod'].includes(packageName));
    const key = packageName + '/' + name;
    if (cache.has(key)) return cache.get(key);
    const source = (packageName === 'mapper' ? mapper : zod).read(name);
    const module = new vm.SourceTextModule(source, {context, identifier: 'https://dependency.invalid/' + key});
    cache.set(key, module); return module;
  }
  const parser = moduleFor('mapper', entry);
  await parser.link((specifier, referencing) => {
    if (specifier === 'zod') return moduleFor('zod', 'index.js');
    assert(specifier.startsWith('./') || specifier.startsWith('../'), 'external source module import');
    const target = new URL(specifier, referencing.identifier);
    assert(target.origin === 'https://dependency.invalid');
    const [packageName, ...parts] = target.pathname.slice(1).split('/');
    const [parentPackage] = new URL(referencing.identifier).pathname.slice(1).split('/');
    assert.equal(packageName, parentPackage, 'relative import escaped package');
    return moduleFor(packageName, parts.join('/'));
  });
  await parser.evaluate({timeout: 1500});
  context.__parser = parser.namespace;
  context.__zod = cache.get('zod/index.js').namespace.z;
  context.__invalidArgument = cache.get('mapper/out/Default/gen/src/protocol/ErrorResponse.js').namespace.InvalidArgumentException;
  context.__profile = profile;
  const script = profile === 'unsupported-legacy-override' ? calibration : fixture;
  const result = JSON.parse(new vm.Script(script, {filename: 'bounded-node-parser-controls.js'}).runInContext(context, {timeout: 1500}));
  const loaded = [...cache.keys()].sort().map(key => {
    const at = key.indexOf('/'); const packageName = key.slice(0, at); const name = key.slice(at + 1);
    const selected = packageName === 'mapper' ? mapperPlan : zodPlan;
    return {package: packageName, name, bytes: selected.members[name].bytes, sha256: selected.members[name].sha256};
  });
  return {result, loaded};
}

async function main() {
  assert.equal(process.argv.length, 3);
  const raw = fs.readFileSync(process.argv[2]); assert(raw.length <= 2 * 1024 * 1024);
  const plan = JSON.parse(raw.toString('utf8')); assert.equal(plan.schema, 1);
  assert.equal(plan.baselineMapper.version, '17.0.2'); assert.equal(plan.baselineZod.version, '3.25.76');
  assert.equal(plan.mapper.version, '157.0.8090-0'); assert.equal(plan.fixed.version, '4.6.7');
  const baselineMapper = readInstalled(plan.baselineMapper); const baselineZod = readInstalled(plan.baselineZod);
  const mapper = readArchive(plan.mapper); const fixed = readArchive(plan.fixed);
  // Refusals use only reviewed ordinary files and metadata; no fixture files or links are created.
  assert.throws(() => baselineMapper.read('../package.json'));
  assert.throws(() => mapper.read('unreviewed-source-member.js'));
  const wrongInstalled = structuredClone(plan.baselineZod); wrongInstalled.members['package.json'].sha256 = '0'.repeat(64);
  assert.throws(() => readInstalled(wrongInstalled).read('package.json'));
  const wrongArchive = structuredClone(plan.fixed); wrongArchive.members['package.json'].sha256 = '0'.repeat(64);
  assert.throws(() => readArchive(wrongArchive).read('package.json'));
  const entry = 'out/Default/gen/src/protocol-parser/protocol-parser.js';
  const baseline = await loadProfile(baselineMapper, baselineZod, plan.baselineMapper, plan.baselineZod, 'baseline', entry);
  const candidate = await loadProfile(mapper, fixed, plan.mapper, plan.fixed, 'candidate', entry);
  const negative = await loadProfile(baselineMapper, fixed, plan.baselineMapper, plan.fixed, 'unsupported-legacy-override', entry);
  assert.equal(baseline.result.malformedNamespaceCases, 77); assert.equal(baseline.result.validNamespaceCases, 13);
  assert.equal(candidate.result.malformedNamespaceCases, 80); assert.equal(candidate.result.validNamespaceCases, 16);
  const totalCases = baseline.result.controls.length + candidate.result.controls.length + negative.result.controls;
  assert.equal(totalCases, 192);
  const added = candidate.result.inventory.filter(name => !baseline.result.inventory.includes(name));
  const removed = baseline.result.inventory.filter(name => !candidate.result.inventory.includes(name));
  assert.deepEqual(added, ['Emulation.parseSetMediaFeaturesOverrideParams', 'Emulation.parseSetTextLayoutModeOverrideParams', 'Emulation.parseSetViewportMetaOverrideParams']);
  assert.deepEqual(removed, []);
  process.stdout.write(JSON.stringify({schema: 1, status: 'BOUNDED_NODE_PARSER_API_CONTROLS_QUALIFIED_MIGRATION_REQUIRES_REVIEW',
    nodeVersion: process.version, nodePlatform: process.platform, nodeArchitecture: process.arch,
    baseline, candidate, unsupportedLegacyOverride: negative, totalCases, sourceGuardCases: 4,
    entry, fixtureSha256: sha(Buffer.from(fixture)), calibrationSha256: sha(Buffer.from(calibration)),
    addedNamespaceMethods: added, removedNamespaceMethods: removed,
    currentInstalledBaselineAndExactCandidateMemberSourcesUsed: true,
    packageCodeExecuted: true, candidateDependencyInstallationPerformed: false,
    mapperBootstrapOrBrowserOrProtocolCommandsExecuted: false, compiledSchemaJITQualified: false,
    vmContextsAreNotASecurityBoundary: true, stringAndWasmCodeGenerationDisabled: true,
    networkOrWalletOrLiveChainExecutionPerformed: false, proposalAdopted: false, productionGate: 'NO_GO'}) + '\n');
}

main().catch(error => { process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1; });
