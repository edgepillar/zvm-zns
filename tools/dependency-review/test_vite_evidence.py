"""Exercise byte and membership checks without an installer or filesystem scratch."""

from copy import deepcopy
from io import BytesIO
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from distribution_evidence import review_traces, verify_publications
from distribution_notices import NOTICE_INDEX, verify_notice_index
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
        self.rolldown = {'name': 'rolldown', 'version': '1.2.19', 'resolved': 'https://registry.npmjs.org/rolldown/-/rolldown-1.2.19.tgz',
            'integrity': self.selection['integrity']}
        self.rows = {'node_modules/example': {}, self.location: self.selection, 'node_modules/rolldown': self.rolldown}
        files = {'assets/app.js': pin(b'compiled'), 'notices/child-LICENSE': pin(b'original notice')}
        distribution = {'files': files}
        trace = {'observed': {'assets/app.js': {**files['assets/app.js'], 'type': 'chunk',
                'sources': ['@generated/rolldown/runtime', 'web/' + self.location + '/index.js']}},
            'publicCopies': {'notices/child-LICENSE': files['notices/child-LICENSE']},
            'nativeHeaderCandidates': {}, 'tailwindCssBanners': {}}
        self.traces = {'normal': trace, 'fixture': deepcopy(trace)}
        self.distributions = {'normal': distribution, 'fixture': deepcopy(distribution)}

    def test_nested_lock_location_and_original_notice_are_bound(self):
        members, summary = review_traces(self.traces, self.distributions, self.rows)
        self.assertEqual(members, {self.location: {'index.js'}, 'node_modules/rolldown': set()})
        source = {'selection': self.selection, 'originalMembers': {'index.js': pin(b'original source')},
            'originalNotices': {'LICENSE': pin(b'original notice')}}
        runtime = {'selection': self.rolldown, 'originalMembers': {}, 'originalNotices': {}}
        checked = verify_publications(self.rows, members, {self.location: source, 'node_modules/rolldown': runtime},
            self.distributions, summary)
        self.assertEqual(checked['normal']['generatedFamilies'], ['@generated/rolldown/runtime'])
        self.assertEqual(checked['normal']['generatedPackageLocations'], {'@generated/rolldown/runtime': 'node_modules/rolldown'})
        self.assertEqual(checked['fixture']['locationsWithOriginalNoticeBytesInOutput'], [self.location])

    def test_final_banner_and_known_virtual_roles_add_locked_contributors(self):
        self.rows['node_modules/tailwindcss'] = {'version': '4.3.3'}
        self.rows['node_modules/@vitejs/plugin-vue'] = {'version': '6.0.9'}
        stage = self.traces['normal']
        css_path = 'assets/app.css'
        css = pin(b'compiled stylesheet')
        self.distributions['normal']['files'][css_path] = css
        stage['observed'][css_path] = {**css, 'type': 'asset', 'sources': ['@generated/tailwindcss/4.3.3']}
        stage['tailwindCssBanners'][css_path] = '4.3.3'
        stage['observed']['assets/app.js']['sources'][1:1] = ['@generated/unresolved', '@generated/vue-export-helper']
        members, summary = review_traces(self.traces, self.distributions, self.rows)
        self.assertEqual(members['node_modules/tailwindcss'], {'index.css', 'theme.css', 'preflight.css', 'utilities.css'})
        self.assertEqual(members['node_modules/@vitejs/plugin-vue'], set())
        self.assertEqual(summary['normal']['outputsWithUnresolvedOrigins'], ['assets/app.js'])
        self.assertEqual(summary['normal']['packageLocations'], [self.location])
        self.rows['node_modules/tailwindcss']['version'] = '4.3.4'
        with self.assertRaisesRegex(ReviewError, 'banner version differs'):
            review_traces(self.traces, self.distributions, self.rows)
        stage['tailwindCssBanners'].clear()
        with self.assertRaisesRegex(ReviewError, 'differs from the final CSS banner'):
            review_traces(self.traces, self.distributions, self.rows)

    def test_trace_must_match_emitted_and_copied_bytes(self):
        for section, name in [('observed', 'assets/app.js'), ('publicCopies', 'notices/child-LICENSE')]:
            traces = deepcopy(self.traces)
            traces['normal'][section][name]['bytes'] += 1
            with self.subTest(section=section), self.assertRaises(ReviewError):
                review_traces(traces, self.distributions, self.rows)

    def test_shipped_index_requires_exact_archive_and_output_bytes(self):
        import json

        path = 'notices/npm/child@1.0.0/LICENSE'
        value = pin(b'original notice')
        source = {self.location: {'selection': self.selection, 'originalNotices': {'LICENSE': value}}}
        entry = {'location': self.location, 'name': 'child', 'version': '1.0.0', 'license': 'MIT',
            'notices': [{'member': 'LICENSE', 'file': path, **value}]}
        text = json.dumps({'schema': 1, 'packages': [entry]})
        distribution = {'files': {NOTICE_INDEX: pin(text.encode()), path: value}}
        result = verify_notice_index(text, distribution, self.rows, source, {self.location})
        self.assertEqual(result['locationsWithOriginalNotices'], [self.location])
        distribution['files'][path] = pin(b'different text')
        with self.assertRaisesRegex(ReviewError, 'shipped notice bytes differ'):
            verify_notice_index(text, distribution, self.rows, source, {self.location})
