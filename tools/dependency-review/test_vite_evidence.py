"""Exercise byte and membership checks without an installer or filesystem scratch."""

from io import BytesIO
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

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
