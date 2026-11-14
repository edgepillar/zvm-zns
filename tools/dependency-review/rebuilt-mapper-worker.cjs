'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {sha} = require('./verified-package-sources.cjs');

const fixture = `(() => {
  const z = globalThis.__rebuiltProbe;
  const arrays = [];
  function run(name, make, input) {
    let refinements = 0;
    const element = z.string().refine(() => { refinements++; return true; });
    const result = make(element).safeParse(input);
    const issues = result.success ? [] : result.error.issues;
    arrays.push({name, success: result.success, elementRefinements: refinements,
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
  const parser = new z.BidiParser();
  const geolocation = [];
  for (const [name, parameters] of [['null', null], ['scalar', 7],
    ['conflict', {coordinates: null, error: {type: 'positionUnavailable'}}]]) {
    let error;
    try { parser.parseSetGeolocationOverrideParams(parameters); } catch (caught) { error = caught; }
    if (!(error instanceof z.InvalidArgumentException) || error.error !== 'invalid argument') throw new Error('Rebuilt geolocation protocol error differs: ' + name);
    const envelope = error.toErrorResponse(7);
    if (envelope.type !== 'error' || envelope.id !== 7 || envelope.error !== 'invalid argument' || !envelope.message) throw new Error('Rebuilt error envelope differs');
    geolocation.push({name, protocolError: error.error, errorEnvelopeVerified: true});
  }
  const valid = {coordinates: {latitude: 1, longitude: 2, accuracy: 1,
    altitude: null, altitudeAccuracy: null, heading: null, speed: null}};
  const before = JSON.stringify(valid);
  const output = parser.parseSetGeolocationOverrideParams(valid);
  if (JSON.stringify(valid) !== before || JSON.stringify(output) !== before) throw new Error('Rebuilt valid geolocation changed');
  geolocation.push({name: 'valid', inputUnchanged: true, output});
  return JSON.stringify({arrays, geolocation, version: z.version});
})()`;

function main() {
  assert.equal(process.argv.length, 3);
  const input = fs.readFileSync(process.argv[2]); assert(input.length <= 16384);
  const plan = JSON.parse(input); assert.equal(plan.schema, 1);
  const info = fs.lstatSync(plan.path); assert(info.isFile() && !info.isSymbolicLink() && info.nlink === 1);
  assert(info.size > 0 && info.size <= 4 * 1024 * 1024);
  const raw = fs.readFileSync(plan.path);
  assert.deepEqual({bytes: raw.length, sha256: sha(raw)}, plan.pin);
  const context = vm.createContext(Object.create(null), {codeGeneration: {strings: false, wasm: false}});
  const source = raw.toString('utf8');
  assert.deepEqual(Buffer.from(source, 'utf8'), raw, 'Declarations must be valid UTF-8');
  new vm.Script(source, {filename: 'rebuilt-mapper-declarations.js'}).runInContext(context, {timeout: 2000});
  const result = JSON.parse(new vm.Script(fixture, {filename: 'rebuilt-mapper-controls.js'}).runInContext(context, {timeout: 2000}));
  assert.deepEqual(result.version, {major: 4, minor: 6, patch: 7});
  assert.equal(result.arrays.length, 8); assert.equal(result.geolocation.length, 4);
  const expected = [
    [true, 2, [], [], 2], [false, 0, ['too_big'], [[]], null],
    [false, 0, ['too_big'], [[]], null], [false, 1, ['too_small'], [[]], null],
    [true, 3, [], [], 2], [false, 0, ['too_big'], [['items']], null],
    [false, 0, ['invalid_type'], [[]], null], [false, 0, ['too_big'], [[]], null],
  ];
  result.arrays.forEach((row, i) => assert.deepEqual(
    [row.success, row.elementRefinements, row.issueCodes, row.issuePaths, row.outputLength], expected[i]));
  assert.deepEqual(result.geolocation.map(row => row.name), ['null', 'scalar', 'conflict', 'valid']);
  assert.deepEqual(fs.readFileSync(plan.path), raw);
  process.stdout.write(JSON.stringify({schema: 1, status: 'REBUILT_DECLARATIONS_QUALIFIED_BROWSER_AND_ADOPTION_NOT_ACCEPTED',
    nodeVersion: process.version, nodePlatform: process.platform, nodeArchitecture: process.arch,
    instrumentedDeclarations: plan.pin, fixtureSha256: sha(Buffer.from(fixture)),
    versionObject: result.version, arrayControls: result.arrays, geolocationControls: result.geolocation,
    totalCases: 12, maximumContainerLength: 3, generatedPackageDeclarationsExecuted: true,
    browserOrCDPBootstrapExecuted: false, stringAndWasmCodeGenerationDisabled: true,
    vmContextsAreNotASecurityBoundary: true, compiledSchemaJITQualified: false,
    fullApplicationOrBrowserCompatibilityQualified: false, proposalAdopted: false, productionGate: 'NO_GO'}) + '\n');
}

try { main(); } catch (error) { process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1; }
