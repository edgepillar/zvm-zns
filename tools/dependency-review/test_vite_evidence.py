"""Exercise byte and membership checks without an installer or filesystem scratch."""

from copy import deepcopy
from io import BytesIO
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from distribution_evidence import review_traces, verify_publications
from lock_review import ReviewError
from profile_sources import pin
from vite_evidence import review_members


def artifact(members):
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return output.getvalue()


class ViteEvidenceControls(unittest.TestCase):
    def test_replay_preserves_the_artifact_bytes(self):
        members = {'npm-generated-lock.json': b'{"lockfileVersion":3}\n', 'streams/node-version.stderr.txt': b''}
        raw = artifact(members)
        self.assertEqual(review_members(raw, pin(raw)['sha256']), members)

    def test_wrong_digest_is_refused_before_member_inspection(self):
        raw = artifact({'report.json': b'{}'})
        with self.assertRaisesRegex(ReviewError, 'artifact digest'):
            review_members(raw, '0' * 64)

    def test_unlisted_input_and_stream_are_refused(self):
        for name in ('unrelated.json', 'streams/another-command.stdout.txt'):
            raw = artifact({'report.json': b'{}', name: b'ordinary text\n'})
            with self.subTest(name=name), self.assertRaisesRegex(ReviewError, 'artifact member differs'):
                review_members(raw, pin(raw)['sha256'])


class DistributionEvidenceControls(unittest.TestCase):
    def setUp(self):
        self.location = 'node_modules/example/node_modules/child'
        self.selection = {'name': 'child', 'version': '1.0.0', 'resolved': 'https://registry.npmjs.org/child/-/child-1.0.0.tgz',
            'integrity': 'sha512-' + 'A' * 86 + '=='}
        self.rows = {'node_modules/example': {}, self.location: self.selection}
        files = {'assets/app.js': pin(b'compiled'), 'notices/child-LICENSE': pin(b'original notice')}
        distribution = {'files': files}
        trace = {'observed': {'assets/app.js': {**files['assets/app.js'], 'type': 'chunk',
                'sources': ['@generated/rolldown', 'web/' + self.location + '/index.js']}},
            'publicCopies': {'notices/child-LICENSE': files['notices/child-LICENSE']}, 'nativeHeaderCandidates': {}}
        self.traces = {'normal': trace, 'fixture': deepcopy(trace)}
        self.distributions = {'normal': distribution, 'fixture': deepcopy(distribution)}

    def test_nested_lock_location_and_original_notice_are_bound(self):
        members, summary = review_traces(self.traces, self.distributions, self.rows)
        self.assertEqual(members, {self.location: {'index.js'}})
        source = {'selection': self.selection, 'originalMembers': {'index.js': pin(b'original source')},
            'originalNotices': {'LICENSE': pin(b'original notice')}}
        checked = verify_publications(self.rows, members, {self.location: source}, self.distributions, summary)
        self.assertEqual(checked['normal']['generatedFamilies'], ['@generated/rolldown'])
        self.assertEqual(checked['fixture']['locationsWithOriginalNoticeBytesInOutput'], [self.location])

    def test_trace_must_match_emitted_and_copied_bytes(self):
        for section, name in [('observed', 'assets/app.js'), ('publicCopies', 'notices/child-LICENSE')]:
            traces = deepcopy(self.traces)
            traces['normal'][section][name]['bytes'] += 1
            with self.subTest(section=section), self.assertRaises(ReviewError):
                review_traces(traces, self.distributions, self.rows)
