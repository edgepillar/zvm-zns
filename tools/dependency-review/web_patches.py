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
                'tools/dependency-review/lock_review.py', 'tools/dependency-review/openzeppelin_candidate.py',
                'web/scripts/source-map-controls.test.mjs', 'web/scripts/source-map-codegen.test.mjs',
                'web/scripts/vite-virtual-module-controls.test.mjs')},
            'runId': os.environ.get('GITHUB_RUN_ID'), 'runAttempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
            'browserLiveChainWalletOrDeploymentQualified': False}
        write_json(output / 'source-binding.json', binding)
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
            'npm_config_userconfig': str(userconfig), 'npm_config_globalconfig': str(globalconfig), 'npm_config_cache': str(cache)}
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
        toolchain = json.loads((output / 'streams/toolchain.stdout.txt').read_bytes())
        require(re.fullmatch(r'v22\.\d+\.\d+', toolchain['node']), 'unreviewed Node major')
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
