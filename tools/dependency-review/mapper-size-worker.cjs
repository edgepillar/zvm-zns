'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {readArchive, sha} = require('./verified-package-sources.cjs');

const fixture = `(() => {
  const z = globalThis.__dependencyProbe;
  const rows = [];
  function run(name, make, input) {
    let refinements = 0;
    const element = z.string().refine(() => { refinements++; return true; });
    const schema = make(element);
    const result = schema.safeParse(input);
    const issues = result.success ? [] : result.error.issues;
    rows.push({name, success: result.success, elementRefinements: refinements,
      issueCodes: issues.map(issue => issue.code), issuePaths: issues.map(issue => issue.path),
      outputLength: result.success && Array.isArray(result.data) ? result.data.length : null});
  }
  run('valid-max', el => z.array(el).max(2), ['a', 'b']);
  run('over-max', el => z.array(el).max(2), ['a', 'b', 'c']);
  run('over-exact-length', el => z.array(el).length(2), ['a', 'b', 'c']);
  run('below-min', el => z.array(el).min(2), ['a']);
  run('rewrite-before-max', el => z.array(el).overwrite(a => a.slice(0, 2)).max(2), ['a', 'b', 'c']);
  run('nested-over-max', el => z.object({items: z.array(el).max(1)}), {items: ['a', 'b']});
  run('wrong-container', el => z.array(el).max(2), 7);
  run('invalid-elements-over-max', el => z.array(el).max(2), [1, 2, 3]);
  return JSON.stringify(rows);
})()`;

function controls(context, role) {
  const rows = JSON.parse(new vm.Script(fixture, {filename: 'bounded-array-controls.js'}).runInContext(context, {timeout: 1500}));
  assert.equal(rows.length, 8);
  const indexed = Object.fromEntries(rows.map(row => [row.name, row]));
  assert.equal(indexed['valid-max'].success, true);
  assert.equal(indexed['valid-max'].elementRefinements, 2);
  assert.equal(indexed['valid-max'].outputLength, 2);
  for (const name of ['over-max', 'over-exact-length']) {
    assert.equal(indexed[name].success, false);
    assert.deepEqual(indexed[name].issueCodes, ['too_big']);
    assert.equal(indexed[name].elementRefinements, role === 'mapper' ? 3 : 0);
  }
  assert.equal(indexed['below-min'].success, false);
  assert.deepEqual(indexed['below-min'].issueCodes, ['too_small']);
  assert.equal(indexed['below-min'].elementRefinements, 1);
  assert.equal(indexed['rewrite-before-max'].success, true);
  assert.equal(indexed['rewrite-before-max'].elementRefinements, 3);
  assert.equal(indexed['rewrite-before-max'].outputLength, 2);
  assert.equal(indexed['nested-over-max'].success, false);
  assert.deepEqual(indexed['nested-over-max'].issueCodes, ['too_big']);
  assert.deepEqual(indexed['nested-over-max'].issuePaths, [['items']]);
  assert.equal(indexed['nested-over-max'].elementRefinements, role === 'mapper' ? 2 : 0);
  assert.equal(indexed['wrong-container'].success, false);
  assert.deepEqual(indexed['wrong-container'].issueCodes, ['invalid_type']);
  assert.equal(indexed['wrong-container'].elementRefinements, 0);
  assert.equal(indexed['invalid-elements-over-max'].success, false);
  assert.deepEqual(indexed['invalid-elements-over-max'].issueCodes,
    role === 'mapper' ? ['invalid_type', 'invalid_type', 'invalid_type', 'too_big'] : ['too_big']);
  return rows;
}

async function main() {
  assert.equal(process.argv.length, 3);
  const planRaw = fs.readFileSync(process.argv[2]); assert(planRaw.length <= 2 * 1024 * 1024);
  const plan = JSON.parse(planRaw.toString('utf8')); assert.equal(plan.schema, 1);
  const mapperArchive = readArchive(plan.mapper);
  const original = mapperArchive.read('out/Default/gen/src/mapperTab.js');
  const marker = '\n    generatePage();\n    const mapperTabToServerTransport';
  const at = original.indexOf(marker);
  assert(at > 0 && original.indexOf(marker, at + 1) === -1, 'mapper bootstrap boundary differs');
  assert(original.startsWith('(function () {\n') && original.endsWith('})();\n//# sourceMappingURL=mapperTab.js.map\n'));
  const capture = '\n    globalThis.__dependencyProbe = Object.freeze({array, string, object, version});\n})();\n';
  const instrumented = original.slice(0, at) + capture;
  const mapperContext = vm.createContext(Object.create(null), {codeGeneration: {strings: false, wasm: false}});
  new vm.Script(instrumented, {filename: 'mapper-declarations-only.js'}).runInContext(mapperContext, {timeout: 1500});
  assert.equal(JSON.stringify(mapperContext.__dependencyProbe.version), JSON.stringify({major: 4, minor: 6, patch: 5}));
  const mapperRows = controls(mapperContext, 'mapper');

  const fixedArchive = readArchive(plan.fixed);
  const fixedContext = vm.createContext(Object.create(null), {codeGeneration: {strings: false, wasm: false}});
  const cache = new Map();
  function moduleFor(name) {
    assert(typeof name === 'string' && /^[A-Za-z0-9_./-]+$/.test(name) && !name.split('/').some(part => !part || part === '.' || part === '..'));
    if (cache.has(name)) return cache.get(name);
    const module = new vm.SourceTextModule(fixedArchive.read(name), {context: fixedContext, identifier: 'https://dependency.invalid/zod/' + name});
    cache.set(name, module); return module;
  }
  const entry = moduleFor('index.js');
  await entry.link((specifier, referencing) => {
    assert(specifier.startsWith('./') || specifier.startsWith('../'), 'external source module import');
    const target = new URL(specifier, referencing.identifier);
    assert(target.origin === 'https://dependency.invalid' && target.pathname.startsWith('/zod/'));
    return moduleFor(target.pathname.slice('/zod/'.length));
  });
  await entry.evaluate({timeout: 1500});
  fixedContext.__dependencyProbe = entry.namespace.default;
  const fixedRows = controls(fixedContext, 'fixed');
  const loadedMembers = [...cache.keys()].sort().map(name => ({name, ...plan.fixed.members[name]}));
  process.stdout.write(JSON.stringify({schema: 1, status: 'BOUNDED_ARRAY_ORDERING_DIFFERENCE_REPRODUCED_NO_MIGRATION_ACCEPTANCE',
    nodeVersion: process.version, nodePlatform: process.platform, nodeArchitecture: process.arch,
    profiles: {mapper: {versionObject: '4.6.5', controls: mapperRows}, fixed: {selectedVersion: '4.6.7', controls: fixedRows}},
    fixedLoadedMembers: loadedMembers, originalMapperSha256: sha(Buffer.from(original)),
    instrumentedMapperSha256: sha(Buffer.from(instrumented)), captureSourceSha256: sha(Buffer.from(capture)),
    fixtureSha256: sha(Buffer.from(fixture)), totalCases: 16, maximumContainerLength: 3,
    mapperBootstrapRemoved: true, mapperBrowserOrCDPBootstrapExecuted: false,
    generatedDeclarationsAndSelectedZodCodeExecuted: true, filesystemArchiveExtractions: 0,
    vmContextsAreNotASecurityBoundary: true, stringAndWasmCodeGenerationDisabled: true,
    browserRuntimeReachabilityOrExploitabilityEstablished: false, compiledSchemaJITQualified: false,
    proposalAdopted: false, productionGate: 'NO_GO'}) + '\n');
}

main().catch(error => { process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1; });
