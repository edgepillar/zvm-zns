"""Read-only inventory of the two reviewed npm lockfile-v3 input graphs."""

import base64
import hashlib
import json
from pathlib import Path
import re
import stat


class ReviewError(ValueError):
    """The selected input cannot support this inventory."""


NAME = re.compile(r"(?:@[a-z0-9_.-]+/)?[a-z0-9_][a-z0-9_.-]*")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?")
SCOPES = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
MAX_INPUT = 2 << 20
MAX_PACKAGES = 8192
MAX_EDGES = 65536


def require(value, message):
    if not value:
        raise ReviewError(message)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate JSON member")
        result[key] = value
    return result


def reject_constant(_):
    raise ReviewError("non-JSON numeric constant")


def decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_INPUT, "input byte budget")
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ReviewError("invalid bounded JSON input") from error
    require(type(value) is dict, "input must be a JSON object")
    return value


def dependencies(row, scope):
    value = row.get(scope, {})
    require(type(value) is dict, "dependency declarations must be objects")
    for name, spec in value.items():
        require(type(name) is str and NAME.fullmatch(name), "unsupported package name")
        require(type(spec) is str and 0 < len(spec) <= 512 and spec.isascii()
                and not any(ord(char) < 32 or ord(char) == 127 for char in spec), "invalid dependency specification")
        effective_name(name, spec)
    return value


def effective_name(name, spec):
    if spec.startswith("npm:"):
        alias = re.fullmatch(r"npm:((?:@[a-z0-9_.-]+/)?[a-z0-9_][a-z0-9_.-]*)@(.+)", spec)
        require(alias is not None, "unsupported npm alias")
        name, spec = alias.groups()
    require(re.fullmatch(r"[0-9A-Za-z*^~<>=|+ ._-]+", spec), "unsupported non-registry dependency specification")
    return name


def bundled_names(row):
    """A publication declaration, not evidence of an archive member."""
    fields = [row[key] for key in ("bundleDependencies", "bundledDependencies") if key in row]
    require(len(fields) < 2 or fields[0] == fields[1], "conflicting bundle declarations")
    value = fields[0] if fields else []
    declared = set(dependencies(row, "dependencies")) | set(dependencies(row, "optionalDependencies"))
    if type(value) is bool:
        return sorted(declared) if value else []
    require(type(value) is list and len(value) <= MAX_PACKAGES, "invalid bundled dependency list")
    require(all(type(name) is str and NAME.fullmatch(name) for name in value), "invalid bundled dependency name")
    require(len(set(value)) == len(value) and set(value) <= declared, "duplicate or undeclared bundled dependency")
    return sorted(value)


def optional_peers(row):
    value = row.get("peerDependenciesMeta", {})
    require(type(value) is dict, "invalid peer dependency metadata")
    declared = dependencies(row, "peerDependencies")
    result = []
    for name, meta in value.items():
        require(type(name) is str and NAME.fullmatch(name) and type(meta) is dict and set(meta) <= {"optional"}, "unreviewed peer metadata")
        require("optional" not in meta or type(meta["optional"]) is bool, "invalid optional peer flag")
        if name in declared and meta.get("optional", False):
            result.append(name)
    return sorted(result)


def location_name(path):
    require(type(path) is str and 0 < len(path) <= 2048, "invalid lock location")
    parts = path.split("/")
    index, name = 0, None
    while index < len(parts):
        require(parts[index] == "node_modules" and index + 1 < len(parts), "unsupported lock location")
        index += 1
        name = parts[index]
        index += 1
        if name.startswith("@"):
            require(index < len(parts), "incomplete scoped package")
            name += "/" + parts[index]
            index += 1
        require(NAME.fullmatch(name), "unsupported package location name")
    return name


def resolve(parent, name, packages):
    """Resolve a lock location, without loading or executing a package."""
    current = parent
    while True:
        candidate = (current + "/" if current else "") + "node_modules/" + name
        if candidate in packages:
            return candidate
        if not current:
            return None
        current = current.rsplit("/node_modules/", 1)[0] if "/node_modules/" in current else ""


