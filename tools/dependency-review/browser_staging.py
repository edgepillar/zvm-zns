"""Hosted-only regular source copies and read-only-fixture application builds."""

import json
import os
from pathlib import PurePosixPath
import platform
import shutil
import stat

from lock_review import read_input, require
from openzeppelin_candidate import run_bounded, sha, write_json
from profile_sources import read_regular, select_profile, pin


def validate_source_plan(plan):
    require(plan['schema'] == 1 and plan['trackedDeploymentRecords'] == 0
        and plan['exampleEnvironmentOnly'] is True and plan['fundedVerificationScriptIncluded'] is False,
        'browser app source scope')
    files = plan['files']
    require(sha(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()) == plan['fileListSha256'], 'browser app source list pin')
    seen = set()
    for row in files:
        name = row['sourcePath']; source = row['sourceRepository']; destination = row['destinationRelativeToOutput']
        path = PurePosixPath(name)
        require(path.as_posix() == name and not path.is_absolute() and '..' not in path.parts and '\\' not in name,
            'browser first-party source path')
        if source == 'main':
            allowed = name.startswith(('web/src/', 'web/public/')) or name in (
                '.env.example', 'web/index.html', 'web/vite.config.ts', 'web/tsconfig.json', 'web/env.d.ts')
            expected = '.env' if name == '.env.example' else 'candidate-web-parent/' + name.removeprefix('web/')
        else:
            require(source == 'core', 'browser source repository')
            allowed = name.startswith('web/src/'); expected = 'zvm-core/' + name
        require(allowed and destination == expected and destination not in seen, 'browser first-party source/destination scope')
        seen.add(destination)
        require(row['gitMode'] == '100644' and row['pin']['bytes'] >= 0, 'browser first-party regular source mode')
    require(len(files) == plan['sourceFiles'] == 71 and sum(row['pin']['bytes'] for row in files) == plan['sourceBytes'] == 471481,
        'browser first-party source packet budget')
    return files


def hosted_only():
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64'
        and os.environ.get('GITHUB_RUN_ID', '').isdigit(), 'browser fixtures require the hosted Linux x64 lane')


def new_file(root, relative, raw, executable=False):
    path = PurePosixPath(relative)
    require(path.as_posix() == relative and not path.is_absolute() and '..' not in path.parts and '\\' not in relative,
        'browser stage destination')
    parent = root
    for part in path.parts[:-1]:
        parent /= part
        if not parent.exists(): parent.mkdir(mode=0o700)
        require(parent.is_dir() and not parent.is_symlink(), 'browser stage linked ancestor')
    target = root / relative
    require(not target.exists() and not target.is_symlink(), 'browser stage destination already present')
    with target.open('xb') as output: output.write(raw)
    target.chmod(0o755 if executable else 0o644)
    return target


def copy_sources(repo, output, plan, baseline=False):
    files = validate_source_plan(plan)
    total = 0; records = []
    for row in files:
        require(row['sourceRepository'] in ('main', 'core'), 'browser source repository')
        root = repo if row['sourceRepository'] == 'main' else repo / 'zvm-core'
        raw = read_input(root, row['sourcePath']); require(pin(raw) == row['pin'], 'browser app source bytes differ')
        destination = row['destinationRelativeToOutput']
        if destination == '.env': require(row['sourcePath'] == '.env.example', 'browser fixture environment source')
        if baseline:
            if destination.startswith('candidate-web-parent/'):
                destination = 'baseline-browser-app/web/' + destination.removeprefix('candidate-web-parent/')
            else: destination = 'baseline-browser-app/' + destination
        new_file(output, destination, raw)
        total += len(raw); records.append({'sourceRepository': row['sourceRepository'], 'sourcePath': row['sourcePath'],
            'destination': destination, 'pin': row['pin']})
    require(len(records) == plan['sourceFiles'] == 71 and total == plan['sourceBytes'] == 471481, 'browser app source copy budget')
    return {'files': len(records), 'bytes': total, 'records': records, 'regularPortableCopiesOnly': True,
        'hardLinksAliasesOrOperatorDataUsed': False}


def copy_baseline_packages(web, destination, inventory, changed):
    lock_raw = read_input(web, 'package-lock.json'); rows = json.loads(lock_raw)['packages']
    installed = {name for name in rows if name and (web / name).exists()}
    classified = select_profile(lock_raw, installed, {'os': 'linux', 'cpu': 'x64', 'libc': 'glibc'})
    sources = dict(inventory['sources']); sources.update(changed['publications'])
    count = total = 0; packages = []
    for location, entry in sorted(classified['selected'].items()):
        selected = entry['selection']; publication = sources.get(selected['integrity'])
        require(publication is not None and publication['selection'] == selected, 'baseline fixture publication absent')
        for name, expected in publication['filePins'].items():
            raw = read_regular(web, location + '/' + name, 16 << 20)
            require(pin(raw) == expected, 'baseline fixture package member differs')
            mode = (web / location / name).stat().st_mode
            require(stat.S_ISREG(mode), 'baseline fixture package type')
            total += len(raw); count += 1
            require(total <= 256 << 20 and count <= 32768, 'baseline fixture portable copy budget')
            new_file(destination, location + '/' + name, raw, bool(mode & 0o111))
        packages.append({'location': location, 'selection': selected, 'regularFiles': len(publication['filePins'])})
    return {'packageLocations': len(packages), 'regularFiles': count, 'bytes': total, 'packages': packages,
        'completePublishedRegularMembersCopiedAndVerified': True, 'npmGeneratedExtrasOrBinLinksCopied': False,
        'hardLinksOrSymbolicAliasesUsed': False, 'copyBudgetBytes': 256 << 20}


