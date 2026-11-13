"""Qualify the tracked patched source without repeating the frozen legacy run."""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

from lock_review import read_input, require
from openzeppelin_candidate import (QUALIFICATION_LOADER, check_candidate, checked_name,
    patch_controls, run_bounded, sha, stage_build_sources, tap_counts, write_json)


def require_output_parity(expected, actual):
    require(type(expected) is dict and type(actual) is dict and set(expected) == set(actual)
        and len(expected) == 12, 'twelve explicit generated outputs required')
    require(expected == actual, 'tracked generated output differs from the current build')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controls', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    plan_raw = read_input(repo, 'tools/dependency-review/openzeppelin-current.json'); plan = json.loads(plan_raw)
    require(not args.output.exists() and not args.output.is_symlink(), 'output must be a new job-owned directory')
    args.output.mkdir(mode=0o700); output = args.output; (output / 'streams').mkdir(mode=0o700)
    report = {'schema': 1, 'status': 'CURRENT_SOURCE_QUALIFICATION_INCOMPLETE', 'commands': [],
        'trackedPatchAdopted': True, 'productionGate': 'NO_GO', 'legacyCalibrationRepeated': False}
    try:
        require(plan['schema'] == 1 and plan['version'] == '4.9.6' and 1 <= len(plan['inputPins']) <= 256, 'current source manifest')
        check_candidate(plan['package'])
        inputs = {checked_name(name): read_input(repo, name) for name in plan['inputPins']}
        require(all({'bytes': len(raw), 'sha256': sha(raw)} == plan['inputPins'][name] for name, raw in inputs.items()), 'tracked source pin differs')
        package, lock = [json.loads(inputs[name]) for name in ('contracts/package.json', 'contracts/package-lock.json')]
        require(package['devDependencies']['@openzeppelin/contracts'] == lock['packages']['node_modules/@openzeppelin/contracts']['version'] == '4.9.6', 'tracked patch not selected')
        require(lock['packages']['node_modules/@openzeppelin/contracts']['integrity'] == plan['package']['integrity'], 'tracked package integrity differs')
        require(len(plan['controls']['files']) == 7, 'control manifest budget')
        controls = {checked_name(name): read_input(args.controls, name) for name in plan['controls']['files']}
        require(all({'bytes': len(raw), 'sha256': sha(raw)} == plan['controls']['files'][name] for name, raw in controls.items()), 'control source differs')
        source_commit = subprocess.check_output(['git', '--no-optional-locks', '--no-replace-objects', 'rev-parse', 'HEAD'], cwd=repo).decode().strip()
        binding = {'schema': 1, 'producerCommit': source_commit, 'planSha256': sha(plan_raw), 'inputPins': plan['inputPins'],
            'controls': plan['controls'], 'package': plan['package'], 'comparisonEvidence': plan['comparisonEvidence'],
            'codePins': {name: {'bytes': len(read_input(repo, name)), 'sha256': sha(read_input(repo, name))} for name in (
                'tools/dependency-review/openzeppelin_current.py', 'tools/dependency-review/openzeppelin_candidate.py',
                'tools/dependency-review/base64-padding.test.mjs', 'tools/dependency-review/lock_review.py')},
            'pythonVersion': sys.version, 'platform': sys.platform, 'machine': platform.machine(),
            'runId': os.environ.get('GITHUB_RUN_ID'), 'runAttempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
            'legacyCalibrationRepeated': False, 'signingLiveChainReleaseOrDeploymentPerformed': False}
        write_json(output / 'source-binding.json', binding)
        profile = output / 'current'; profile.mkdir()
        for name, raw in {**inputs, **controls}.items():
            target = profile / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
        names = ['contracts/test/package.json', 'contracts/test/package-lock.json']
        for name, raw in zip(names, patch_controls(*(controls[name] for name in names), plan['package'])):
            (profile / name).write_bytes(raw)
        fixture = read_input(repo, 'tools/dependency-review/base64-padding.test.mjs')
        (profile / 'contracts/test/base64-padding.test.mjs').write_bytes(fixture)
        loader = profile / 'qualification-loader.mjs'; loader.write_text(QUALIFICATION_LOADER)
        cache = output / 'npm-cache'; cache.mkdir()
        userconfig, globalconfig = output / 'user.npmrc', output / 'global.npmrc'
        userconfig.write_bytes(b''); globalconfig.write_bytes(b'')
        env = {'PATH': os.environ['PATH'], 'LANG': 'C', 'TZ': 'UTC', 'CI': 'true',
            'NODE_PATH': str(profile / 'contracts/test/node_modules'), 'ZNS_QUALIFIED_TEST_ROOT': str(profile / 'contracts/test'),
            'npm_config_cache': str(cache), 'npm_config_userconfig': str(userconfig), 'npm_config_globalconfig': str(globalconfig),
            'npm_config_fetch_retries': '0', 'npm_config_fetch_timeout': '45000', 'ZNS_TEST_OPENZEPPELIN_VERSION': '4.9.6'}
        commands = [('toolchain', ['node', '-p', 'JSON.stringify({node:process.version,versions:process.versions})'], profile),
            ('install', ['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], profile / 'contracts/test'),
            ('build', ['node', '--import', str(loader), 'scripts/build.mjs'], profile / 'contracts'),
            ('controls', ['node', '--import', str(loader), '--test', '--test-concurrency=1', '--test-reporter=tap', 'behavior.test.mjs', 'base64-padding.test.mjs'], profile / 'contracts/test')]
        for label, argv, cwd in commands:
            if label == 'build':
                report['stagedBuildSourcePins'] = stage_build_sources(profile, plan['packageSourcePins'])
            result = run_bounded(argv, cwd, env, output, 'current-' + label)
            report['commands'].append(result)
            require(result['actualExit'] == 0 and result['outputComplete'], 'current ' + label + ' failed or incomplete')
        toolchain = json.loads((output / 'streams/current-toolchain.stdout.txt').read_bytes())
        require(re.fullmatch(r'v22\.\d+\.\d+', toolchain['node']), 'unreviewed Node major')
        actual = {name: {'bytes': len(read_input(profile, name)), 'sha256': sha(read_input(profile, name))} for name in plan['generatedOutputPins']}
        require_output_parity(plan['generatedOutputPins'], actual)
        raw = (output / 'streams/current-controls.stdout.txt').read_bytes(); totals = tap_counts(raw)
        values = re.findall(rb'^# ZNS_BASE64_PADDING_RESULT (.+)$', raw, re.M)
        require(len(values) == 1, 'current padding receipt absent')
        padding = json.loads(values[0])
        require(padding['version'] == '4.9.6' and padding['cases'] == padding['tailRestored'] == 291
            and padding['noncanonical'] == 0, 'current padding qualification incomplete')
        require(all(read_input(repo, name) == value for name, value in inputs.items()), 'tracked inputs changed during qualification')
        report.update(status='TRACKED_PATCHED_SOURCE_QUALIFIED_NO_DEPLOYMENT', testCounts=totals, padding=padding,
            toolchain=toolchain, generatedOutputPins=actual, all12TrackedGeneratedOutputsExactlyReproduced=True,
            inputPinsVerifiedAndUnchanged=True, syntheticParisMessageFramesOnly=True,
            signingLiveChainReleaseOrDeploymentPerformed=False)
    except Exception as error:
        report['failure'] = {'type': type(error).__name__, 'reason': str(error) if isinstance(error, ValueError) else 'Qualification failed; retained command evidence requires review.'}
        raise
    finally:
        write_json(output / 'report.json', report)
    print(json.dumps({'status': report['status'], 'testCounts': report['testCounts'], 'padding': report['padding'],
        'generatedOutputsExactlyReproduced': 12, 'legacyCalibrationRepeated': False, 'productionGate': 'NO_GO'}))


if __name__ == '__main__':
    main()
