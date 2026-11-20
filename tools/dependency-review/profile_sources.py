"""Verify one new hosted installation against its current-job npm cache bytes.

The cache locator is supplied by npm's bundled cacache API. No cache layout,
historical cache, cleanup, fallback transport or archive extraction is used.
"""

import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import stat
import tarfile

from lock_review import ReviewError, decode, dependencies, require
from openzeppelin_candidate import checked_name, sha
from proposal_delta import package_table, registry_identity, selector


def pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def read_regular(root, name, limit):
    checked_name(name); path = root
    for part in Path(name).parts:
        path /= part; require(not path.is_symlink(), 'linked profile source or ancestor')
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= limit, 'profile source type or byte budget')
    with path.open('rb') as stream: raw = stream.read(limit + 1)
    after = path.stat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    require(len(raw) == before.st_size and identity(before) == identity(after), 'profile source changed while reading')
    return raw


def matches_profile(row, profile):
    for field in ('os', 'cpu', 'libc'):
        if field not in row: continue
        values = selector(row, field); actual = profile[field]
        positives = [value for value in values if not value.startswith('!')]
        if '!' + actual in values or '!any' in values: return False
        if positives and actual not in positives and 'any' not in positives: return False
    return True


def package_ancestor(location, rows):
    parent = location.rsplit('/node_modules/', 1)[0] if '/node_modules/' in location else ''
    return parent if parent in rows else None


def select_profile(lock_raw, installed, profile):
    require(profile == {'os': 'linux', 'cpu': 'x64', 'libc': 'glibc'}, 'unreviewed installed profile')
    _, rows = package_table(lock_raw); selected, excluded, decisions = {}, {}, {}
    require(type(installed) is set and installed <= set(rows) - {''}, 'unbound installed package location')
    for location in sorted(set(rows) - {''}, key=lambda value: (value.count('/'), value)):
        row = rows[location]; parent = package_ancestor(location, rows)
        if parent in excluded:
            require(location not in installed, 'package installed beneath excluded parent')
            reason = {'reason': 'EXCLUDED_ANCESTOR', 'ancestor': parent}
        elif not matches_profile(row, profile):
            require(row.get('optional', False) is True and location not in installed, 'required or installed platform-mismatched package')
            reason = {'reason': 'OPTIONAL_PLATFORM_MISMATCH', 'selectors': {field: row[field] for field in ('os', 'cpu', 'libc') if field in row}}
        else:
            require(location in installed, 'profile-compatible package missing from the installation: ' + location)
            require(not row.get('inBundle', False) and 'link' not in row, 'installed bundled/link profile needs separate qualification')
            selected[location] = {'selection': registry_identity(location, row), 'lockRow': row}
            decisions[location] = {'reason': 'INSTALLED_REGISTRY_PUBLICATION'}
            continue
        excluded[location] = reason; decisions[location] = reason
    require(set(selected) == installed and len(decisions) == len(rows) - 1, 'installed profile classification incomplete')
    return {'selected': selected, 'excluded': excluded, 'decisions': decisions}


