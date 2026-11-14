"""Qualify selected web package bytes, bounded controls and the normal build."""

import argparse
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tarfile
import urllib.request

from bundled_archive import inspect_archive
from compiled_labels import canonical_sha256, inspect_labels
from lock_review import read_input, require
from openzeppelin_candidate import checked_name, run_bounded, sha, write_json
from web_parent_candidate import stage_candidate, inspect_candidate
from proposal_range_qualification import qualify_ranges
from proposal_delta import prepare_platform_candidate
from changed_source_installation import verify_selected_installation
from mapper_size_controls import qualify_mapper_controls
from node_parser_controls import qualify_parser_controls
from mapper_rebuild import qualify_rebuild
from node_consumer_controls import qualify_consumers


def pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def verify_files(root, expected):
    require(type(expected) is dict and 0 < len(expected) <= 512, 'file manifest budget')
    actual = {}
    for name, value in expected.items():
        checked_name(name)
        raw = read_input(root, name); require(pin(raw) == value, 'reviewed source bytes differ')
        actual[name] = value
    return actual


def test_summary(raw, expected):
    result = {}
    for key in ('tests', 'pass', 'fail', 'cancelled', 'skipped', 'todo'):
        rows = re.findall(rb'^# ' + key.encode() + rb' (\d+)\s*$', raw, re.M)
        require(len(rows) == 1, 'incomplete or ambiguous test totals'); result[key] = int(rows[0])
    require(result['tests'] == result['pass'] == expected and all(result[k] == 0 for k in ('fail', 'cancelled', 'skipped', 'todo')), 'web controls did not pass completely')
    return result


def marker(raw, name):
    rows = re.findall(rb'^# ' + name.encode() + rb' (.+)$', raw, re.M)
    require(len(rows) == 1, 'web control receipt absent or ambiguous')
    return json.loads(rows[0])


def baseline_source(output, selected):
    request = urllib.request.Request(selected['resolved'], headers={'User-Agent': 'edgepillar-dependency-review'})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read((2 << 20) + 1)
        require(response.status == 200 and response.geturl() == selected['resolved'] and len(raw) <= 2 << 20, 'baseline transport budget or URL')
    require(pin(raw) == {'bytes': selected['archiveBytes'], 'sha256': selected['archiveSha256']}, 'baseline publication digest differs')
    reviewed = inspect_archive(raw, selected, expanded_limit=32 << 20)
    actual = {row['path'].removeprefix('package/'): {'bytes': row['bytes'], 'sha256': row['sha256']}
        for row in reviewed['archiveMembers'] if row['kind'] == 'file'}
    require(actual == selected['filePins'], 'baseline publication member pins differ')
    root = output / 'baseline-source-map'; root.mkdir()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for member in archive:
            if not member.isfile():
                continue
            name = member.name.removeprefix('package/'); checked_name(name)
            body = archive.extractfile(member).read()
            require(pin(body) == selected['filePins'][name], 'baseline member changed')
            target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as destination:
                destination.write(body)
    return root, {'url': selected['resolved'], 'bytes': len(raw), 'sha256': sha(raw), 'integrity': selected['integrity'],
        'filePins': actual, 'requests': 1, 'filesystemArchiveExtractionScope': 'Explicit regular members in new hosted job-owned baseline directory only.'}


def dist_inventory(root):
    require(root.is_dir() and not root.is_symlink(), 'build output absent or linked')
    rows = {}; total = 0
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories:
            require(not (Path(current) / name).is_symlink(), 'linked build directory')
        for name in files:
            path = Path(current) / name; value = path.lstat()
            require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1, 'nonregular build output')
            require(value.st_size <= 4 << 20 and len(rows) < 512, 'build member budget')
            total += value.st_size; require(total <= 64 << 20, 'build payload budget')
            relative = path.relative_to(root).as_posix(); checked_name(relative)
            raw = path.read_bytes(); require(len(raw) == value.st_size, 'build output changed')
            rows[relative] = pin(raw)
    require('index.html' in rows, 'static entry point absent')
    return {'files': rows, 'fileCount': len(rows), 'payloadBytes': total, 'browserRuntimeQualified': False}


