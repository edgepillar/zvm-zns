// A Node string-code-generation restriction is not a browser CSP qualification.
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {readFileSync} from 'node:fs'
import path from 'node:path'
import test from 'node:test'

const root = process.env.ZNS_SOURCE_MAP_ROOT
assert.ok(root && path.isAbsolute(root))
assert.ok(process.execArgv.includes('--disallow-code-generation-from-strings'))
const require = createRequire(path.join(root, 'package.json'))
const version = JSON.parse(readFileSync(path.join(root, 'package.json'), 'utf8')).version
assert.equal(version, process.env.ZNS_SOURCE_MAP_VERSION)
assert.ok(['1.2.1', '1.2.2'].includes(version))
const {SourceMapConsumer, SourceMapGenerator} = require('./source-map.js')

test('small sorting controls observe the selected runtime restriction', () => {
  function sort() {
    const generator = new SourceMapGenerator({file: 'output.js'})
    for (const line of [3, 1, 2]) generator.addMapping({generated: {line, column: 0}, original: {line, column: 0}, source: 'fixture.js'})
    const consumer = new SourceMapConsumer(generator.toJSON())
    const lines = []; consumer.eachMapping((row) => lines.push(row.generatedLine))
    assert.deepEqual(lines, [1, 2, 3])
  }
  if (version === '1.2.1') assert.throws(sort, (error) => error.name === 'EvalError')
  else assert.doesNotThrow(sort)
  console.log('ZNS_SOURCE_MAP_CODEGEN ' + JSON.stringify({version, stringCodeGenerationDisabled: true,
    expectedLegacyRejectionObserved: version === '1.2.1', patchedSortingPassed: version === '1.2.2', browserCSPQualified: false}))
})
