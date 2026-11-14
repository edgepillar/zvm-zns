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


def raw_profile(repo, web, output, env, run, npm_version):
    lock_raw = read_input(web, 'package-lock.json'); rows = json.loads(lock_raw)['packages']
    installed = {name for name in rows if name and (web / name).exists()}
    profile = {'os': 'linux', 'cpu': 'x64', 'libc': 'glibc'}
    selected = select_profile(lock_raw, installed, profile)['selected']
    npm_bin = shutil.which('npm', path=env['PATH']); require(npm_bin, 'npm executable absent')
    npm_root = Path(npm_bin).resolve(strict=True).parent.parent
    manifest = json.loads(read_regular(npm_root, 'package.json', 65536))
    require(manifest['name'] == 'npm' and manifest['version'] == npm_version, 'npm root/version differs')
    cache = Path(env['npm_config_cache']) / '_cacache'
    require(cache.is_dir() and not cache.is_symlink(), 'current-job npm cache absent or linked')
    request = output / 'cache-input.json'
    write_json(request, {'schema': 1, 'npmRoot': str(npm_root), 'cacheRoot': str(cache), 'npmVersion': npm_version,
        'integrities': sorted({row['selection']['integrity'] for row in selected.values()})})
    run('application-cache-index', ['node', *permission_args([repo / 'tools/dependency-review', npm_root, cache, request]),
        str(repo / 'tools/dependency-review/npm-cache-index.cjs'), str(request)], web, 45)
    result = json.loads(read_input(output, 'streams/application-cache-index.stdout.txt'))
    require(result['npmVersion'] == npm_version and not result['historicalCacheFallbackOrAdditionalTransport']
        and not result['cacheVerifyCleanOrMutationRequested'], 'npm cache API evidence scope')
    budgets_raw = read_input(repo, 'tools/dependency-review/profile-source-budgets.json')
    inventory = verify_profile(web, lock_raw, cache, result['index'], profile, json.loads(budgets_raw))
    inventory['sourceBudgetPlanPin'] = pin(budgets_raw)
    write_json(output / 'application-raw-profile-sources.json', inventory)
    return inventory, result


def effective_profile(web, manifest):
    require(pin(read_regular(web, 'package-lock.json', 2 << 20))['sha256'] == manifest['baseLockSha256'], 'effective lock differs')
    require(pin(read_regular(web, PACKAGE + 'package.json', 1 << 20)) == manifest['originalPackageManifest'], 'effective package manifest differs')
    for name, row in manifest['effectiveMembers'].items():
        require(pin(read_regular(web, name, 16 << 20)) == row['effective'], 'effective application runtime differs')


