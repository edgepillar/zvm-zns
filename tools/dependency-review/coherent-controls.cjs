'use strict';

const assert = require('node:assert/strict');

// This function is used directly with native Node exports and serialized into
// Chrome with the map-bound full-bootstrap inspection copy. No large inputs.
function runControls(z) {
  const arrays = [];
  function run(name, make, input) {
    let refinements = 0; const element = z.string().refine(() => { refinements++; return true; });
    const result = make(element).safeParse(input); const issues = result.success ? [] : result.error.issues;
    arrays.push({name, success: result.success, elementRefinements: refinements,
      issueCodes: issues.map(row => row.code), issuePaths: issues.map(row => row.path),
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
  const parser = new z.BidiParser(); const geolocation = [];
  for (const [name, parameters] of [['null', null], ['scalar', 7],
    ['conflict', {coordinates: null, error: {type: 'positionUnavailable'}}]]) {
    let error; try { parser.parseSetGeolocationOverrideParams(parameters); } catch (caught) { error = caught; }
    if (!(error instanceof z.InvalidArgumentException) || error.error !== 'invalid argument') throw new Error('Direct geolocation error contract: ' + name);
    const envelope = error.toErrorResponse(7);
    if (envelope.type !== 'error' || envelope.id !== 7 || envelope.error !== 'invalid argument' || !envelope.message) throw new Error('Direct error envelope');
    geolocation.push({name, protocolError: error.error, errorEnvelopeVerified: true});
  }
  const valid = {coordinates: {latitude: 1, longitude: 2, accuracy: 1, altitude: null, altitudeAccuracy: null, heading: null, speed: null}};
  const before = JSON.stringify(valid); const output = parser.parseSetGeolocationOverrideParams(valid);
  if (JSON.stringify(valid) !== before || JSON.stringify(output) !== before) throw new Error('Direct valid geolocation output');
  geolocation.push({name: 'valid', inputUnchanged: true, output});
  return {arrays, geolocation, version: z.version};
}
function validateControls(result) {
  assert.deepEqual(result.version, {major: 4, minor: 6, patch: 7});
  assert.equal(result.arrays.length, 8); assert.equal(result.geolocation.length, 4);
  const expected = [[true, 2, [], [], 2], [false, 0, ['too_big'], [[]], null], [false, 0, ['too_big'], [[]], null],
    [false, 1, ['too_small'], [[]], null], [true, 3, [], [], 2], [false, 0, ['too_big'], [['items']], null],
    [false, 0, ['invalid_type'], [[]], null], [false, 0, ['too_big'], [[]], null]];
  result.arrays.forEach((row, i) => assert.deepEqual([row.success, row.elementRefinements, row.issueCodes, row.issuePaths, row.outputLength], expected[i]));
  assert.deepEqual(result.geolocation.map(row => row.name), ['null', 'scalar', 'conflict', 'valid']);
  return result;
}
async function nativeControls(guard) {
  const zod = await import(guard.resolve('zod'));
  const core = await import(guard.resolve('zod/v4/core'));
  const parser = await import(guard.resolve('chromium-bidi/out/Default/gen/src/bidiTab/BidiParser.js'));
  const errors = await import(guard.resolve('chromium-bidi/out/Default/gen/src/protocol/ErrorResponse.js'));
  const result = validateControls(runControls({...zod, version: core.version,
    BidiParser: parser.BidiParser, InvalidArgumentException: errors.InvalidArgumentException}));
  return {schema: 1, kind: 'ACTUAL_NATIVE_ESM_DERIVED_PARSER_AND_ROOT_VALIDATOR', cases: 12, maximumContainerLength: 3,
    result, importConditionsPreserved: true, modelOrVmModuleReplacementUsed: false, productionGate: 'NO_GO'};
}
module.exports = {runControls, validateControls, nativeControls};
