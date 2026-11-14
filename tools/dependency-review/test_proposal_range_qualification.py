"""A source pin alone must not admit a different tool identity or dependencies."""

import base64
import hashlib
import io
import json
import tarfile
import unittest

from lock_review import ReviewError
from proposal_range_qualification import checked_source


def fixture(dependencies=None):
    package = {'name': 'semver', 'version': '7.8.4', 'license': 'ISC', 'dependencies': dependencies or {}}
    files = {'package.json': json.dumps(package).encode(), 'index.js': b'// Data fixture; never executed.\n', 'LICENSE': b'ISC fixture\n'}
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        for name, raw in files.items():
            member = tarfile.TarInfo('package/' + name); member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    raw = output.getvalue()
    selected = {'name': 'semver', 'version': '7.8.4', 'resolved': 'https://registry.npmjs.org/semver/-/semver-7.8.4.tgz',
        'archiveBytes': len(raw), 'archiveSha256': hashlib.sha256(raw).hexdigest(),
        'integrity': 'sha512-' + base64.b64encode(hashlib.sha512(raw).digest()).decode(),
        'filePins': {name: {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()} for name, body in files.items()}}
    return raw, selected


class RangeToolSourceControls(unittest.TestCase):
    def test_exact_regular_source_members_are_required_without_execution(self):
        raw, selected = fixture()
        self.assertEqual(checked_source(raw, selected), selected['filePins'])
        del selected['filePins']['index.js']
        with self.assertRaises(ReviewError): checked_source(raw, selected)

    def test_changed_bytes_or_independent_integrity_are_refused(self):
        raw, selected = fixture()
        with self.assertRaises(ReviewError): checked_source(raw + b' ', selected)
        selected['integrity'] = 'sha512-' + base64.b64encode(bytes(64)).decode()
        with self.assertRaises(ReviewError): checked_source(raw, selected)

    def test_hash_matching_tool_with_new_runtime_dependencies_is_refused(self):
        raw, selected = fixture({'unexpected-package': '^1'})
        with self.assertRaises(ReviewError): checked_source(raw, selected)


if __name__ == '__main__': unittest.main()
