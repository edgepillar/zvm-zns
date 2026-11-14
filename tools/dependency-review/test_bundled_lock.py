"""Bind real archive bytes to lock claims without inventing child tarballs."""

import copy
import json
import tarfile
import unittest

from bundled_lock import inventory_with_archives
from lock_review import ReviewError, inventory
from test_bundled_archive import make_publication


def fixture(parent=None, child=None, extra=None):
    raw, selected = make_publication(parent=parent, bundled=child, extra=extra)
    package = {'name': 'fixture', 'dependencies': {'a': '1.0.0'}}
    lock = {'name': 'fixture', 'lockfileVersion': 3, 'packages': {
        '': copy.deepcopy(package), 'node_modules/a': selected,
        'node_modules/a/node_modules/b': {'version': '1.0.1', 'inBundle': True, 'license': 'MIT'}}}
    if child:
        row = lock['packages']['node_modules/a/node_modules/b']
        row.update({key: child[key] for key in ('version', 'license', 'dependencies', 'optionalDependencies', 'peerDependencies', 'peerDependenciesMeta') if key in child})
        if child.get('name', 'b') != 'b': row['name'] = child['name']
    return package, lock, {'node_modules/a': raw}


def inputs(package, lock):
    return [json.dumps(value).encode() for value in (package, lock)]


