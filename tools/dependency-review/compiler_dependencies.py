"""Bind the real compiler installation and the derived contract-test graph."""

import json
import os
from pathlib import Path
import re
import stat

from lock_review import read_input, require
from openzeppelin_candidate import checked_name, encoded, sha

VERSIONS = {'solc': '0.8.26', 'follow-redirects': '1.16.3', 'tmp': '0.2.7'}
OVERRIDE = {'solc@0.8.26': {'tmp': '0.2.7'}}
METADATA = ('dependencies', 'optionalDependencies', 'peerDependencies', 'peerDependenciesMeta', 'engines', 'bin', 'license', 'funding')


def dependency_test_counts(raw, expected):
    result = {}
    for key in ('tests', 'pass', 'fail', 'cancelled', 'skipped', 'todo'):
        rows = re.findall(rb'^# ' + key.encode() + rb' (\d+)\s*$', raw, re.M)
        require(len(rows) == 1, 'dependency control totals missing or ambiguous')
        result[key] = int(rows[0])
    require(result['tests'] == result['pass'] == expected and all(result[key] == 0
        for key in ('fail', 'cancelled', 'skipped', 'todo')), 'dependency controls did not pass completely')
    return result


def patch_test_compiler_graph(package_raw, lock_raw, selected):
    """Keep the original test source frozen; derive its reviewed install inputs."""
    package, lock = json.loads(package_raw), json.loads(lock_raw)
    require(package['devDependencies']['solc'] == lock['packages']['node_modules/solc']['version'] == '0.8.26', 'compiler selection differs')
    require(not package.get('overrides'), 'unreviewed existing control override')
    package['overrides'] = OVERRIDE
    for name in ('follow-redirects', 'tmp'):
        candidate = selected[name]
        require(candidate['publication']['name'] == name and candidate['publication']['version'] == VERSIONS[name], 'compiler dependency candidate differs')
        row = lock['packages']['node_modules/' + name]
        require(row['version'] == ('1.16.0' if name == 'follow-redirects' else '0.0.33'), 'control baseline differs')
        for field in METADATA:
            row.pop(field, None)
        row.update(candidate['lockMetadata'])
        row.update({field: candidate['publication'][field] for field in ('version', 'resolved', 'integrity')})
    # The replaced tmp publication has no runtime dependency on os-tmpdir.
    require(not any('os-tmpdir' in row.get(scope, {}) for row in lock['packages'].values()
        for scope in ('dependencies', 'optionalDependencies')), 'os-tmpdir is still required')
    removed = lock['packages'].pop('node_modules/os-tmpdir', None)
    require(removed is not None and removed['version'] == '1.0.2', 'unexpected unused package')
    return encoded(package), encoded(lock)


def verify_source_package(root, publication):
    require(not any(path.is_symlink() for path in (Path(root), *Path(root).parents)), 'linked compiler package root or ancestor')
    expected = publication['filePins']
    require(type(expected) is dict and 0 < len(expected) <= 512, 'compiler publication member budget')
    require(sum(p['bytes'] for p in expected.values()) <= 32 << 20, 'compiler publication payload budget')
    result = {}
    for name, pin in expected.items():
        checked_name(name)
        require(type(pin['bytes']) is int and 0 <= pin['bytes'] <= 16 << 20, 'compiler member byte budget')
        path = Path(root)
        for part in Path(name).parts:
            path /= part
            require(not path.is_symlink(), 'linked compiler package member or ancestor')
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == pin['bytes'], 'compiler member type or size differs')
            raw = stream.read(pin['bytes'] + 1)
            after = os.fstat(stream.fileno())
        identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        require(identity(before) == identity(after) == identity(path.lstat()), 'compiler member changed while reading')
        require({'bytes': len(raw), 'sha256': sha(raw)} == pin, 'compiler member digest differs')
        result[name] = pin
    return result


def verify_compiler_trees(profile, selected):
    result = {}
    for role, location in [('application', 'contracts'), ('testSDK', 'contracts/test')]:
        root = profile / location
        package = json.loads(read_input(root, 'package.json'))
        lock = json.loads(read_input(root, 'package-lock.json'))
        require(package.get('overrides') == OVERRIDE, 'scoped tmp override differs')
        require(package['devDependencies']['solc'] == '0.8.26', 'compiler input changed')
        result[role] = {}
        for name in VERSIONS:
            publication = selected[name]['publication']
            row = lock['packages']['node_modules/' + name]
            require(row['version'] == publication['version'] == VERSIONS[name]
                and row['integrity'] == publication['integrity'] and row['resolved'] == publication['resolved'], 'compiler lock identity differs')
            result[role][name] = verify_source_package(root / 'node_modules' / name, publication)
    require(result['application'] == result['testSDK'], 'application and test compiler sources differ')
    return result
