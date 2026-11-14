"""Keep a proposed parent lock separate from current application evidence."""

import base64
import json
import unittest
from unittest.mock import patch

from web_parent_candidate import candidate_manifest, inspect_candidate
from openzeppelin_candidate import sha


class MemoryPath:
    def __init__(self, files, name=''):
        self.files, self.name = files, name
    def __truediv__(self, name): return MemoryPath(self.files, name)
    def read_bytes(self): return self.files[self.name]
    def write_bytes(self, raw): self.files[self.name] = raw


def fixture():
    package = {'name': 'web-controls', 'private': True, 'scripts': {'build': 'review'},
        'devDependencies': {'puppeteer-core': '^25.11.0', 'keep': '1.0.0'}}
    original = json.dumps(package).encode(); proposed = candidate_manifest(original)
    selected = [('puppeteer-core', '25.17.0'), ('chromium-bidi', '157.0.8090-0'), ('zod', '4.6.7'), ('keep', '1.0.0')]
    lock = {'name': package['name'], 'lockfileVersion': 3,
        'packages': {'': {'name': package['name'], 'devDependencies': json.loads(proposed)['devDependencies']}}}
    for name, version in selected:
        lock['packages']['node_modules/' + name] = {'version': version,
            'resolved': 'https://registry.npmjs.org/' + name + '/-/' + name + '-' + version + '.tgz',
            'integrity': 'sha512-' + base64.b64encode(b'x' * 64).decode(), 'license': 'MIT'}
    old_lock = b'{"source":"frozen"}'
    source = {'web/package.json': original, 'web/package-lock.json': old_lock}
    pins = {'packageJsonSha256': sha(original), 'packageLockSha256': sha(old_lock)}
    root = MemoryPath({'package.json': proposed, 'package-lock.json': json.dumps(lock).encode()})
    return source, pins, root


class CandidateBoundaryControls(unittest.TestCase):
    def test_manifest_candidate_preserves_unrelated_source_settings(self):
        source, _, root = fixture()
        before = json.loads(source['web/package.json']); after = json.loads(root.files['package.json'])
        self.assertEqual(after['scripts'], before['scripts'])
        self.assertEqual(after['private'], before['private'])
        self.assertEqual(after['devDependencies']['keep'], '1.0.0')
        self.assertEqual(before['devDependencies']['puppeteer-core'], '^25.11.0')

    def test_an_existing_validator_or_different_parent_is_not_overwritten(self):
        source, _, _ = fixture(); value = json.loads(source['web/package.json'])
        for field, version in [('zod', '3.25.76'), ('puppeteer-core', '^26.0.0')]:
            data = json.loads(json.dumps(value)); data['devDependencies'][field] = version
            with self.subTest(field=field), self.assertRaises(ValueError): candidate_manifest(json.dumps(data))

    def test_successful_proposal_never_waives_the_current_source_finding(self):
        source, pins, root = fixture(); outputs = MemoryPath({})
        with patch('web_parent_candidate.read_input', side_effect=lambda repo, name: source[name]):
            result = inspect_candidate(None, root, pins, outputs)
        self.assertFalse(result['applicationInputsChanged'])
        self.assertFalse(result['rootOldZodFindingWaivedOrRemediated'])
        self.assertFalse(result['newPackagesInstalledOrExecuted'])
        self.assertEqual(result['status'], 'PROPOSED_PARENT_LOCK_REQUIRES_REVIEW_NOT_APPLIED')
        self.assertEqual(set(outputs.files), {'candidate-web-package.json', 'candidate-web-package-lock.json'})

    def test_changed_current_source_cannot_be_bound_to_a_candidate(self):
        source, pins, root = fixture(); source['web/package-lock.json'] += b' '
        with patch('web_parent_candidate.read_input', side_effect=lambda repo, name: source[name]):
            with self.assertRaises(ValueError): inspect_candidate(None, root, pins, MemoryPath({}))


if __name__ == '__main__': unittest.main()
