'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const {fileURLToPath} = require('node:url');
const {setSourceMapsSupport, getSourceMapsSupport, findSourceMap, SourceMap} = require('node:module');
const {read, pin} = require('./browser-source-guard.cjs');

function validateSupport(value) {
  assert(value && typeof value === 'object');
  assert.deepEqual(Object.keys(value).sort(), ['enabled', 'generatedCode', 'nodeModules']);
  assert.equal(value.enabled, true); assert.equal(value.nodeModules, true); assert.equal(value.generatedCode, false);
}

function enableRuntimeMaps() {
  setSourceMapsSupport(true, {nodeModules: true, generatedCode: false});
  validateSupport(getSourceMapsSupport());
}

async function nativeMapControls(input, guard) {
  const prefix = 'node_modules/chromium-bidi/out/Default/gen/src/';
  const parserMember = prefix + 'protocol-parser/protocol-parser.js';
  // The parser is already imported through the native source guard. Keep the
  // loaded-source and explicit-asset inventories separate.
  const parserRaw = read(path.join(input.root, parserMember)); const parserMapRaw = guard.asset(parserMember + '.map');
  const data = JSON.parse(parserMapRaw); const manifest = JSON.parse(read(input.derivation, 1 << 20));
  assert(manifest.changeNotices && manifest.debuggerSamples.length === 7);
  assert.deepEqual(pin(parserRaw), manifest.effectiveMembers[parserMember].effective);
  const parserURL = guard.resolve('chromium-bidi/out/Default/gen/src/protocol-parser/protocol-parser.js');
  const parser = await import(parserURL); const zod = await import(guard.resolve('zod'));
  let error;
  try { parser.parseObject(null, zod.object({value: zod.string()})); } catch (caught) { error = caught; }
  assert(error && error.error === 'invalid argument');
  const stack = String(error.stack); assert(stack.length <= 65536);
  const cached = findSourceMap(fileURLToPath(parserURL)); assert(cached instanceof SourceMap);
  assert.deepEqual(cached.payload.sourcesContent, data.sourcesContent);
  const lines = data.sourcesContent[0].split(/\r\n|[\r\n\u2028\u2029]/); if (lines.at(-1) === '') lines.pop();
  for (let line = 0; line < lines.length; line++) {
    const entry = cached.findEntry(line, 0);
    assert.equal(entry.generatedLine, line); assert.equal(entry.generatedColumn, 0);
    assert.equal(entry.originalLine, line); assert.equal(entry.originalColumn, 0);
    assert(entry.originalSource.endsWith('/derived-compiled-js/protocol-parser.js'));
    const origin = cached.findOrigin(line + 1, 1);
    assert.equal(origin.lineNumber, line + 1); assert.equal(origin.columnNumber, 1);
  }
  const throwLine = lines.findIndex(line => line.includes('throw new InvalidArgumentException(errorMessage);'));
  assert(throwLine >= 0 && stack.includes('/derived-compiled-js/protocol-parser.js:' + (throwLine + 1) + ':'));
  const mapperRaw = guard.asset(prefix + 'mapperTab.js.map'); const mapper = JSON.parse(mapperRaw);
  const consumer = new SourceMap(mapper); const samples = [];
  for (const row of manifest.debuggerSamples) {
    const entry = consumer.findEntry(row.generatedLine, row.generatedColumn);
    assert.deepEqual([entry.generatedLine, entry.generatedColumn, entry.originalSource, entry.originalLine, entry.originalColumn],
      [row.generatedLine, row.generatedColumn, row.source, row.originalLine, row.originalColumn]);
    const origin = consumer.findOrigin(row.generatedLine + 1, row.generatedColumn + 1);
    assert.equal(origin.fileName, row.source); assert.equal(origin.lineNumber, row.originalLine + 1);
    assert.equal(origin.columnNumber, row.originalColumn + 1); samples.push(row);
  }
  return {schema: 1, kind: 'ACTUAL_NODE_SOURCE_MAP_CACHE_STACK_AND_NATIVE_CONSUMER',
    parserSource: pin(parserRaw), parserMap: pin(parserMapRaw), mapperMap: pin(mapperRaw),
    automaticallyLoadedParserMap: true, parserMappedLines: lines.length, mappedErrorStackVerified: true,
    mappedErrorLine: throwLine + 1, mapperSamples: samples, mapSources: mapper.sources.length,
    nodeModulesSourceMapSupportExplicitlyEnabledBeforeImports: true, originalTypeScriptMappingClaimed: false,
    privateStackOrPathsPublished: false, productionGate: 'NO_GO'};
}
module.exports = {enableRuntimeMaps, nativeMapControls, validateSupport};
