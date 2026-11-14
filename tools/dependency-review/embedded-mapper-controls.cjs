'use strict';

const assert = require('node:assert/strict');
const {read, pin} = require('./browser-source-guard.cjs');
const {runControls, validateControls} = require('./coherent-controls.cjs');
const {openMapperRoute, inspectMapperMap} = require('./devtools-source-map-controls.cjs');
const {bounded} = require('./runtime-stage.cjs');

async function embeddedMapperControls(browser, input, guard, progress = {}, checkpoint = () => {}) {
  const member = 'node_modules/chromium-bidi/out/Default/gen/src/mapperTab.js';
  const source = guard.asset(member); const map = guard.asset(member + '.map');
  guard.asset('node_modules/chromium-bidi/out/Default/gen/src/protocol-parser/protocol-parser.js.map');
  guard.asset('node_modules/chromium-bidi/out/Default/gen/src/mapper.js.LEGAL.txt');
  const manifest = JSON.parse(read(input.derivation, 1 << 20));
  for (const [name, row] of Object.entries(manifest.effectiveMembers)) if (row.kind === 'RETAINED_ORIGINAL_NOTICE') guard.asset(name);
  const probe = read(input.mapperProbe, 4 << 20); assert.deepEqual(pin(probe), manifest.probe.derived);
  const rows = []; progress.status = 'EMBEDDED_MAPPER_INCOMPLETE'; progress.rows = rows;
  for (const instrumented of [false, true]) {
    const page = await browser.newPage(); const session = await page.createCDPSession();
    const root = await browser.target().createCDPSession(); const pending = new Map(); const wire = []; let sequence = 0; let events = 0;
    const row = {kind: instrumented ? 'FULL_BOOTSTRAP_INSPECTION_COPY' : 'INSTALLED_MAPPER_PAYLOAD',
      baseSource: pin(source), sourceMap: pin(map), instrumented, generatedSourceMapAttached: !instrumented,
      codePin: pin(instrumented ? probe : source), protocolCommands: wire}; rows.push(row);
    const binding = event => {
      if (event.name !== 'sendBidiResponse') return;
      assert(typeof event.payload === 'string' && event.payload.length <= 65536);
      const message = JSON.parse(event.payload);
      if (message.id === undefined) { assert(++events <= 1024); return; }
      const item = pending.get(message.id); assert(item, 'Unexpected embedded mapper response ID');
      pending.delete(message.id); clearTimeout(item.timer); item.resolve(message);
    };
    session.on('Runtime.bindingCalled', binding);
    function evaluatedOK(value, stage) {
      row.lastStage = stage;
      if (value.exceptionDetails) {
        const detail = value.exceptionDetails;
        row.runtimeException = {text: String(detail.text).slice(0, 256),
          description: String(detail.exception?.description ?? '').slice(0, 2048),
          lineNumber: detail.lineNumber, columnNumber: detail.columnNumber};
        throw new Error(stage);
      }
    }
    async function send(method, params, expectedError = null) {
      assert(sequence < 32); const id = ++sequence;
      const message = {id, method, params};
      const resultPromise = new Promise((resolve, reject) => {
        const timer = setTimeout(() => { pending.delete(id); reject(new Error('Embedded mapper command timeout: ' + method)); }, 15000);
        pending.set(id, {resolve, reject, timer});
      });
      resultPromise.catch(() => {}); // A CDP failure is retained separately; avoid an orphan rejection during cleanup.
      const evaluated = await session.send('Runtime.evaluate', {
        expression: 'window.onBidiMessage(' + JSON.stringify(JSON.stringify(message)) + ')', awaitPromise: true, returnByValue: true});
      evaluatedOK(evaluated, 'Embedded mapper transport evaluation');
      const response = await resultPromise;
      if (expectedError) assert.equal(response.error, expectedError);
      else assert.equal(response.type, 'success', response.message);
      wire.push({method, paramsKind: params === null ? 'null' : typeof params,
        responseType: response.type, protocolError: response.error ?? null});
      return response.result;
    }
    let context; let route;
    try {
      checkpoint(instrumented ? 'BEGIN_INSPECTION_MAPPER' : 'BEGIN_INSTALLED_MAPPER');
      if (!instrumented && manifest.debuggerSamples) {
        route = await openMapperRoute(source, map, row);
        await page.goto(route.origin + '/mapper.html', {waitUntil: 'load'});
      }
      await session.send('Runtime.enable');
      const info = await session.send('Target.getTargetInfo'); const targetId = info.targetInfo.targetId; assert(targetId);
      await root.send('Target.exposeDevToolsProtocol', {targetId, bindingName: 'cdp'});
      await session.send('Runtime.addBinding', {name: 'sendBidiResponse'});
      if (route) {
        row.executionSource = pin(source); row.sourceMapAttachment = 'AUTOMATIC_RELATIVE_FILE_ROUTE';
        await inspectMapperMap(browser, page, session, targetId, route, source, map, manifest, row, checkpoint);
      } else {
        let expression = (instrumented ? probe : source).toString('utf8');
        if (!instrumented) expression += '\n//# sourceMappingURL=data:application/json;base64,' + map.toString('base64') + '\n';
        expression += '//# sourceURL=coherent-bidi://mapperTab.js\n';
        assert(Buffer.byteLength(expression) <= 8 << 20); row.executionSource = pin(Buffer.from(expression));
        const loaded = await session.send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
        evaluatedOK(loaded, 'Embedded mapper full payload evaluation');
        row.sourceMapAttachment = instrumented ? 'NONE_INSPECTION_COPY' : 'INLINE_DATA';
      }
      const started = await session.send('Runtime.evaluate', {
        expression: 'window.runMapperInstance(' + JSON.stringify(targetId) + ')', awaitPromise: true, returnByValue: true});
      evaluatedOK(started, 'Embedded mapper bootstrap evaluation'); row.fullBrowserBootstrapExecuted = true;
      checkpoint(instrumented ? 'INSPECTION_BOOTSTRAP_COMPLETED' : 'INSTALLED_BOOTSTRAP_COMPLETED');
      if (instrumented) {
        const result = await session.send('Runtime.evaluate', {expression: '(' + runControls.toString() + ')(globalThis.__rebuiltProbe)',
          awaitPromise: true, returnByValue: true});
        evaluatedOK(result, 'Embedded mapper direct generated controls'); row.directGeneratedControls = validateControls(result.result.value);
        row.directGeneratedCases = 12; row.maximumContainerLength = 3;
      }
      await send('session.new', {capabilities: {}});
      const created = await send('browsingContext.create', {type: 'tab'}); context = created.context; assert(typeof context === 'string');
      await send('browsingContext.navigate', {context, url: 'about:blank', wait: 'complete'});
      const evaluated = await send('script.evaluate', {expression: "document.body.textContent='embedded-mapper-fixture'; 'embedded-mapper-fixture'",
        target: {context}, awaitPromise: true});
      assert.equal(evaluated.type, 'success'); assert.deepEqual(evaluated.result, {type: 'string', value: 'embedded-mapper-fixture'});
      await send('browsingContext.setViewport', {context, viewport: {width: 320, height: 240}, devicePixelRatio: 1});
      await send('emulation.setGeolocationOverride', {contexts: [context], coordinates: {latitude: 1, longitude: 2, accuracy: 1,
        altitude: null, altitudeAccuracy: null, heading: null, speed: null}});
      await send('emulation.setGeolocationOverride', 7, 'invalid argument');
      await send('emulation.setGeolocationOverride', {coordinates: null, error: {type: 'positionUnavailable'}, contexts: [context]}, 'invalid argument');
      await send('browsingContext.close', {context}); context = null;
      row.scalarWireRefusalOccursAtObjectOnlyWindowTransport = true;
      row.scalarWireResultIsNotEvidenceThatParserTypeGuardWasReached = true;
      row.applicationWalletOrLiveChainExecuted = false;
    } finally {
      if (context) {
        try { await send('browsingContext.close', {context}); context = null; } catch { row.contextCleanupNotEstablished = true; }
      }
      for (const item of pending.values()) { clearTimeout(item.timer); item.reject(new Error('Embedded mapper closed')); }
      pending.clear(); session.off('Runtime.bindingCalled', binding);
      checkpoint('BEGIN_MAPPER_CLEANUP');
      const cleanup = async (label, operation) => {
        try { await bounded(operation, label, 5000); }
        catch (error) { (row.cleanupFailures ??= []).push(label + ': ' + error.name); }
      };
      await cleanup('Root session detach', () => root.detach());
      await cleanup('Mapper session detach', () => session.detach());
      await cleanup('Mapper page close', () => page.close()); row.mapperPageClosed = page.isClosed();
      if (route) { await cleanup('Mapper route close', async () => { await route.close(); row.mapperRouteClosed = true; }); }
      checkpoint('MAPPER_CLEANUP_OBSERVED');
    }
    assert(row.mapperPageClosed && !row.contextCleanupNotEstablished && !row.cleanupFailures?.length);
  }
  progress.status = 'INSTALLED_AND_INSPECTED_FULL_BROWSER_MAPPER_BOOTSTRAPS_PASSED';
  return {schema: 1, status: progress.status, bootstraps: 2,
    nativeChromeProcessReused: true, additionalChromeParentInstances: 0, additionalChromeDownloads: 0, generatedBrowserDirectCases: 12,
    rows, originalPublishedMapperAndMapsPreservedInRawProfile: true, productionGate: 'NO_GO'};
}
module.exports = {embeddedMapperControls};