def inspect_profile_archive(raw, selection, row, *, expanded_limit=192 << 20, member_limit=8192, member_bytes=16 << 20):
    require(type(raw) is bytes and 0 < len(raw) <= 32 << 20, 'profile compressed source budget')
    require(selection['integrity'] == 'sha512-' + base64.b64encode(hashlib.sha512(raw).digest()).decode(), 'profile raw publication integrity differs')
    require(type(expanded_limit) is int and 0 < expanded_limit <= 192 << 20, 'profile expansion limit')
    require(type(member_limit) is int and 0 < member_limit <= 32768, 'profile archive member limit')
    require(type(member_bytes) is int and 0 < member_bytes <= 32 << 20, 'profile member byte limit')
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as source: expanded = source.read(expanded_limit + 1)
    require(len(expanded) <= expanded_limit and len(expanded) % 512 == 0, 'profile expanded source budget or alignment')
    seen, files, bodies, roots = set(), {}, {}, set()
    with tarfile.open(fileobj=io.BytesIO(expanded), mode='r:') as source:
        count = 0
        for member in source:
            count += 1; require(count <= member_limit, 'profile archive member count')
            name = member.name.rstrip('/') if member.isdir() else member.name
            require(type(name) is str and name.isascii() and not any(ord(char) < 32 or ord(char) == 127 for char in name), 'profile archive name encoding')
            checked_name(name); parts = name.split('/'); roots.add(parts[0])
            require(len(roots) == 1 and name.casefold() not in seen, 'profile archive root or case alias differs')
            seen.add(name.casefold())
            require((member.isfile() or member.isdir()) and not member.sparse and 0 <= member.size <= member_bytes, 'profile archive type or member budget')
            if member.isdir():
                require(member.size == 0, 'profile directory payload'); continue
            require(len(parts) >= 2, 'profile member outside package root')
            relative = '/'.join(parts[1:]); checked_name(relative)
            start, end = member.offset_data, member.offset_data + member.size
            require(0 <= start <= end <= len(expanded), 'profile archive truncated member')
            require(not any(expanded[end:((end + 511) // 512) * 512]), 'profile member nonzero padding')
            body = memoryview(expanded)[start:end]; files[relative] = pin(body)
            if relative == 'package.json': bodies[relative] = bytes(body)
        require(len(expanded) - source.offset >= 1024 and not any(expanded[source.offset:]), 'profile tar terminator or trailer')
    require('package.json' in bodies and files, 'profile publication manifest absent')
    manifest = decode(bodies['package.json'])
    require(manifest.get('name') == selection['name'] and manifest.get('version') == selection['version'], 'profile publication manifest identity differs')
    for scope in ('dependencies', 'optionalDependencies'):
        require(dependencies(manifest, scope) == dependencies(row, scope), 'profile manifest dependency declarations differ')
    return {'selection': selection, 'publication': pin(raw), 'archiveRoot': next(iter(roots)),
        'archiveMemberCount': count, 'expandedBytes': len(expanded), 'regularPayloadBytes': sum(value['bytes'] for value in files.values()),
        'filePins': files, 'manifestSha256': files['package.json']['sha256'],
        'manifestSelectors': {field: manifest[field] for field in ('os', 'cpu', 'libc') if field in manifest},
        'manifestEngines': manifest.get('engines', {}),
        'noticeCandidates': sorted(name for name in files if name.rsplit('/', 1)[-1].upper().startswith(
            ('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'COPYRIGHT', 'OFL', 'UNLICENSE'))),
        'publisherAuthenticationOrCompleteLegalReview': False}


def inspect_with_budget(raw, selection, row, budgets):
    require(budgets['schema'] == 1 and budgets['defaultArchiveMembers'] == 8192
        and budgets['maximumExplicitArchiveMembers'] == 32768, 'profile source budget model differs')
    overrides = budgets['overrides']
    require(type(overrides) is dict and len(overrides) <= 16, 'profile explicit budget count')
    for integrity, value in overrides.items():
        require(value['selection']['integrity'] == integrity and type(value['maxArchiveMembers']) is int
            and 0 < value['maxArchiveMembers'] <= 32768 and value['maxArchiveMembers'] == value['observedArchiveMembers'],
            'profile explicit source budget identity or bound')
    scoped = overrides.get(selection['integrity'])
    if scoped is not None:
        require(scoped['selection'] == selection and scoped['publication'] == pin(raw), 'profile explicit budget raw source differs')
    observed = inspect_profile_archive(raw, selection, row, member_limit=scoped['maxArchiveMembers'] if scoped else 8192)
    if scoped is not None:
        require(observed['archiveMemberCount'] == scoped['observedArchiveMembers']
            and len(observed['filePins']) == scoped['observedRegularFiles']
            and observed['expandedBytes'] == scoped['observedExpandedBytes'], 'profile measured source shape differs')
        inventory_hash = sha(json.dumps(observed['filePins'], sort_keys=True, separators=(',', ':')).encode())
        require(inventory_hash == scoped['filePinInventorySha256'], 'profile measured source inventory differs')
    return observed


def verify_profile(root, lock_raw, cache_root, cache_index, profile, source_budgets):
    _, rows = package_table(lock_raw); installed = set()
    for location in set(rows) - {''}:
        path = root / location
        if path.exists() or path.is_symlink():
            require(path.is_dir() and not path.is_symlink(), 'installed profile package is linked or not a directory')
            installed.add(location)
    classification = select_profile(lock_raw, installed, profile)
    sources, records, total_raw, total_expanded, total_files = {}, {}, 0, 0, 0
    needed = {value['selection']['integrity'] for value in classification['selected'].values()}
    require(set(cache_index) == needed, 'cache index differs from installed profile publication set')
    for location, value in sorted(classification['selected'].items()):
        selected, row = value['selection'], value['lockRow']; integrity = selected['integrity']
        if integrity not in sources:
            cached = cache_index[integrity]; require(type(cached['bytes']) is int and 0 < cached['bytes'] <= 32 << 20, 'cache source size budget')
            raw = read_regular(cache_root, cached['cacheRelative'], 32 << 20)
            require(len(raw) == cached['bytes'], 'cache source changed from API index')
            try:
                observed = inspect_with_budget(raw, selected, row, source_budgets)
            except (ValueError, OSError, EOFError, tarfile.TarError) as error:
                raise ReviewError('profile publication ' + selected['name'] + '@' + selected['version'] + ': ' + str(error)) from error
            total_raw += len(raw); total_expanded += observed['expandedBytes']; total_files += len(observed['filePins'])
            require(total_raw <= 256 << 20 and total_expanded <= 1 << 30 and total_files <= 32768, 'profile aggregate source budget')
            sources[integrity] = observed
        observed = sources[integrity]
        require(observed['selection'] == selected, 'same integrity mapped to different profile identity')
        require(matches_profile(observed['manifestSelectors'], profile), 'published manifest excludes the installed profile')
        for name, expected in observed['filePins'].items():
            require(pin(read_regular(root, location + '/' + name, 16 << 20)) == expected, 'installed profile member differs from raw source: ' + location + '/' + name)
        records[location] = {'selection': selected, 'fileCount': len(observed['filePins']), 'allPublishedRegularMembersMatch': True}
    return {'schema': 1, 'status': 'SELECTED_INSTALLED_LINUX_PROFILE_BOUND_TO_CURRENT_JOB_CACHE_PUBLICATIONS',
        'profile': profile, 'lockSha256': sha(lock_raw), 'installed': records, 'excluded': classification['excluded'],
        'decisions': classification['decisions'], 'sources': sources,
        'installedPackageLocations': len(installed), 'uniquePublications': len(sources), 'regularSourceFiles': total_files,
        'compressedSourceBytes': total_raw, 'expandedSourceBytes': total_expanded,
        'sourceSpecificBudgetsApplied': sorted(set(sources) & set(source_budgets['overrides'])),
        'rawSHA512AndInstalledMemberSHA256Verified': True, 'additionalSourceTransportForVerification': False,
        'historicalCacheAccessOrFilesystemArchiveExtraction': False, 'unknownExtraFilesAuthenticated': False,
        'otherPlatformsOrFullGraphSemanticLegalPublisherAcceptance': False, 'proposalAdopted': False, 'productionGate': 'NO_GO'}
