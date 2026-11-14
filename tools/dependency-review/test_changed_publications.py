"""Changed-source identity cannot be inferred from a passing version range."""

import base64
import copy
import gzip
import hashlib
import io
import json
import tarfile
import unittest

from changed_publications import review_changed_publications
from lock_review import ReviewError


def publication(version, source=b'// fixture\n', deps=None):
    manifest = {'name': 'a', 'version': version, 'license': 'MIT', 'dependencies': deps or {}}
    files = {'package.json': json.dumps(manifest).encode(), 'index.js': source, 'LICENSE': b'Fixture license\n'}
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, raw in files.items():
            member = tarfile.TarInfo('package/' + name); member.size = len(raw); archive.addfile(member, io.BytesIO(raw))
    raw = gzip.compress(output.getvalue(), mtime=0)
    row = {'version': version, 'license': 'MIT', 'dependencies': deps or {},
        'resolved': 'https://registry.npmjs.org/a/-/a-' + version + '.tgz',
        'integrity': 'sha512-' + base64.b64encode(hashlib.sha512(raw).digest()).decode()}
    return raw, row


def fixture():
    old_raw, old = publication('1.0.0'); new_raw, new = publication('1.1.0', b'// new fixture\n')
    lock = lambda row: {'name': 'fixture', 'lockfileVersion': 3, 'packages': {'': {'name': 'fixture'}, 'node_modules/a': row}}
    return lock(old), lock(new), {old['integrity']: old_raw, new['integrity']: new_raw}


def raw(value): return json.dumps(value).encode()


class ChangedPublicationControls(unittest.TestCase):
    def test_every_changed_pair_and_regular_member_is_bound_without_accepting_migration(self):
        old, new, archives = fixture(); result = review_changed_publications(raw(old), raw(new), archives)
        self.assertEqual((result['publicationPairCount'], result['uniquePublicationCount'], result['regularMemberOccurrences']), (1, 2, 6))
        self.assertEqual(result['pairs'][0]['changedMembers'], ['index.js', 'package.json'])
        self.assertTrue(result['allChangedRegistryPublicationsBound'])
        self.assertFalse(result['proposalAdopted']); self.assertFalse(result['APIOrBrowserRuntimeCompatibilityEstablished'])

    def test_missing_and_unrelated_archives_are_refused(self):
        old, new, archives = fixture(); missing = dict(archives); missing.pop(next(iter(missing)))
        extra = {**archives, 'unrelated': b'not a publication'}
        for value in [missing, extra]:
            with self.assertRaises(ReviewError): review_changed_publications(raw(old), raw(new), value)

    def test_wrong_bytes_cannot_replace_a_pinned_source(self):
        old, new, archives = fixture(); archives[next(iter(archives))] += b' '
        with self.assertRaisesRegex(ReviewError, 'SHA-512'): review_changed_publications(raw(old), raw(new), archives)

    def test_declared_dependencies_must_match_the_actual_source_manifest(self):
        old, new, archives = fixture(); new['packages']['node_modules/a']['dependencies'] = {'unreviewed': '^1'}
        with self.assertRaisesRegex(ReviewError, 'dependency declarations differ'): review_changed_publications(raw(old), raw(new), archives)

    def test_platform_metadata_cannot_disagree_with_the_hashed_manifest(self):
        old, new, archives = fixture(); new['packages']['node_modules/a']['libc'] = ['musl']
        with self.assertRaisesRegex(ReviewError, 'platform declaration differs'): review_changed_publications(raw(old), raw(new), archives)

    def test_alias_uses_share_one_source_object_without_hiding_lock_locations(self):
        old, new, archives = fixture()
        for lock in [old, new]:
            row = lock['packages']['node_modules/a']; row['name'] = 'a'
            lock['packages']['node_modules/alias'] = copy.deepcopy(row)
        result = review_changed_publications(raw(old), raw(new), archives)
        self.assertEqual(result['publicationPairCount'], 2); self.assertEqual(result['uniquePublicationCount'], 2)
        self.assertTrue(all(len(row['uses']) == 2 for row in result['publications'].values()))

    def test_added_removed_and_same_publication_metadata_stay_open(self):
        old, new, archives = fixture(); unchanged = {'version': '1.0.0',
            'resolved': 'https://registry.npmjs.org/b/-/b-1.0.0.tgz', 'integrity': 'sha512-' + base64.b64encode(bytes(64)).decode()}
        old['packages']['node_modules/b'] = {**unchanged, 'libc': ['glibc']}; new['packages']['node_modules/b'] = unchanged
        new['packages']['node_modules/bundle'] = {'inBundle': True, 'version': '1.0.0'}
        result = review_changed_publications(raw(old), raw(new), archives)
        self.assertEqual(len(result['samePublicationMetadataChanges']), 1)
        self.assertEqual(result['delta']['addedLocations'], ['node_modules/bundle'])
        self.assertFalse(result['completeProposedGraphIntegrityReview'])

    def test_conflicting_identity_for_one_digest_is_refused_before_execution(self):
        old, new, archives = fixture(); new['packages']['node_modules/other'] = {**new['packages']['node_modules/a'],
            'resolved': 'https://registry.npmjs.org/other/-/other-1.1.0.tgz'}
        old['packages']['node_modules/other'] = {**old['packages']['node_modules/a'],
            'resolved': 'https://registry.npmjs.org/other/-/other-1.0.0.tgz'}
        with self.assertRaisesRegex(ReviewError, 'conflicting publication identities'):
            review_changed_publications(raw(old), raw(new), archives)


if __name__ == '__main__': unittest.main()
