'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
const sha = raw => crypto.createHash('sha256').update(raw).digest('hex');

function nameChecked(name) {
  assert(typeof name === 'string' && /^[A-Za-z0-9_./-]+$/.test(name));
  assert(!name.split('/').some(part => !part || part === '.' || part === '..'));
  return name;
}

function regularBytes(filename, expected, limit) {
  assert(path.isAbsolute(filename) && fs.realpathSync(filename) === filename);
  const before = fs.lstatSync(filename);
  assert(before.isFile() && before.nlink === 1 && before.size === expected.bytes && before.size <= limit);
  const fd = fs.openSync(filename, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
  let raw;
  try {
    const opened = fs.fstatSync(fd);
    assert(opened.dev === before.dev && opened.ino === before.ino && opened.size === before.size);
    raw = fs.readFileSync(fd);
    const after = fs.fstatSync(fd);
    assert(after.dev === before.dev && after.ino === before.ino && after.size === before.size && after.mtimeMs === before.mtimeMs);
  } finally { fs.closeSync(fd); }
  const final = fs.lstatSync(filename);
  assert(final.dev === before.dev && final.ino === before.ino && final.nlink === 1 && final.mtimeMs === before.mtimeMs);
  assert(raw.length === expected.bytes && sha(raw) === expected.sha256);
  return raw;
}

function readArchive(source) {
  const raw = regularBytes(source.path, source, 8 * 1024 * 1024);
  assert.equal('sha512-' + crypto.createHash('sha512').update(raw).digest('base64'), source.integrity);
  const expanded = zlib.gunzipSync(raw, {maxOutputLength: 64 * 1024 * 1024});
  assert(expanded.length === source.expandedBytes && sha(expanded) === source.expandedSha256);
  assert(Object.keys(source.members).length > 0 && Object.keys(source.members).length <= 8192);
  return {read(name) {
    nameChecked(name); assert(Object.hasOwn(source.members, name), 'source member not in reviewed inventory');
    const member = source.members[name];
    assert(Number.isSafeInteger(member.offset) && member.offset >= 0 && member.offset % 512 === 0);
    assert(Number.isSafeInteger(member.bytes) && member.bytes >= 0 && member.bytes <= 16 * 1024 * 1024);
    assert(member.offset + member.bytes <= expanded.length);
    const body = expanded.subarray(member.offset, member.offset + member.bytes);
    assert.equal(sha(body), member.sha256);
    return new TextDecoder('utf8', {fatal: true}).decode(body);
  }};
}

function readInstalled(source) {
  assert(source.kind === 'REVIEWED_INSTALLED_MEMBERS' && path.isAbsolute(source.root));
  assert(fs.realpathSync(source.root) === source.root && fs.lstatSync(source.root).isDirectory());
  assert(Object.keys(source.members).length > 0 && Object.keys(source.members).length <= 8192);
  return {read(name) {
    nameChecked(name); assert(Object.hasOwn(source.members, name), 'installed member not in reviewed inventory');
    const raw = regularBytes(path.join(source.root, name), source.members[name], 16 * 1024 * 1024);
    return new TextDecoder('utf8', {fatal: true}).decode(raw);
  }};
}

module.exports = {nameChecked, readArchive, readInstalled, sha};
