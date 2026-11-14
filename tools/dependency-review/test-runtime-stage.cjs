'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const {bounded} = require('./runtime-stage.cjs');

test('preserve a completed owned operation result', async () => {
  const result = {complete: true}; assert.equal(await bounded(() => result, 'completed', 50), result);
});
test('preserve the original operation failure', async () => {
  const failure = new Error('Declared fixture failure');
  await assert.rejects(bounded(() => { throw failure; }, 'failed', 50), error => error === failure);
});
test('report a pending operation deadline without claiming completion', async () => {
  await assert.rejects(bounded(() => new Promise(() => {}), 'pending fixture', 5),
    {message: 'Owned runtime stage deadline: pending fixture'});
});
