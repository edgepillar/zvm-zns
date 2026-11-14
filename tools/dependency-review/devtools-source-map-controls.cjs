'use strict';

// Exercise the browser's bundled DevTools frontend and automatic relative-map
// fetch, rather than substituting a model or manually attaching a parsed map.
const assert = require('node:assert/strict');
const http = require('node:http');
const {pin} = require('./browser-source-guard.cjs');

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
    close: () => new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()))};
}

async function inspectMapperMap(browser, page, session, targetId, route, source, map, manifest, row) {
  const frontend = await browser.newPage(); const errors = []; const requests = []; row.frontendErrors = errors;
  row.frontendRequests = requests; let scriptId;
  const onScript = event => { if (event.url === route.origin + '/mapperTab.js') { assert(!scriptId); scriptId = event.scriptId; } };
  session.on('Debugger.scriptParsed', onScript);
  try {
    frontend.setDefaultTimeout(20000); frontend.setDefaultNavigationTimeout(20000);
    frontend.on('pageerror', error => errors.push(String(error.message).slice(0, 512)));
    await frontend.setRequestInterception(true);
    const endpoint = new URL(browser.wsEndpoint()); assert.equal(endpoint.hostname, '127.0.0.1');
    const socket = '127.0.0.1:' + endpoint.port + '/devtools/page/' + targetId;
    frontend.on('request', request => {
      const url = new URL(request.url()); const allowed = ['devtools:', 'data:', 'about:'].includes(url.protocol)
        || url.origin === route.origin || (url.protocol === 'ws:' && url.host === endpoint.host);
      assert(requests.length < 2048); requests.push({protocol: url.protocol, path: url.pathname, allowed});
      if (allowed) request.continue().catch(error => errors.push('DevTools continuation: ' + error.name));
      else request.abort().catch(() => {});
    });
    await session.send('Debugger.enable');
    await frontend.goto('devtools://devtools/bundled/inspector.html?ws=' + socket, {waitUntil: 'domcontentloaded'});
    await frontend.waitForFunction(async () => {
      const SDK = await import('./core/sdk/sdk.js');
      return SDK.TargetManager.TargetManager.instance().models(SDK.DebuggerModel.DebuggerModel).length > 0;
    });
    await page.evaluate(async url => {
      await new Promise((resolve, reject) => { const script = document.createElement('script'); script.src = url;
        script.onload = resolve; script.onerror = () => reject(new Error('Mapper script load failed')); document.head.append(script); });
    }, route.origin + '/mapperTab.js');
    assert(scriptId); const executed = await session.send('Debugger.getScriptSource', {scriptId});
    assert.deepEqual(pin(Buffer.from(executed.scriptSource)), pin(source));
    await frontend.waitForFunction(async scriptURL => {
      const SDK = await import('./core/sdk/sdk.js');
      return SDK.TargetManager.TargetManager.instance().models(SDK.DebuggerModel.DebuggerModel)
        .some(model => model.scriptsForSourceURL(scriptURL).length > 0);
    }, {}, route.origin + '/mapperTab.js');
    const actual = await frontend.evaluate(async ({scriptURL, samples}) => {
      const SDK = await import('./core/sdk/sdk.js');
      const candidates = SDK.TargetManager.TargetManager.instance().models(SDK.DebuggerModel.DebuggerModel)
        .flatMap(model => model.scriptsForSourceURL(scriptURL).map(script => ({model, script})));
      if (candidates.length !== 1) throw new Error('DevTools mapper script selection differs');
      const {model, script} = candidates[0];
      const sourceMap = await model.sourceMapManager().sourceMapForClientPromise(script);
      if (!sourceMap) throw new Error('DevTools automatic source map absent');
      return {compiledURL: sourceMap.compiledURL(), mapURL: sourceMap.url(),
        contents: sourceMap.sourceURLs().map(url => ({url, content: sourceMap.embeddedContentByURL(url)})),
        samples: samples.map(row => {
          const found = sourceMap.findEntry(row.generatedLine, row.generatedColumn);
          if (!found) throw new Error('DevTools mapped sample absent');
          return {binding: row.binding, generatedLine: found.lineNumber, generatedColumn: found.columnNumber,
            sourceIndex: found.sourceIndex, source: found.sourceURL, originalLine: found.sourceLineNumber, originalColumn: found.sourceColumnNumber};
        })};
    }, {scriptURL: route.origin + '/mapperTab.js', samples: manifest.debuggerSamples});
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
      manuallyAttachedMapOrReplacementConsumerUsed: false, productionGate: 'NO_GO'};
  } finally {
    session.off('Debugger.scriptParsed', onScript); await session.send('Debugger.disable');
    await frontend.close(); row.frontendClosed = frontend.isClosed();
  }
}
module.exports = {openMapperRoute, inspectMapperMap};
