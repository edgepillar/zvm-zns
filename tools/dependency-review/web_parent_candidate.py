"""Stage review-only parent migration inputs without changing the application."""

import json

from lock_review import inventory, read_input, require
from openzeppelin_candidate import encoded, sha


def candidate_manifest(package_raw):
    package = json.loads(package_raw)
    require(package['devDependencies']['puppeteer-core'] == '^25.11.0', 'parent baseline differs')
    require('zod' not in package['devDependencies'], 'unexpected direct validator dependency')
    package['devDependencies']['puppeteer-core'] = '25.17.0'
    package['devDependencies']['zod'] = '4.6.7'
    return encoded(package)


def stage_candidate(repo, output):
    package_raw, lock_raw = [read_input(repo, name) for name in ('web/package.json', 'web/package-lock.json')]
    require(json.loads(lock_raw)['packages']['node_modules/puppeteer-core']['version'] == '25.11.0', 'locked parent baseline differs')
    proposed_package = candidate_manifest(package_raw)
    root = output / 'candidate-web-parent'; root.mkdir()
    (root / 'package.json').write_bytes(proposed_package)
    (root / 'package-lock.json').write_bytes(lock_raw)
    return root, {'packageJsonSha256': sha(package_raw), 'packageLockSha256': sha(lock_raw)}


def inspect_candidate(repo, root, source_pins, output):
    package_raw, lock_raw = [(root / name).read_bytes() for name in ('package.json', 'package-lock.json')]
    require(len(package_raw) <= 64 << 10 and len(lock_raw) <= 2 << 20, 'parent candidate output budget')
    package, lock = json.loads(package_raw), json.loads(lock_raw)
    require(package['devDependencies']['puppeteer-core'] == '25.17.0' and package['devDependencies']['zod'] == '4.6.7', 'candidate parent selection differs')
    require(lock['packages']['node_modules/puppeteer-core']['version'] == '25.17.0'
        and lock['packages']['node_modules/chromium-bidi']['version'] == '157.0.8090-0'
        and lock['packages']['node_modules/zod']['version'] == '4.6.7', 'candidate protocol or validator selection differs')
    original = json.loads(read_input(repo, 'web/package.json'))
    original['devDependencies']['puppeteer-core'] = '25.17.0'; original['devDependencies']['zod'] = '4.6.7'
    require(package == original, 'unreviewed manifest edits in candidate')
    require(sha(read_input(repo, 'web/package.json')) == source_pins['packageJsonSha256']
        and sha(read_input(repo, 'web/package-lock.json')) == source_pins['packageLockSha256'], 'application source inputs changed')
    outputs = {}
    for name, raw in [('candidate-web-package.json', package_raw), ('candidate-web-package-lock.json', lock_raw)]:
        (output / name).write_bytes(raw)
        outputs[name] = {'bytes': len(raw), 'sha256': sha(raw)}
    return {'status': 'PROPOSED_PARENT_LOCK_REQUIRES_REVIEW_NOT_APPLIED', 'sourcePins': source_pins,
        'outputs': outputs, 'inventory': inventory(package_raw, lock_raw), 'applicationInputsChanged': False,
        'newPackagesInstalledOrExecuted': False, 'browserRuntimeQualified': False,
        'rootOldZodFindingWaivedOrRemediated': False, 'productionGate': 'NO_GO'}
