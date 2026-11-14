"""Install one raw candidate profile, bind source bytes and exercise real Node APIs."""

import json
from pathlib import Path
import platform
import shutil

from changed_source_installation import verify_selected_installation
from lock_review import read_input, require
from openzeppelin_candidate import run_bounded, sha, write_json
from profile_sources import pin, read_regular, select_profile, verify_profile


def permission_args(paths):
    return ['--experimental-permission', *['--allow-fs-read=' + str(path) for path in sorted(set(paths))]]


def qualify_consumers(repo, web, parent_root, output, env, commands, source_plan, execution):
    execution.update(status='PREPARING_RAW_CANDIDATE_PROFILE', candidateInstallationPerformed=False,
        npmToolCodeExecuted=False, candidateConsumerCodeExecuted=False, baselineConsumerCodeExecuted=False)
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64' and platform.libc_ver()[0] == 'glibc', 'Node consumer lane requires the reviewed Linux x64 glibc profile')
    profile = {'os': 'linux', 'cpu': 'x64', 'libc': 'glibc'}
    plan_raw = read_input(repo, 'tools/dependency-review/node-consumer-plan.json'); plan = json.loads(plan_raw)
    require(plan['schema'] == 1 and len(plan['callers']) == 2, 'Node consumer plan scope')
    for caller in plan['callers']: require(pin(read_input(repo, caller['path'])) == caller['sourcePin'], 'actual browser caller source differs')
    baseline_lock = read_input(web, 'package-lock.json'); candidate_lock = read_input(parent_root, 'package-lock.json')
    require(sha(baseline_lock) == plan['profiles']['baseline']['lockSha256'] and sha(candidate_lock) == plan['profiles']['candidate']['lockSha256'], 'consumer profile lock differs')
    package_before = read_input(parent_root, 'package.json')
    require(not (parent_root / 'node_modules').exists(), 'candidate profile was already installed')
    def run(label, argv, cwd, timeout):
        row = run_bounded(argv, cwd, env, output, label, timeout=timeout); commands.append(row); execution['lastCommand'] = row
        require(row['actualExit'] == 0 and row['outputComplete'], label + ' failed or incomplete')
        return row
    execution.update(status='CANDIDATE_PROFILE_INSTALL_ATTEMPTED', candidateInstallationPerformed=None, npmToolCodeExecuted=None)
    run('candidate-profile-install', ['npm', 'ci', '--ignore-scripts', '--include=dev', '--include=optional', '--no-audit', '--no-fund', '--no-progress'], parent_root, 180)
    execution.update(status='CANDIDATE_PROFILE_INSTALLED_SOURCES_NOT_YET_QUALIFIED', candidateInstallationPerformed=True, npmToolCodeExecuted=True)
    require(read_input(parent_root, 'package.json') == package_before and read_input(parent_root, 'package-lock.json') == candidate_lock, 'candidate installation changed review-only manifest or lock')
    rows = json.loads(candidate_lock)['packages']; installed = {location for location in rows if location and (parent_root / location).exists()}
    classified = select_profile(candidate_lock, installed, profile)
    npm_bin = shutil.which('npm', path=env['PATH']); require(npm_bin is not None, 'selected npm executable absent')
    npm_root = Path(npm_bin).resolve(strict=True).parent.parent
    npm_manifest = json.loads(read_regular(npm_root, 'package.json', 64 << 10)); npm_version = npm_manifest['version']
    require(npm_manifest['name'] == 'npm' and npm_version == read_input(output, 'streams/parent-package-toolchain.stdout.txt').decode().strip(), 'npm root or version differs from observed toolchain')
    cache = Path(env['npm_config_cache']) / '_cacache'
    require(cache.is_dir() and not cache.is_symlink(), 'current-job cache absent or linked')
    index_input = output / 'profile-cache-input.json'
    write_json(index_input, {'schema': 1, 'npmRoot': str(npm_root), 'cacheRoot': str(cache), 'npmVersion': npm_version,
        'integrities': sorted({row['selection']['integrity'] for row in classified['selected'].values()})})
    execution['status'] = 'CURRENT_JOB_CACHE_API_READ_ATTEMPTED'
    run('candidate-profile-cache-index', ['node', *permission_args([repo / 'tools/dependency-review', npm_root, cache, index_input]),
        str(repo / 'tools/dependency-review/npm-cache-index.cjs'), str(index_input)], parent_root, 45)
    cache_result = json.loads(read_input(output, 'streams/candidate-profile-cache-index.stdout.txt'))
    require(cache_result['npmVersion'] == npm_version and not cache_result['historicalCacheFallbackOrAdditionalTransport']
        and not cache_result['cacheVerifyCleanOrMutationRequested'], 'cache API scope differs')
    budgets_raw = read_input(repo, 'tools/dependency-review/profile-source-budgets.json'); budgets = json.loads(budgets_raw)
    inventory = verify_profile(parent_root, candidate_lock, cache, cache_result['index'], profile, budgets)
    inventory['sourceBudgetPlanPin'] = pin(budgets_raw)
    inventory_path = output / 'candidate-profile-sources.json'; write_json(inventory_path, inventory)
    require(len(inventory_path.read_bytes()) <= 16 << 20, 'profile source inventory artifact budget')
    candidate_changed = verify_selected_installation(parent_root, candidate_lock, source_plan, 'candidate')
    execution.update(status='PROFILE_SOURCES_QUALIFIED_CONSUMERS_NOT_YET_RUN', candidateSourceMembersVerified=True)
    results = {}
    for role, root in [('baseline', web), ('candidate', parent_root)]:
        input_path = output / ('node-consumer-' + role + '-input.json')
        write_json(input_path, {'schema': 1, 'profile': role, 'root': str(root.resolve(strict=True)), 'repo': str(repo),
            'inventory': str(inventory_path), 'changedSources': str(repo / 'tools/dependency-review/changed-publications.json'),
            'plan': str(repo / 'tools/dependency-review/node-consumer-plan.json'),
            'resolver': str(repo / 'tools/dependency-review/node-consumer-resolve.mjs')})
        execution.update(status=role.upper() + '_CONSUMER_EXECUTION_ATTEMPTED', **{role + 'ConsumerCodeExecuted': None})
        allowed = [root, repo / 'tools/dependency-review', repo / 'web/scripts', inventory_path, input_path]
        run('node-consumer-' + role, ['node', '--max-old-space-size=256', '--experimental-import-meta-resolve',
            *permission_args(allowed), str(repo / 'tools/dependency-review/node-consumer-worker.cjs'), str(input_path)], root, 60)
        result = json.loads(read_input(output, 'streams/node-consumer-' + role + '.stdout.txt'))
        require(result['status'] == 'ACTUAL_NODE_ENTRIES_AND_TRACKED_CALLER_DEFAULT_ARGS_QUALIFIED_BROWSER_NOT_RUN'
            and result['profile'] == role and result['puppeteerVersion'] == plan['profiles'][role]['puppeteer']
            and result['sourceGuardRefusals'] == 4 and result['packageAPIObservations'] == 3 and result['trackedCallerOptionCases'] == 2,
            'Node consumer result scope differs')
        require(result['planPin'] == pin(plan_raw) and result['nodePlatform'] == 'linux' and result['nodeArchitecture'] == 'x64'
            and result['libc'] == 'glibc' and result['actualInstalledPackageCodeExecuted'] and result['actualNodeResolutionPreserved'], 'actual Node execution or source binding differs')
        require(result['sourceGuardViolations'] == result['requestedNetworkOrProcessOperations'] == 0
            and not result['browserOrCDPOrProtocolHandlersOrApplicationScriptsExecuted']
            and not result['fundedVerificationOrWalletSigningOrLiveChainExecuted'] and not result['proposalAdopted'], 'Node consumer boundary differs')
        results[role] = result
        execution.update(status=role.upper() + '_CONSUMER_QUALIFIED', **{role + 'ConsumerCodeExecuted': True})
    changes = []
    for old, new in zip(results['baseline']['options'], results['candidate']['options']):
        require(old['path'] == new['path'] and old['options'] == new['options'], 'actual caller options differ across profiles')
        changes.append({'path': old['path'], 'addedArguments': [value for value in new['argv'] if value not in old['argv']],
            'removedArguments': [value for value in old['argv'] if value not in new['argv']],
            'exactOrderingEqual': old['argv'] == new['argv'], 'browserBehaviorOrFlagChangesAccepted': False})
    require(read_input(parent_root, 'package-lock.json') == candidate_lock and read_input(web, 'package-lock.json') == baseline_lock,
        'consumer controls changed an application or candidate lock')
    for caller in plan['callers']: require(pin(read_input(repo, caller['path'])) == caller['sourcePin'], 'consumer controls changed a tracked caller')
    execution['status'] = 'ACTUAL_NODE_ENTRIES_AND_TRACKED_OPTIONS_QUALIFIED_APPLICATION_BROWSER_OPEN'
    return {'schema': 1, 'status': execution['status'], 'planPin': pin(plan_raw), 'profile': profile,
        'profileSourceInventory': {'path': 'candidate-profile-sources.json', **pin(inventory_path.read_bytes())},
        'sourceBudgetPlanPin': pin(budgets_raw), 'sourceSpecificBudgetsApplied': inventory['sourceSpecificBudgetsApplied'],
        'candidateInstalledPackages': inventory['installedPackageLocations'], 'excludedLockRows': len(inventory['excluded']),
        'uniqueCandidatePublications': inventory['uniquePublications'], 'regularCandidateSourceFiles': inventory['regularSourceFiles'],
        'rawCacheSourceBytes': inventory['compressedSourceBytes'], 'currentJobCacheAPITool': {k: cache_result[k] for k in ('npmVersion', 'toolPins', 'API', 'cacheAPIIsNotIndependentNpmToolchainAuthentication')},
        'candidateChangedPublications': candidate_changed, 'profiles': results, 'argumentDifferences': changes,
        'cacheVerificationAdditionalArchiveRequests': 0, 'baselineAdditionalInstallations': 0,
        'candidateInstallScriptsEnabled': False, 'rawPublishedCandidateUsed': True,
        'derivedGuardOrRebuiltMapperInstalledIntoProfile': False,
        'applicationInputsChanged': False, 'actualBrowserOrCDPHandlersExecuted': False,
        'unfundedBrowserOrFullGraphPlatformPublisherLegalOwnerAcceptance': False, 'proposalAdopted': False, 'productionGate': 'NO_GO'}
