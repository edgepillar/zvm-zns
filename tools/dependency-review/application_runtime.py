"""Qualify the actual adopted web installation with one pinned Chrome input."""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

from browser_runtime import download_browser, extract_browser
from browser_staging import hosted_only, new_file, validate_source_plan
from coherent_derivation import PACKAGE, MAPPER, runtime_probe
from compiled_labels import canonical_sha256, inspect_labels
from lock_review import read_input, require
from node_consumer_controls import permission_args
from openzeppelin_candidate import run_bounded, write_json
from profile_sources import pin, read_regular, select_profile, verify_profile
from web_patches import dist_inventory

VENDOR = 'vendor/chromium-bidi-157-reviewed'


def temporary_directory(output):
    # Linux sockaddr_un has a finite byte budget. Leave room for Chrome's
    # generated singleton directory and socket basename before any install.
    require(output.is_absolute(), 'browser output must be absolute')
    result = output / 't'
    require(len(str(result).encode('utf8')) <= 48, 'owned Chrome temporary path exceeds the reviewed socket budget')
    return result


def verify_inputs(repo, expected):
    require(type(expected) is dict and 0 < len(expected) <= 256, 'application input pin count')
    total = 0
    for name, value in expected.items():
        raw = read_regular(repo, name, 16 << 20); total += len(raw)
        require(total <= 16 << 20 and pin(raw) == value, 'application input source or aggregate budget differs')


def current_cache_index(repo, web, output, env, run, npm_version, integrities):
    npm_bin = shutil.which('npm', path=env['PATH']); require(npm_bin, 'npm executable absent')
    npm_root = Path(npm_bin).resolve(strict=True).parent.parent
    manifest = json.loads(read_regular(npm_root, 'package.json', 65536))
    require(manifest['name'] == 'npm' and manifest['version'] == npm_version, 'npm root/version differs')
    cache = Path(env['npm_config_cache']) / '_cacache'
    require(cache.is_dir() and not cache.is_symlink(), 'current-job npm cache absent or linked')
    request = output / 'cache-input.json'
    write_json(request, {'schema': 1, 'npmRoot': str(npm_root), 'cacheRoot': str(cache), 'npmVersion': npm_version,
        'integrities': sorted(integrities)})
    run('application-cache-index', ['node', *permission_args([repo / 'tools/dependency-review', npm_root, cache, request]),
        str(repo / 'tools/dependency-review/npm-cache-index.cjs'), str(request)], web, 45)
    result = json.loads(read_input(output, 'streams/application-cache-index.stdout.txt'))
    require(result['npmVersion'] == npm_version and not result['historicalCacheFallbackOrAdditionalTransport']
        and not result['cacheVerifyCleanOrMutationRequested'], 'npm cache API evidence scope')
    return cache, result


def raw_profile(repo, web, output, env, run, npm_version):
    lock_raw = read_input(web, 'package-lock.json'); rows = json.loads(lock_raw)['packages']
    installed = {name for name in rows if name and (web / name).exists()}
    profile = {'os': 'linux', 'cpu': 'x64', 'libc': 'glibc'}
    selected = select_profile(lock_raw, installed, profile)['selected']
    cache, result = current_cache_index(repo, web, output, env, run, npm_version,
        {row['selection']['integrity'] for row in selected.values()})
    budgets_raw = read_input(repo, 'tools/dependency-review/profile-source-budgets.json')
    inventory = verify_profile(web, lock_raw, cache, result['index'], profile, json.loads(budgets_raw))
    inventory['sourceBudgetPlanPin'] = pin(budgets_raw)
    write_json(output / 'application-raw-profile-sources.json', inventory)
    return inventory, result


def installed_vite_labels(web, publication):
    location = 'node_modules/vite'
    files = {}
    for name, value in publication['filePins'].items():
        if name.endswith(('.js', '.mjs', '.cjs')):
            raw = read_regular(web, location + '/' + name, 2 << 20)
            require(pin(raw) == value, 'installed Vite label source differs from its publication')
            files[name] = raw
    return inspect_labels(files)