def stage_fixture(repo, web, output, inventory, manifest, run):
    source_raw = read_input(repo, 'tools/dependency-review/browser-app-sources.json'); source = json.loads(source_raw)
    root = output / 'application-fixture' / 'web'; count = size = 0; sources = []
    require(not root.exists() and not root.is_symlink(), 'application fixture must be new')
    for row in validate_source_plan(source):
        provider = repo if row['sourceRepository'] == 'main' else repo / 'zvm-core'
        raw = read_input(provider, row['sourcePath']); require(pin(raw) == row['pin'], 'fixture source differs')
        dest = row['destinationRelativeToOutput']
        dest = ('application-fixture/web/' + dest.removeprefix('candidate-web-parent/')
            if dest.startswith('candidate-web-parent/') else 'application-fixture/' + dest)
        new_file(output, dest, raw); sources.append({'sourcePath': row['sourcePath'], 'destination': dest, 'pin': row['pin']})
    # Only explicit current source files needed for preparation/build are copied.
    extra = ['package.json', 'package-lock.json', '.npmrc', 'scripts/prepare-runtime.mjs',
        VENDOR + '/manifest.json', VENDOR + '/NOTICE.md', *[VENDOR + '/payload/' + name for name in manifest['payloads']]]
    extras = {}
    for name in extra:
        raw = read_input(web, name) if not name.endswith('.map') else read_regular(web, name, 16 << 20)
        new_file(root, name, raw); extras[name] = pin(raw)
    lock = json.loads(read_input(web, 'package-lock.json'))['packages']; packages = []
    for location in sorted(inventory['installed']):
        publication = inventory['sources'][lock[location]['integrity']]
        for member, original in publication['filePins'].items():
            name = location + '/' + member; overlay = manifest['effectiveMembers'].get(name)
            expected = overlay['effective'] if overlay else original
            raw = read_regular(web, name, 16 << 20); require(pin(raw) == expected, 'fixture installed member differs')
            new_file(root, name, raw, bool((web / name).stat().st_mode & 0o111)); count += 1; size += len(raw)
            require(count <= 32768 and size <= 256 << 20, 'fixture portable package budget')
        packages.append({'location': location, 'selection': publication['selection'], 'publishedMembers': len(publication['filePins'])})
    for name, row in manifest['effectiveMembers'].items():
        if row['original'] is not None: continue
        raw = read_regular(web, name, 16 << 20); require(pin(raw) == row['effective'], 'fixture added member differs')
        new_file(root, name, raw); count += 1; size += len(raw)
    require(count <= 32768 and size <= 256 << 20, 'fixture final portable package budget')
    fixture = (json.dumps(source['syntheticDeploymentFixture'], sort_keys=True, indent=2) + '\n').encode()
    new_file(output, 'application-fixture/deployments/browser-fixture.json', fixture)
    for label, argv in [
        ('fixture-runtime-check', ['node', 'scripts/prepare-runtime.mjs', '--check']),
        ('fixture-types', ['node', 'node_modules/vue-tsc/bin/vue-tsc.js', '--noEmit']),
        ('fixture-vite', ['node', 'node_modules/vite/bin/vite.js', 'build'])]:
        run(label, argv, root, 120)
    return {'schema': 1, 'sourcePlan': pin(source_raw), 'sources': sources, 'extraBuildInputs': extras,
        'packageLocations': len(packages), 'packages': packages, 'portableRegularMembers': count,
        'portablePackageBytes': size, 'syntheticDeployment': pin(fixture), 'distribution': dist_inventory(root / 'dist'),
        'fixtureNpmScriptExecuted': False, 'explicitEquivalentPreparationAndCompilerStepsExecuted': True,
        'hardLinksAliasesOrOperatorDataUsed': False, 'productionGate': 'NO_GO'}, root / 'dist'


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True); args = parser.parse_args()
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
    (output / 'npm-cache').mkdir(mode=0o700)
    for name in ['user.npmrc', 'global.npmrc']: (output / name).write_bytes(b'')
    env = {'PATH': os.environ['PATH'], 'LANG': 'C', 'TZ': 'UTC', 'CI': 'true',
        'GITHUB_ACTIONS': 'true', 'GITHUB_RUN_ID': os.environ['GITHUB_RUN_ID'], 'RUNNER_TEMP': os.environ['RUNNER_TEMP'],
        'npm_config_cache': str(output / 'npm-cache'), 'npm_config_userconfig': str(output / 'user.npmrc'),
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
            str(repo / 'tools/dependency-review/test-runtime-source-map-support.cjs')])
        run('npm-version', ['npm', '--version']); npm_version = read_input(output, 'streams/npm-version.stdout.txt').decode().strip()
        run('npm-script-policy', ['npm', 'config', 'get', 'ignore-scripts'])
        require(read_input(output, 'streams/npm-script-policy.stdout.txt').strip() == b'true', 'project install scripts must be disabled')
        run('application-install', ['npm', 'ci', '--ignore-scripts', '--include=dev', '--include=optional', '--no-audit', '--no-fund', '--no-progress'], timeout=180)
        inventory, cache = raw_profile(repo, web, output, env, run, npm_version)
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
        package = json.loads(read_input(web, 'package.json'))
        require(package['scripts']['build'] == 'node scripts/prepare-runtime.mjs && vue-tsc --noEmit && vite build'
            and not any(key in package['scripts'] for key in ['prebuild', 'postbuild']), 'application build command differs')
        run('application-build', ['npm', 'run', 'build'])
        report['normalDistribution'] = dist_inventory(web / 'dist')
        for notice in plan['retainedStaticNotices']:
            require(report['normalDistribution']['files'][notice['distPath']] == notice['pin'], 'static notice differs')
        normal = output / 'normal-dist'; (web / 'dist').rename(normal)
        fixture, fixture_dist = stage_fixture(repo, web, output, inventory, manifest, run); report['fixtureBuild'] = fixture
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
            'temporaryRoot': str(temporary),
            'runId': os.environ['GITHUB_RUN_ID'], 'distributions': {'normal': str(normal), 'fixture': str(fixture_dist)},
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
        for image in worker['screenshots']:
            require(pin(read_input(output, image['path'])) == {key: image[key] for key in ['bytes', 'sha256']}, 'application image differs')
        verify_inputs(repo, plan['inputPins']); effective_profile(web, manifest)
        require(shutil.disk_usage(output).free >= 10 << 30, 'application final free-space floor')
        report.update(status='APPLICATION_DEPENDENCY_INSTALL_AND_COHERENT_RUNTIME_QUALIFIED_FULL_D04_OPEN',
            actualApplicationDependencyInputsAdopted=True, actualApplicationInstalledEffectiveMembers=9,
            npmInstallCommands=1, thirdPartyInstallScriptsEnabled=False, compilerDownloadOrMapperRebuildPerformed=False,
            browserDownloads=1, actualSdkChromeSessions=2, embeddedMapperBootstraps=2,
            nativeNodeDirectCases=12, generatedBrowserDirectCases=12, screenshots=6,
            priorReferenceRunsReusedAsCurrentRevisionQualification=False, fullD04OrProductionAcceptance=False,
            walletFundingSigningLiveChainReleaseOrDeploymentPerformed=False)
    except BaseException as error:
        report['failure'] = {'type': type(error).__name__, 'message': str(error)[:2048]}
        raise
    finally:
        write_json(output / 'report.json', report)
    print(json.dumps({'status': report['status'], 'commands': len(report['commands']), 'productionGate': 'NO_GO'}))


if __name__ == '__main__': main()
