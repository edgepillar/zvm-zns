// Small source-map compatibility and input-validation controls.
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {readFileSync} from 'node:fs'
import path from 'node:path'
import test from 'node:test'

const root = process.env.ZNS_SOURCE_MAP_ROOT
assert.ok(root && path.isAbsolute(root))
const require = createRequire(path.join(root, 'package.json'))
const version = JSON.parse(readFileSync(path.join(root, 'package.json'), 'utf8')).version
assert.equal(version, process.env.ZNS_SOURCE_MAP_VERSION)
assert.ok(['1.2.1', '1.2.2'].includes(version))
const {SourceMapConsumer, SourceMapGenerator, SourceNode} = require('./source-map.js')
const leaf = () => ({version: 3, sources: ['fixture.js'], sourcesContent: ['var x;\n'], names: [], mappings: 'AAAA'})
const indexed = (line = 0, column = 0, map = leaf()) => ({version: 3, sections: [{offset: {line, column}, map}]})

test('flat maps retain small line gaps, original positions and generated text', () => {
  const generator = new SourceMapGenerator({file: 'output.js'})
  for (const line of [9, 1, 5, 2]) generator.addMapping({generated: {line, column: 0}, original: {line, column: 0}, source: 'fixture.js'})
  const text = Array.from({length: 9}, (_, i) => `line${i + 1};\n`).join('')
  generator.setSourceContent('fixture.js', text)
  const consumer = new SourceMapConsumer(generator.toJSON())
  for (const line of [1, 2, 5, 9]) assert.equal(consumer.originalPositionFor({line, column: 0}).line, line)
  assert.equal(SourceNode.fromStringWithSourceMap(text, consumer).toString(), text)
})

test('small indexed maps preserve text when mappings extend past its end', () => {
  const text = 'var x;\n'
  for (const line of [0, 2, 8, 16]) {
    const consumer = new SourceMapConsumer(indexed(line))
    assert.equal(SourceNode.fromStringWithSourceMap(text, consumer).toString(), text)
  }
})

test('malformed offsets are checked at construction without generating mappings', () => {
  const invalid = [-1, 0.5, NaN, Infinity, -Infinity, '1', null, undefined, {}, Number.MAX_SAFE_INTEGER + 1]
  let accepted = 0, rejected = 0
  for (const value of invalid) for (const field of ['line', 'column']) {
    const map = indexed(); map.sections[0].offset[field] = value
    // This only constructs one tiny section. No mapping iteration, source-node
    // conversion or serialization is performed with these malformed offsets.
    try { new SourceMapConsumer(map); accepted++ } catch { rejected++ }
  }
  assert.equal(accepted + rejected, 20)
  if (version === '1.2.2') assert.equal(accepted, 0)
  else assert.ok(accepted > 0)
  console.log('ZNS_SOURCE_MAP_OFFSETS ' + JSON.stringify({version, cases: 20, accepted, rejected, malformedMappingIterationPerformed: false}))
})

test('four nested sections need one deepest source read after the patch', () => {
  let map = leaf()
  for (let i = 0; i < 4; i++) map = indexed(1, 0, map)
  const consumer = new SourceMapConsumer(map)
  let inner = consumer
  for (let i = 0; i < 4; i++) inner = inner._sections[0].consumer
  const sources = inner.sources
  let reads = 0
  Object.defineProperty(inner, 'sources', {get() { reads++; return sources }})
  assert.deepEqual(consumer.sources, ['fixture.js'])
  assert.equal(reads, version === '1.2.2' ? 1 : 81)
  console.log('ZNS_SOURCE_MAP_NESTING ' + JSON.stringify({version, depth: 4, deepestSourceReads: reads}))
})
