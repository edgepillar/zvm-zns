"""Data-only guards for the explicitly selected source variant and receipts."""

import base64
import copy
import json
import unittest

from openzeppelin_candidate import (check_candidate, checked_name, executable_part,
                                    patch_controls, patch_inputs, sha, tap_counts)


def candidate():
    return {'name': '@openzeppelin/contracts', 'version': '4.9.6', 'license': 'MIT',
        'resolved': 'https://registry.npmjs.org/@openzeppelin/contracts/-/contracts-4.9.6.tgz',
        'integrity': 'sha512-' + base64.b64encode(bytes(range(64))).decode(),
        'archiveBytes': 100, 'archiveSha256': 'a' * 64, 'licenseFileSha256': 'b' * 64}


def inputs():
    package = {'devDependencies': {'@openzeppelin/contracts': '4.9.3', 'solc': '0.8.26'}}
    lock = {'packages': {'': copy.deepcopy(package),
        'node_modules/@openzeppelin/contracts': {'version': '4.9.3'},
        'node_modules/solc': {'version': '0.8.26', 'integrity': 'unchanged'}}}
    vendor = {'selection': {'files': {'untouched': 'original'}}, 'dependencyLock': {'sha256': 'old', 'imports': [
        {'prefix': '@openzeppelin/contracts', 'version': '4.9.3'}, {'prefix': '@ensdomains/buffer', 'version': '0.1.3'}]}}
    return [json.dumps(value).encode() for value in (package, lock, vendor)]


class CandidateControls(unittest.TestCase):
    def test_only_reviewed_dependency_and_binding_change(self):
        old = inputs(); result = patch_inputs(*old, candidate()); package, lock, vendor = map(json.loads, result)
        self.assertEqual(package['devDependencies']['@openzeppelin/contracts'], '4.9.6')
        self.assertEqual(package['devDependencies']['solc'], '0.8.26')
        self.assertEqual(lock['packages']['node_modules/solc'], json.loads(old[1])['packages']['node_modules/solc'])
        self.assertEqual(vendor['selection'], json.loads(old[2])['selection'])
        self.assertEqual(vendor['dependencyLock']['sha256'], sha(result[1]))
        self.assertEqual(vendor['dependencyLock']['imports'][1], json.loads(old[2])['dependencyLock']['imports'][1])

    def test_unexpected_baseline_is_refused(self):
        values = inputs(); package = json.loads(values[0]); package['devDependencies']['@openzeppelin/contracts'] = '5.1.0'
        with self.assertRaises(ValueError):
            patch_inputs(json.dumps(package).encode(), values[1], values[2], candidate())

    def test_control_lock_changes_only_one_selected_package(self):
        old = inputs(); before = json.loads(old[1]); package, lock = map(json.loads, patch_controls(old[0], old[1], candidate()))
        self.assertEqual(package['devDependencies']['solc'], '0.8.26')
        self.assertEqual(lock['packages']['node_modules/solc'], before['packages']['node_modules/solc'])

    def test_candidate_url_algorithm_and_version_are_fixed(self):
        check_candidate(candidate())
        for patch in ({'version': '5.1.0'}, {'resolved': 'https://example.invalid/file'}, {'integrity': 'sha1-deadbeef'}, {'archiveBytes': True}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                check_candidate({**candidate(), **patch})

    def test_source_paths_cannot_escape_or_select_protected_data(self):
        self.assertEqual(checked_name('contracts/src/Example.sol'), 'contracts/src/Example.sol')
        for name in ('../private', '/private', 'contracts//src', 'contracts/./src', 'contracts/.env', '.git/config', 'contracts/../private'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                checked_name(name)

    def test_metadata_is_separate_from_creation_executable(self):
        metadata = 'a2' + '11' * 8
        a = '0x6001' + metadata + (len(metadata) // 2).to_bytes(2, 'big').hex()
        b = a.replace('11', '22')
        self.assertEqual(executable_part(a), executable_part(b))
        self.assertNotEqual(executable_part(a), executable_part(a.replace('6001', '6002')))
        for code in ('0x', '0x6001ffff', 'not-hex'):
            with self.subTest(code=code), self.assertRaises(ValueError):
                executable_part(code)

    def test_tap_needs_complete_unique_positive_totals(self):
        raw = b'# tests 33\n# pass 33\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n'
        self.assertEqual(tap_counts(raw)['pass'], 33)
        for changed in (raw.replace(b'# fail 0', b'# fail 1'), raw + b'# pass 33\n', raw.replace(b'# skipped 0\n', b''), raw.replace(b'# skipped 0', b'# skipped 1')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                tap_counts(changed)


if __name__ == '__main__':
    unittest.main()
