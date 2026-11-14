"""Observe the complete lock delta and preserve existing platform constraints."""

import base64
import hashlib
import json
import re

from lock_review import MAX_PACKAGES, NAME, VERSION, ReviewError, decode, location_name, read_input, require

SELECTORS = ('os', 'cpu', 'libc')


def package_table(raw):
    lock = decode(raw); rows = lock.get('packages')
    require(type(lock.get('lockfileVersion')) is int and lock['lockfileVersion'] == 3, 'platform review requires lock version 3')
    require(type(rows) is dict and 1 <= len(rows) <= MAX_PACKAGES + 1 and type(rows.get('')) is dict
        and all(type(row) is dict for row in rows.values()), 'platform review package table differs')
    for location in rows:
        if location: location_name(location)
    return lock, rows


def registry_identity(location, row):
    require('link' not in row and row.get('inBundle', False) is False, 'platform carry requires an independent registry publication')
    name = row.get('name', location_name(location)); version = row.get('version'); integrity = row.get('integrity')
    require(type(name) is str and NAME.fullmatch(name) and type(version) is str and VERSION.fullmatch(version), 'invalid registry identity')
    url = 'https://registry.npmjs.org/' + name + '/-/' + name.rsplit('/', 1)[-1] + '-' + version + '.tgz'
    require(row.get('resolved') == url and type(integrity) is str and integrity.startswith('sha512-'), 'registry publication locator differs')
    try: digest = base64.b64decode(integrity[7:], validate=True)
    except ValueError as error: raise ReviewError('invalid registry publication integrity') from error
    require(len(digest) == 64 and base64.b64encode(digest).decode() == integrity[7:], 'registry publication integrity differs')
    return {'name': name, 'version': version, 'resolved': url, 'integrity': integrity}


def selector(row, field):
    values = row[field]
    require(type(values) is list and len(values) <= 32 and all(type(value) is str
        and re.fullmatch(r'!?[a-z0-9_-]+', value) for value in values), 'invalid recorded platform selector')
    return values


def changes(before, after):
    return {key: {'baselinePresent': key in before, 'candidatePresent': key in after,
        'baselineValue': before.get(key), 'candidateValue': after.get(key)}
        for key in sorted(set(before) | set(after)) if (key in before) != (key in after) or before.get(key) != after.get(key)}


def lock_delta(baseline_raw, candidate_raw):
    baseline, old = package_table(baseline_raw); candidate, new = package_table(candidate_raw)
    publications, metadata, source_kinds, root = [], [], [], changes(old[''], new[''])
    for location in sorted(set(old) & set(new) - {''}):
        fields = changes(old[location], new[location])
        if not fields: continue
        before, after = old[location], new[location]
        row = {'location': location, 'changedFields': fields}
        if before.get('inBundle', False) is not False or after.get('inBundle', False) is not False or 'link' in before or 'link' in after:
            source_kinds.append(row); continue
        old_identity, new_identity = registry_identity(location, before), registry_identity(location, after)
        row.update(baselinePublication=old_identity, candidatePublication=new_identity)
        (metadata if old_identity == new_identity else publications).append(row)
    return {'schema': 1, 'baselineLockSha256': hashlib.sha256(baseline_raw).hexdigest(),
        'candidateLockSha256': hashlib.sha256(candidate_raw).hexdigest(),
        'topLevelChanges': changes({k: v for k, v in baseline.items() if k != 'packages'}, {k: v for k, v in candidate.items() if k != 'packages'}),
        'rootChanges': root, 'publicationChanges': publications, 'samePublicationMetadataChanges': metadata,
        'sourceKindChanges': source_kinds, 'addedLocations': sorted(set(new) - set(old)), 'removedLocations': sorted(set(old) - set(new)),
        'allOriginalRowsCompared': True, 'platformOrMigrationAcceptanceEstablished': False, 'productionGate': 'NO_GO'}


def preserve_platform_selectors(baseline_raw, generated_raw):
    """Carry a missing selector only across the exact same recorded publication."""
    baseline, old = package_table(baseline_raw); candidate, new = package_table(generated_raw)
    require(baseline.get('name') == candidate.get('name'), 'platform carry project identity differs')
    carried = []
    for location in sorted(set(old) & set(new) - {''}):
        before, after = old[location], new[location]
        if before.get('inBundle', False) is not False or after.get('inBundle', False) is not False or 'link' in before or 'link' in after:
            continue
        identity = registry_identity(location, before)
        if identity != registry_identity(location, after): continue
        for field in SELECTORS:
            if field not in before: continue
            value = selector(before, field)
            if field in after:
                require(selector(after, field) == value, 'conflicting explicit platform selector requires review')
                continue
            after[field] = list(value)
            carried.append({'location': location, 'field': field, 'value': list(value), 'unchangedPublication': identity,
                'evidenceAuthority': 'PRESERVED_BASELINE_LOCK_CONSTRAINT_FOR_IDENTICAL_PUBLICATION'})
    raw = (json.dumps(candidate, indent=2) + '\n').encode() if carried else generated_raw
    return raw, {'schema': 1, 'baselineLockSha256': hashlib.sha256(baseline_raw).hexdigest(),
        'originalNpmGeneratedLockSha256': hashlib.sha256(generated_raw).hexdigest(), 'candidateLockSha256': hashlib.sha256(raw).hexdigest(),
        'carriedSelectors': carried, 'carriedSelectorCount': len(carried),
        'rawNpmOutputMustBeRetainedSeparately': True, 'sourcePublicationChangesMade': False,
        'packageManifestAuthenticationOrPlatformExecutionEstablished': False, 'applicationInputsChanged': False,
        'proposalAdopted': False, 'productionGate': 'NO_GO'}


def prepare_platform_candidate(repo, parent_root, output):
    baseline = read_input(repo, 'web/package-lock.json'); generated = read_input(parent_root, 'package-lock.json')
    preserved, report = preserve_platform_selectors(baseline, generated)
    raw_name = 'npm-generated-web-package-lock.json'
    require(not (output / raw_name).exists(), 'original npm lock output already exists')
    with (output / raw_name).open('xb') as target: target.write(generated)
    report['originalNpmOutput'] = {'path': raw_name, 'bytes': len(generated), 'sha256': hashlib.sha256(generated).hexdigest()}
    report['originalGeneratedDelta'] = lock_delta(baseline, generated)
    report['preservedCandidateDelta'] = lock_delta(baseline, preserved)
    report['onlyCarryDelta'] = lock_delta(generated, preserved)
    delta = report['onlyCarryDelta']
    require(not any(delta[key] for key in ('publicationChanges', 'sourceKindChanges', 'rootChanges',
        'topLevelChanges', 'addedLocations', 'removedLocations')), 'platform preservation changed an unrelated lock identity')
    require({(row['location'], field) for row in delta['samePublicationMetadataChanges'] for field in row['changedFields']}
        == {(row['location'], row['field']) for row in report['carriedSelectors']}, 'platform carry delta differs from the recorded selectors')
    (parent_root / 'package-lock.json').write_bytes(preserved)
    require(read_input(parent_root, 'package-lock.json') == preserved, 'preserved proposal bytes changed')
    return report
