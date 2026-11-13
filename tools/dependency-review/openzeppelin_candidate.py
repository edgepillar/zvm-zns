"""Build two explicit hosted source variants and retain their bounded evidence."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import subprocess
import time

from lock_review import read_input, require

QUALIFICATION_LOADER = '''import {registerHooks, isBuiltin, createRequire} from 'node:module'
import {pathToFileURL} from 'node:url'
import path from 'node:path'
const anchor = pathToFileURL(path.join(process.env.ZNS_QUALIFIED_TEST_ROOT, 'package.json')).href
const selected = createRequire(anchor)
registerHooks({resolve(specifier, context, next) {
  if (isBuiltin(specifier) || /^(?:[./]|[a-z]+:|#)/.test(specifier)) return next(specifier, context)
  try { return next(specifier, context) } catch (error) {
    if (!['ERR_MODULE_NOT_FOUND', 'MODULE_NOT_FOUND'].includes(error.code)) throw error
    if (context.conditions?.includes('require')) return {url: pathToFileURL(selected.resolve(specifier)).href, shortCircuit: true}
    return next(specifier, {...context, parentURL: anchor})
  }
}})
'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    with path.open('x') as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write('\n')


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def checked_name(name):
    require(type(name) is str and 0 < len(name) <= 2048, 'invalid source name')
    parsed = PurePosixPath(name)
    require(parsed.as_posix() == name and not parsed.is_absolute() and name != '.'
        and '..' not in parsed.parts and '\\' not in name and ':' not in name, 'unsafe source name')
    require(not any(part.casefold() in ('.git', '.ssh', '.codex', '.env', 'credentials', 'wallet.json') for part in parsed.parts), 'protected source name')
    return name


def check_candidate(value):
    require(value['name'] == '@openzeppelin/contracts' and value['version'] == '4.9.6'
        and value['resolved'] == 'https://registry.npmjs.org/@openzeppelin/contracts/-/contracts-4.9.6.tgz'
        and value['license'] == 'MIT', 'unreviewed candidate identity')
    integrity = value['integrity']; require(type(integrity) is str and integrity.startswith('sha512-'), 'candidate integrity algorithm')
    try:
        digest = base64.b64decode(integrity[7:], validate=True)
    except ValueError as error:
        raise ValueError('candidate integrity encoding') from error
    require(len(digest) == 64 and base64.b64encode(digest).decode() == integrity[7:], 'candidate integrity bytes')
    require(type(value['archiveBytes']) is int and 0 < value['archiveBytes'] <= 8 << 20, 'candidate archive budget')
    for key in ('archiveSha256', 'licenseFileSha256'):
        require(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]), 'candidate content pin')


def patch_inputs(package_raw, lock_raw, vendor_raw, candidate):
    package, lock, vendor = [json.loads(raw) for raw in (package_raw, lock_raw, vendor_raw)]
    require(package['devDependencies']['@openzeppelin/contracts'] == '4.9.3', 'unexpected baseline dependency')
    require(lock['packages']['node_modules/@openzeppelin/contracts']['version'] == '4.9.3', 'unexpected baseline lock')
    package['devDependencies']['@openzeppelin/contracts'] = candidate['version']
    lock['packages']['']['devDependencies']['@openzeppelin/contracts'] = candidate['version']
    selected = {key: candidate[key] for key in ('version', 'resolved', 'integrity', 'license')}
    lock['packages']['node_modules/@openzeppelin/contracts'] = {**selected, 'dev': True}
    package_raw, lock_raw = encoded(package), encoded(lock)
    vendor['dependencyLock']['sha256'] = sha(lock_raw)
    rows = [row for row in vendor['dependencyLock']['imports'] if row['prefix'] == '@openzeppelin/contracts']
    require(len(rows) == 1, 'ambiguous provenance dependency')
    rows[0].update({key: candidate[key] for key in ('version', 'resolved', 'integrity')})
    return package_raw, lock_raw, encoded(vendor)


def patch_controls(package_raw, lock_raw, candidate):
    package, lock = json.loads(package_raw), json.loads(lock_raw)
    require(package['devDependencies']['@openzeppelin/contracts'] == '4.9.3', 'unexpected control package')
    package['devDependencies']['@openzeppelin/contracts'] = candidate['version']
    lock['packages']['']['devDependencies']['@openzeppelin/contracts'] = candidate['version']
    lock['packages']['node_modules/@openzeppelin/contracts'] = {
        **{key: candidate[key] for key in ('version', 'resolved', 'integrity', 'license')}, 'dev': True}
    return encoded(package), encoded(lock)


def check_build_source(unit, raw, pin):
    checked_name(unit)
    require(unit.startswith(('@openzeppelin/contracts/', '@openzeppelin/contracts-v5/', '@ensdomains/buffer/'))
        and unit.endswith('.sol'), 'unreviewed build source')
    require(type(raw) is bytes and {'bytes': len(raw), 'sha256': sha(raw)} == pin, 'installed build source differs')


def stage_build_sources(profile, expected):
    require(type(expected) is dict and 1 <= len(expected) <= 64, 'build source budget')
    sources = {}
    for unit, pin in expected.items():
        checked_name(unit)
        raw = read_input(profile / 'contracts/test/node_modules', unit)
        check_build_source(unit, raw, pin)
        sources[unit] = raw
    for unit, raw in sources.items():
        target = profile / 'contracts/node_modules' / unit
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as output:
            output.write(raw)
    return expected


def executable_part(bytecode):
    require(type(bytecode) is str and re.fullmatch(r'0x[0-9a-f]+', bytecode), 'invalid creation bytecode')
    code = bytecode[2:]
    trailer = int(code[-4:], 16) * 2 + 4
    require(4 < trailer <= len(code), 'invalid Solidity metadata trailer')
    require(code[-trailer:-trailer + 2] in ('a1', 'a2', 'a3'), 'unreviewed metadata prefix')
    return code[:-trailer]


def tap_counts(raw):
    text = raw.decode()
    result = {key: re.findall(r'^# ' + key + r' (\d+)\s*$', text, re.M) for key in ('tests', 'pass', 'fail', 'cancelled', 'skipped', 'todo')}
    require(all(len(rows) == 1 for rows in result.values()), 'missing or ambiguous TAP totals')
    result = {key: int(rows[0]) for key, rows in result.items()}
    require(result['tests'] == result['pass'] >= 33 and all(result[key] == 0 for key in ('fail', 'cancelled', 'skipped', 'todo')), 'contract controls did not all pass')
    return result


def run_bounded(argv, cwd, env, output, label, timeout=240):
    streams = {name: {'path': 'streams/' + label + '.' + name + '.txt', 'limit': limit, 'bytes': 0, 'eofObserved': False}
               for name, limit in [('stdout', 2 << 20), ('stderr', 256 << 10)]}
    handles = {name: (output / row['path']).open('xb') for name, row in streams.items()}
    hashes = {name: hashlib.sha256() for name in streams}
    child = selector = None
    reason, exited_at, stopped_at = None, None, None
    started = time.monotonic()
    try:
        child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        selector = selectors.DefaultSelector()
        for name, pipe in [('stdout', child.stdout), ('stderr', child.stderr)]:
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, name)
        while selector.get_map() or child.poll() is None:
            now = time.monotonic()
            if child.poll() is not None and exited_at is None:
                exited_at = now
            if reason is None and now - started >= timeout:
                reason = 'deadline_exceeded'
            if reason is None and exited_at is not None and selector.get_map() and now - exited_at >= 2:
                reason = 'incomplete_inherited_streams'
            if reason and stopped_at is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stopped_at = now
            if stopped_at is not None and now - stopped_at >= 3:
                break
            for key, _ in selector.select(0.05):
                name = key.data
                try:
                    block = os.read(key.fileobj.fileno(), 65536)
                except BlockingIOError:
                    continue
                if not block:
                    streams[name]['eofObserved'] = True
                    selector.unregister(key.fileobj)
                    continue
                row = streams[name]; remaining = row['limit'] - row['bytes']; prefix = block[:remaining]
                handles[name].write(prefix); hashes[name].update(prefix); row['bytes'] += len(prefix)
                if len(block) > remaining and reason is None:
                    reason = name + '_limit_exceeded'
        try:
            actual_exit = child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            actual_exit = None; reason = reason or 'termination_unknown'
        return {'label': label, 'actualExit': actual_exit, 'terminationReason': reason,
            'outputComplete': reason is None and all(row['eofObserved'] for row in streams.values()),
            'seconds': round(time.monotonic() - started, 3),
            'streams': {name: {**row, 'sha256': hashes[name].hexdigest()} for name, row in streams.items()}}
    finally:
        if child is not None:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=3)
            child.stdout.close(); child.stderr.close()
        if selector is not None:
            selector.close()
        for handle in handles.values():
            handle.flush(); os.fsync(handle.fileno()); handle.close()


def compare_artifacts(old, new):
    require(set(old) == set(new) and len(old) == 10, 'ten contract artifacts required')
    return {name: {'ABIUnchanged': old[name]['abi'] == new[name]['abi'],
                  'creationExecutableUnchanged': executable_part(old[name]['bytecode']) == executable_part(new[name]['bytecode']),
                  'creationBytecodeSha256Before': sha(bytes.fromhex(old[name]['bytecode'][2:])),
                  'creationBytecodeSha256After': sha(bytes.fromhex(new[name]['bytecode'][2:]))}
            for name in sorted(old)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controls', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    plan_raw = read_input(repo, 'tools/dependency-review/openzeppelin-candidate.json'); plan = json.loads(plan_raw)
    require(not args.output.exists() and not args.output.is_symlink(), 'output must be a new job-owned directory')
    args.output.mkdir(mode=0o700); (args.output / 'streams').mkdir(mode=0o700)
    output = args.output
    report = {'schema': 1, 'status': 'QUALIFICATION_INCOMPLETE', 'commands': [], 'profiles': {},
        'candidateAdopted': False, 'productionGate': 'NO_GO'}
    try:
        require(plan['schema'] == 1 and 1 <= len(plan['baselineInputPins']) <= 256 and len(plan['controls']['files']) == 7, 'source manifest budget')
        require(all(name.startswith(('contracts/src/', 'contracts/vendor/', 'contracts/out/')) or name in (
            'contracts/scripts/build.mjs', 'contracts/package.json', 'contracts/package-lock.json', 'web/src/abi.ts')
            for name in plan['baselineInputPins']), 'unexpected production input')
        inputs = {checked_name(name): read_input(repo, name) for name in plan['baselineInputPins']}
        require(all({'bytes': len(raw), 'sha256': sha(raw)} == plan['baselineInputPins'][name] for name, raw in inputs.items()), 'baseline source inputs differ')
        controls = {checked_name(name): read_input(args.controls, name) for name in plan['controls']['files']}
        require(all({'bytes': len(raw), 'sha256': sha(raw)} == plan['controls']['files'][name] for name, raw in controls.items()), 'control source differs')
        license_raw = read_input(repo, 'tools/dependency-review/licenses/OpenZeppelin-v4.9.6-LICENSE')
        require(sha(license_raw) == plan['candidate']['licenseFileSha256'], 'upstream license bytes differ')
        control_test = read_input(repo, 'tools/dependency-review/base64-padding.test.mjs')
        candidate = plan['candidate']
        check_candidate(candidate)
        require(candidate['version'] == '4.9.6' and plan['baselineVersion'] == '4.9.3', 'unexpected candidate pair')
        source_commit = subprocess.check_output(['git', '--no-optional-locks', '--no-replace-objects', 'rev-parse', 'HEAD'], cwd=repo).decode().strip()
        source_binding = {'schema': 1, 'producerCommit': source_commit, 'baselineSourceRef': plan['baselineSourceRef'],
            'baselineInputPins': plan['baselineInputPins'], 'controls': plan['controls'], 'planSha256': sha(plan_raw),
            'candidate': candidate, 'qualificationCodePins': {name: {'bytes': len(read_input(repo, name)), 'sha256': sha(read_input(repo, name))} for name in (
                'tools/dependency-review/openzeppelin_candidate.py', 'tools/dependency-review/base64-padding.test.mjs', 'tools/dependency-review/lock_review.py')},
            'runId': os.environ.get('GITHUB_RUN_ID'), 'runAttempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
            'applicationInputsUnchangedByQualification': True, 'signingLiveChainReleaseOrDeploymentPerformed': False}
        write_json(output / 'source-binding.json', source_binding)
        cache = output / 'npm-cache'; cache.mkdir()
        userconfig, globalconfig = output / 'user.npmrc', output / 'global.npmrc'
        userconfig.write_bytes(b''); globalconfig.write_bytes(b'')
        snapshots = {}
        for role, version in [('baseline', '4.9.3'), ('candidate', '4.9.6')]:
            profile = output / role; profile.mkdir()
            for name, raw in {**inputs, **controls}.items():
                target = profile / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            (profile / 'contracts/test/base64-padding.test.mjs').write_bytes(control_test)
            loader = profile / 'qualification-loader.mjs'
            loader.write_text(QUALIFICATION_LOADER)
            if role == 'candidate':
                names = ['contracts/package.json', 'contracts/package-lock.json', 'contracts/vendor/ens-contracts.lock.json']
                for name, raw in zip(names, patch_inputs(*(inputs[name] for name in names), candidate)):
                    (profile / name).write_bytes(raw)
                names = ['contracts/test/package.json', 'contracts/test/package-lock.json']
                for name, raw in zip(names, patch_controls(*(controls[name] for name in names), candidate)):
                    (profile / name).write_bytes(raw)
            env = {'PATH': os.environ['PATH'], 'LANG': 'C', 'TZ': 'UTC', 'CI': 'true',
                'NODE_PATH': str(profile / 'contracts/test/node_modules'),
                'npm_config_cache': str(cache), 'npm_config_userconfig': str(userconfig),
                'npm_config_globalconfig': str(globalconfig), 'npm_config_fetch_retries': '0',
                'npm_config_fetch_timeout': '45000', 'ZNS_TEST_OPENZEPPELIN_VERSION': version,
                'ZNS_QUALIFIED_TEST_ROOT': str(profile / 'contracts/test')}
            commands = [('install', ['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], profile / 'contracts/test'),
                ('build', ['node', '--import', str(loader), 'scripts/build.mjs'], profile / 'contracts'),
                ('controls', ['node', '--import', str(loader), '--test', '--test-concurrency=1', '--test-reporter=tap', 'behavior.test.mjs', 'base64-padding.test.mjs'], profile / 'contracts/test')]
            saved = {Path(name).stem: json.loads(raw) for name, raw in inputs.items() if name.startswith('contracts/out/') and name.endswith('.json') and not name.endswith('/input.json')}
            for label, argv, cwd in commands:
                if label == 'build':
                    staged_sources = stage_build_sources(profile, plan['profilePackageSourcePins'][role])
                result = run_bounded(argv, cwd, env, output, role + '-' + label)
                report['commands'].append(result)
                require(result['actualExit'] == 0 and result['outputComplete'], role + ' ' + label + ' failed or incomplete')
            artifacts = {path.stem: json.loads(path.read_bytes()) for path in (profile / 'contracts/out').glob('*.json') if path.name != 'input.json'}
            original_comparison = compare_artifacts(saved, artifacts)
            if role == 'baseline':
                require(all(row['ABIUnchanged'] and row['creationExecutableUnchanged'] for row in original_comparison.values()), 'baseline executable or ABI drift')
            stream = report['commands'][-1]['streams']['stdout']; tap = (output / stream['path']).read_bytes()
            padding = re.findall(rb'^# ZNS_BASE64_PADDING_RESULT (.+)$', tap, re.M)
            require(len(padding) == 1, 'padding control receipt absent')
            padding = json.loads(padding[0]); require(padding['version'] == version and padding['cases'] == padding['tailRestored'] == 291, 'padding control incomplete')
            require(padding['noncanonical'] == (128 if role == 'baseline' else 0), 'padding control mismatch')
            report['profiles'][role] = {'version': version, 'testCounts': tap_counts(tap), 'padding': padding,
                'stagedBuildSourcePins': staged_sources,
                'savedArtifactComparison': original_comparison, 'sourceInputSha256': sha((profile / 'contracts/out/input.json').read_bytes()),
                'compilerVersion': next(iter(artifacts.values()))['compilerVersion']}
            snapshots[role] = artifacts
        comparison = compare_artifacts(snapshots['baseline'], snapshots['candidate'])
        require(all(row['ABIUnchanged'] for row in comparison.values()), 'candidate changes a contract ABI')
        changed = [name for name, row in comparison.items() if not row['creationExecutableUnchanged']]
        require(changed == ['ZNSRegistrar'], 'unexpected executable change set')
        candidate_root = output / 'candidate'
        names = ['contracts/package.json', 'contracts/package-lock.json', 'contracts/vendor/ens-contracts.lock.json',
            'contracts/out/input.json', 'web/src/abi.ts'] + ['contracts/out/' + name + '.json' for name in sorted(snapshots['candidate'])]
        payloads = {}
        for name in names:
            raw = read_input(candidate_root, name); payloads[name] = {'bytes': len(raw), 'sha256': sha(raw), 'base64': base64.b64encode(raw).decode()}
        payloads['contracts/vendor/notices/openzeppelin-contracts-4.9.6-LICENSE'] = {'bytes': len(license_raw), 'sha256': sha(license_raw), 'base64': base64.b64encode(license_raw).decode()}
        write_json(output / 'outputs.json', {'schema': 1, 'producerCommit': source_commit, 'profile': 'candidate', 'files': payloads,
            'candidateAdopted': False, 'originalApplicationAndDeploymentUnchanged': True})
        require(all(read_input(repo, name) == raw for name, raw in inputs.items()), 'application inputs changed during qualification')
        report.update(status='BASELINE_AND_PATCHED_SOURCE_VARIANTS_QUALIFIED_NOT_ADOPTED',
            candidateArtifactComparison=comparison, changedCreationExecutableContracts=changed,
            sourceAndControlPinsVerified=True, applicationInputsUnchanged=True,
            sameCompilerAndProductionSettings=True, syntheticParisMessageFramesOnly=True,
            newLocalInputsOrHistoricalCleanupRequired=False)
    except Exception as error:
        report['failure'] = {'type': type(error).__name__, 'reason': str(error) if isinstance(error, ValueError) else 'Qualification failed; retained command evidence requires review.'}
        raise
    finally:
        write_json(output / 'report.json', report)
    print(json.dumps({'status': report['status'], 'profiles': {name: row['testCounts'] for name, row in report['profiles'].items()},
        'changedCreationExecutableContracts': report['changedCreationExecutableContracts'], 'candidateAdopted': False}))


if __name__ == '__main__':
    main()
