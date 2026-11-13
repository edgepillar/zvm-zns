"""Data controls for input identity and declaration-graph boundaries."""

import base64
import copy
import json
import unittest

from lock_review import ReviewError, decode, inventory, location_name


def entry(effective="a", version="1.0.0", **extra):
    return {"version": version, "resolved": "https://registry.npmjs.org/" + effective + "/-/"
            + effective.rsplit("/", 1)[-1] + "-" + version + ".tgz",
            "integrity": "sha512-" + base64.b64encode(bytes(range(64))).decode(), "license": "MIT", **extra}


class LockControls(unittest.TestCase):
    def setUp(self):
        self.package = {"name": "fixture", "dependencies": {"a": "^1.0.0"}}
        self.lock = {"name": "fixture", "lockfileVersion": 3,
                     "packages": {"": copy.deepcopy(self.package), "node_modules/a": entry()}}

    def run_inventory(self):
        return inventory(json.dumps(self.package).encode(), json.dumps(self.lock).encode())

    def rejects(self):
        with self.assertRaises(ReviewError):
            self.run_inventory()

    def test_single_package_keeps_acceptance_open(self):
        result = self.run_inventory()
        self.assertEqual(result["packageCount"], 1)
        self.assertEqual(result["rootDeclarationRoutes"][0]["declaredGraphLocations"], ["node_modules/a"])
        for name in ("applicationRuntimeReachabilityEstablished", "semverSatisfactionIndependentlyVerified",
                     "vulnerabilityScanExecuted", "licenseReviewComplete", "packagePayloadsAcquiredOrVerified", "releaseAccepted"):
            self.assertIs(result[name], False)

    def test_duplicate_members_and_constants(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'[]', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(ReviewError):
                decode(raw)

    def test_lock_schema_and_package_budget(self):
        for value in (True, 2, "3"):
            self.lock["lockfileVersion"] = value
            self.rejects()
        self.lock["lockfileVersion"] = 3
        self.lock["packages"] = {str(index): {} for index in range(8194)}
        self.rejects()

    def test_manifest_lock_disagreement(self):
        self.package["dependencies"]["a"] = "2.0.0"
        self.rejects()

    def test_root_version_disagreement(self):
        self.package["version"] = "2.0.0"
        self.rejects()

    def test_required_dependency_missing(self):
        del self.lock["packages"]["node_modules/a"]
        self.rejects()

    def test_noncanonical_and_unsafe_locations(self):
        for value in ("/node_modules/a", "node_modules/../a", "node_modules/a/extra", "node_modules/@scope", "node_modules/a//node_modules/b"):
            with self.subTest(value=value), self.assertRaises(ReviewError):
                location_name(value)
        self.assertEqual(location_name("node_modules/a/node_modules/@scope/b"), "@scope/b")

    def test_unreviewed_link_and_boolean_types(self):
        row = self.lock["packages"]["node_modules/a"]
        row["link"] = False
        self.rejects()
        del row["link"]
        row["dev"] = "false"
        self.rejects()

    def test_unreviewed_urls(self):
        row = self.lock["packages"]["node_modules/a"]
        for url in (row["resolved"] + "?token=redacted", "http://registry.npmjs.org/a/-/a-1.0.0.tgz",
                    "https://user@registry.npmjs.org/a/-/a-1.0.0.tgz", "https://example.invalid/a.tgz"):
            row["resolved"] = url
            self.rejects()

    def test_integrity_algorithm_length_and_encoding(self):
        row = self.lock["packages"]["node_modules/a"]
        for value in (None, "sha1-deadbeef", "sha512-@@@@", "sha512-" + base64.b64encode(b"short").decode()):
            row["integrity"] = value
            self.rejects()

    def test_alias_resolves_effective_publisher_package(self):
        self.package["dependencies"] = {"alias": "npm:@scope/real@^1.0.0"}
        self.lock["packages"] = {"": copy.deepcopy(self.package),
            "node_modules/alias": entry("@scope/real", name="@scope/real")}
        result = self.run_inventory()
        self.assertEqual(result["packageRecords"][0]["effectiveName"], "@scope/real")
        self.lock["packages"]["node_modules/alias"] = entry("other", name="other")
        self.rejects()

    def test_non_registry_specs_refused(self):
        for spec in ("file:../a", "git+https://example.invalid/a", "npm:broken", "https://example.invalid/a.tgz"):
            self.package["dependencies"]["a"] = spec
            self.lock["packages"][""]["dependencies"]["a"] = spec
            self.rejects()

    def test_nested_resolution_prefers_nearest_location(self):
        packages = self.lock["packages"]
        packages["node_modules/a"]["dependencies"] = {"b": "^2"}
        packages["node_modules/b"] = entry("b")
        packages["node_modules/a/node_modules/b"] = entry("b", "2.0.0")
        result = self.run_inventory()
        route = result["rootDeclarationRoutes"][0]["declaredGraphLocations"]
        self.assertEqual(route, ["node_modules/a", "node_modules/a/node_modules/b"])
        self.assertEqual(result["locationsWithoutRootDeclarationRoute"], ["node_modules/b"])

    def test_hoisted_cycles_terminate_without_runtime_claim(self):
        packages = self.lock["packages"]
        packages["node_modules/a"]["dependencies"] = {"b": "1"}
        packages["node_modules/b"] = entry("b", dependencies={"a": "1"})
        result = self.run_inventory()
        self.assertEqual(len(result["rootDeclarationRoutes"][0]["declaredGraphLocations"]), 2)
        self.assertFalse(result["applicationRuntimeReachabilityEstablished"])

    def test_optional_and_peer_absences_remain_visible(self):
        self.lock["packages"]["node_modules/a"].update(optionalDependencies={"optional": "1"}, peerDependencies={"peer": "1"})
        result = self.run_inventory()
        self.assertEqual(len(result["unresolvedDeclarations"]), 2)
        self.assertTrue(result["allRequiredDeclarationsHaveRecordedSourceRoute"])

    def test_missing_required_transitive_is_an_explicit_open_gap(self):
        self.lock["packages"]["node_modules/a"].update(optional=True, cpu=["wasm32"], dependencies={"missing": "1"})
        result = self.run_inventory()
        self.assertFalse(result["allRequiredDeclarationsHaveRecordedSourceRoute"])
        self.assertEqual(result["unresolvedRequiredDeclarations"][0]["name"], "missing")
        self.assertEqual(result["unresolvedRequiredDeclarations"][0]["parentDeclaredCPU"], ["wasm32"])
        self.assertFalse(result["completeLockIntegrityReview"])

    def test_invalid_platform_declaration(self):
        self.lock["packages"]["node_modules/a"]["cpu"] = "wasm32"
        self.rejects()

    def test_bundle_declaration_is_not_a_missing_lock_target(self):
        self.lock["packages"]["node_modules/a"].update(dependencies={"bundled": "^1"}, bundleDependencies=["bundled"])
        result = self.run_inventory()
        self.assertEqual(result["schema"], 2)
        self.assertEqual(result["unresolvedRequiredDeclarations"], [])
        self.assertEqual(result["declaredBundledArchiveDependencies"][0]["name"], "bundled")
        self.assertTrue(result["allRequiredDeclarationsHaveRecordedSourceRoute"])
        self.assertFalse(result["allRequiredDeclarationsHaveSeparateLockLocation"])
        self.assertFalse(result["bundledArchiveContentsVerified"])
        self.assertEqual(result["rootDeclarationRoutes"][0]["declaredArchiveDependencies"][0]["name"], "bundled")

    def test_bundle_alias_and_boolean_forms(self):
        row = self.lock["packages"]["node_modules/a"]
        row.update(dependencies={"bundled": "1"}, bundledDependencies=True)
        self.assertEqual(len(self.run_inventory()["declaredBundledArchiveDependencies"]), 1)
        row["bundledDependencies"] = False
        self.assertEqual(len(self.run_inventory()["unresolvedRequiredDeclarations"]), 1)
        row["bundledDependencies"] = ["bundled"]
        row["bundleDependencies"] = ["bundled"]
        self.assertEqual(len(self.run_inventory()["declaredBundledArchiveDependencies"]), 1)
        row["bundleDependencies"] = False
        self.rejects()

    def test_malformed_or_undeclared_bundles_refused(self):
        row = self.lock["packages"]["node_modules/a"]
        row["dependencies"] = {"bundled": "1"}
        for value in (["bundled", "bundled"], ["other"], {"bundled": True}, ["../outside"], 1):
            row["bundleDependencies"] = value
            self.rejects()

    def test_optional_peer_absence_has_its_own_classification(self):
        self.lock["packages"]["node_modules/a"].update(peerDependencies={"peer": "1"}, peerDependenciesMeta={"peer": {"optional": True}})
        result = self.run_inventory()
        self.assertEqual(result["unresolvedDeclarations"], [])
        self.assertEqual(result["absentOptionalPeerDeclarations"][0]["name"], "peer")

    def test_invalid_optional_peer_metadata(self):
        row = self.lock["packages"]["node_modules/a"]
        row["peerDependencies"] = {"peer": "1"}
        for value in ({"peer": {"optional": "true"}}, {"../other": {"optional": True}}, {"peer": {"unknown": True}}):
            row["peerDependenciesMeta"] = value
            self.rejects()

    def test_orphan_optional_peer_metadata_is_not_an_invented_dependency(self):
        self.lock["packages"]["node_modules/a"]["peerDependenciesMeta"] = {"orphan": {"optional": True}}
        result = self.run_inventory()
        self.assertEqual(result["packageRecords"][0]["peerMetadataWithoutDeclaration"], ["orphan"])
        self.assertEqual(result["absentOptionalPeerDeclarations"], [])

    def test_license_absence_and_install_scripts_are_observations(self):
        row = self.lock["packages"]["node_modules/a"]
        del row["license"]
        row["hasInstallScript"] = True
        result = self.run_inventory()
        self.assertEqual(result["locationsWithoutDeclaredLicense"], ["node_modules/a"])
        self.assertEqual(result["locationsDeclaringInstallScripts"], ["node_modules/a"])
        self.assertFalse(result["licenseReviewComplete"])


if __name__ == "__main__":
    unittest.main()