def inventory(package_raw, lock_raw):
    package, lock = decode(package_raw), decode(lock_raw)
    require(type(lock.get("lockfileVersion")) is int and lock["lockfileVersion"] == 3, "requires reviewed lockfile version 3")
    require(package.get("name") == lock.get("name") and type(package.get("name")) is str, "root package identity differs")
    packages = lock.get("packages")
    require(type(packages) is dict and 1 <= len(packages) <= MAX_PACKAGES + 1 and type(packages.get("")) is dict,
            "invalid package table or package budget")
    root = packages[""]
    require(root.get("name", package["name"]) == package["name"], "root table identity differs")
    require(root.get("version") == package.get("version"), "root version differs")
    for scope in SCOPES:
        require(dependencies(package, scope) == dependencies(root, scope), "manifest and lock root declarations differ")

    bundles = {path: bundled_names(row) for path, row in packages.items() if type(row) is dict}
    peers = {path: optional_peers(row) for path, row in packages.items() if type(row) is dict}
    require(not bundles[""], "root publication bundling is outside this private-project inventory")
    records = []
    for path, row in sorted(packages.items()):
        if path == "":
            continue
        name = location_name(path)
        require(type(row) is dict and "link" not in row, "linked package is outside this review")
        effective = row.get("name", name)
        require(type(effective) is str and NAME.fullmatch(effective), "invalid effective package name")
        version = row.get("version")
        require(type(version) is str and len(version) <= 256 and VERSION.fullmatch(version), "unsupported locked version")
        expected = "https://registry.npmjs.org/" + effective + "/-/" + effective.rsplit("/", 1)[-1] + "-" + version + ".tgz"
        require(row.get("resolved") == expected, "requires the exact unauthenticated npm registry tarball URL")
        integrity = row.get("integrity")
        require(type(integrity) is str and integrity.startswith("sha512-"), "requires SHA-512 integrity")
        try:
            digest = base64.b64decode(integrity[7:], validate=True)
        except ValueError as error:
            raise ReviewError("invalid SHA-512 encoding") from error
        require(len(digest) == 64 and base64.b64encode(digest).decode() == integrity[7:], "noncanonical SHA-512 digest")
        for flag in ("dev", "optional", "peer", "devOptional", "hasInstallScript"):
            require(flag not in row or type(row[flag]) is bool, "invalid package boolean")
        for field in ("os", "cpu", "libc"):
            values = row.get(field, [])
            require(type(values) is list and len(values) <= 32 and all(type(value) is str
                and re.fullmatch(r"!?[a-z0-9_-]+", value) for value in values), "invalid platform declarations")
        license_value = row.get("license")
        require(license_value is None or type(license_value) is str and 0 < len(license_value) <= 512
                and license_value.isascii() and all(32 <= ord(char) < 127 for char in license_value), "invalid declared license text")
        records.append({"location": path, "name": name, "effectiveName": effective, "version": version,
            "resolved": expected, "integrity": integrity, "declaredLicense": license_value,
            "lockDeclaredDev": row.get("dev", False), "lockDeclaredOptional": row.get("optional", False),
            "lockDeclaredPeer": row.get("peer", False), "declaredInstallScript": row.get("hasInstallScript", False),
            "declaredOS": row.get("os", []), "declaredCPU": row.get("cpu", []), "declaredLibc": row.get("libc", []),
            "declaredBundledDependencies": bundles[path], "declaredOptionalPeers": peers[path],
            "peerMetadataWithoutDeclaration": sorted(set(row.get("peerDependenciesMeta", {})) - set(row.get("peerDependencies", {})))})

    edges, unresolved, direct, archive_routes, absent_optional_peers = [], [], [], [], []
    for path, row in sorted(packages.items()):
        scopes = SCOPES if path == "" else ("dependencies", "optionalDependencies", "peerDependencies")
        for scope in scopes:
            for name, spec in sorted(dependencies(row, scope).items()):
                target = resolve(path, name, packages)
                edge = {"from": path, "scope": scope, "name": name, "requested": spec, "to": target}
                if scope in ("dependencies", "optionalDependencies") and name in bundles[path]:
                    archive_routes.append({"from": path, "scope": scope, "name": name, "requested": spec,
                        "effectiveName": effective_name(name, spec), "parentArchiveURL": row["resolved"],
                        "parentArchiveIntegrity": row["integrity"], "coincidentLockLocation": target,
                        "status": "DECLARED_BUNDLED_ARCHIVE_CONTENT_NOT_VERIFIED"})
                elif target is None and scope == "peerDependencies" and name in peers[path]:
                    absent_optional_peers.append({**edge, "status": "OPTIONAL_PEER_NOT_RECORDED"})
                elif target is None:
                    require(path != "", "root dependency has no locked target")
                    edge["parentLockDeclaredOptional"] = row.get("optional", False)
                    edge["parentDeclaredOS"] = row.get("os", [])
                    edge["parentDeclaredCPU"] = row.get("cpu", [])
                    unresolved.append(edge)
                else:
                    require(packages[target].get("name", location_name(target)) == effective_name(name, spec),
                            "effective package identity differs from declaration")
                    edges.append(edge)
                    if path == "":
                        direct.append(edge)
                require(sum(map(len, (edges, unresolved, archive_routes, absent_optional_peers))) <= MAX_EDGES, "dependency edge budget")
    adjacency = {}
    for edge in edges:
        adjacency.setdefault(edge["from"], set()).add(edge["to"])
    routes, covered = [], set()
    for edge in direct:
        seen, pending = set(), [edge["to"]]
        while pending:
            here = pending.pop()
            if here in seen:
                continue
            seen.add(here)
            pending.extend(adjacency.get(here, set()) - seen)
        covered.update(seen)
        routes.append({"scope": edge["scope"], "name": edge["name"], "lockedTarget": edge["to"],
                       "declaredGraphLocations": sorted(seen), "declaredArchiveDependencies": [
                           {"from": row["from"], "name": row["name"], "parentArchiveIntegrity": row["parentArchiveIntegrity"]}
                           for row in archive_routes if row["from"] in seen]})
    return {"schema": 2, "status": "LOCK_AND_BUNDLED_DECLARATIONS_OBSERVED_REVIEW_REQUIRED", "lockfileVersion": 3,
        "packageJsonSha256": hashlib.sha256(package_raw).hexdigest(), "packageLockSha256": hashlib.sha256(lock_raw).hexdigest(),
        "packageCount": len(records), "packageRecords": records, "resolvedDeclarationEdges": edges,
        "unresolvedDeclarations": unresolved, "rootDeclarationRoutes": routes,
        "unresolvedRequiredDeclarations": [row for row in unresolved if row["scope"] == "dependencies"],
        "declaredBundledArchiveDependencies": archive_routes, "absentOptionalPeerDeclarations": absent_optional_peers,
        "allRequiredDeclarationsHaveRecordedSourceRoute": not any(row["scope"] == "dependencies" for row in unresolved),
        "allRequiredDeclarationsHaveSeparateLockLocation": not any(row["scope"] == "dependencies" for row in unresolved + archive_routes),
        "locationsWithoutRootDeclarationRoute": sorted(set(packages) - {""} - covered),
        "locationsWithoutDeclaredLicense": [row["location"] for row in records if row["declaredLicense"] is None],
        "locationsDeclaringInstallScripts": [row["location"] for row in records if row["declaredInstallScript"]],
        "scope": "All lock locations, including development and optional/platform packages; no installed platform projection.",
        "packagePayloadsAcquiredOrVerified": False, "publisherOrRegistryAttestationsVerified": False,
        "bundledArchiveContentsVerified": False,
        "semverSatisfactionIndependentlyVerified": False, "vulnerabilityScanExecuted": False,
        "applicationRuntimeReachabilityEstablished": False, "licenseReviewComplete": False,
        "installedPlatformQualified": False, "completeLockIntegrityReview": False,
        "completeSBOM": False, "releaseAccepted": False}


def read_input(root, relative):
    current = root
    for part in Path(relative).parts:
        current /= part
        require(not current.is_symlink(), "linked source input or ancestor")
    before = current.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= MAX_INPUT, "source file budget or type")
    with current.open("rb") as source:
        raw = source.read(MAX_INPUT + 1)
    after = current.stat()
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_nlink, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    require(len(raw) == before.st_size and identity(before) == identity(after), "source changed while reading")
    return raw


def main():
    root = Path(__file__).resolve().parents[2]
    inputs = {name: read_input(root, name) for folder in ("contracts", "web")
              for name in (folder + "/package.json", folder + "/package-lock.json")}
    reports = {folder: inventory(inputs[folder + "/package.json"], inputs[folder + "/package-lock.json"])
               for folder in ("contracts", "web")}
    require(all(read_input(root, name) == raw for name, raw in inputs.items()), "source changed during review")
    print(json.dumps({"schema": 1, "roots": reports, "sourceInputsUnchanged": True,
        "dependenciesInstalled": False, "applicationOrLifecycleCodeExecuted": False}, sort_keys=True))


if __name__ == "__main__":
    main()