def verify_vite_labels(web, inventory, expected):
    location = 'node_modules/vite'
    require(location in inventory['installed'], 'installed Vite publication missing')
    selected = inventory['installed'][location]['selection']
    require(selected['name'] == 'vite' and selected['version'] == expected['version'], 'installed Vite identity differs')
    labels = installed_vite_labels(web, inventory['sources'][selected['integrity']])
    require(not labels['unparsedRegionLabels'], 'installed Vite has unreviewed compiled labels')
    digest = canonical_sha256(labels)
    require(digest == expected['inventorySha256'], 'installed Vite compiled label inventory differs')
    return {'version': selected['version'], 'integrity': selected['integrity'],
        'inventorySha256': digest, 'fileCount': len(labels['sourceFilePins']),
        'occurrences': len(labels['generatedRegionLabels']), 'pairs': len(labels['distinctNameVersionLabels']),
        'evidenceAuthority': labels['evidenceAuthority']}


def effective_profile(web, manifest):
    require(pin(read_regular(web, 'package-lock.json', 2 << 20))['sha256'] == manifest['baseLockSha256'], 'effective lock differs')
    require(pin(read_regular(web, PACKAGE + 'package.json', 1 << 20)) == manifest['originalPackageManifest'], 'effective package manifest differs')
    for name, row in manifest['effectiveMembers'].items():
        require(pin(read_regular(web, name, 16 << 20)) == row['effective'], 'effective application runtime differs')


def verify_build_sources(repo, source):
    rows = validate_source_plan(source)
    for row in rows:
        provider = repo if row['sourceRepository'] == 'main' else repo / 'zvm-core'
        require(pin(read_input(provider, row['sourcePath'])) == row['pin'], 'browser build source differs')
    return rows


def verify_reused_members(web, publications, manifest):
    count = size = 0
    for location, publication in publications.items():
        for member, original in publication['filePins'].items():
            name = location + '/' + member
            overlay = manifest['effectiveMembers'].get(name)
            expected = overlay['effective'] if overlay else original
            require(pin(read_regular(web, name, 16 << 20)) == expected, 'reused installed member differs')
            count += 1
            size += expected['bytes']
            require(count <= 32768 and size <= 256 << 20, 'reused installed package budget')
    for name, row in manifest['effectiveMembers'].items():
        if row['original'] is None:
            count += 1
            size += row['effective']['bytes']
    require(count <= 32768 and size <= 256 << 20, 'reused effective package budget')
    return {'publicationLocations': len(publications), 'regularMembers': count, 'payloadBytes': size}


