'use strict';

// Exercise the browser's bundled DevTools frontend and automatic relative-map
// fetch, rather than substituting a model or manually attaching a parsed map.
const assert = require('node:assert/strict');
const http = require('node:http');
const {pin} = require('./browser-source-guard.cjs');
const {bounded} = require('./runtime-stage.cjs');

async function waitInFrontend(frontend, scriptURL = null) {
  // Query the browser-created frontend's initialized SDK with an explicit
  // finite readiness budget. Importing the SDK does not itself bootstrap UI.
  return await bounded(() => frontend.evaluate(async scriptURL => {
    const SDK = await import('./core/sdk/sdk.js'); const deadline = performance.now() + 15000;
    do {
      const models = SDK.TargetManager.TargetManager.instance().models(SDK.DebuggerModel.DebuggerModel);
      if (scriptURL ? models.some(model => model.scriptsForSourceURL(scriptURL).length > 0) : models.length > 0) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    } while (performance.now() < deadline);
    throw new Error(scriptURL ? 'Main-world DevTools mapper script absent' : 'Main-world DevTools debugger model absent');
  }, scriptURL), 'Main-world DevTools readiness', 18000);
}

async function openMapperRoute(source, map, row) {
  const files = new Map([
    ['/mapper.html', {type: 'text/html', raw: Buffer.from('<!doctype html><meta charset="utf-8"><title>Mapper map fixture</title>')}],
    ['/mapperTab.js', {type: 'text/javascript', raw: source}],
    ['/mapperTab.js.map', {type: 'application/json', raw: map}],
  ]);
  const requests = []; row.routeRequests = requests;
  const server = http.createServer((request, response) => {
    assert(requests.length < 128); const file = files.get(request.url);
    requests.push({path: request.url, method: request.method, status: file ? 200 : 404, ...(file ? {pin: pin(file.raw)} : {})});
    response.writeHead(file ? 200 : 404, {'Content-Type': file?.type ?? 'text/plain', 'Cache-Control': 'no-store'});
    response.end(file?.raw ?? 'Not found');
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  return {origin: 'http://127.0.0.1:' + server.address().port,
    close: () => new Promise((resolve, reject) => {
      server.close(error => error ? reject(error) : resolve()); server.closeAllConnections();
    })};
}

async function inspectMapperMap(browser, root, page, targetId, route, source, map, manifest, row, checkpoint = () => {}) {
  checkpoint('BEGIN_NATIVE_DEVTOOLS_OPEN');
  const opened = await root.send('Target.openDevTools', {targetId, panelId: 'sources'});
  assert(typeof opened.targetId === 'string' && opened.targetId !== targetId);
  const frontendTarget = await browser.waitForTarget(async target => {
    if (!target.url().startsWith('devtools://devtools/')) return false;
    const inspector = await target.createCDPSession();
    try { return (await inspector.send('Target.getTargetInfo')).targetInfo.targetId === opened.targetId; }
    finally { await inspector.detach(); }
  }, {timeout: 15000});
  const frontend = await frontendTarget.asPage(); assert(frontend);
  row.frontendCreatedBy = 'Target.openDevTools'; row.frontendTargetMatchedNativeReply = true;
  checkpoint('NATIVE_DEVTOOLS_FRONTEND_ATTACHED');
  const errors = []; const requests = []; row.frontendErrors = errors;
  row.frontendRequests = requests;
  try {
    frontend.setDefaultTimeout(20000); frontend.setDefaultNavigationTimeout(20000);
    frontend.on('pageerror', error => errors.push(String(error.message).slice(0, 512)));
    await frontend.setRequestInterception(true);
    frontend.on('request', request => {
      const url = new URL(request.url()); const allowed = ['devtools:', 'data:', 'about:'].includes(url.protocol)
        || url.origin === route.origin;
      assert(requests.length < 2048); requests.push({protocol: url.protocol, path: url.pathname, allowed});
      if (allowed) request.continue().catch(error => errors.push('DevTools continuation: ' + error.name));
      else request.abort().catch(() => {});
    });
    row.frontendRequestObservationBeganAfterNativeOpen = true;
    await waitInFrontend(frontend);
    checkpoint('DEVTOOLS_DEBUGGER_MODEL_READY');
    await page.evaluate(async url => {
      await new Promise((resolve, reject) => { const script = document.createElement('script'); script.src = url;
        script.onload = resolve; script.onerror = () => reject(new Error('Mapper script load failed')); document.head.append(script); });
    }, route.origin + '/mapperTab.js');
    checkpoint('INSTALLED_MAPPER_SCRIPT_LOADED');
    await waitInFrontend(frontend, route.origin + '/mapperTab.js');
    checkpoint('DEVTOOLS_MAPPER_SCRIPT_DISCOVERED');
    const actual = await bounded(() => frontend.evaluate(async ({scriptURL, samples}) => {
      const SDK = await import('./core/sdk/sdk.js');
      const candidates = SDK.TargetManager.TargetManager.instance().models(SDK.DebuggerModel.DebuggerModel)
        .flatMap(model => model.scriptsForSourceURL(scriptURL).map(script => ({model, script})));
      if (candidates.length !== 1) throw new Error('DevTools mapper script selection differs');
      const {model, script} = candidates[0];
      const executed = await model.target().debuggerAgent().invoke_getScriptSource({scriptId: script.scriptId});
      if (executed.getError() || typeof executed.scriptSource !== 'string') throw new Error('DevTools executed script source absent');
      const sourceMap = await model.sourceMapManager().sourceMapForClientPromise(script);
      if (!sourceMap) throw new Error('DevTools automatic source map absent');
      return {executedSource: executed.scriptSource, compiledURL: sourceMap.compiledURL(), mapURL: sourceMap.url(),
        contents: sourceMap.sourceURLs().map(url => ({url, content: sourceMap.embeddedContentByURL(url)})),
        samples: samples.map(row => {
          const found = sourceMap.findEntry(row.generatedLine, row.generatedColumn);
          if (!found) throw new Error('DevTools mapped sample absent');
          return {binding: row.binding, generatedLine: found.lineNumber, generatedColumn: found.columnNumber,
            sourceIndex: found.sourceIndex, source: found.sourceURL, originalLine: found.sourceLineNumber, originalColumn: found.sourceColumnNumber};
        })};
    }, {scriptURL: route.origin + '/mapperTab.js', samples: manifest.debuggerSamples}), 'DevTools map consumption', 25000);
    checkpoint('DEVTOOLS_MAP_CONSUMPTION_RETURNED');
    assert.deepEqual(pin(Buffer.from(actual.executedSource)), pin(source)); delete actual.executedSource;
    checkpoint('EXECUTED_MAPPER_SOURCE_VERIFIED');
    const data = JSON.parse(map); assert.equal(actual.compiledURL, route.origin + '/mapperTab.js');
    assert.equal(actual.mapURL, route.origin + '/mapperTab.js.map');
    assert.deepEqual(actual.contents, data.sources.map((name, index) => ({url: new URL(name, actual.mapURL).href, content: data.sourcesContent[index]})));
    assert.deepEqual(actual.samples, manifest.debuggerSamples.map(sample => ({...sample, source: new URL(sample.source, actual.mapURL).href})));
    assert(row.routeRequests.some(item => item.path === '/mapperTab.js.map' && item.status === 200 && item.pin.sha256 === pin(map).sha256));
    assert.equal(errors.length, 0); assert(requests.every(request => request.allowed));
    row.devtoolsSourceMap = {kind: 'BUNDLED_CHROME_DEVTOOLS_AUTOMATIC_RELATIVE_SOURCE_MAP_CONSUMPTION',
      scriptSource: pin(source), sourceMap: pin(map), automaticallyFetchedRelativeMap: true,
      mappedSourcesAndEmbeddedContentsVerified: actual.contents.length, debuggerSamples: manifest.debuggerSamples,
      frontendRevisionFromChromeDEPS: '12ada949de6a27116dea47c600da5322f44c64f4',
      frontendRevisionIndependentlyAuthenticated: false, additionalChromeParentInstances: 0,
      initializedFrontendSDKQueriedInMainWorld: true,
      nativeBrowserCreatedFrontend: true,
      scriptSourceRetrievedThroughFrontendDebuggerSession: true,
      manuallyAttachedMapOrReplacementConsumerUsed: false, productionGate: 'NO_GO'};
    checkpoint('DEVTOOLS_MAP_CONTENTS_AND_SAMPLES_VERIFIED');
  } finally {
    checkpoint('BEGIN_DEVTOOLS_FRONTEND_CLEANUP');
    await bounded(() => frontend.close(), 'DevTools frontend close', 5000); row.frontendClosed = frontend.isClosed();
    checkpoint('DEVTOOLS_FRONTEND_CLOSED');
  }
}
module.exports = {openMapperRoute, inspectMapperMap};
