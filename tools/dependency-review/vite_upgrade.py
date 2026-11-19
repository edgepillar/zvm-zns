"""Review the pinned Vite upgrade in a fresh hosted application checkout."""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

from application_runtime import VENDOR, build_distributions, current_cache_index, installed_vite_labels, verify_inputs
from browser_staging import hosted_only
from compiled_labels import canonical_sha256
from lock_review import NAME, ReviewError, decode, dependencies, read_input, require, resolve
from openzeppelin_candidate import encoded, run_bounded, write_json
from profile_sources import inspect_profile_archive, pin, read_regular
from proposal_delta import lock_delta, package_table, preserve_platform_selectors, registry_identity

LOCATION = 'node_modules/vite'
PUBLICATION = {'name': 'vite', 'version': '8.3.8',
    'resolved': 'https://registry.npmjs.org/vite/-/vite-8.3.8.tgz',
    'integrity': 'sha512-LzOn3h9rG/0vhLdXrV4yJ4QFA9eEoqCl+Yx+kGJd7aB9w6nfNgVHKSYwLPZUHrz4ZGa+t+kXjV9itvcHDLQouA=='}
# packages/vite/LICENSE.md at the verified v8.3.8 release commit b39e6e63.
RELEASE_NOTICE = {'bytes': 98196, 'sha256': 'a22152baa1aef74402443008e767e7c689a524c0909d19b0431d97f5ab066a13'}
ROLLDOWN_LINUX_BINDINGS = {'@rolldown/binding-linux-x64-gnu', '@rolldown/binding-linux-x64-musl'}
PRIOR_LABELS = [('follow-redirects', '1.15.11'), ('nanoid', '5.1.6'),
    ('postcss-selector-parser', '7.1.0'), ('ws', '8.18.3')]
INSTALL_FLAGS = ['--ignore-scripts', '--include=dev', '--include=optional', '--no-audit', '--no-fund', '--no-progress']


def dependency_locations(rows, start):
    visited, pending = set(), [start]
    while pending:
        location = pending.pop()
        if location in visited:
            continue
        require(location in rows, 'reviewed dependency location is missing: ' + location)
        visited.add(location)
        for scope in ('dependencies', 'optionalDependencies'):
            for name in dependencies(rows[location], scope):
                target = resolve(location, name, rows)
                require(target is not None or scope == 'optionalDependencies', 'required dependency is missing: ' + name)
                if target is not None:
                    pending.append(target)
    return visited


def candidate_lock(baseline_raw, generated_raw):
    effective_raw, selectors = preserve_platform_selectors(baseline_raw, generated_raw)
    _, before = package_table(baseline_raw)
    _, after = package_table(effective_raw)
    require(len(after) <= 512, 'candidate lock location budget')
    require(registry_identity(LOCATION, after.get(LOCATION, {})) == PUBLICATION, 'candidate Vite publication differs')
    require(after[''] == {**before[''], 'devDependencies': {**before['']['devDependencies'],
        'vite': PUBLICATION['version']}}, 'candidate root declarations differ beyond Vite')
    old_bundled = {name: row for name, row in before.items() if row.get('inBundle') is True}
    new_bundled = {name: row for name, row in after.items() if row.get('inBundle') is True}
    require(old_bundled == new_bundled, 'reviewed bundled rows changed')
    for location, row in after.items():
        if location and row.get('inBundle') is not True:
            registry_identity(location, row)

    unchanged_runtime = set()
    for root in ('node_modules/puppeteer-core', 'node_modules/zod'):
        members = dependency_locations(before, root)
        require(members == dependency_locations(after, root) and all(before[name] == after[name] for name in members),
            'reviewed runtime dependency graph changed: ' + root)
        unchanged_runtime.update(members)

    vite_graph = dependency_locations(before, LOCATION) | dependency_locations(after, LOCATION)
    for name in sorted((set(before) | set(after)) - vite_graph - {''}):
        require(before.get(name) == after.get(name), 'dependency outside the Vite graph changed: ' + name)
    delta = lock_delta(baseline_raw, effective_raw)
    require(not delta['topLevelChanges'] and not delta['sourceKindChanges'], 'candidate lock identity or source kind changed')
    return effective_raw, {'lockDelta': delta, 'selectorCarry': selectors,
        'unchangedRuntimeLocations': sorted(unchanged_runtime), 'reviewedViteGraphLocations': sorted(vite_graph)}