def proposal_archives(root, selected):
    lock = json.loads(read_input(root, 'package-lock.json'))['packages']
    require(type(selected) is dict and len(selected) == 1, 'proposal archive source budget')
    sources, transport = {}, {}
    for location, publication in selected.items():
        row = lock[location]
        require(type(publication['archiveBytes']) is int and 0 < publication['archiveBytes'] <= 8 << 20, 'proposal archive byte budget')
        require(publication['resolved'] == 'https://registry.npmjs.org/' + publication['name'] + '/-/'
            + publication['name'].rsplit('/', 1)[-1] + '-' + publication['version'] + '.tgz', 'proposal archive URL differs')
        require(all(row[key] == publication[key] for key in ('version', 'resolved', 'integrity')), 'proposal parent publication selection differs')
        request = urllib.request.Request(publication['resolved'], headers={'User-Agent': 'edgepillar-dependency-review'})
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read(publication['archiveBytes'] + 1)
            require(response.status == 200 and response.geturl() == publication['resolved'], 'proposal archive response differs')
            if response.headers.get('Content-Length') is not None:
                require(int(response.headers['Content-Length']) == len(raw), 'proposal archive response incomplete')
        require(pin(raw) == {'bytes': publication['archiveBytes'], 'sha256': publication['archiveSha256']}, 'proposal archive bytes differ')
        sources[location] = raw
        transport[location] = {'url': publication['resolved'], 'bytes': len(raw), 'sha256': sha(raw),
            'integrity': publication['integrity'], 'requests': 1, 'archiveFilesystemExtractions': 0}
    return sources, transport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); repo = Path(__file__).resolve().parents[2]; web = repo / 'web'
    plan_raw = read_input(repo, 'tools/dependency-review/web-patches.json'); plan = json.loads(plan_raw)
    require(not args.output.exists() and not args.output.is_symlink(), 'output must be a new job-owned directory')
    args.output.mkdir(mode=0o700); output = args.output; (output / 'streams').mkdir(mode=0o700)
    report = {'schema': 1, 'status': 'WEB_PATCH_QUALIFICATION_INCOMPLETE', 'commands': [], 'productionGate': 'NO_GO'}
    try:
        require(plan['schema'] == 1 and set(plan['packages']) == {'vite', 'source-map-js'}, 'unreviewed patch set')
        verify_files(repo, plan['sourcePins'])
        require(read_input(repo, '.env') == read_input(repo, '.env.example'), 'qualification environment differs from tracked example')
        commit = subprocess.check_output(['git', '--no-optional-locks', '--no-replace-objects', 'rev-parse', 'HEAD'], cwd=repo).decode().strip()
        core = subprocess.check_output(['git', '--no-optional-locks', '--no-replace-objects', '-C', 'zvm-core', 'rev-parse', 'HEAD'], cwd=repo).decode().strip()
        require(core == plan['coreCommit'], 'core submodule source differs')
        binding = {'schema': 1, 'producerCommit': commit, 'coreCommit': core, 'planSha256': sha(plan_raw),
            'sourcePins': plan['sourcePins'], 'packages': plan['packages'], 'baselineSourceMap': plan['baselineSourceMap'],
            'codePins': {name: pin(read_input(repo, name)) for name in (
                'tools/dependency-review/web_patches.py', 'tools/dependency-review/bundled_archive.py',
                'tools/dependency-review/compiled_labels.py',
                'tools/dependency-review/web_parent_candidate.py', 'tools/dependency-review/bundled_lock.py',
                'tools/dependency-review/lock_review.py', 'tools/dependency-review/openzeppelin_candidate.py',
                'web/scripts/source-map-controls.test.mjs', 'web/scripts/source-map-codegen.test.mjs',
                'web/scripts/vite-virtual-module-controls.test.mjs',
                'tools/dependency-review/proposal_versions.py', 'tools/dependency-review/version_ranges.cjs',
                'tools/dependency-review/proposal_range_qualification.py', 'tools/dependency-review/proposal_delta.py',
                'tools/dependency-review/changed_publications.py', 'tools/dependency-review/changed_source_installation.py',
                'tools/dependency-review/changed-publications.json', 'tools/dependency-review/mapper_size_controls.py',
                'tools/dependency-review/mapper-size-worker.cjs', 'tools/dependency-review/verified-package-sources.cjs',
                'tools/dependency-review/node_parser_controls.py', 'tools/dependency-review/node-parser-worker.cjs',
                'tools/dependency-review/parser_guard.py', 'tools/dependency-review/node-parser-guard.json',
                'tools/dependency-review/node-parser-guard.patch',
                'tools/dependency-review/mapper_rebuild.py', 'tools/dependency-review/mapper_rebuild_plan.py',
                'tools/dependency-review/mapper_rebuild_map.py', 'tools/dependency-review/mapper-rebuild-sources.json',
                'tools/dependency-review/rebuilt-mapper-worker.cjs',
                'tools/dependency-review/node_consumer_controls.py', 'tools/dependency-review/profile_sources.py',
                'tools/dependency-review/npm-cache-index.cjs', 'tools/dependency-review/node-consumer-worker.cjs',
                'tools/dependency-review/node-consumer-resolve.mjs', 'tools/dependency-review/node-consumer-plan.json',
                'tools/dependency-review/profile-source-budgets.json')},
            'runId': os.environ.get('GITHUB_RUN_ID'), 'runAttempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
            'browserLiveChainWalletOrDeploymentQualified': False}
        write_json(output / 'source-binding.json', binding)
        source_plan_raw = read_input(repo, 'tools/dependency-review/changed-publications.json')
        source_plan = json.loads(source_plan_raw)
        report['changedParentPublicationSources'] = verify_selected_installation(web,
            read_input(repo, 'web/package-lock.json'), source_plan, 'baseline')
        report['changedParentPublicationSources']['sourcePlanSha256'] = sha(source_plan_raw)
        report['installedPackagePins'] = {}
        lock = json.loads(read_input(repo, 'web/package-lock.json'))
        for name, selected in plan['packages'].items():
            entry = lock['packages']['node_modules/' + name]
            require(entry['version'] == selected['version'] and entry['integrity'] == selected['integrity']
                and entry['resolved'] == selected['resolved'], 'selected lock identity differs')
            report['installedPackagePins'][name] = verify_files(web / 'node_modules' / name, selected['filePins'])
        vite_files = {name: read_input(web / 'node_modules/vite', name) for name in plan['packages']['vite']['filePins']}
        compiled_labels = inspect_labels(vite_files)
        require(canonical_sha256(compiled_labels) == plan['compiledLabelInventoryExpected']['sha256'], 'compiled Vite inventory drift')
        require(not compiled_labels['unparsedRegionLabels'], 'compiled Vite region labels need review')
        report['compiledViteLabels'] = compiled_labels
        baseline, transport = baseline_source(output, plan['baselineSourceMap'])
        report['baselineSourceTransport'] = transport
        userconfig, globalconfig = output / 'user.npmrc', output / 'global.npmrc'
        userconfig.write_bytes(b''); globalconfig.write_bytes(b''); cache = output / 'npm-cache'; cache.mkdir()
        env = {'PATH': os.environ['PATH'], 'LANG': 'C', 'TZ': 'UTC', 'CI': 'true',
            'npm_config_userconfig': str(userconfig), 'npm_config_globalconfig': str(globalconfig), 'npm_config_cache': str(cache),
            'npm_config_fetch_retries': '0', 'npm_config_fetch_timeout': '45000', 'npm_config_registry': 'https://registry.npmjs.org/'}
        commands = [('toolchain', ['node', '-p', 'JSON.stringify({node:process.version,versions:process.versions})'], env),
            ('vite-version', ['node', 'node_modules/vite/bin/vite.js', '--version'], env)]
        fixtures = output / 'vite-module-fixtures'; fixtures.mkdir()
        commands += [('vite-virtual-module-controls', ['node', '--experimental-vm-modules', '--test', '--test-reporter=tap',
            'scripts/vite-virtual-module-controls.test.mjs'], {**env, 'ZNS_VITE_CONTROL_TMPDIR': str(fixtures)})]
        for role, version, root in [('baseline', '1.2.1', baseline), ('candidate', '1.2.2', web / 'node_modules/source-map-js')]:
            selected_env = {**env, 'ZNS_SOURCE_MAP_ROOT': str(root), 'ZNS_SOURCE_MAP_VERSION': version}
            commands += [(role + '-controls', ['node', '--test', '--test-reporter=tap', 'scripts/source-map-controls.test.mjs'], selected_env),
                (role + '-codegen', ['node', '--disallow-code-generation-from-strings', '--test', '--test-reporter=tap', 'scripts/source-map-codegen.test.mjs'], selected_env)]
        commands += [('build', ['npm', 'run', 'build'], env)]
        for label, argv, selected_env in commands:
            result = run_bounded(argv, web, selected_env, output, label)
            report['commands'].append(result)
            require(result['actualExit'] == 0 and result['outputComplete'], label + ' failed or incomplete')
        parent_root, parent_source_pins = stage_candidate(repo, output)
        for label, argv in [('parent-package-toolchain', ['npm', '--version']),
            ('parent-lock-plan', ['npm', 'install', '--package-lock-only', '--ignore-scripts', '--no-audit', '--no-fund'])]:
            result = run_bounded(argv, parent_root, env, output, label)
            report['commands'].append(result)
            require(result['actualExit'] == 0 and result['outputComplete'], label + ' failed or incomplete')
        require(not (parent_root / 'node_modules').exists(), 'parent lock planning unexpectedly installed packages')
        report['parentLockPlatformPreservation'] = prepare_platform_candidate(repo, parent_root, output)
        archives, report['parentArchiveTransport'] = proposal_archives(parent_root, plan['proposalArchiveSources'])
        report['parentMigrationCandidate'] = inspect_candidate(repo, parent_root, parent_source_pins, output, archives)
        require(report['parentMigrationCandidate']['outputs']['candidate-web-package-lock.json']['sha256']
            == source_plan['candidateLockSha256'], 'parent proposal differs from the reviewed changed-source lock')
        proposed_inventory = report['parentMigrationCandidate']['inventory']
        require(proposed_inventory['sourceInventoryCoversEveryLockRow'] and proposed_inventory['allSelectedBundleManifestsBound'],
            'proposal source inventory incomplete')
        for location, publication in plan['proposalArchiveSources'].items():
            observed = proposed_inventory['parentPublications'][location]
            require(observed['parentManifestSha256'] == publication['parentManifestSha256'], 'proposal parent manifest differs')
            members = {row['location']: {key: row['sourceBinding'][key] for key in ('name', 'version', 'manifestPath', 'manifestBytes', 'manifestSha256')}
                for row in proposed_inventory['packageRecords'] if row['sourceKind'] == 'PARENT_PUBLICATION_MEMBER'
                    and row['sourceBinding']['parentLockLocation'] == location}
            require(members == publication['memberManifestPins'], 'proposal bundled manifests differ')
        report['parentMigrationCandidate']['npmVersion'] = (output / 'streams/parent-package-toolchain.stdout.txt').read_text().strip()
        toolchain = json.loads((output / 'streams/toolchain.stdout.txt').read_bytes())
        require(re.fullmatch(r'v22\.\d+\.\d+', toolchain['node']), 'unreviewed Node major')
        report['proposalVersionRanges'] = qualify_ranges(repo, parent_root, proposed_inventory,
            {'node': toolchain['node'], 'npm': report['parentMigrationCandidate']['npmVersion']},
            output, env, report['commands'], plan['versionRangeTool'])
        ranges = report['proposalVersionRanges']['versionReview']
        require(ranges['allRecordedVersionCasesEvaluated'] and ranges['allResolvedDependencyRangesSatisfied']
            and ranges['allRecordedEngineRangesSatisfiedForProfile'], 'proposal version or engine constraints require review')
        # Until a successful bounded result is verified, a failed launch or
        # partial execution cannot be reported as "no proposed code executed".
        report['parentMigrationCandidate'].update(newPackagesInstalledOrExecuted=None,
            proposedPackageExecutionScope='Selected generated mapper declarations and pinned Zod library code in bounded array controls only.',
            completeCandidateDependencyInstallation=False, candidateBrowserBootstrapExecuted=False,
            migrationAcceptanceEstablished=False)
        report['mapperControlExecution'] = {}
        report['mapperArrayControls'] = qualify_mapper_controls(repo, parent_root, output, env, report['commands'],
            source_plan, report['mapperControlExecution'])
        report['parentMigrationCandidate']['newPackagesInstalledOrExecuted'] = True
        report['parentMigrationCandidate']['proposedPackageExecutionScope'] = 'Bounded generated mapper, root validator and Node protocol-parser module controls only.'
        report['parserControlExecution'] = {}
        report['nodeParserControls'] = qualify_parser_controls(repo, web, parent_root, output, env,
            report['commands'], source_plan, report['parserControlExecution'])
        report['mapperRebuildExecution'] = {}
        report['mapperRebuild'] = qualify_rebuild(repo, parent_root, output, env, report['commands'],
            source_plan, report['mapperRebuildExecution'])
        report['parentMigrationCandidate']['proposedPackageExecutionScope'] = 'Bounded original mapper, root validator, Node parser and separately rebuilt generated mapper declarations. Original and rebuilt browser bootstraps were not executed.'
        report['nodeConsumerExecution'] = {}
        report['nodeConsumerControls'] = qualify_consumers(repo, web, parent_root, output, env, report['commands'],
            source_plan, report['nodeConsumerExecution'])
        report['parentMigrationCandidate'].update(candidateProfileInstallationPerformed=True,
            candidateInstalledProfile='linux/x64/glibc',
            proposedPackageExecutionScope='Existing bounded mapper/parser controls plus actual baseline/raw-candidate Node entry imports and tracked caller defaultArgs in read-only permission profiles. Browser and CDP/protocol handlers were not run.')
        vite_version = plan['packages']['vite']['version']
        require(('vite/' + vite_version).encode() in (output / 'streams/vite-version.stdout.txt').read_bytes(), 'selected Vite CLI not observed')
        virtual_raw = (output / 'streams/vite-virtual-module-controls.stdout.txt').read_bytes()
        virtual_totals = test_summary(virtual_raw, 4)
        virtual_result = marker(virtual_raw, 'ZNS_VITE_VIRTUAL_MODULE_RESULT')
        require(virtual_result == plan['viteVirtualModuleControlsExpected'], 'Vite virtual-module controls differ from reviewed scope')
        profiles = {}
        for role, version in [('baseline', '1.2.1'), ('candidate', '1.2.2')]:
            raw, restricted = [(output / ('streams/' + role + '-' + label + '.stdout.txt')).read_bytes() for label in ('controls', 'codegen')]
            normal_totals, restricted_totals = test_summary(raw, 4), test_summary(restricted, 1)
            offsets, nesting, codegen = marker(raw, 'ZNS_SOURCE_MAP_OFFSETS'), marker(raw, 'ZNS_SOURCE_MAP_NESTING'), marker(restricted, 'ZNS_SOURCE_MAP_CODEGEN')
            source_node = marker(raw, 'ZNS_SOURCE_MAP_NODE')
            require(offsets['version'] == nesting['version'] == codegen['version'] == source_node['version'] == version
                and offsets['cases'] == 20, 'selected control version differs')
            require(offsets['accepted'] + offsets['rejected'] == 20 and not offsets['malformedMappingIterationPerformed'], 'offset control budget differs')
            require(source_node['cases'] == source_node['unchanged'] + source_node['mismatches'] == 4
                and source_node['maximumSectionOffset'] == 16 and not source_node['malformedNumericOffsetsUsed'], 'source-node control budget differs')
            require(source_node['mismatches'] == 0 if role == 'candidate' else source_node['mismatches'] > 0,
                'source-node correction not observed')
            require((offsets['accepted'] == 0 if role == 'candidate' else offsets['accepted'] > 0)
                and nesting['depth'] == 4 and nesting['deepestSourceReads'] == (1 if role == 'candidate' else 81), 'source-map correction not observed')
            require(codegen['stringCodeGenerationDisabled'] and codegen['patchedSortingPassed'] == (role == 'candidate')
                and codegen['expectedLegacyRejectionObserved'] == (role == 'baseline') and not codegen['browserCSPQualified'], 'restricted-runtime control differs')
            profiles[role] = {'version': version, 'normalTestCounts': normal_totals, 'restrictedTestCounts': restricted_totals,
                'offsets': offsets, 'nesting': nesting, 'sourceNode': source_node, 'codeGenerationRestriction': codegen}
        distribution = dist_inventory(web / 'dist')
        for notice in plan['retainedNotices']:
            require(distribution['files'][notice['distPath']] == notice['pin'], 'original notice not preserved in build output')
        verify_files(repo, plan['sourcePins'])
        report.update(status='SELECTED_WEB_PATCH_BYTES_AND_BUILD_QUALIFIED_NO_BROWSER_RUNTIME', profiles=profiles,
            toolchain=toolchain, viteVersion=vite_version, distribution=distribution, originalNoticesInDistributionVerified=True,
            virtualModuleControls={'testCounts': virtual_totals, 'result': virtual_result},
            sourcePinsVerifiedAndUnchanged=True, completeAdvisoryCoverageOrLegalReviewEstablished=False,
            signingLiveChainReleaseOrDeploymentPerformed=False)
    except Exception as error:
        report['failure'] = {'type': type(error).__name__, 'reason': str(error) if isinstance(error, ValueError) else 'Qualification failed; retained command evidence requires review.'}
        raise
    finally:
        write_json(output / 'report.json', report)
    print(json.dumps({'status': report['status'], 'profiles': report['profiles'], 'distFiles': distribution['fileCount'],
        'productionGate': 'NO_GO', 'browserRuntimeQualified': False}))


if __name__ == '__main__':
    main()
