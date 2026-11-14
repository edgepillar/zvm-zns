"""Memory-only archive controls; no browser, filesystem fixture or network use."""

import io
import stat
import struct
import unittest
import zipfile

from browser_archive import inspect_stream, pin, MAX_MEMBERS
from lock_review import ReviewError


def elf(machine=62):
    value = bytearray(64); value[:7] = b'\x7fELF\x02\x01\x01'
    value[16:24] = struct.pack('<HHI', 3, machine, 1)
    return bytes(value)


def fixture(extra=(), chrome=None, compression=zipfile.ZIP_DEFLATED):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, body, mode in [('chrome-linux64/chrome', elf() if chrome is None else chrome, stat.S_IFREG | 0o755),
            ('chrome-linux64/ABOUT', b'Synthetic test notice\n', stat.S_IFREG | 0o644), *extra]:
            member = zipfile.ZipInfo(name); member.create_system = 3; member.external_attr = mode << 16
            member.compress_type = compression; archive.writestr(member, body)
    return output.getvalue()


class BrowserArchiveTests(unittest.TestCase):
    def inspect(self, raw): return inspect_stream(io.BytesIO(raw), pin(raw))

    def test_complete_bytes_modes_notice_and_no_execution(self):
        raw = fixture(); result = self.inspect(raw)
        self.assertEqual(result['regularFiles'], 2)
        self.assertEqual(result['filePins']['chrome']['sha256'], pin(elf())['sha256'])
        self.assertEqual(result['filePins']['chrome']['unixPermissions'], 0o755)
        self.assertEqual(result['noticeCandidates'], ['ABOUT'])
        self.assertFalse(result['archiveFilesystemExtractionOrBrowserExecution'])

    def test_raw_sha_refusal(self):
        raw = fixture()
        with self.assertRaises(ReviewError): inspect_stream(io.BytesIO(raw), {**pin(raw), 'sha256': '0' * 64})

    def test_raw_length_refusal(self):
        raw = fixture()
        with self.assertRaises(ReviewError): inspect_stream(io.BytesIO(raw), {**pin(raw), 'bytes': len(raw) + 1})

    def test_trailing_payload_refusal(self):
        with self.assertRaises(ReviewError): self.inspect(fixture() + b'other-payload')

    def test_member_count_refusal_before_directory_parse(self):
        raw = bytearray(fixture()); raw[-14:-10] = struct.pack('<HH', MAX_MEMBERS + 1, MAX_MEMBERS + 1)
        with self.assertRaises(ReviewError): self.inspect(bytes(raw))

    def test_symbolic_link_refusal(self):
        with self.assertRaises(ReviewError): self.inspect(fixture([('chrome-linux64/link', b'chrome', stat.S_IFLNK | 0o777)]))

    def test_fifo_metadata_refusal_without_filesystem_fixture(self):
        with self.assertRaises(ReviewError): self.inspect(fixture([('chrome-linux64/fifo', b'', stat.S_IFIFO | 0o600)]))

    def test_protected_name_refusal(self):
        with self.assertRaises(ReviewError): self.inspect(fixture([('chrome-linux64/.env', b'x', stat.S_IFREG | 0o600)]))

    def test_file_ancestor_refusal_in_both_orders(self):
        rows = [('chrome-linux64/a', b'x', stat.S_IFREG | 0o644), ('chrome-linux64/a/child', b'x', stat.S_IFREG | 0o644)]
        for ordered in [rows, list(reversed(rows))]:
            with self.subTest(order=ordered):
                with self.assertRaises(ReviewError): self.inspect(fixture(ordered))

    def test_traversal_refusal(self):
        with self.assertRaises(ReviewError): self.inspect(fixture([('chrome-linux64/../outside', b'x', stat.S_IFREG | 0o644)]))

    def test_foreign_root_refusal(self):
        with self.assertRaises(ReviewError): self.inspect(fixture([('other-root/file', b'x', stat.S_IFREG | 0o644)]))

    def test_case_alias_refusal(self):
        with self.assertRaises(ReviewError): self.inspect(fixture([('chrome-linux64/about', b'x', stat.S_IFREG | 0o644)]))

    def test_directory_payload_refusal(self):
        with self.assertRaises(ReviewError): self.inspect(fixture([('chrome-linux64/directory/', b'x', stat.S_IFDIR | 0o755)]))

    def test_non_elf_refusal(self):
        with self.assertRaises(ReviewError): self.inspect(fixture(chrome=b'x' * 64))

    def test_wrong_architecture_refusal(self):
        with self.assertRaises(ReviewError): self.inspect(fixture(chrome=elf(machine=183)))

    def test_unsupported_compression_refusal(self):
        with self.assertRaises(ReviewError): self.inspect(fixture(compression=zipfile.ZIP_BZIP2))


if __name__ == '__main__': unittest.main()
