"""A lock-only resolver must not silently widen existing platform constraints."""

import base64
import copy
import json
import unittest

from lock_review import ReviewError
from proposal_delta import lock_delta, preserve_platform_selectors


def fixture():
    package = {'name': 'fixture', 'lockfileVersion': 3, 'packages': {'': {'name': 'fixture'}, 'node_modules/native': {
        'version': '1.0.0', 'resolved': 'https://registry.npmjs.org/native/-/native-1.0.0.tgz',
        'integrity': 'sha512-' + base64.b64encode(bytes(64)).decode(), 'os': ['linux'], 'cpu': ['x64'], 'libc': ['glibc']}}}
    candidate = copy.deepcopy(package); candidate['packages']['node_modules/native'].pop('libc')
    return package, candidate


def raw(value): return json.dumps(value).encode()


class PlatformDeltaControls(unittest.TestCase):
    def test_missing_selectors_are_carried_only_with_exact_identity_and_other_fields_preserved(self):
        before, after = fixture(); after['packages']['']['devDependencies'] = {'new': '1.0.0'}
        result, report = preserve_platform_selectors(raw(before), raw(after))
        expected = copy.deepcopy(after); expected['packages']['node_modules/native']['libc'] = ['glibc']
        self.assertEqual(json.loads(result), expected)
        self.assertEqual(report['carriedSelectorCount'], 1)
        self.assertFalse(report['sourcePublicationChangesMade'])
        self.assertFalse(report['proposalAdopted'])

    def test_changed_publication_does_not_inherit_old_selectors(self):
        before, after = fixture(); row = after['packages']['node_modules/native']
        row.update(version='2.0.0', resolved='https://registry.npmjs.org/native/-/native-2.0.0.tgz')
        generated = raw(after); result, report = preserve_platform_selectors(raw(before), generated)
        self.assertEqual(result, generated); self.assertEqual(report['carriedSelectorCount'], 0)
        self.assertEqual(len(lock_delta(raw(before), generated)['publicationChanges']), 1)

    def test_explicit_conflicting_selector_is_refused_instead_of_overwritten(self):
        before, after = fixture(); after['packages']['node_modules/native']['libc'] = ['musl']
        with self.assertRaisesRegex(ReviewError, 'conflicting explicit'): preserve_platform_selectors(raw(before), raw(after))

    def test_repeated_carry_is_idempotent_and_preserves_bytes_when_no_carry_is_needed(self):
        before, after = fixture(); first, _ = preserve_platform_selectors(raw(before), raw(after))
        second, report = preserve_platform_selectors(raw(before), first)
        self.assertEqual(second, first); self.assertEqual(report['carriedSelectorCount'], 0)

    def test_incomplete_or_noncanonical_publication_cannot_authorize_a_carry(self):
        for field, value in [('integrity', None), ('resolved', 'https://example.invalid/source'), ('version', 'latest')]:
            before, after = fixture(); before['packages']['node_modules/native'][field] = value
            with self.subTest(field=field), self.assertRaises(ReviewError): preserve_platform_selectors(raw(before), raw(after))

    def test_presence_changes_are_recorded_even_when_values_are_null(self):
        before, after = fixture(); after['packages']['node_modules/native']['newMetadata'] = None
        delta = lock_delta(raw(before), raw(after)); row, = delta['samePublicationMetadataChanges']
        self.assertFalse(row['changedFields']['newMetadata']['baselinePresent'])
        self.assertTrue(row['changedFields']['newMetadata']['candidatePresent'])
        self.assertEqual(delta['removedLocations'], [])
        self.assertFalse(delta['platformOrMigrationAcceptanceEstablished'])

    def test_added_removed_and_reclassified_locations_are_not_hidden(self):
        before, after = fixture(); after['packages']['node_modules/new'] = {'inBundle': True, 'version': '1.0.0'}
        after['packages']['node_modules/native']['inBundle'] = True
        before['packages']['node_modules/removed'] = before['packages']['node_modules/native'].copy()
        delta = lock_delta(raw(before), raw(after))
        self.assertEqual(delta['addedLocations'], ['node_modules/new'])
        self.assertEqual(delta['removedLocations'], ['node_modules/removed'])
        self.assertEqual(len(delta['sourceKindChanges']), 1)
        self.assertTrue(delta['allOriginalRowsCompared'])

    def test_aliases_and_all_three_selectors_keep_the_effective_publication_identity(self):
        before, after = fixture()
        for rows in [before['packages'], after['packages']]:
            row = rows.pop('node_modules/native'); row['name'] = 'native'; rows['node_modules/alias'] = row
        for field in ('os', 'cpu'): after['packages']['node_modules/alias'].pop(field)
        result, report = preserve_platform_selectors(raw(before), raw(after))
        self.assertEqual(report['carriedSelectorCount'], 3)
        self.assertEqual(json.loads(result)['packages'], before['packages'])


if __name__ == '__main__': unittest.main()
