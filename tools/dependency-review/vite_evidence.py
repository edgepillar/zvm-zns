"""Replay the exact Vite review artifact in a fresh hosted job."""

import argparse
from io import BytesIO
import os
from pathlib import Path
import re
import stat
import subprocess
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from browser_staging import hosted_only
from compiled_labels import canonical_sha256
from distribution_evidence import (OUTPUT_EVIDENCE, has_tailwind_style_import, review_traces,
    verify_notice_indexes, verify_publications)
from lock_review import NAME, decode, read_input, require
from openzeppelin_candidate import checked_name, encoded, write_json
from profile_sources import pin, read_regular
from proposal_delta import package_table
from vite_upgrade import PLATFORM_PLAN, LOCATION, PUBLICATION, RELEASE_NOTICE, candidate_lock, changed_publications, review_platform_installation

MAX_ARCHIVE = 1 << 20
MAX_MEMBER = 2 << 20
MAX_PAYLOAD = 6 << 20
INPUTS = {'report.json', 'candidate-package.json', 'npm-generated-lock.json', 'candidate-lock.json',
    'vite-compiled-labels.json', OUTPUT_EVIDENCE}
COMMANDS = ('node-version', 'npm-version', 'candidate-lock-resolution', 'candidate-install',
    'application-cache-index', 'application-build', 'fixture-application-build')


def review_members(raw, digest):
    require(0 < len(raw) <= MAX_ARCHIVE and pin(raw)['sha256'] == digest, 'candidate artifact digest or byte cap differs')
    require(raw.startswith(b'PK\x03\x04'), 'candidate artifact must be a ZIP file')
    files, total = {}, 0
    with ZipFile(BytesIO(raw)) as archive:
        require(0 < len(archive.infolist()) <= len(INPUTS) + 2 * len(COMMANDS), 'candidate artifact member budget')
        for member in archive.infolist():
            name = member.filename
            is_stream = re.fullmatch(r'streams/([a-z-]+)\.(stdout|stderr)\.txt', name)
            require(name == member.orig_filename and name not in files and (name in INPUTS or
                is_stream and is_stream[1] in COMMANDS), 'candidate artifact member differs')
            file_type = stat.S_IFMT(member.external_attr >> 16)
            require(file_type in (0, stat.S_IFREG) and not member.is_dir() and not member.flag_bits & 1
                and member.compress_type in (ZIP_STORED, ZIP_DEFLATED), 'candidate artifact member type differs')
            total += member.file_size
            require(member.file_size <= MAX_MEMBER and total <= MAX_PAYLOAD, 'candidate artifact payload cap')
            with archive.open(member) as source:
                body = source.read(member.file_size + 1)
            require(len(body) == member.file_size, 'candidate artifact member length differs')
            files[name] = body
    return files


def verify_pin(value, maximum):
    require(type(value) is dict and set(value) == {'bytes', 'sha256'} and type(value['bytes']) is int
        and 0 < value['bytes'] <= maximum and type(value['sha256']) is str
        and re.fullmatch(r'[0-9a-f]{64}', value['sha256']), 'candidate evidence pin differs')


def review_commands(members, commands):
    require(tuple(value['label'] for value in commands) == COMMANDS, 'candidate command sequence differs')
    expected = set(INPUTS) - {'candidate-lock.json'}
    for row in commands:
        require(row['actualExit'] == 0 and row['outputComplete'] is True and row['terminationReason'] is None,
            'candidate command did not complete')
        require(set(row['streams']) == {'stdout', 'stderr'}, 'candidate command stream roles differ')
        for role, stream in row['streams'].items():
            path = 'streams/' + row['label'] + '.' + role + '.txt'
            require(stream['path'] == path and stream['eofObserved'] is True, 'candidate command stream did not complete')
            require(pin(members[path]) == {key: stream[key] for key in ['bytes', 'sha256']}, 'candidate stream digest differs')
            expected.add(path)
    return expected


