"""Reviewed archive hashes must be checked against actual selected file bytes."""

import copy
import unittest
from unittest.mock import patch

from changed_publications import review_changed_publications
from changed_source_installation import verify_selected_installation
from lock_review import ReviewError
from test_changed_publications import fixture, raw


class SelectedSourceControls(unittest.TestCase):
    def fixture(self):
        old, new, archives = fixture(); plan = review_changed_publications(raw(old), raw(new), archives)
        bodies = {'node_modules/a/package.json': b'', 'node_modules/a/index.js': b'// fixture\n', 'node_modules/a/LICENSE': b'Fixture license\n'}
        # Use the actual retained fixture package manifest, rather than a
        # reconstructed manifest with different JSON whitespace or field order.
        import io, tarfile
        first = plan['pairs'][0]['baselinePublication']['integrity']
        with tarfile.open(fileobj=io.BytesIO(archives[first]), mode='r:gz') as archive:
            bodies['node_modules/a/package.json'] = archive.extractfile('package/package.json').read()
        return raw(old), plan, bodies

    def test_every_selected_file_must_match_and_does_not_accept_runtime(self):
        lock, plan, bodies = self.fixture()
        with patch('changed_source_installation.read_publication_member', side_effect=lambda root, name, size: bodies[name]):
            result = verify_selected_installation(None, lock, plan, 'baseline')
        self.assertEqual(result['selectedRegularFileOccurrences'], 3)
        self.assertTrue(result['allReviewedSelectedSourceMembersMatch'])
        self.assertFalse(result['packageCodeExecutedByThisCheck']); self.assertFalse(result['proposalAdopted'])

    def test_wrong_lock_or_role_is_refused_before_source_consumption(self):
        lock, plan, _ = self.fixture()
        with patch('changed_source_installation.read_publication_member') as read:
            for role, value in [('other', lock), ('candidate', lock), ('baseline', lock + b' ')]:
                with self.subTest(role=role), self.assertRaises(ReviewError): verify_selected_installation(None, value, plan, role)
            read.assert_not_called()

    def test_one_changed_installed_byte_prevents_source_qualification(self):
        lock, plan, bodies = self.fixture(); bodies['node_modules/a/index.js'] = b'// altered\n'
        with patch('changed_source_installation.read_publication_member', side_effect=lambda root, name, size: bodies[name]):
            with self.assertRaisesRegex(ReviewError, 'installed source bytes differ'): verify_selected_installation(None, lock, plan, 'baseline')

    def test_unbound_or_duplicate_source_locations_are_refused(self):
        lock, plan, bodies = self.fixture()
        duplicate = copy.deepcopy(plan); duplicate['pairs'].append(duplicate['pairs'][0])
        unbound = copy.deepcopy(plan); unbound['allChangedRegistryPublicationsBound'] = False
        with patch('changed_source_installation.read_publication_member', side_effect=lambda root, name, size: bodies[name]):
            for value in [duplicate, unbound]:
                with self.assertRaises(ReviewError): verify_selected_installation(None, lock, value, 'baseline')

    def test_plan_cannot_substitute_another_source_for_the_selected_location(self):
        lock, plan, _ = self.fixture(); selected = plan['pairs'][0]['baselinePublication']['integrity']
        plan['publications'][selected]['selection']['version'] = '99.0.0'
        with self.assertRaises(ReviewError): verify_selected_installation(None, lock, plan, 'baseline')


if __name__ == '__main__': unittest.main()
