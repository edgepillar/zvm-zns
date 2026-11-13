"""In-memory archive controls; no filesystem fixture or package execution."""

import base64
import gzip
import hashlib
import io
import json
import tarfile
import unittest

from bundled_archive import inspect_archive
from lock_review import ReviewError


def make_publication(extra=None, omit=(), parent=None, bundled=None):
    parent = parent or {"name": "a", "version": "1.0.0", "dependencies": {"b": "^1"}, "bundleDependencies": ["b"]}
    bundled = bundled or {"name": "b", "version": "1.0.1", "license": "MIT"}
    entries = [("package/package.json", json.dumps(parent).encode(), tarfile.REGTYPE),
        ("package/node_modules/b/package.json", json.dumps(bundled).encode(), tarfile.REGTYPE),
        ("package/node_modules/b/LICENSE", b"Fixture notice\r\n", tarfile.REGTYPE)]
    entries = [entry for entry in entries if entry[0] not in omit] + (extra or [])
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, body, kind in entries:
            member = tarfile.TarInfo(name); member.type = kind; member.size = len(body)
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                member.linkname = "package/package.json"; member.size = 0
            archive.addfile(member, io.BytesIO(body) if kind == tarfile.REGTYPE else None)
    raw = gzip.compress(stream.getvalue(), mtime=0)
    selected = {**parent, "resolved": "https://registry.npmjs.org/a/-/a-1.0.0.tgz",
        "integrity": "sha512-" + base64.b64encode(hashlib.sha512(raw).digest()).decode()}
    return raw, selected


class ArchiveControls(unittest.TestCase):
    def test_original_manifest_notice_and_open_gates(self):
        raw, selected = make_publication()
        result = inspect_archive(raw, selected)
        self.assertEqual(result["declaredBundleCount"], 1)
        self.assertEqual(result["bundledPackages"][0]["version"], "1.0.1")
        self.assertEqual(result["originalNoticeCandidates"][0]["sha256"], hashlib.sha256(b"Fixture notice\r\n").hexdigest())
        for field in ("packageCodeOrLifecycleScriptsExecuted", "WASIRuntimeQualified", "licenseReviewComplete",
                      "semverSatisfactionIndependentlyVerified", "releaseAccepted"):
            self.assertIs(result[field], False)
        self.assertEqual(result["archiveFilesystemExtractions"], 0)
        self.assertEqual(result["packageLocationsWithoutStandaloneNoticeCandidates"], [""])

    def test_missing_declared_bundle_is_refused(self):
        raw, selected = make_publication(omit=["package/node_modules/b/package.json"])
        with self.assertRaisesRegex(ReviewError, "manifest absent"):
            inspect_archive(raw, selected)

    def test_locked_integrity_mismatch_is_refused(self):
        raw, selected = make_publication()
        selected["integrity"] = "sha512-" + base64.b64encode(bytes(64)).decode()
        with self.assertRaisesRegex(ReviewError, "SHA-512"):
            inspect_archive(raw, selected)

    def test_parent_identity_and_bundle_declaration_are_bound(self):
        raw, selected = make_publication()
        for patch in ({"version": "2.0.0"}, {"bundleDependencies": []}, {"dependencies": {"b": "^2"}}):
            with self.subTest(patch=patch), self.assertRaises(ReviewError):
                inspect_archive(raw, {**selected, **patch})

    def test_links_and_nonregular_members_refused_in_memory(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE):
            raw, selected = make_publication(extra=[("package/link", b"", kind)])
            with self.subTest(kind=kind), self.assertRaisesRegex(ReviewError, "nonregular"):
                inspect_archive(raw, selected)

    def test_unsafe_duplicate_and_case_aliased_members(self):
        for path in ("../outside", "package/../outside", "package//outside", "package/package.json", "package/PACKAGE.json"):
            raw, selected = make_publication(extra=[(path, b"{}", tarfile.REGTYPE)])
            with self.subTest(path=path), self.assertRaises(ReviewError):
                inspect_archive(raw, selected)

    def test_expansion_cap_and_corrupt_or_truncated_gzip(self):
        raw, selected = make_publication()
        with self.assertRaisesRegex(ReviewError, "expanded"):
            inspect_archive(raw, selected, expanded_limit=512)
        damaged = raw[:-8]
        selected["integrity"] = "sha512-" + base64.b64encode(hashlib.sha512(damaged).digest()).decode()
        with self.assertRaises(ReviewError):
            inspect_archive(damaged, selected)

    def test_missing_internal_dependency_is_visible(self):
        raw, selected = make_publication(bundled={"name": "b", "version": "1.0.1", "dependencies": {"absent": "^1"}})
        result = inspect_archive(raw, selected)
        self.assertEqual(result["unresolvedInternalRegularDeclarations"], [{"from": "node_modules/b", "name": "absent", "requested": "^1"}])

    def test_bundled_alias_uses_the_effective_package_identity(self):
        parent = {"name": "a", "version": "1.0.0", "dependencies": {"b": "npm:real@^1"}, "bundleDependencies": ["b"]}
        raw, selected = make_publication(parent=parent, bundled={"name": "real", "version": "1.0.1"})
        self.assertEqual(inspect_archive(raw, selected)["bundledPackages"][0]["name"], "real")

    def test_trailing_nonzero_tar_data_refused(self):
        raw, selected = make_publication()
        expanded = bytearray(gzip.decompress(raw)); expanded[-512] = 1
        changed = gzip.compress(expanded, mtime=0)
        selected["integrity"] = "sha512-" + base64.b64encode(hashlib.sha512(changed).digest()).decode()
        with self.assertRaisesRegex(ReviewError, "trailing"):
            inspect_archive(changed, selected)


if __name__ == "__main__":
    unittest.main()
