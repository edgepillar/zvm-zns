'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const child = require('node:child_process');
const {syncBuiltinESMExports} = require('node:module');
const {fixture} = require('./browser-fixture.cjs');
const {sourceGuard, read, pin} = require('./browser-source-guard.cjs');
const {nativeControls} = require('./coherent-controls.cjs');
const {embeddedMapperControls} = require('./embedded-mapper-controls.cjs');

const partial = {schema: 1, status: 'BROWSER_WORKER_INCOMPLETE_NOT_QUALIFIED', sessions: [], screenshots: [],
  sourceGuardQualification: 'NOT_COMPLETE', productionGate: 'NO_GO'};

function userAgentEvidence(userAgent, expected) {
  assert(typeof userAgent === 'string' && userAgent.length <= 1024);
  const match = /(?:HeadlessChrome|Chrome)\/(\d+\.\d+\.\d+\.\d+)/.exec(userAgent);
  assert(match && match[1].split('.')[0] === expected.split('.')[0]);
  return {versionToken: match[1], majorVersionMatches: true, fullBinaryVersionProof: false};
}

function profileSize(root) {
  let bytes = 0; let files = 0; let links = 0;
  function visit(directory) {
    for (const name of fs.readdirSync(directory)) {
      const target = path.join(directory, name); const stat = fs.lstatSync(target);
      if (stat.isSymbolicLink()) links++;
      else if (stat.isDirectory()) visit(target);
      else { assert(stat.isFile()); files++; bytes += stat.size; }
      assert(files + links <= 32768 && bytes <= 192 << 20, 'Hosted browser profile budget');
    }
  }
  visit(root); return {regularFiles: files, regularBytes: bytes, untraversedLinks: links};
}
async function main() {
  assert.equal(process.argv.length, 3); const input = JSON.parse(read(process.argv[2], 65536));
  assert.equal(input.schema, 1); assert(['baseline', 'candidate', 'coherentCandidate', 'application'].includes(input.profile));
  const derivativeProfile = ['coherentCandidate', 'application'].includes(input.profile);
  const baseProfile = derivativeProfile ? 'candidate' : input.profile;
  partial.profile = input.profile; partial.browserVersion = input.browserVersion;
  assert.equal(process.platform, 'linux'); assert.equal(process.arch, 'x64');
  assert(/^\d+$/.test(input.runId)); assert(process.report.getReport().header.glibcVersionRuntime);
  assert.equal(fs.realpathSync(input.executable), input.executable);
  assert.deepEqual(pin(read(input.executable, 512 << 20)), input.executablePin);
  const output = fs.realpathSync(input.output); assert.equal(output, input.output);
  if (input.temporaryRoot) {
    const temporary = fs.realpathSync(input.temporaryRoot);
    assert.equal(temporary, input.temporaryRoot);
    assert.equal(path.dirname(temporary), path.dirname(output)); assert.equal(path.basename(temporary), 't');
    assert(fs.lstatSync(temporary).isDirectory() && Buffer.byteLength(temporary) <= 48);
    partial.hostedTemporaryPathBytes = Buffer.byteLength(temporary);
  }
  const plan = JSON.parse(read(input.plan, 65536)); const caller = plan.callers.find(row => row.path === 'web/scripts/shots.mjs'); assert(caller);
  const raw = read(path.join(input.repo, caller.path), 65536); assert.deepEqual(pin(raw), caller.sourcePin);
  const matches = [...raw.toString().matchAll(/^const browser = await puppeteer\.launch\((\{[^\r\n]*\})\)\s*$/gm)];
  assert.equal(matches.length, 1); assert.equal(pin(Buffer.from(matches[0][1])).sha256, caller.expressionSha256);
  const context = vm.createContext({chrome: input.executable}, {codeGeneration: {strings: false, wasm: false}});
  const tracked = new vm.Script('(' + matches[0][1] + ')').runInContext(context, {timeout: 100});
  assert.deepEqual(Object.keys(tracked).sort(), caller.expectedKeys);
  const source = await sourceGuard(input);
  const viem = await import(source.resolve('viem')); const {default: puppeteer} = await import(source.resolve('puppeteer-core'));
  const coherentNode = derivativeProfile ? await nativeControls(source) : null;
  partial.coherentNativeNodeControls = coherentNode;
  const server = await fixture(input, viem); const sessions = partial.sessions; const spawns = []; let deniedProcesses = 0;
  partial.fixture = server.report;
  const originalSpawn = child.spawn;
  child.spawn = function(executable, args, options) {
    if (executable !== input.executable || spawns.length >= 2) { deniedProcesses++; throw new Error('Unreviewed child process'); }
    assert(Array.isArray(args) && args.includes('--no-sandbox') && args.includes('--headless=new'));
    const process = originalSpawn.call(this, executable, args, options); spawns.push({process, args}); return process;
  };
  for (const name of ['spawnSync', 'exec', 'execSync', 'execFile', 'execFileSync', 'fork']) {
    child[name] = () => { deniedProcesses++; throw new Error('Unreviewed child process method'); };
  }
  syncBuiltinESMExports();
  const screenshots = partial.screenshots;
  async function screenshot(page, protocol, name) {
    const raw = Buffer.from(await page.screenshot({type: 'png', fullPage: false}));
    assert(raw.length <= 1 << 20 && raw.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])));
    const width = raw.readUInt32BE(16); const height = raw.readUInt32BE(20);
    const filename = input.profile + '-' + protocol + '-' + name + '.png';
    fs.writeFileSync(path.join(output, filename), raw, {flag: 'wx', mode: 0o600});
    screenshots.push({path: 'browser-evidence/' + filename, width, height, ...pin(raw)});
  }
  async function position(page) {
    return await page.evaluate(() => new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(p => resolve({latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy: p.coords.accuracy}),
        error => reject(new Error('Synthetic geolocation read failed: ' + error.code)), {timeout: 5000, maximumAge: 0});
    }));
  }
  try {
    for (const protocol of ['cdp', 'webDriverBiDi']) {
      const directory = path.join(output, input.profile + '-' + protocol + '-profile'); fs.mkdirSync(directory, {mode: 0o700});
      let browser; let process; const errors = []; const network = []; const geo = [];
      const row = {protocol, application: [], externalPageRequests: [], pageErrors: errors}; sessions.push(row);
      try {
        // Preserve the tracked caller expression, then record the hosted-only
        // transport/profile/budget overlays rather than claiming shots.mjs ran.
        browser = await puppeteer.launch({...tracked, args: [...tracked.args, '--disable-dev-shm-usage', '--no-first-run',
          '--disable-background-networking', '--disable-component-update', '--disable-domain-reliability',
          '--disable-sync', '--metrics-recording-only', '--no-default-browser-check',
          '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost'],
          protocol, userDataDir: directory, timeout: 20000, protocolTimeout: 20000,
          env: {...processEnv(input), XDG_CACHE_HOME: directory, XDG_CONFIG_HOME: directory}});
        process = browser.process(); assert(process && spawns.some(row => row.process === process));
        row.browserClass = browser.constructor.name; assert.equal(row.browserClass, protocol === 'cdp' ? 'CdpBrowser' : 'BidiBrowser');
        row.version = await browser.version(); assert(row.version.includes(input.browserVersion));
        row.userAgent = await browser.userAgent(); row.userAgentEvidence = userAgentEvidence(row.userAgent, input.browserVersion);
        if (derivativeProfile && protocol === 'cdp') {
          row.embeddedMapper = {};
          row.embeddedMapper = await embeddedMapperControls(browser, input, source, row.embeddedMapper);
        }
        const page = await browser.newPage(); page.setDefaultTimeout(15000); page.setDefaultNavigationTimeout(15000);
        page.on('pageerror', error => errors.push(String(error.message).slice(0, 1024)));
        await page.setRequestInterception(true);
        page.on('request', request => {
          const url = new URL(request.url()); const allowed = url.origin === server.origin || ['data:', 'about:'].includes(url.protocol);
          assert(network.length < 2048); network.push({method: request.method(), path: url.origin === server.origin ? url.pathname : url.protocol, allowed});
          if (allowed) request.continue().catch(error => errors.push('Request continuation: ' + error.name));
          else { row.externalPageRequests.push({protocol: url.protocol, host: url.hostname}); request.abort().catch(() => {}); }
        });
        await page.setViewport({width: 1280, height: 900, deviceScaleFactor: 1});
        const query = '?rpc=' + encodeURIComponent(server.origin + '/rpc');
        await page.goto(server.origin + '/normal/' + query + '#/', {waitUntil: 'networkidle0'});
        await page.waitForFunction(() => document.body.innerText.includes('ZNS is not deployed on chain 7340469.'));
        const nominal = await page.evaluate(() => ({heading: document.querySelector('h1')?.textContent.trim(),
          notDeployed: document.body.innerText.includes('ZNS is not deployed on chain 7340469.'),
          injectedProvider: typeof window.ethereum !== 'undefined', savedWallet: localStorage.getItem('zns.wallet')}));
        assert(nominal.heading.includes('Your name on the') && nominal.notDeployed && !nominal.injectedProvider && nominal.savedWallet === null);
        row.application.push({case: 'nominal-no-deployment', ...nominal});
        await screenshot(page, protocol, 'normal-wide');
        await browser.defaultBrowserContext().overridePermissions(server.origin, ['geolocation']);
        await page.setGeolocation({latitude: 12.5, longitude: 23.5, accuracy: 1});
        const explicit = await position(page); assert.deepEqual(explicit, {latitude: 12.5, longitude: 23.5, accuracy: 1});
        geo.push({case: 'valid-explicit-accuracy', observed: explicit});
        if (protocol === 'webDriverBiDi') {
          let omitted;
          try { await page.setGeolocation({latitude: 12.5, longitude: 23.5}); omitted = {status: 'returned', observed: await position(page)}; }
          catch (error) { omitted = {status: 'rejected', type: error.name, message: String(error.message).slice(0, 512)}; }
          if (baseProfile === 'candidate') {
            assert.equal(omitted.status, 'returned'); assert.deepEqual(omitted.observed, {latitude: 12.5, longitude: 23.5, accuracy: 0});
            await page.setGeolocation(null); geo.push({case: 'candidate-null-reset', status: 'returned'});
          }
          geo.push({case: 'omitted-accuracy-benign-input', ...omitted});
        }
        row.geolocation = geo;
        await page.goto(server.origin + '/fixture/' + query + '#/', {waitUntil: 'networkidle0'});
        await page.waitForFunction(() => !document.body.innerText.includes('ZNS is not deployed') && document.body.innerText.includes('1 ZNN / year'));
        await page.type('[data-testid="search"]', 'source-fixture');
        await page.waitForSelector('[data-testid="result"]');
        const search = await page.$eval('[data-testid="result"]', node => ({text: node.innerText, href: node.getAttribute('href')}));
        assert(search.text.includes('Available') && search.text.includes('1 ZNN') && search.href.includes('/name/source-fixture.znn'));
        row.application.push({case: 'synthetic-available-name-and-price', ...search});
        await page.click('[data-testid="result"]');
        await page.waitForFunction(() => document.querySelector('[data-testid="total"]')?.textContent.trim() === '1 ZNN');
        await page.click('button[aria-label="One year more"]');
        await page.waitForFunction(() => document.querySelector('[data-testid="total"]')?.textContent.trim() === '2 ZNN');
        assert.equal(await page.$('[data-testid="register-go"]'), null);
        const term = await page.$eval('[data-testid="years"]', node => node.textContent.trim());
        row.application.push({case: 'synthetic-navigation-and-two-year-price', term, total: '2 ZNN', registrationActionUnavailableWithoutWallet: true});
        const beforeTheme = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
        await page.click('button[title^="Switch to the "]');
        const theme = await page.evaluate(() => ({theme: document.documentElement.getAttribute('data-theme'), saved: localStorage.getItem('zns.theme')}));
        assert(theme.theme !== beforeTheme && theme.saved === theme.theme); row.application.push({case: 'theme-toggle', ...theme});
        await screenshot(page, protocol, 'fixture-wide');
        await page.setViewport({width: 400, height: 860, deviceScaleFactor: 1});
        await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth);
        const dimensions = await page.evaluate(() => ({viewportWidth: innerWidth, documentWidth: document.documentElement.scrollWidth}));
        assert.equal(dimensions.viewportWidth, 400); assert(dimensions.documentWidth <= 400);
        row.application.push({case: 'mobile-layout-no-horizontal-overflow', ...dimensions});
        await screenshot(page, protocol, 'fixture-mobile');
        row.network = network; assert.equal(errors.length, 0); assert.equal(row.externalPageRequests.length, 0);
      } finally {
        if (browser) await browser.close();
        if (process) {
          if (process.exitCode === null && process.signalCode === null) await new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('Owned browser did not exit')), 10000);
            process.once('exit', () => { clearTimeout(timer); resolve(); });
          });
          assert(process.exitCode !== null || process.signalCode !== null);
          row.processExit = {actualExit: process.exitCode, signal: process.signalCode, disconnected: !browser.connected};
          assert(row.processExit.disconnected);
        }
        row.profile = profileSize(directory);
      }
    }
  } finally { await server.close(); }
  assert.equal(server.report.refusals.length, 0); assert.equal(deniedProcesses, 0); assert.equal(spawns.length, 2);
  assert(sessions.reduce((sum, row) => sum + row.profile.regularBytes, 0) <= 192 << 20);
  assert(server.report.rpc.some(row => row.functionName === 'rentPrice') && server.report.rpc.some(row => row.method === 'eth_getLogs'));
  const guard = source.finish();
  process.stdout.write(JSON.stringify({schema: 1, status: 'PAIRED_PROTOCOL_AND_SYNTHETIC_APPLICATION_CONTROLS_PASSED',
    profile: input.profile, browserVersion: input.browserVersion, runId: input.runId, nodeVersion: process.version,
    nodePlatform: process.platform, nodeArchitecture: process.arch, glibc: process.report.getReport().header.glibcVersionRuntime,
    puppeteerVersion: plan.profiles[baseProfile].puppeteer, coherentNativeNodeControls: coherentNode,
    effectiveLocalDerivativeUsed: derivativeProfile,
    actualApplicationDependencyInputsAdopted: input.profile === 'application',
    actualApplicationInstalledMembersChanged: input.profile === 'application' ? 9 : 0,
    hostedTemporaryPathBytes: input.temporaryRoot ? Buffer.byteLength(input.temporaryRoot) : null,
    trackedCaller: {path: caller.path, sourcePin: caller.sourcePin,
      expressionSha256: caller.expressionSha256, completeOriginalScriptExecuted: false},
    sessions, sourceGuard: guard, screenshots, distributions: server.distributions, fixture: server.report,
    spawnedBrowserArguments: spawns.map(row => row.args.map(arg => arg.startsWith('--user-data-dir=') ? '--user-data-dir=<owned-profile>' : arg)),
    deniedChildProcesses: deniedProcesses, realBrowserProtocolSessions: 2, noSandboxFlagFromTrackedCaller: true,
    pageRequestAndSourceObserversAreNotOperatingSystemNetworkOrProcessIsolation: true,
    fundedVerificationWalletSigningLiveChainReleaseOrDeploymentPerformed: false,
    derivedGuardOrRebuiltMapperInstalled: derivativeProfile, rawCandidateOrBaselinePackageSourcesModified: false,
    fullApplicationMigrationAcceptance: false, productionGate: 'NO_GO'}) + '\n');
}
function processEnv(input) {
  // Deliberately pass a bounded child environment; no inherited credentials.
  return {PATH: process.env.PATH, LANG: 'C', TZ: 'UTC', TMPDIR: input.temporaryRoot ?? input.output};
}
main().catch(error => {
  partial.failure = {type: error.name, reason: 'Qualification incomplete; inspect retained stderr'};
  process.stdout.write(JSON.stringify(partial) + '\n');
  process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1;
});