def review_notice_evidence(rows, report):
    selected = changed_publications(rows, report['lockDelta'])
    installed = report['installedChangedPublications']
    absent = report['absentOptionalChangedLocations']
    require(absent == sorted(set(absent)) and not set(absent) & set(installed)
        and set(selected) == set(installed) | set(absent) and LOCATION in installed, 'candidate publication coverage differs')
    require(all(rows[location].get('optional') is True for location in absent), 'candidate required publication is absent')
    for location, record in installed.items():
        require(record['selection'] == selected[location], 'candidate notice publication differs')
        require(record['lockSelectors'] == {field: rows[location][field] for field in ('os', 'cpu', 'libc') if field in rows[location]},
            'candidate platform selector evidence differs')
        require(type(record['manifestSelectors']) is dict and set(record['manifestSelectors']) <= {'os', 'cpu', 'libc'},
            'candidate manifest selector evidence differs')
        verify_pin(record['archive'], 32 << 20)
        verify_pin(record['originalManifest'], 1 << 20)
        for path, notice in record['originalNotices'].items():
            checked_name(path)
            verify_pin(notice, 1 << 20)
    publication = report['viteArchive']
    vite = installed[LOCATION]
    require(report['archivedNoticeMatchesReleaseSource'] is True and publication['selection'] == PUBLICATION
        and publication['publication'] == vite['archive'] and len(publication['filePins']) == 37
        and publication['filePins']['package.json'] == vite['originalManifest']
        and publication['filePins']['LICENSE.md'] == vite['originalNotices']['LICENSE.md'] == RELEASE_NOTICE,
        'candidate Vite archive notice binding differs')
    names = report['releaseNoticeDependencyNames']
    require(0 < len(names) <= 256 and names == sorted(set(names)) and all(NAME.fullmatch(name) for name in names),
        'candidate release notice package headings differ')
    return installed, absent


