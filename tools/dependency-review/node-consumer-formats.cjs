'use strict';

const assert = require('node:assert/strict');

function describeLoad(file, context, result) {
  assert(Array.isArray(context.conditions) && context.conditions.length <= 64);
  assert(context.conditions.every(value => typeof value === 'string'));
  const nativeAutodetect = result.format === undefined && context.format === undefined &&
    file.endsWith('.js') && context.conditions.includes('require') && !context.conditions.includes('import');
  assert(['module', 'commonjs', 'json'].includes(result.format) || nativeAutodetect,
    'Unreviewed runtime module format: ' + String(result.format));
  // This is an evidence label. Return the original load result to Node unchanged.
  return {format: nativeAutodetect ? 'node-autodetect' : result.format,
    nativeLoadFormat: result.format === undefined ? null : result.format,
    nativeFormatHint: context.format === undefined ? null : context.format,
    loadConditions: [...context.conditions].sort()};
}

function controls() {
  let accepted = 0; let refused = 0;
  for (const format of ['module', 'commonjs', 'json']) {
    const result = {format};
    assert.equal(describeLoad('selected.js', {format, conditions: ['node', 'import']}, result).format, format);
    assert.deepEqual(result, {format}); accepted++;
  }
  const result = {format: undefined};
  const context = {format: undefined, conditions: ['node', 'require', 'module-sync']};
  assert.deepEqual(describeLoad('selected.js', context, result), {format: 'node-autodetect',
    nativeLoadFormat: null, nativeFormatHint: null, loadConditions: ['module-sync', 'node', 'require']});
  assert.equal(result.format, undefined); assert.equal(context.format, undefined); accepted++;
  for (const [file, hint, conditions, format] of [
    ['selected.node', undefined, ['require'], undefined],
    ['selected.js', 'commonjs', ['require'], undefined],
    ['selected.js', undefined, ['import'], undefined],
    ['selected.js', undefined, ['require', 'import'], undefined],
    ['selected.js', undefined, ['require'], null],
    ['selected.js', undefined, ['require'], 'addon'],
    ['selected.ts', undefined, ['require'], 'commonjs-typescript'],
    ['selected.wasm', undefined, ['require'], 'wasm'],
  ]) {
    assert.throws(() => describeLoad(file, {format: hint, conditions}, {format})); refused++;
  }
  return {acceptedCases: accepted, refusedCases: refused, nativeLoadResultsModified: false};
}

module.exports = {describeLoad, controls};