def inspect_vite(web, cache, cache_row, lock_row):
    raw = read_regular(cache, cache_row['cacheRelative'], 2 << 20)
    require(len(raw) == cache_row['bytes'], 'cached Vite archive length differs')
    archive = inspect_profile_archive(raw, PUBLICATION, lock_row, expanded_limit=4 << 20, member_limit=64)
    require(len(archive['filePins']) == 37 and archive['regularPayloadBytes'] == 2405422,
        'published Vite file count or payload differs')
    require(archive['filePins'].get('LICENSE.md') == RELEASE_NOTICE, 'Vite archive notice differs from the release source')
    for name, expected in archive['filePins'].items():
        require(pin(read_regular(web, LOCATION + '/' + name, 4 << 20)) == expected, 'installed Vite member differs: ' + name)
    require(archive['noticeCandidates'] and (web / 'node_modules/.bin/vite').resolve(strict=True) == web / LOCATION / 'bin/vite.js',
        'published Vite notices or selected executable differ')
    return archive, installed_vite_labels(web, archive)


def changed_publications(rows, delta):
    locations = set(delta['addedLocations']) | {row['location'] for row in delta['publicationChanges']}
    require(LOCATION in locations and len(locations) <= 64, 'candidate changed publication budget')
    return {location: registry_identity(location, rows[location]) for location in sorted(locations)}


def installed_changes(web, rows, delta):
    installed, absent = {}, []
    for location, selection in changed_publications(rows, delta).items():
        path = web / location
        if path.exists() or path.is_symlink():
            require(path.is_dir() and not path.is_symlink(), 'candidate package location differs: ' + location)
            installed[location] = selection
        else:
            require(rows[location].get('optional') is True, 'candidate required publication is missing: ' + location)
            absent.append(location)
    require(LOCATION in installed, 'candidate Vite is missing')
    return installed, absent


def review_installed_publications(web, rows, installed, cache, index, vite_archive):
    archives = {PUBLICATION['integrity']: vite_archive}
    records = {}
    for location, selection in installed.items():
        integrity = selection['integrity']
        if integrity not in archives:
            cached = index[integrity]
            raw = read_regular(cache, cached['cacheRelative'], 32 << 20)
            require(len(raw) == cached['bytes'], 'cached publication length differs: ' + location)
            member_bytes = 32 << 20 if selection['name'] in ROLLDOWN_LINUX_BINDINGS else 16 << 20
            try:
                archives[integrity] = inspect_profile_archive(raw, selection, rows[location],
                    expanded_limit=64 << 20, member_limit=4096, member_bytes=member_bytes)
            except ValueError as error:
                raise ReviewError(f"{selection['name']}@{selection['version']}: {error}") from error
        archive = archives[integrity]
        require(archive['selection'] == selection, 'candidate publication identity collision')
        manifest_raw = read_regular(web, location + '/package.json', 1 << 20)
        manifest_pin = archive['filePins']['package.json']
        require(pin(manifest_raw) == manifest_pin, 'candidate manifest differs from its archive: ' + location)
        manifest = decode(manifest_raw)
        notices = {name: archive['filePins'][name] for name in archive['noticeCandidates']}
        for name, expected in notices.items():
            require(pin(read_regular(web, location + '/' + name, 1 << 20)) == expected,
                'candidate original notice differs: ' + location + '/' + name)
        records[location] = {'selection': selection, 'archive': archive['publication'],
            'originalManifest': manifest_pin, 'manifestLicense': manifest.get('license'), 'originalNotices': notices,
            'manifestSelectors': archive['manifestSelectors'],
            'lockSelectors': {field: rows[location][field] for field in ('os', 'cpu', 'libc') if field in rows[location]}}
    return records