def replay(repo, members, source, run_id, attempt):
    report = decode(members['report.json'])
    baseline = read_input(repo, 'web/package-lock.json')
    plan = read_input(repo, 'tools/dependency-review/application-runtime.json')
    require(report['status'] == 'VITE_CANDIDATE_APPLICATION_BUILDS_OBSERVED'
        and report['schema'] == 1 and report['producerCommit'] == source and report['coreCommit'] == decode(plan)['coreCommit']
        and report['runId'] == run_id and report['runAttempt'] == attempt and report['publicationSelection'] == PUBLICATION
        and report['baselineLock'] == pin(baseline) and report['baselinePlan'] == pin(plan), 'candidate producer source, run or inputs differ')
    expected_files = review_commands(members, report['commands'])
    expected_package = decode(read_input(repo, 'web/package.json'))
    expected_package['devDependencies']['vite'] = PUBLICATION['version']
    require(members['candidate-package.json'] == encoded(expected_package)
        and pin(members['candidate-package.json']) == report['candidatePackage'], 'candidate package manifest differs')
    generated = members['npm-generated-lock.json']
    selected, review = candidate_lock(baseline, generated, read_input(repo, PLATFORM_PLAN))
    require(all(report[key] == value for key, value in review.items()), 'replayed lock comparison differs from the producer')
    if selected != generated:
        expected_files.add('candidate-lock.json')
        require(selected == members['candidate-lock.json'], 'replayed platform carries differ from the selected lock')
    require(set(members) == expected_files, 'candidate artifact files differ from the command and lock records')
    runtime_path = 'web/vendor/chromium-bidi-157-reviewed/manifest.json'
    runtime = decode(read_input(repo, runtime_path))
    runtime['baseLockSha256'] = pin(selected)['sha256']
    require(pin(encoded(runtime)) == report['candidateRuntimeManifest'], 'candidate runtime manifest derivation differs')
    labels = decode(members['vite-compiled-labels.json'])
    require(canonical_sha256(labels) == report['compiledLabels']['inventorySha256'], 'candidate compiled label evidence differs')
    _, rows = package_table(selected)
    installed, absent = review_notice_evidence(rows, report)
    platform = review_platform_installation(review['publishedLibc'], installed, absent)
    require(platform == report['nativePlatformInstallation'], 'replayed native installation differs')
    evidence_raw = members[OUTPUT_EVIDENCE]
    require(pin(evidence_raw) == report['distributionEvidence'], 'distribution evidence receipt differs')
    distribution_evidence = decode(evidence_raw)
    require(distribution_evidence['schema'] == 3 and distribution_evidence['selectedLockSha256'] == pin(selected)['sha256'],
        'distribution lock binding differs')
    distributions = {'normal': report['normalDistribution'], 'fixture': report['fixtureBuild']['distribution']}
    member_paths, stage_reports = review_traces(distribution_evidence['traces'], distributions, rows,
        has_tailwind_style_import(repo))
    package_sources = distribution_evidence['packageSources']
    for row in package_sources.values():
        verify_pin(row['archive'], 32 << 20)
        for path, value in {**row['originalMembers'], **row['originalNotices']}.items():
            checked_name(path)
            if value != pin(b''):
                verify_pin(value, 16 << 20)
    distribution_summary = verify_publications(rows, member_paths, package_sources, distributions, stage_reports)
    verify_notice_indexes(distribution_evidence['traces'], distributions, rows, package_sources, distribution_summary)
    require(distribution_summary == distribution_evidence['summary'], 'replayed distribution summary differs')
    return {'candidateLock': pin(selected), 'generatedLock': pin(generated), 'lockLocations': len(rows) - 1,
        'noticeEvidence': installed, 'absentOptionalChangedLocations': absent,
        'publishedLibc': review['publishedLibc'], 'nativePlatformInstallation': platform,
        'distributionEvidence': pin(evidence_raw), 'distributionSummary': distribution_summary,
        'distributionPackageNotices': {location: {key: row[key] for key in ('selection', 'manifestLicense', 'originalNotices')}
            for location, row in package_sources.items()},
        'releaseNoticeDependencyNames': report['releaseNoticeDependencyNames'],
        'compiledLabelInventorySha256': report['compiledLabels']['inventorySha256'],
        'lockDeltaCounts': {key: len(review['lockDelta'][key]) for key in ['addedLocations', 'removedLocations',
            'publicationChanges', 'samePublicationMetadataChanges']}, 'replayedCommandStreams': 2 * len(COMMANDS),
        'reviewedRuntimeGraphLocations': len(review['unchangedRuntimeLocations'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', type=Path, required=True)
    args = parser.parse_args()
    hosted_only()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'requires a hosted job')
    root = Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    require(args.download == root / 'zns-vite-review' and args.download.resolve(strict=True) == args.download,
        'candidate archive must be in the isolated download directory')
    entries = list(args.download.iterdir())
    require(len(entries) == 1, 'expected one candidate artifact archive')
    artifact_id = os.environ['VITE_ARTIFACT_ID']
    digest = os.environ['VITE_ARTIFACT_DIGEST'].removeprefix('sha256:')
    require(re.fullmatch(r'[0-9]+', artifact_id) and re.fullmatch(r'[0-9a-f]{64}', digest), 'candidate artifact identity differs')
    raw = read_regular(args.download, entries[0].name, MAX_ARCHIVE)
    repo = Path(__file__).resolve().parents[2]
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    run_id, attempt = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    checked = replay(repo, review_members(raw, digest), source, run_id, attempt)
    write_json(root / 'zns-vite-review-result.json', {'schema': 1, 'status': 'VITE_CANDIDATE_LOCK_REPLAYED',
        'source': source, 'runId': run_id, 'attempt': attempt, 'artifactId': artifact_id, 'artifact': pin(raw),
        **checked, 'producerPublicationEvidenceRevalidated': True, 'packageInstallOrBrowserRun': False,
        'compiledCodeVersionAndCompleteShippedLicenseReview': False, 'productionGate': 'NO_GO'})
    print('### Vite 8 lock and notice replay\n')
    print(f"Selected lock SHA-256 `{checked['candidateLock']['sha256']}` covers {checked['lockLocations']} locations.")
    delta = checked['lockDeltaCounts']
    print(f"The lock adds {delta['addedLocations']} locations, removes {delta['removedLocations']} and changes "
        f"{delta['publicationChanges']} existing publication identities.\n")
    print(f"Replayed {checked['replayedCommandStreams']} command streams. Verified notice records for "
        f"{len(checked['noticeEvidence'])} changed installed locations. "
        f"{len(checked['absentOptionalChangedLocations'])} changed optional locations were absent.\n")
    published = checked['publishedLibc']
    platform = checked['nativePlatformInstallation']
    print(f"Restored {len(published['carriedLocations'])} published libc selectors. The glibc job installed "
        f"{len(platform['installedLocations'])} matching native publications.")
    print(f"The {len(platform['excludedByLibc'])} packages excluded by libc represent "
        f"{platform['excludedUnpackedBytesFromRegistry']:,} unpacked bytes in npm registry metadata.\n")
    for location, row in checked['noticeEvidence'].items():
        license_value = row['manifestLicense']
        declared = (license_value if isinstance(license_value, str) and re.fullmatch(r'[A-Za-z0-9.+() -]{1,256}', license_value)
            else 'unclassified')
        print(f"- `{location}@{row['selection']['version']}` declares `{declared}` and has {len(row['originalNotices'])} notice files.")
    omitted_libc = [location for location, row in checked['noticeEvidence'].items()
        if 'libc' in row['manifestSelectors'] and 'libc' not in row['lockSelectors']]
    if omitted_libc:
        print('\nThe lock omits a published libc selector for ' + ', '.join(omitted_libc) + '.')
    print(f"\nThe pinned Vite release notice names {len(checked['releaseNoticeDependencyNames'])} packages.")
    print('\n### Vite 8 static distribution evidence\n')
    for stage, row in checked['distributionSummary'].items():
        print(f"- The {stage} build contains {row['outputFiles']} files, with {len(row['packageLocations'])} reported npm origins, "
            f"{len(row['standaloneNativeCandidates'])} standalone native candidates and "
            f"{len(row['locationsWithOriginalNoticeBytesInOutput'])} npm origins with exact original notice bytes in the output.")
        families = ', '.join(row['generatedFamilies']) or 'none recorded'
        print(f"  Generated origin categories are {families}. {row['assetsWithoutReportedOrigins']} assets lack origin evidence.")
        for role, location in row['generatedPackageLocations'].items():
            selection = checked['distributionPackageNotices'][location]['selection']
            print(f"  {role} maps to {selection['name']}@{selection['version']}.")
        for name, version in row['tailwindCssBanners'].items():
            print(f"  The final CSS asset {name} contains the Tailwind {version} publication banner.")
        for name, sources in list(row['stylesheetInputs'].items())[:12]:
            print(f"  Vite links {name} to " + ', '.join(sources[:12]) + '.')
        for label, names in (('Assets without origin evidence', row['assetsWithoutOriginNames']),
                ('Outputs with unresolved origins', row['outputsWithUnresolvedOrigins'])):
            if names:
                print(f"  {label} ({len(names)}): " + ', '.join(names[:12]) + '.')
        notices = row['shippedNotices']
        print(f"  The shipped index covers {len(notices['locationsWithOriginalNotices'])} locked origins with "
            f"{notices['noticeFiles']} distinct original notice files.")
    print('')
    for row in checked['distributionPackageNotices'].values():
        selection = row['selection']
        print(f"- Verified the published archive receipt for `{selection['name']}@{selection['version']}`.")


if __name__ == '__main__':
    main()