def build_distributions(repo, web, output, plan, manifest, publications, run):
    source_raw = read_input(repo, 'tools/dependency-review/browser-app-sources.json')
    source = json.loads(source_raw)
    sources = verify_build_sources(repo, source)
    require(read_input(repo, '.env') == read_input(repo, '.env.example'), 'browser build environment differs')
    package_raw = read_input(web, 'package.json')
    scripts = json.loads(package_raw)['scripts']
    require(scripts['build'] == 'node scripts/prepare-runtime.mjs && vue-tsc --noEmit && vite build'
        and not {'prebuild', 'postbuild'} & set(scripts), 'application build command differs')

    deployments = repo / 'deployments'
    dist = web / 'dist'
    normal = output / 'normal-dist'
    fixture_dist = output / 'fixture-dist'
    require(all(not path.exists() and not path.is_symlink() for path in (deployments, dist, normal, fixture_dist)),
        'application builds require fresh output paths and an empty deployment scope')
    run('application-build', ['npm', 'run', 'build'])
    distribution = dist_inventory(dist)
    dist.rename(normal)

    effective_profile(web, manifest)
    reused = verify_reused_members(web, publications, manifest)
    fixture = (json.dumps(source['syntheticDeploymentFixture'], sort_keys=True, indent=2) + '\n').encode()
    deployments.mkdir(mode=0o700)
    owned_directory = deployments.lstat()
    target = new_file(repo, 'deployments/browser-fixture.json', fixture)
    owned_fixture = target.lstat()
    try:
        run('fixture-application-build', ['npm', 'run', 'build'])
        fixture_distribution = dist_inventory(dist)
        dist.rename(fixture_dist)
    finally:
        current_directory = deployments.lstat()
        current_fixture = target.lstat()
        require((current_directory.st_dev, current_directory.st_ino) == (owned_directory.st_dev, owned_directory.st_ino)
            and (current_fixture.st_dev, current_fixture.st_ino) == (owned_fixture.st_dev, owned_fixture.st_ino)
            and set(deployments.iterdir()) == {target} and read_regular(repo, 'deployments/browser-fixture.json', 65536) == fixture,
            'preserve unexpected synthetic deployment state')
        target.unlink()
        deployments.rmdir()
    require(dist_inventory(normal) == distribution, 'normal output changed during the fixture build')
    require(distribution != fixture_distribution, 'fixture did not change the distribution')
    for notice in plan['retainedStaticNotices']:
        for built in (distribution, fixture_distribution):
            require(built['files'].get(notice['distPath']) == notice['pin'], 'static notice differs')
    verify_build_sources(repo, source)
    effective_profile(web, manifest)
    require(read_input(web, 'package.json') == package_raw, 'application manifest changed during the builds')
    return distribution, {'schema': 2, 'sourcePlan': pin(source_raw), 'sources': sources,
        'verifiedReusedMembers': reused, 'dependencyBytesCopied': 0, 'dependencyTreesCopied': 0,
        'syntheticDeployment': pin(fixture), 'syntheticDeploymentRemoved': True,
        'distribution': fixture_distribution, 'fixtureNpmScriptExecuted': True, 'productionGate': 'NO_GO'}


