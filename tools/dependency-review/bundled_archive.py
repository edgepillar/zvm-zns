"""Inspect a locked npm publication in memory; never install or execute it."""

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile

from lock_review import (MAX_INPUT, NAME, ReviewError, VERSION, bundled_names, decode, dependencies,
                         effective_name, inventory, location_name, read_input, require, resolve)

MAX_COMPRESSED = 32 << 20
MAX_EXPANDED = 192 << 20
MAX_MEMBERS = 8192


def inspect_archive(raw, selected, *, expanded_limit=MAX_EXPANDED):
    review, _ = inspect_archive_with_manifests(raw, selected, expanded_limit=expanded_limit)
    return review


def inspect_archive_with_manifests(raw, selected, *, expanded_limit=MAX_EXPANDED):
    """Return the archive report and the exact manifests decoded in that pass."""
    require(type(raw) is bytes and 0 < len(raw) <= MAX_COMPRESSED, "compressed publication budget")
    require(type(expanded_limit) is int and 0 < expanded_limit <= MAX_EXPANDED, "invalid expanded budget")
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(raw).digest()).decode()
    require(integrity == selected["integrity"], "publication differs from locked SHA-512 integrity")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            expanded = stream.read(expanded_limit + 1)
        require(len(expanded) <= expanded_limit and len(expanded) % 512 == 0, "expanded tar budget or alignment")
        archive = tarfile.open(fileobj=io.BytesIO(expanded), mode="r:")
    except (OSError, EOFError, tarfile.TarError) as error:
        raise ReviewError("invalid complete gzip/tar publication") from error
    members, seen = [], set()
    package_rows, package_manifests = {}, {}
    regular_files = regular_bytes = 0
    parent_manifest_hash = None
    expanded_view = memoryview(expanded)
    try:
        for member in archive:
            require(len(members) < MAX_MEMBERS, "archive member budget")
            name = member.name.rstrip("/") if member.isdir() else member.name
            require(type(name) is str and 0 < len(name) <= 2048 and name.isascii()
                and not any(ord(char) < 32 or ord(char) == 127 for char in name)
                and "\\" not in name and ":" not in name, "unsafe archive path")
            parts = name.split("/")
            require(parts[0] == "package" and all(part not in ("", ".", "..") for part in parts), "noncanonical archive path")
            require(name.casefold() not in seen, "duplicate or case-aliased archive member")
            seen.add(name.casefold())
            require(member.isfile() or member.isdir(), "nonregular archive member")
            require(not member.sparse and member.size >= 0 and member.size <= 128 << 20, "unreviewed sparse or oversized member")
            if member.isdir():
                require(member.size == 0, "directory payload is outside this review")
                members.append({"path": name, "kind": "directory", "bytes": 0})
                continue
            start, end = member.offset_data, member.offset_data + member.size
            require(0 <= start <= end <= len(expanded), "truncated archive payload")
            body = expanded_view[start:end]
            require(len(body) == member.size, "incomplete member payload")
            require(not any(expanded[end:((end + 511) // 512) * 512]), "nonzero member padding")
            digest = hashlib.sha256(body).hexdigest()
            members.append({"path": name, "kind": "file", "bytes": len(body), "sha256": digest})
            regular_files += 1
            regular_bytes += len(body)
            if name == "package/package.json":
                require(0 < len(body) <= MAX_INPUT, "parent manifest byte budget")
                package_rows[""] = decode(bytes(body))
                parent_manifest_hash = digest
            elif name.startswith("package/node_modules/") and name.endswith("/package.json"):
                location = name[len("package/"):-len("/package.json")]
                try:
                    location_name(location)
                except ReviewError:
                    continue  # Package-internal data manifests remain hashed members.
                require(0 < len(body) <= MAX_INPUT, "bundled manifest byte budget")
                manifest = decode(bytes(body))
                require(type(manifest.get("name")) is str and NAME.fullmatch(manifest["name"])
                    and type(manifest.get("version")) is str and VERSION.fullmatch(manifest["version"]),
                    "bundled package manifest identity differs")
                package_rows[location] = manifest
                package_manifests[location] = {"name": manifest["name"], "version": manifest["version"],
                    "manifestPath": name, "manifestBytes": len(body), "manifestSha256": digest,
                    "declaredLicense": manifest.get("license"), "declaredLifecycleScripts": sorted(
                        key for key in manifest.get("scripts", {}) if key in ("preinstall", "install", "postinstall"))}
        require(len(expanded) - archive.offset >= 1024 and not any(expanded[archive.offset:]), "missing tar terminator or trailing nonzero data")
    except tarfile.TarError as error:
        raise ReviewError("invalid tar member stream") from error
    finally:
        archive.close()
    require("" in package_rows, "publication manifest absent")
    parent = package_rows[""]
    require(parent.get("name") == selected["name"] and parent.get("version") == selected["version"], "publication package identity differs")
    expected_bundles = bundled_names(selected)
    require(bundled_names(parent) == expected_bundles, "publication bundle declarations differ from lock")
    for scope in ("dependencies", "optionalDependencies"):
        require(dependencies(parent, scope) == dependencies(selected, scope), "publication dependency declarations differ from lock")
    required_bundles = []
    for name in expected_bundles:
        location = "node_modules/" + name
        require(location in package_rows, "declared bundled package manifest absent from archive")
        require(package_rows[location]["name"] == effective_name(name, dependencies(parent, "dependencies").get(
            name, dependencies(parent, "optionalDependencies").get(name))), "bundled alias identity differs")
        required_bundles.append({"declaredName": name, **package_manifests[location]})
    unresolved = []
    for location, row in sorted(package_rows.items()):
        for name, spec in sorted(dependencies(row, "dependencies").items()):
            target = resolve(location, name, package_rows)
            if target is None:
                unresolved.append({"from": location, "name": name, "requested": spec})
            else:
                require(package_rows[target]["name"] == effective_name(name, spec), "archive dependency identity differs")
    notices = [row for row in members if row["kind"] == "file" and row["path"].rsplit("/", 1)[-1].upper().startswith(
        ("LICENSE", "LICENCE", "COPYING", "NOTICE", "COPYRIGHT"))]
    unit_notices = {location: [] for location in package_rows}
    for notice in notices:
        owners = [location for location in package_rows if notice["path"].startswith(
            "package/" + (location + "/" if location else ""))]
        unit_notices[max(owners, key=len)].append(notice)
    review = {"schema": 1, "status": "LOCKED_BUNDLED_PUBLICATION_CONTENT_OBSERVED_REVIEW_REQUIRED",
        "publication": {"name": selected["name"], "version": selected["version"], "url": selected["resolved"],
            "integrity": integrity, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)},
        "expandedTarBytes": len(expanded), "archiveMemberCount": len(members),
        "regularFileCount": regular_files, "regularPayloadBytes": regular_bytes,
        "parentManifestSha256": parent_manifest_hash,
        "declaredBundleCount": len(expected_bundles), "bundledPackages": required_bundles,
        "allArchivePackageManifests": package_manifests,
        "archivePackageManifestCount": len(package_manifests), "originalNoticeCandidates": notices,
        "standaloneNoticeCandidatesByPackageLocation": unit_notices,
        "packageLocationsWithoutStandaloneNoticeCandidates": sorted(location for location, rows in unit_notices.items() if not rows),
        "unresolvedInternalRegularDeclarations": unresolved,
        "allDeclaredBundleManifestsObserved": True, "allRegularMemberSha256Observed": True,
        "archiveMembers": members, "archiveFilesystemExtractions": 0,
        "packageCodeOrLifecycleScriptsExecuted": False, "semverSatisfactionIndependentlyVerified": False,
        "publisherOrRegistryAttestationsVerified": False, "applicationRuntimeReachabilityEstablished": False,
        "WASIRuntimeQualified": False, "vulnerabilityScanExecuted": False,
        "licenseReviewComplete": False, "completeSBOM": False, "releaseAccepted": False}
    return review, package_rows


def archive_bytes(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= MAX_COMPRESSED,
                "archive must be an independent bounded regular file")
        raw = source.read(MAX_COMPRESSED + 1)
        after = os.fstat(source.fileno())
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_nlink, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    require(len(raw) == before.st_size and identity(before) == identity(after) == identity(Path(path).lstat()), "archive changed while reading")
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", choices=("web", "contracts"), required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    package_name, lock_name = args.root + "/package.json", args.root + "/package-lock.json"
    package_raw, lock_raw = read_input(root, package_name), read_input(root, lock_name)
    inventory(package_raw, lock_raw)
    selected = decode(lock_raw)["packages"][args.location]
    selected = {**selected, "name": selected.get("name", location_name(args.location))}
    result = inspect_archive(archive_bytes(args.archive), selected)
    require(read_input(root, package_name) == package_raw and read_input(root, lock_name) == lock_raw, "source changed during archive review")
    result.update(packageLockSha256=hashlib.sha256(lock_raw).hexdigest(), lockLocation=args.location,
                  sourceInputsUnchanged=True)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
