'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const {validateSupport, enableRuntimeMaps} = require('./runtime-source-map-controls.cjs');

test('accept documented source-map support values', () => {
  validateSupport({enabled: true, generatedCode: false, nodeModules: true});
});
test('accept the native null-prototype result with identical values', () => {
  validateSupport(Object.assign(Object.create(null), {enabled: true, generatedCode: false, nodeModules: true}));
});
test('refuse missing or additional support fields', () => {
  assert.throws(() => validateSupport({enabled: true, nodeModules: true}));
  assert.throws(() => validateSupport({enabled: true, nodeModules: true, generatedCode: false, other: true}));
});
test('refuse altered support values', () => {
  for (const key of ['enabled', 'nodeModules', 'generatedCode']) {
    const value = {enabled: true, nodeModules: true, generatedCode: false}; value[key] = !value[key];
    assert.throws(() => validateSupport(value));
  }
});
test('enable the actual hosted Node support before dependency installation', {skip: process.env.GITHUB_ACTIONS !== 'true'}, () => {
  assert.equal(process.platform, 'linux'); assert.equal(process.arch, 'x64'); enableRuntimeMaps();
});