class BundledLockControls(unittest.TestCase):
    def test_member_identity_uses_parent_publication_and_preserves_strict_registry_reader(self):
        p, lock, archives = fixture(); package_raw, lock_raw = inputs(p, lock)
        with self.assertRaises(ReviewError): inventory(package_raw, lock_raw)
        result = inventory_with_archives(package_raw, lock_raw, archives)
        self.assertEqual((result['packageCount'], result['registryPackageCount'], result['boundArchiveMemberCount']), (2, 1, 1))
        child = next(row for row in result['packageRecords'] if row['sourceKind'] == 'PARENT_PUBLICATION_MEMBER')
        self.assertIsNone(child['resolved']); self.assertIsNone(child['integrity'])
        self.assertEqual(child['sourceBinding']['parentLockLocation'], 'node_modules/a')
        self.assertEqual(result['rootDeclarationRoutes'][0]['declaredGraphLocations'], ['node_modules/a', 'node_modules/a/node_modules/b'])
        self.assertEqual(result['declaredBundledArchiveDependencies'][0]['status'], 'BOUND_TO_PARENT_PUBLICATION_MANIFEST')
        self.assertTrue(result['allRequiredDeclarationsHaveRecordedSourceRoute'])
        self.assertEqual(inputs(p, lock), [package_raw, lock_raw])
        for name in ['completeLockIntegrityReview', 'completeSBOM', 'applicationRuntimeReachabilityEstablished',
                'semverSatisfactionIndependentlyVerified', 'installedPlatformQualified', 'releaseAccepted']:
            self.assertIs(result[name], False)

    def test_archive_integrity_and_parent_identity_are_required(self):
        p, lock, archives = fixture()
        for change in ['integrity', 'version']:
            other = copy.deepcopy(lock); other['packages']['node_modules/a'][change] = 'unreviewed'
            with self.subTest(change=change), self.assertRaises(ReviewError): inventory_with_archives(*inputs(p, other), archives)

    def test_a_lock_flag_without_an_archive_cannot_qualify_a_member(self):
        p, lock, _ = fixture()
        with self.assertRaises(ReviewError): inventory_with_archives(*inputs(p, lock), {})

    def test_missing_or_extra_member_rows_refuse_the_whole_binding(self):
        p, lock, archives = fixture()
        missing = copy.deepcopy(lock); del missing['packages']['node_modules/a/node_modules/b']
        extra = copy.deepcopy(lock); extra['packages']['node_modules/a/node_modules/extra'] = {'version': '1.0.0', 'inBundle': True}
        for value in [missing, extra]:
            with self.subTest(rows=value), self.assertRaises(ReviewError): inventory_with_archives(*inputs(p, value), archives)

    def test_a_member_cannot_be_moved_under_another_parent(self):
        p, lock, archives = fixture()
        lock['packages']['node_modules/other/node_modules/b'] = lock['packages'].pop('node_modules/a/node_modules/b')
        with self.assertRaises(ReviewError): inventory_with_archives(*inputs(p, lock), archives)

    def test_independent_tarball_fields_and_links_are_not_fabricated_for_members(self):
        p, lock, archives = fixture()
        for field, value in [('resolved', None), ('integrity', None), ('link', False)]:
            other = copy.deepcopy(lock); other['packages']['node_modules/a/node_modules/b'][field] = value
            with self.subTest(field=field), self.assertRaises(ReviewError): inventory_with_archives(*inputs(p, other), archives)

    def test_boolean_flags_and_member_identity_are_exact(self):
        p, lock, archives = fixture()
        for field, value in [('inBundle', 'true'), ('inBundle', False), ('version', '2.0.0'), ('name', 'different'), ('optional', 'true')]:
            other = copy.deepcopy(lock); other['packages']['node_modules/a/node_modules/b'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ReviewError): inventory_with_archives(*inputs(p, other), archives)

    def test_member_metadata_is_corroborated_by_its_hashed_manifest(self):
        p, lock, archives = fixture()
        for field, value in [('license', 'Unreviewed'), ('dependencies', {'outside': '1'}), ('cpu', ['other']),
                ('peerDependencies', {'peer': '1'}), ('peerDependenciesMeta', {'peer': {'optional': True}}), ('hasInstallScript', True)]:
            other = copy.deepcopy(lock); other['packages']['node_modules/a/node_modules/b'][field] = value
            with self.subTest(field=field), self.assertRaises(ReviewError): inventory_with_archives(*inputs(p, other), archives)

    def test_parent_archive_metadata_also_matches_the_lock(self):
        p, lock, archives = fixture(); lock['packages']['node_modules/a']['peerDependencies'] = {'unreviewed': '1'}
        with self.assertRaises(ReviewError): inventory_with_archives(*inputs(p, lock), archives)

    def test_nested_resolution_and_cycles_keep_the_real_member_locations(self):
        child = {'name': 'b', 'version': '1.0.1', 'license': 'MIT', 'dependencies': {'c': '^2'}}
        extra = [('package/node_modules/c/package.json', json.dumps({'name': 'c', 'version': '2.0.0', 'dependencies': {'b': '^1'}}).encode(), tarfile.REGTYPE)]
        p, lock, archives = fixture(child=child, extra=extra)
        lock['packages']['node_modules/a/node_modules/c'] = {'version': '2.0.0', 'inBundle': True, 'dependencies': {'b': '^1'}}
        result = inventory_with_archives(*inputs(p, lock), archives)
        self.assertEqual(result['boundArchiveMemberCount'], 2)
        self.assertEqual(len(result['rootDeclarationRoutes'][0]['declaredGraphLocations']), 3)
        self.assertEqual(result['unresolvedRequiredDeclarations'], [])

    def test_aliases_use_the_member_manifest_identity(self):
        parent = {'name': 'a', 'version': '1.0.0', 'dependencies': {'b': 'npm:real@^1'}, 'bundleDependencies': ['b']}
        child = {'name': 'real', 'version': '1.0.1', 'license': 'MIT'}
        p, lock, archives = fixture(parent=parent, child=child)
        result = inventory_with_archives(*inputs(p, lock), archives)
        self.assertEqual(next(row for row in result['packageRecords'] if row['name'] == 'b')['effectiveName'], 'real')

    def test_package_internal_data_manifests_do_not_become_lock_packages(self):
        extra = [('package/node_modules/b/data/package.json', b'{}', tarfile.REGTYPE)]
        p, lock, archives = fixture(extra=extra)
        self.assertEqual(inventory_with_archives(*inputs(p, lock), archives)['boundArchiveMemberCount'], 1)

    def test_missing_regular_declarations_remain_an_open_gap(self):
        child = {'name': 'b', 'version': '1.0.1', 'license': 'MIT', 'dependencies': {'missing': '1'}}
        p, lock, archives = fixture(child=child)
        result = inventory_with_archives(*inputs(p, lock), archives)
        self.assertFalse(result['allRequiredDeclarationsHaveRecordedSourceRoute'])
        self.assertEqual(result['unresolvedRequiredDeclarations'][0]['name'], 'missing')

    def test_no_archive_path_can_silently_relax_a_registry_record(self):
        p, lock, archives = fixture(); lock['packages']['node_modules/a']['resolved'] += '?credential=redacted'
        with self.assertRaises(ReviewError): inventory_with_archives(*inputs(p, lock), archives)


if __name__ == '__main__': unittest.main()