def notice_dependency_names(raw):
    require(pin(raw) == RELEASE_NOTICE, 'Vite release notice bytes differ')
    sections = raw.decode('utf-8').split('\n# Licenses of bundled dependencies\n')
    require(len(sections) == 2, 'reviewed Vite notice heading differs')
    names = set()
    for line in sections[1].splitlines():
        if line.startswith('## '):
            group = line[3:].split(', ')
            require(all(NAME.fullmatch(name) for name in group), 'unrecognized dependency notice heading')
            names.update(group)
    require(0 < len(names) <= 256, 'Vite dependency notice names budget')
    return sorted(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    hosted_only()
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and platform.libc_ver()[0] == 'glibc', 'requires hosted Linux x64 glibc')
    repo = Path(__file__).resolve().parents[2]
    web, output = repo / 'web', args.output
    require(output == Path(os.environ['RUNNER_TEMP']).resolve() / 'zns-vite-upgrade', 'candidate output must be job-owned')
    require(shutil.disk_usage(output.parent).free >= (10 << 30) + (2 << 30), 'candidate free-space floor and reserve')
    for path in (web / 'node_modules', web / 'dist', repo / '.env', repo / 'deployments'):
        require(not path.exists() and not path.is_symlink(), 'candidate requires a fresh checkout without local inputs')
    plan_raw = read_input(repo, 'tools/dependency-review/application-runtime.json')
    plan = decode(plan_raw)
    verify_inputs(repo, plan['inputPins'])
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    core = subprocess.check_output(['git', '-C', 'zvm-core', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    require(re.fullmatch(r'[0-9a-f]{40}', commit) and core == plan['coreCommit'], 'candidate source binding differs')
    output.mkdir(mode=0o700)
    (output / 'streams').mkdir(mode=0o700)
    vendor_path = VENDOR + '/manifest.json'
    baseline_lock = read_input(web, 'package-lock.json')
    manifest = decode(read_input(web, vendor_path))
    require(pin(baseline_lock)['sha256'] == manifest['baseLockSha256'], 'baseline runtime lock binding differs')
    package = decode(read_input(web, 'package.json'))
    require(package['devDependencies']['vite'] == '^' + plan['viteCompiledLabels']['version'], 'baseline Vite declaration differs')
    report = {'schema': 1, 'status': 'VITE_UPGRADE_REVIEW_INCOMPLETE', 'producerCommit': commit, 'coreCommit': core,
        'baselinePlan': pin(plan_raw), 'baselineLock': pin(baseline_lock), 'publicationSelection': PUBLICATION,
        'runId': os.environ['GITHUB_RUN_ID'], 'runAttempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'commands': [], 'trackedApplicationInputsAdopted': False, 'browserRuntimeQualified': False,
        'publisherOrCompleteLicenseReview': False, 'productionGate': 'NO_GO'}
    (output / 'npm-cache').mkdir(mode=0o700)
    for name in ('user.npmrc', 'global.npmrc'):
        (output / name).write_bytes(b'')
    env = {'PATH': os.environ['PATH'], 'LANG': 'C', 'TZ': 'UTC', 'CI': 'true',
        'npm_config_cache': str(output / 'npm-cache'), 'npm_config_userconfig': str(output / 'user.npmrc'),
        'npm_config_globalconfig': str(output / 'global.npmrc'), 'npm_config_fetch_retries': '0',
        'npm_config_fetch_timeout': '45000', 'npm_config_registry': 'https://registry.npmjs.org/'}

    def run(label, argv, cwd=web, timeout=120):
        row = run_bounded(argv, cwd, env, output, label, timeout=timeout)
        report['commands'].append(row)
        require(row['actualExit'] == 0 and row['outputComplete'], label + ' failed or incomplete')
        return read_input(output, row['streams']['stdout']['path'])

    try:
        node = run('node-version', ['node', '--version']).decode().strip()
        require(re.fullmatch(r'v22\.\d+\.\d+', node), 'candidate requires Node 22')
        npm = run('npm-version', ['npm', '--version']).decode().strip()
        report['toolchain'] = {'node': node, 'npm': npm}
        package['devDependencies']['vite'] = PUBLICATION['version']
        package_raw = encoded(package)
        (web / 'package.json').write_bytes(package_raw)
        (output / 'candidate-package.json').write_bytes(package_raw)
        run('candidate-lock-resolution', ['npm', 'install', '--package-lock-only', *INSTALL_FLAGS])
        generated_lock = read_input(web, 'package-lock.json')
        (output / 'npm-generated-lock.json').write_bytes(generated_lock)
        selected_lock, review = candidate_lock(baseline_lock, generated_lock)
        report.update(review)
        if selected_lock != generated_lock:
            (output / 'candidate-lock.json').write_bytes(selected_lock)
            (web / 'package-lock.json').write_bytes(selected_lock)
        manifest['baseLockSha256'] = pin(selected_lock)['sha256']
        (web / vendor_path).write_bytes(encoded(manifest))
        report['candidateRuntimeManifest'] = pin(read_input(web, vendor_path))
        report['candidatePackage'] = pin(package_raw)

        run('candidate-install', ['npm', 'ci', *INSTALL_FLAGS], timeout=180)
        require(read_input(web, 'package-lock.json') == selected_lock and read_input(web, 'package.json') == package_raw,
            'candidate npm ci changed the selected inputs')
        _, rows = package_table(selected_lock)
        installed, absent = installed_changes(web, rows, report['lockDelta'])
        cache, index = current_cache_index(repo, web, output, env, run, npm,
            {selection['integrity'] for selection in installed.values()})
        archive, labels = inspect_vite(web, cache, index['index'][PUBLICATION['integrity']], rows[LOCATION])
        write_json(output / 'vite-compiled-labels.json', labels)
        observed = {(row['name'], row['version']) for row in labels['distinctNameVersionLabels']}
        report['viteArchive'] = archive
        report['archivedNoticeMatchesReleaseSource'] = True
        report['releaseNoticeDependencyNames'] = notice_dependency_names(read_regular(web, LOCATION + '/LICENSE.md', 1 << 20))
        report['installedChangedPublications'] = review_installed_publications(web, rows, installed, cache, index['index'], archive)
        report['absentOptionalChangedLocations'] = absent
        report['compiledLabels'] = {'inventorySha256': canonical_sha256(labels), 'distinctPairs': len(observed),
            'unparsedHeaders': len(labels['unparsedRegionLabels']), 'recognizedOccurrences': len(labels['generatedRegionLabels']),
            'previousExactPairs': [{'name': name, 'version': version, 'observed': (name, version) in observed}
                for name, version in PRIOR_LABELS]}
        report['cachedPublicationReadWithoutAdditionalTransport'] = True

        with (repo / '.env').open('xb') as stream:
            stream.write(read_input(repo, '.env.example'))
        env['npm_config_offline'] = 'true'
        normal, fixture = build_distributions(repo, web, output, plan, manifest, {LOCATION: archive}, run)
        require(read_input(web, 'package.json') == package_raw, 'candidate application manifest changed during build')
        for built in (normal, fixture['distribution']):
            for group in ('viem', 'vue'):
                require(any(re.fullmatch(r'assets/' + group + r'-[\w-]+\.js', name, re.ASCII) for name in built['files']),
                    'candidate distribution lost the reviewed ' + group + ' chunk')
        report['normalDistribution'] = normal
        report['fixtureBuild'] = fixture
        report['status'] = 'VITE_CANDIDATE_APPLICATION_BUILDS_OBSERVED'
        print('### Vite 8.3.8 candidate\n')
        print('The Vite archive and its release notice matched their pins. Both application builds passed.\n')
        print(f"The scanner recognized {len(observed)} package/version pairs and recorded "
            f"{len(labels['unparsedRegionLabels'])} unparsed pnpm headers.\n")
        for row in report['compiledLabels']['previousExactPairs']:
            count = int(row['observed'])
            print(f"- `{row['name']}@{row['version']}` appears in {count} distinct recognized pairs.")
    except Exception as error:
        report['failureType'] = type(error).__name__
        report['failure'] = str(error)[:512]
        raise
    finally:
        write_json(output / 'report.json', report)


if __name__ == '__main__':
    main()