def reviewed_upgrade(output, candidate_output, binding, baseline_lock):
    if candidate_output is None:
        return None
    root = Path(candidate_output)
    require(root == output.parent / 'zns-vite-upgrade' and root.resolve(strict=True) == root, 'candidate evidence scope differs')
    report_raw = read_regular(root, 'report.json', 2 << 20)
    report = json.loads(report_raw)
    require(report['status'] == 'VITE_CANDIDATE_APPLICATION_BUILDS_OBSERVED'
        and report['producerCommit'] == binding['producerCommit'] and report['coreCommit'] == binding['coreCommit']
        and report['runId'] == binding['runId'] and report['runAttempt'] == binding['runAttempt']
        and report['baselineLock'] == baseline_lock and report['baselinePlan'] == binding['planPin'],
        'candidate app evidence differs from the current job')
    lock_file = 'candidate-lock.json' if report['selectorCarry']['carriedSelectorCount'] else 'npm-generated-lock.json'
    lock_sha256 = pin(read_regular(root, lock_file, 2 << 20))['sha256']
    require(lock_sha256 == report['lockDelta']['candidateLockSha256'], 'candidate application lock differs')
    expected = {'upgrade-normal': report['normalDistribution'], 'upgrade-fixture': report['fixtureBuild']['distribution']}
    paths = {'upgrade-normal': root / 'normal-dist', 'upgrade-fixture': root / 'fixture-dist'}
    for role, path in paths.items():
        require(dist_inventory(path) == expected[role], 'candidate browser distribution differs: ' + role)
    return {'root': root, 'paths': paths, 'expected': expected, 'binding': {
        'candidateReport': pin(report_raw), 'candidateLockSha256': lock_sha256,
        'publicationSelection': report['publicationSelection'],
        'verifiedReusedMembers': report['fixtureBuild']['verifiedReusedMembers'],
        'dependencyBytesCopied': report['fixtureBuild']['dependencyBytesCopied'],
        'syntheticDeployment': report['fixtureBuild']['syntheticDeployment'],
    }}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--vite-upgrade')
    args = parser.parse_args()
    hosted_only(); require(platform.libc_ver()[0] == 'glibc', 'application qualification requires Linux x64 glibc')
    repo = Path(__file__).resolve().parents[2]; web = repo / 'web'; output = Path(args.output).resolve()
    temporary = temporary_directory(output)
    require(not output.exists() and not output.is_symlink(), 'application output must be new')
    require(shutil.disk_usage(output.parent).free >= (10 << 30) + (3 << 30), 'application free-space floor and allocation reserve')
    output.mkdir(mode=0o700); (output / 'streams').mkdir(mode=0o700)
    plan_raw = read_input(repo, 'tools/dependency-review/application-runtime.json'); plan = json.loads(plan_raw)
    verify_inputs(repo, plan['inputPins'])
    require(read_input(repo, '.env') == read_input(repo, '.env.example'), 'application environment differs from example')
    commit = subprocess.check_output(['git', '--no-optional-locks', '--no-replace-objects', 'rev-parse', 'HEAD'], cwd=repo).decode().strip()
    core = subprocess.check_output(['git', '--no-optional-locks', '--no-replace-objects', '-C', 'zvm-core', 'rev-parse', 'HEAD'], cwd=repo).decode().strip()
    require(core == plan['coreCommit'], 'application core source differs')
    require(not subprocess.check_output(['git', 'ls-files', '--', 'deployments'], cwd=repo), 'tracked operator deployments are outside this lane')
    require(not (web / 'node_modules').exists(), 'application lane requires a fresh actual npm installation')
    binding = {'schema': 1, 'producerCommit': commit, 'coreCommit': core, 'planPin': pin(plan_raw),
        'inputPins': plan['inputPins'], 'codePins': {name: pin(read_input(repo, name)) for name in plan['codeFiles']},
        'runId': os.environ['GITHUB_RUN_ID'], 'runAttempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'legacyQualificationIsHistoricalNotCurrentRevisionEvidence': True, 'productionGate': 'NO_GO'}
    write_json(output / 'source-binding.json', binding)
    report = {'schema': 1, 'status': 'APPLICATION_RUNTIME_INCOMPLETE', 'commands': [], 'productionGate': 'NO_GO'}
    upgrade = reviewed_upgrade(output, args.vite_upgrade, binding, pin(read_input(web, 'package-lock.json')))
    npm_cache = output / 'npm-cache'
    if upgrade is None:
        npm_cache.mkdir(mode=0o700)
    else:
        npm_cache = upgrade['root'] / 'npm-cache'
        require(npm_cache.is_dir() and not npm_cache.is_symlink(), 'candidate job cache differs')
        report['viteUpgrade'] = upgrade['binding']
    for name in ['user.npmrc', 'global.npmrc']: (output / name).write_bytes(b'')
    env = {'PATH': os.environ['PATH'], 'LANG': 'C', 'TZ': 'UTC', 'CI': 'true',
        'GITHUB_ACTIONS': 'true', 'GITHUB_RUN_ID': os.environ['GITHUB_RUN_ID'], 'RUNNER_TEMP': os.environ['RUNNER_TEMP'],
        'npm_config_cache': str(npm_cache), 'npm_config_userconfig': str(output / 'user.npmrc'),
        'npm_config_globalconfig': str(output / 'global.npmrc'), 'npm_config_fetch_retries': '0',
        'npm_config_fetch_timeout': '45000', 'npm_config_registry': 'https://registry.npmjs.org/'}
    def run(label, argv, cwd=web, timeout=120):
        row = run_bounded(argv, cwd, env, output, label, timeout=timeout); report['commands'].append(row)
        require(row['actualExit'] == 0 and row['outputComplete'], label + ' failed or incomplete')
        return row
    try:
        run('toolchain', ['node', '-p', 'JSON.stringify({node:process.version,versions:process.versions})'])
        report['toolchain'] = json.loads(read_input(output, 'streams/toolchain.stdout.txt'))
        require(re.fullmatch(r'v22\.\d+\.\d+', report['toolchain']['node']), 'unreviewed Node major')
        run('runtime-source-map-support-controls', ['node', '--test', '--test-reporter=tap',
            str(repo / 'tools/dependency-review/test-runtime-source-map-support.cjs'),
            str(repo / 'tools/dependency-review/test-runtime-stage.cjs')])
        run('npm-version', ['npm', '--version']); npm_version = read_input(output, 'streams/npm-version.stdout.txt').decode().strip()
        run('npm-script-policy', ['npm', 'config', 'get', 'ignore-scripts'])
        require(read_input(output, 'streams/npm-script-policy.stdout.txt').strip() == b'true', 'project install scripts must be disabled')
        run('application-install', ['npm', 'ci', '--ignore-scripts', '--include=dev', '--include=optional', '--no-audit', '--no-fund', '--no-progress'], timeout=180)
        inventory, cache = raw_profile(repo, web, output, env, run, npm_version)
        report['installedViteCompiledLabels'] = verify_vite_labels(web, inventory, plan['viteCompiledLabels'])
        report['rawInstalledProfile'] = {key: inventory[key] for key in ['installedPackageLocations', 'uniquePublications', 'regularSourceFiles', 'compressedSourceBytes', 'expandedSourceBytes']}
        report['rawSourceInventory'] = pin((output / 'application-raw-profile-sources.json').read_bytes())
        report['npmCacheAPITool'] = {key: cache[key] for key in ['npmVersion', 'toolPins', 'API', 'cacheAPIIsNotIndependentNpmToolchainAuthentication']}
        run('runtime-installer-controls', ['node', '--test', '--test-reporter=tap', 'scripts/prepare-runtime.test.mjs'])
        run('application-runtime-prepare', ['npm', 'run', 'prepare:runtime'])
        run('application-runtime-check', ['node', 'scripts/prepare-runtime.mjs', '--check'])
        report['runtimePreparation'] = json.loads(read_input(output, 'streams/application-runtime-check.stdout.txt'))
        manifest_raw = read_input(web, VENDOR + '/manifest.json'); manifest = json.loads(manifest_raw)
        effective_profile(web, manifest)
        report['vendorManifest'] = pin(manifest_raw)
        for role, argv, extra in [
            ('source-map-controls', ['node', '--test', '--test-reporter=tap', 'scripts/source-map-controls.test.mjs'],
                {'ZNS_SOURCE_MAP_ROOT': str(web / 'node_modules/source-map-js'), 'ZNS_SOURCE_MAP_VERSION': '1.2.2'}),
            ('source-map-codegen', ['node', '--disallow-code-generation-from-strings', '--test', '--test-reporter=tap', 'scripts/source-map-codegen.test.mjs'],
                {'ZNS_SOURCE_MAP_ROOT': str(web / 'node_modules/source-map-js'), 'ZNS_SOURCE_MAP_VERSION': '1.2.2'}),
            ('vite-virtual-module-controls', ['node', '--experimental-vm-modules', '--test', '--test-reporter=tap', 'scripts/vite-virtual-module-controls.test.mjs'],
                {'ZNS_VITE_CONTROL_TMPDIR': str(output / 'vite-fixtures')})]:
            if 'ZNS_VITE_CONTROL_TMPDIR' in extra: Path(extra['ZNS_VITE_CONTROL_TMPDIR']).mkdir()
            row = run_bounded(argv, web, {**env, **extra}, output, role, timeout=60); report['commands'].append(row)
            require(row['actualExit'] == 0 and row['outputComplete'], role + ' failed or incomplete')
        run('browser-request-shapes', ['node', '--test', '--test-reporter=tap', str(repo / 'tools/dependency-review/test-browser-request-shapes.cjs')])
        publications = {location: inventory['sources'][row['selection']['integrity']]
            for location, row in inventory['installed'].items()}
        report['normalDistribution'], report['fixtureBuild'] = build_distributions(
            repo, web, output, plan, manifest, publications, run)
        distributions = {'normal': output / 'normal-dist', 'fixture': output / 'fixture-dist'}
        expected_distributions = {'normal': report['normalDistribution'], 'fixture': report['fixtureBuild']['distribution']}
        if upgrade is not None:
            require(upgrade['binding']['syntheticDeployment'] == report['fixtureBuild']['syntheticDeployment'],
                'candidate and baseline use different synthetic deployment bytes')
            distributions.update(upgrade['paths'])
            expected_distributions.update(upgrade['expected'])
        derivative = {'schema': 1, 'kind': 'REVIEWED_LOCAL_DERIVATIVE_PROFILE', 'baseProfile': 'candidate',
            'baseLockSha256': manifest['baseLockSha256'], 'sourceInventory': report['rawSourceInventory'],
            'publication': manifest['publication'], 'effectiveMembers': manifest['effectiveMembers'],
            **{key: manifest[key] for key in ['parserGuard', 'parserMap', 'mapperMap', 'probe', 'changeNotices', 'debuggerSamples']},
            'registryArtifactOrPublisherAuthenticationClaimed': False, 'originalRawSourceProfilesModified': False,
            'actualApplicationDependencyInputsAdopted': True, 'productionGate': 'NO_GO'}
        derivative_path = output / 'application-profile-source-binding.json'; write_json(derivative_path, derivative)
        mapper = read_regular(web, PACKAGE + MAPPER, 4 << 20); suffix = b'//# sourceMappingURL=mapperTab.js.map\n'
        require(mapper.endswith(suffix), 'effective mapper route differs')
        probe, review = runtime_probe(mapper[:-len(suffix)], manifest['bootstrapInspection'])
        require(review == manifest['probe'], 'application inspection copy differs')
        probe_path = new_file(output, 'application-mapper-probe.js', probe)
        browser_plan_raw = read_input(repo, 'tools/dependency-review/browser-inputs.json')
        selected = json.loads(browser_plan_raw)['profiles']['candidate']
        revisions = read_regular(web, 'node_modules/puppeteer-core/' + selected['revisionMember'], 65536)
        require(pin(revisions) == selected['revisionMemberPin'] and selected['version'].encode() in revisions, 'actual SDK browser revision differs')
        (output / 'browsers').mkdir(); (output / 'browser-evidence').mkdir(); temporary.mkdir(mode=0o700)
        browser = {'inputPlan': pin(browser_plan_raw), 'transport': {}}; report['browser'] = browser
        archive = output / 'browsers/candidate.zip'; browser_root = output / 'browsers/candidate'
        download_browser(selected, archive, browser['transport'])
        browser['extraction'] = extract_browser(archive, browser_root, selected)
        executable = browser_root / 'chrome'
        run('browser-version', [str(executable), '--version'], browser_root, 15)
        require(selected['version'].encode() in read_input(output, 'streams/browser-version.stdout.txt'), 'executed browser version differs')
        input_path = output / 'application-browser-input.json'
        write_json(input_path, {'schema': 1, 'profile': 'application', 'root': str(web.resolve(strict=True)), 'repo': str(repo),
            'inventory': str(output / 'application-raw-profile-sources.json'), 'changedSources': str(repo / 'tools/dependency-review/changed-publications.json'),
            'plan': str(repo / 'tools/dependency-review/node-consumer-plan.json'), 'resolver': str(repo / 'tools/dependency-review/node-consumer-resolve.mjs'),
            'executable': str(executable), 'executablePin': {key: selected['archiveReview']['filePins']['chrome'][key] for key in ['bytes', 'sha256']},
            'browserVersion': selected['version'], 'abi': str(repo / 'web/src/abi.ts'), 'output': str(output / 'browser-evidence'),
            'temporaryRoot': str(temporary), 'runId': os.environ['GITHUB_RUN_ID'],
            'distributions': {role: str(path) for role, path in distributions.items()},
            'derivation': str(derivative_path), 'derivationPin': pin(derivative_path.read_bytes()), 'mapperProbe': str(probe_path)})
        run('browser-application', ['node', '--max-old-space-size=512', '--experimental-import-meta-resolve',
            str(repo / 'tools/dependency-review/browser-worker.cjs'), str(input_path)], web, 240)
        worker = json.loads(read_input(output, 'streams/browser-application.stdout.txt')); browser['worker'] = worker
        require(worker['status'] == 'PAIRED_PROTOCOL_AND_SYNTHETIC_APPLICATION_CONTROLS_PASSED'
            and worker['actualApplicationDependencyInputsAdopted'] and worker['actualApplicationInstalledMembersChanged'] == 9
            and worker['sourceGuard']['sourceGuardViolations'] == 0, 'actual application browser scope differs')
        require(worker['coherentNativeNodeControls']['cases'] == 12 and worker['sessions'][0]['embeddedMapper']['bootstraps'] == 2,
            'actual native and embedded mapper scope differs')
        require(worker['nativeRuntimeSourceMapControls']['automaticallyLoadedParserMap']
            and worker['nativeRuntimeSourceMapControls']['mappedErrorStackVerified']
            and worker['sessions'][0]['embeddedMapper']['rows'][0]['devtoolsSourceMap']['mappedSourcesAndEmbeddedContentsVerified'] == 177,
            'actual Node and DevTools source-map consumption differs')
        require(set(worker['distributions']) == set(expected_distributions), 'browser distribution roles differ')
        for role, expected in expected_distributions.items():
            require(worker['distributions'][role] == {'files': expected['files'], 'bytes': expected['payloadBytes']},
                'browser-served distribution differs: ' + role)
        require(len(worker['sessions']) == 2 and all(row['processExit'] ==
            {'actualExit': 0, 'signal': None, 'disconnected': True} for row in worker['sessions']), 'browser parents did not exit cleanly')
        require(len(worker['screenshots']) == (12 if upgrade else 6), 'browser evidence image count differs')
        if upgrade is not None:
            for row in worker['sessions']:
                require([item['case'] for item in row['viteUpgrade']['application']] ==
                    [item['case'] for item in row['application']], 'candidate browser controls differ')
            report['viteUpgrade']['nativeBrowserApplicationScenariosPassed'] = 4
        for image in worker['screenshots']:
            require(pin(read_input(output, image['path'])) == {key: image[key] for key in ['bytes', 'sha256']}, 'application image differs')
        verify_inputs(repo, plan['inputPins']); effective_profile(web, manifest)
        require(shutil.disk_usage(output).free >= 10 << 30, 'application final free-space floor')
        report.update(status='APPLICATION_DEPENDENCY_INSTALL_AND_COHERENT_RUNTIME_QUALIFIED_FULL_D04_OPEN',
            actualApplicationDependencyInputsAdopted=True, actualApplicationInstalledEffectiveMembers=9,
            npmInstallCommands=1, thirdPartyInstallScriptsEnabled=False, compilerDownloadOrMapperRebuildPerformed=False,
            browserDownloads=1, actualSdkChromeSessions=2, embeddedMapperBootstraps=2,
            nativeNodeDirectCases=12, generatedBrowserDirectCases=12, screenshots=len(worker['screenshots']),
            priorReferenceRunsReusedAsCurrentRevisionQualification=False, fullD04OrProductionAcceptance=False,
            walletFundingSigningLiveChainReleaseOrDeploymentPerformed=False)
    except BaseException as error:
        report['failure'] = {'type': type(error).__name__, 'message': str(error)[:2048]}
        raise
    finally:
        write_json(output / 'report.json', report)
    print(json.dumps({'status': report['status'], 'commands': len(report['commands']), 'productionGate': 'NO_GO'}))
    reused = report['fixtureBuild']['verifiedReusedMembers']
    print(f"Baseline fixture reused {reused['regularMembers']:,} verified members ({reused['payloadBytes']:,} bytes).")
    if upgrade is not None:
        print('Vite 8 passed both application scenarios over CDP and BiDi using the same two Chrome sessions.')
        print('Both locked installs used the current job npm cache. The browser input was downloaded once.')


if __name__ == '__main__': main()
