'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

function progressWriter(output, partial) {
  let sequence = 0;
  return stage => {
    assert(/^[A-Z0-9_]{1,96}$/.test(stage) && ++sequence <= 256);
    const raw = JSON.stringify({schema: 1, kind: 'DIAGNOSTIC_SNAPSHOT_NOT_QUALIFICATION', sequence,
      lastObservedStage: stage, partial, productionGate: 'NO_GO'}) + '\n';
    assert(Buffer.byteLength(raw) <= 256 << 10);
    fs.writeFileSync(path.join(output, 'browser-progress.json'), raw, {mode: 0o600});
  };
}

async function bounded(operation, label, timeout = 10000) {
  let timer;
  try {
    return await Promise.race([Promise.resolve().then(operation), new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('Owned runtime stage deadline: ' + label)), timeout);
    })]);
  } finally { clearTimeout(timer); }
}
module.exports = {progressWriter, bounded};
