"""Keep a proposed parent lock separate from current application evidence."""

import base64
import json
import unittest
from unittest.mock import patch

from web_parent_candidate import candidate_inputs, candidate_manifest, inspect_candidate
from openzeppelin_candidate import sha
from lock_review import ReviewError
from test_bundled_archive import make_publication


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
    def test_an_archive_binding_request_inventory_includes_the_actual_member(self):
        source, pins, root = fixture(); raw, selected = make_publication()
        original = json.loads(source['web/package.json']); original['devDependencies']['a'] = '1.0.0'
        source['web/package.json'] = json.dumps(original).encode(); pins['packageJsonSha256'] = sha(source['web/package.json'])
        package = json.loads(root.files['package.json']); package['devDependencies']['a'] = '1.0.0'
        root.files['package.json'] = json.dumps(package).encode()
        lock = json.loads(root.files['package-lock.json']); lock['packages']['']['devDependencies']['a'] = '1.0.0'
        lock['packages']['node_modules/a'] = selected
        lock['packages']['node_modules/a/node_modules/b'] = {'version': '1.0.1', 'inBundle': True, 'license': 'MIT'}
        root.files['package-lock.json'] = json.dumps(lock).encode()
        with patch('web_parent_candidate.read_input', side_effect=lambda repo, name: source[name]):
            result = inspect_candidate(None, root, pins, MemoryPath({}), {'node_modules/a': raw})
        self.assertEqual(result['inventoryStatus'], 'LOCK_AND_PARENT_ARCHIVE_MEMBERS_INVENTORIED_REVIEW_REQUIRED')
        self.assertEqual(result['inventory']['boundArchiveMemberCount'], 1)
        self.assertIsNone(result['inventoryRefusal'])
        self.assertEqual(result['registryOnlyInventoryRefusal']['type'], 'ReviewError')
        self.assertFalse(result['completeProposedGraphQualified'])
        self.assertFalse(result['rootOldZodFindingWaivedOrRemediated'])

    def test_an_explicit_archive_request_cannot_fall_back_after_a_binding_refusal(self):
        source, pins, root = fixture()
        with patch('web_parent_candidate.read_input', side_effect=lambda repo, name: source[name]), \
                patch('web_parent_candidate.inventory_with_archives', side_effect=ReviewError('parent digest differs')):
            with self.assertRaisesRegex(ReviewError, 'parent digest differs'):
                inspect_candidate(None, root, pins, MemoryPath({}), {'node_modules/a': b'untrusted'})

    def test_proposal_binds_the_actual_locked_parent_instead_of_the_declared_minimum(self):
        source, _, _ = fixture()
        locked = {'packages': {'node_modules/puppeteer-core': {'version': '25.12.0'}}}
        raw = json.dumps(locked).encode()
        proposed, preserved = candidate_inputs(source['web/package.json'], raw)
        self.assertEqual(preserved, raw)
        self.assertEqual(json.loads(proposed)['devDependencies']['puppeteer-core'], '25.17.0')
        for version in ['25.11.0', '25.17.0', '26.0.0']:
            locked['packages']['node_modules/puppeteer-core']['version'] = version
            with self.subTest(version=version), self.assertRaises(ValueError): candidate_inputs(source['web/package.json'], json.dumps(locked))

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
        self.assertFalse(result['completeProposedGraphQualified'])
        self.assertEqual(result['inventoryStatus'], 'DECLARATIONS_INVENTORIED_REVIEW_REQUIRED')
        self.assertIsNone(result['inventoryRefusal'])
        self.assertEqual(result['status'], 'PROPOSED_PARENT_LOCK_REQUIRES_REVIEW_NOT_APPLIED')
        self.assertEqual(set(outputs.files), {'candidate-web-package.json', 'candidate-web-package-lock.json'})

    def test_proposal_inventory_refusal_is_retained_without_qualifying_or_applying_the_graph(self):
        source, pins, root = fixture(); outputs = MemoryPath({})
        with patch('web_parent_candidate.read_input', side_effect=lambda repo, name: source[name]), \
                patch('web_parent_candidate.inventory', side_effect=ReviewError('bundled graph needs a separate source binding')):
            result = inspect_candidate(None, root, pins, outputs)
        self.assertEqual(result['inventoryStatus'], 'NOT_ESTABLISHED')
        self.assertIsNone(result['inventory'])
        self.assertEqual(result['inventoryRefusal'], {'type': 'ReviewError', 'reason': 'bundled graph needs a separate source binding'})
        self.assertEqual(set(outputs.files), {'candidate-web-package.json', 'candidate-web-package-lock.json'})
        self.assertFalse(result['completeProposedGraphQualified'])
        self.assertFalse(result['applicationInputsChanged'])
        self.assertFalse(result['rootOldZodFindingWaivedOrRemediated'])
        self.assertFalse(result['newPackagesInstalledOrExecuted'])

    def test_changed_current_source_cannot_be_bound_to_a_candidate(self):
        source, pins, root = fixture(); source['web/package-lock.json'] += b' '
        with patch('web_parent_candidate.read_input', side_effect=lambda repo, name: source[name]):
            with self.assertRaises(ValueError): inspect_candidate(None, root, pins, MemoryPath({}))


if __name__ == '__main__': unittest.main()
