import assert from 'node:assert/strict'
import {createServer} from 'node:http'
import {createRequire} from 'node:module'
import {once} from 'node:events'
import {existsSync, fstatSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync} from 'node:fs'
import {basename, join, relative} from 'node:path'
import {test} from 'node:test'
import {runInNewContext} from 'node:vm'

const application = process.env.ZNS_COMPILER_APPLICATION_ROOT
const temporary = process.env.ZNS_COMPILER_API_TMPDIR
assert.ok(application && temporary, 'a hosted application installation and owned fixture root are required')
assert.equal(process.env.TMPDIR, temporary)
const require = createRequire(join(application, 'package.json'))
const redirects = require('follow-redirects')
const tmp = require('tmp')
const versions = Object.fromEntries(['solc', 'follow-redirects', 'tmp'].map(name => [name, require(`${name}/package.json`).version]))
assert.deepEqual(versions, {solc: '0.8.26', 'follow-redirects': '1.16.3', tmp: '0.2.7'})
const result = {versions, redirectCases: 0, synchronousTempCases: 0, asynchronousTempCases: 0,
  rejectedOptionCases: 0, symlinkConfinementCases: 0, externalNetworkRequestsPerformed: false,
  remoteCompilerOrSMTSolverInvoked: false, hostedSymlinkFixture: true}

const contained = path => {
  const name = relative(temporary, path)
  assert.ok(name && !name.startsWith('..') && !name.startsWith('/'))
}
const clean = callback => new Promise((resolve, reject) => callback(error => error ? reject(error) : resolve()))

await test('redirects remove declared synthetic fields across representations and realms', async () => {
  const seen = new Map()
  const target = createServer((request, response) => {
    seen.set(request.url, request.headers)
    response.writeHead(200, {'content-type': 'text/plain'})
    response.end('ok')
  })
  target.listen(0, '127.0.0.1'); await once(target, 'listening')
  const destination = `http://127.0.0.1:${target.address().port}`
  const first = createServer((request, response) => {
    response.writeHead(302, {location: destination + request.url})
    response.end()
  })
  first.listen(0, '127.0.0.1'); await once(first, 'listening')
  try {
    for (const name of ['X-Review-Field', 'X-Review^Field', 'X-Review|Field']) {
      for (const arrayForm of [false, true]) {
        for (const crossRealm of [false, true]) {
          const route = `/case-${result.redirectCases}`
          const sensitiveHeaders = crossRealm ? runInNewContext(JSON.stringify([name]), Object.create(null), {timeout: 1000}) : [name]
          assert.equal(Array.isArray(sensitiveHeaders), true)
          assert.equal(sensitiveHeaders instanceof Array, !crossRealm)
          const headers = arrayForm ? [name, 'review-marker', 'X-Review-Public', 'kept'] : {[name]: 'review-marker', 'X-Review-Public': 'kept'}
          await new Promise((resolve, reject) => {
            const request = redirects.http.get(`http://127.0.0.1:${first.address().port}${route}`, {headers, sensitiveHeaders, maxRedirects: 1}, response => {
              if (response.statusCode !== 200) {
                response.resume(); reject(new Error('unexpected loopback status')); return
              }
              response.resume(); response.on('end', resolve); response.on('error', reject)
            })
            request.setTimeout(2000, () => request.destroy(new Error('loopback control timeout')))
            request.on('error', reject)
          })
          const received = seen.get(route)
          assert.ok(received)
          assert.equal(received[name.toLowerCase()], undefined)
          assert.equal(received['x-review-public'], 'kept')
          result.redirectCases++
        }
      }
    }
  } finally {
    await new Promise(resolve => first.close(resolve))
    await new Promise(resolve => target.close(resolve))
  }
})

await test('the compiler SMT tempfile option retains normal synchronous cleanup behavior', () => {
  const file = tmp.fileSync({postfix: '.smt2'})
  contained(file.name); assert.ok(basename(file.name).endsWith('.smt2'))
  writeFileSync(file.name, 'review-only\n')
  assert.equal(readFileSync(file.name, 'utf8'), 'review-only\n')
  assert.equal(fstatSync(file.fd).mode & 0o777, 0o600)
  file.removeCallback(); assert.equal(existsSync(file.name), false)
  assert.throws(() => fstatSync(file.fd), {code: 'EBADF'})
  result.synchronousTempCases++
  const directory = tmp.dirSync({tmpdir: temporary})
  contained(directory.name); directory.removeCallback(); assert.equal(existsSync(directory.name), false)
  result.synchronousTempCases++
})

await test('temporary file and directory callbacks keep their cleanup API', async () => {
  const file = await new Promise((resolve, reject) => tmp.file({tmpdir: temporary, postfix: '.smt2'},
    (error, name, fd, cleanup) => error ? reject(error) : resolve({name, fd, cleanup})))
  contained(file.name); writeFileSync(file.fd, 'review-only')
  await clean(file.cleanup); assert.equal(existsSync(file.name), false)
  assert.throws(() => fstatSync(file.fd), {code: 'EBADF'})
  result.asynchronousTempCases++
  const directory = await new Promise((resolve, reject) => tmp.dir({tmpdir: temporary},
    (error, name, cleanup) => error ? reject(error) : resolve({name, cleanup})))
  contained(directory.name); await clean(directory.cleanup); assert.equal(existsSync(directory.name), false)
  result.asynchronousTempCases++
})

await test('bounded invalid paths and option types are rejected before creation', () => {
  const root = mkdtempSync(join(temporary, 'options-'))
  try {
    for (const options of [{prefix: '../outside'}, {postfix: '../outside'}, {template: '../XXXXXX'},
      {name: '../outside'}, {dir: '..'}, {prefix: []}, {postfix: {}}, {prefix: 1}, {template: []}]) {
      assert.throws(() => tmp.fileSync({tmpdir: root, ...options}))
      assert.deepEqual(readdirSync(root), [])
      result.rejectedOptionCases++
    }
  } finally { rmSync(root, {recursive: true}) }
})

await test('hosted-only symlink fixtures cannot redirect creation outside the selected base', async () => {
  const root = mkdtempSync(join(temporary, 'confinement-'))
  const allowed = join(root, 'allowed'), other = join(root, 'other')
  mkdirSync(allowed); mkdirSync(other)
  symlinkSync(other, join(allowed, 'alias'), 'dir')
  try {
    for (const operation of [tmp.fileSync, tmp.dirSync]) {
      assert.throws(() => operation({tmpdir: allowed, dir: 'alias'}))
      assert.deepEqual(readdirSync(other), [])
      result.symlinkConfinementCases++
    }
    await assert.rejects(new Promise((resolve, reject) => tmp.file({tmpdir: allowed, dir: 'alias'},
      error => error ? reject(error) : resolve())))
    assert.deepEqual(readdirSync(other), [])
    assert.equal(lstatSync(join(allowed, 'alias')).isSymbolicLink(), true)
    result.symlinkConfinementCases++
  } finally { rmSync(root, {recursive: true}) }
})

assert.equal(result.redirectCases, 12)
assert.equal(result.synchronousTempCases, 2)
assert.equal(result.asynchronousTempCases, 2)
assert.equal(result.rejectedOptionCases, 9)
assert.equal(result.symlinkConfinementCases, 3)
console.log('ZNS_COMPILER_DEPENDENCY_RESULT ' + JSON.stringify(result))