def qualify_application_builds(repo, web, candidate, output, env, commands, source_plan, execution):
    hosted_only()
    require(shutil.disk_usage(output).free >= (10 << 30) + (3 << 30), 'browser lane free-space floor and allocation budget')
    plan_raw = read_input(repo, 'tools/dependency-review/browser-app-sources.json'); plan = json.loads(plan_raw)
    require(not (candidate / 'src').exists(), 'candidate app source already staged')
    execution.update(status='APPLICATION_SOURCE_STAGING_ATTEMPTED', candidateBuildExecuted=False, syntheticBuildsExecuted=False)
    candidate_copy = copy_sources(repo, output, plan)
    require(read_input(output, '.env') == read_input(repo, '.env.example'), 'candidate app environment differs')
    baseline_root = output / 'baseline-browser-app' / 'web'
    baseline_copy = copy_sources(repo, output, plan, baseline=True)
    for name in ['package.json', 'package-lock.json']:
        new_file(baseline_root, name, read_input(web, name))
    inventory = json.loads(read_input(output, 'candidate-profile-sources.json'))
    package_copy = copy_baseline_packages(web, baseline_root, inventory, source_plan)
    def run(label, root):
        package = json.loads(read_input(root, 'package.json'))
        require(package['scripts']['build'] == 'vue-tsc --noEmit && vite build' and not any(name in package['scripts'] for name in ('prebuild', 'postbuild')),
            'browser application build script scope')
        for suffix, argv in [('types', ['node', 'node_modules/vue-tsc/bin/vue-tsc.js', '--noEmit']),
                ('vite', ['node', 'node_modules/vite/bin/vite.js', 'build'])]:
            row = run_bounded(argv, root, env, output, label + '-' + suffix, timeout=120)
            commands.append(row); execution['lastCommand'] = row
            require(row['actualExit'] == 0 and row['outputComplete'], label + '-' + suffix + ' failed or incomplete')
    execution['status'] = 'CANDIDATE_NORMAL_APPLICATION_BUILD_ATTEMPTED'
    run('candidate-app-build', candidate); execution['candidateBuildExecuted'] = True
    from web_patches import dist_inventory
    normal_inventory = dist_inventory(candidate / 'dist')
    normal_root = output / 'candidate-normal-dist'; require(not normal_root.exists(), 'candidate normal distribution already present')
    (candidate / 'dist').rename(normal_root)
    fixture = plan['syntheticDeploymentFixture']
    require(fixture['chainId'] == 7340469 and fixture['terms']['network'] == 'isolated-browser-fixture'
        and fixture['startBlock'] == 1 and fixture['launchTime'] == 1700000000, 'synthetic deployment scope')
    fixture_raw = (json.dumps(fixture, sort_keys=True, indent=2) + '\n').encode()
    new_file(output, 'deployments/browser-fixture.json', fixture_raw)
    new_file(output, 'baseline-browser-app/deployments/browser-fixture.json', fixture_raw)
    execution['status'] = 'EXPLICIT_SYNTHETIC_APPLICATION_BUILDS_ATTEMPTED'
    run('baseline-fixture-app-build', baseline_root)
    run('candidate-fixture-app-build', candidate); execution['syntheticBuildsExecuted'] = True
    baseline_fixture = dist_inventory(baseline_root / 'dist'); candidate_fixture = dist_inventory(candidate / 'dist')
    for row in plan['files']:
        root = repo if row['sourceRepository'] == 'main' else repo / 'zvm-core'
        require(pin(read_input(root, row['sourcePath'])) == row['pin'], 'browser staging changed original source')
    execution['status'] = 'NORMAL_CANDIDATE_AND_EXPLICIT_SYNTHETIC_BUILDS_COMPLETE_BROWSER_NOT_YET_RUN'
    result = {'schema': 1, 'sourcePlanPin': pin(plan_raw), 'candidateSourceCopies': candidate_copy,
        'baselineFixtureSourceCopies': baseline_copy, 'baselinePublishedPackageCopies': package_copy,
        'candidateNormalDistribution': normal_inventory, 'baselineFixtureDistribution': baseline_fixture,
        'candidateFixtureDistribution': candidate_fixture, 'syntheticDeploymentPin': pin(fixture_raw),
        'trackedDeploymentRecords': 0, 'operatorDeploymentOrWalletDataAdopted': False,
        'originalFirstPartyInputsVerifiedUnchanged': True, 'candidateApplicationMigrationAdopted': False,
        'fixtureBuildIsNotDeploymentArtifact': True, 'productionGate': 'NO_GO'}
    write_json(output / 'browser-app-builds.json', result)
    return result, {'baseline': {'normal': web / 'dist', 'fixture': baseline_root / 'dist'},
        'candidate': {'normal': normal_root, 'fixture': candidate / 'dist'}}
