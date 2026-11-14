"""Bounded hosted-only paired Chrome, protocol and synthetic application controls."""

import hashlib
import json
import os
import shutil
import stat
import time
import urllib.request
import zipfile

from browser_archive import inspect_file, safe_name
from browser_staging import hosted_only, qualify_application_builds
from lock_review import read_input, require
from openzeppelin_candidate import run_bounded, write_json
from profile_sources import pin, read_regular


def download_browser(selected, target, transport):
    expected = selected['archiveReview']['archive']
    require(selected['resolved'] == 'https://storage.googleapis.com/chrome-for-testing-public/' + selected['version']
        + '/linux64/chrome-linux64.zip', 'browser source URL scope')
    require(not target.exists() and not target.is_symlink(), 'browser archive already present')
    transport.update(status='REQUEST_ATTEMPTED', requests=1, expected=expected, bytesReceived=0, complete=False)
    digest = hashlib.sha256(); deadline = time.monotonic() + 120
    request = urllib.request.Request(selected['resolved'], headers={'User-Agent': 'edgepillar-dependency-review', 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(request, timeout=45) as response, target.open('xb') as destination:
        require(response.status == 200 and response.geturl() == selected['resolved'], 'browser response or redirect')
        require(response.headers.get('Content-Encoding', 'identity') == 'identity', 'browser response encoding')
        require(int(response.headers['Content-Length']) == expected['bytes'], 'browser response length')
        require(response.headers['x-goog-generation'] == selected['generation'], 'browser object generation')
        hashes = ','.join(response.headers.get_all('x-goog-hash') or []).split(',')
        require('md5=' + selected['vendorMd5'] in [value.strip() for value in hashes], 'browser vendor MD5 metadata')
        while True:
            require(time.monotonic() < deadline, 'browser transport time budget')
            chunk = response.read(min(1 << 20, expected['bytes'] + 1 - transport['bytesReceived']))
            if not chunk: break
            transport['bytesReceived'] += len(chunk)
            require(transport['bytesReceived'] <= expected['bytes'], 'browser transport cap')
            destination.write(chunk); digest.update(chunk)
    require(transport['bytesReceived'] == expected['bytes'] and digest.hexdigest() == expected['sha256'], 'browser raw pin differs')
    transport.update(status='COMPLETE_RAW_SHA256_VERIFIED', complete=True, sha256=digest.hexdigest(), generation=selected['generation'])


def extract_browser(archive, destination, selected):
    require(not destination.exists() and not destination.is_symlink(), 'browser extraction destination already present')
    observed = inspect_file(archive, selected['archiveReview']['archive'])
    require(observed == selected['archiveReview'], 'complete browser archive review differs')
    destination.mkdir(mode=0o700); count = total = 0
    with zipfile.ZipFile(archive) as source:
        for name, expected in observed['filePins'].items():
            safe_name('chrome-linux64/' + name)
            target = destination / name; parent = destination
            for part in target.relative_to(destination).parts[:-1]:
                parent /= part
                if not parent.exists(): parent.mkdir(mode=0o700)
                require(parent.is_dir() and not parent.is_symlink(), 'browser extraction ancestor')
            require(not target.exists() and not target.is_symlink(), 'browser extraction collision')
            digest = hashlib.sha256(); size = 0
            with source.open('chrome-linux64/' + name) as raw, target.open('xb') as output:
                while True:
                    chunk = raw.read(1 << 20)
                    if not chunk: break
                    size += len(chunk); require(size <= expected['bytes'], 'browser extraction member cap')
                    digest.update(chunk); output.write(chunk)
            require(size == expected['bytes'] and digest.hexdigest() == expected['sha256'], 'browser extracted member differs')
            target.chmod(0o755 if expected['unixPermissions'] & 0o111 else 0o644)
            require(stat.S_ISREG(target.lstat().st_mode) and target.lstat().st_nlink == 1, 'browser extracted file identity')
            total += size; count += 1
    require(count == observed['regularFiles'] and total == observed['expandedBytes'], 'browser extraction inventory differs')
    return {'regularFiles': count, 'expandedBytes': total, 'inventorySha256': observed['filePinInventorySha256'],
        'rawAndEveryExtractedMemberVerified': True, 'originalPrivilegedPermissionBitsApplied': False,
        'directoryEntriesMaterializedOnlyAsNeeded': True, 'publisherAuthenticationEstablished': False}


def qualify_browsers(repo, web, candidate, output, env, commands, source_plan, execution):
    hosted_only(); execution.update(status='APPLICATION_BUILDS_NOT_YET_ATTEMPTED', browserExecutionAttempted=False)
    builds, distributions = qualify_application_builds(repo, web, candidate, output, env, commands, source_plan, execution)
    plan_raw = read_input(repo, 'tools/dependency-review/browser-inputs.json'); plan = json.loads(plan_raw)
    require(plan['schema'] == 1 and set(plan['profiles']) == {'baseline', 'candidate'}, 'paired browser input scope')
    root = output / 'browsers'; root.mkdir(mode=0o700)
    evidence = output / 'browser-evidence'; evidence.mkdir(mode=0o700)
    result = {'schema': 1, 'status': 'BROWSER_QUALIFICATION_INCOMPLETE', 'inputPlanPin': pin(plan_raw),
        'applicationBuilds': builds, 'profiles': {}, 'productionGate': 'NO_GO'}
    def run(label, argv, cwd, timeout):
        row = run_bounded(argv, cwd, env, output, label, timeout=timeout); commands.append(row); execution['lastCommand'] = row
        require(row['actualExit'] == 0 and row['outputComplete'], label + ' failed or incomplete')
    try:
        for role, package_root in [('baseline', web), ('candidate', candidate)]:
            require(shutil.disk_usage(output).free >= (10 << 30) + (2 << 30), 'browser lane remaining free-space floor')
            selected = plan['profiles'][role]; record = {'transport': {}, 'status': 'INPUT_NOT_YET_FETCHED'}; result['profiles'][role] = record
            revisions = read_regular(package_root, 'node_modules/puppeteer-core/' + selected['revisionMember'], 65536)
            require(pin(revisions) == selected['revisionMemberPin'], 'actual installed SDK revision bytes differ')
            require(selected['version'].encode() in revisions, 'actual SDK browser revision absent')
            archive = root / (role + '.zip'); executable_root = root / role
            execution['status'] = role.upper() + '_BROWSER_DOWNLOAD_ATTEMPTED'
            download_browser(selected, archive, record['transport'])
            execution['status'] = role.upper() + '_BROWSER_INSPECTION_AND_EXTRACTION_ATTEMPTED'
            record['extraction'] = extract_browser(archive, executable_root, selected)
            executable = executable_root / 'chrome'; executable_pin = {key: selected['archiveReview']['filePins']['chrome'][key] for key in ('bytes', 'sha256')}
            execution.update(status=role.upper() + '_BROWSER_VERSION_PROCESS_ATTEMPTED', browserExecutionAttempted=True)
            run('browser-version-' + role, [str(executable), '--version'], executable_root, 15)
            version = read_input(output, 'streams/browser-version-' + role + '.stdout.txt').decode().strip()
            require(selected['version'] in version and len(version) <= 256, 'executed browser version differs')
            input_path = output / ('browser-' + role + '-input.json')
            write_json(input_path, {'schema': 1, 'profile': role, 'root': str(package_root.resolve(strict=True)),
                'repo': str(repo), 'inventory': str(output / 'candidate-profile-sources.json'),
                'changedSources': str(repo / 'tools/dependency-review/changed-publications.json'),
                'plan': str(repo / 'tools/dependency-review/node-consumer-plan.json'),
                'resolver': str(repo / 'tools/dependency-review/node-consumer-resolve.mjs'),
                'executable': str(executable), 'executablePin': executable_pin, 'browserVersion': selected['version'],
                'abi': str(repo / 'web/src/abi.ts'), 'output': str(evidence),
                'runId': os.environ['GITHUB_RUN_ID'], 'distributions': {key: str(value) for key, value in distributions[role].items()}})
            execution['status'] = role.upper() + '_REAL_PROTOCOL_AND_APPLICATION_CONTROLS_ATTEMPTED'
            run('browser-' + role, ['node', '--max-old-space-size=512', '--experimental-import-meta-resolve',
                str(repo / 'tools/dependency-review/browser-worker.cjs'), str(input_path)], package_root, 180)
            worker = json.loads(read_input(output, 'streams/browser-' + role + '.stdout.txt'))
            require(worker['status'] == 'PAIRED_PROTOCOL_AND_SYNTHETIC_APPLICATION_CONTROLS_PASSED'
                and worker['profile'] == role and worker['browserVersion'] == selected['version']
                and worker['realBrowserProtocolSessions'] == 2 and worker['deniedChildProcesses'] == 0, 'browser worker result differs')
            require(worker['sourceGuard']['sourceGuardViolations'] == 0 and len(worker['screenshots']) == 6, 'browser source or screenshot scope differs')
            for row in worker['screenshots']:
                require(pin(read_input(output, row['path'])) == {key: row[key] for key in ('bytes', 'sha256')}, 'browser PNG bytes differ')
                require((row['width'], row['height']) in [(1280, 900), (400, 860)], 'browser PNG dimensions differ')
            record.update(status='BOTH_PROTOCOLS_AND_SYNTHETIC_APPLICATION_CONTROLS_PASSED', versionProcessOutput=version,
                executablePin=executable_pin, worker=worker)
        require(shutil.disk_usage(output).free >= 10 << 30, 'browser final free-space floor')
        execution['status'] = 'FOUR_REAL_PROTOCOL_SESSIONS_AND_SYNTHETIC_APPLICATION_CONTROLS_PASSED'
        result.update(status=execution['status'], actualChromeSessions=4, downloads=2, extractions=2,
            archiveBytes=sum(row['archiveReview']['archive']['bytes'] for row in plan['profiles'].values()),
            expandedBrowserBytes=sum(row['archiveReview']['expandedBytes'] for row in plan['profiles'].values()),
            screenshotFiles=12, ChromeArchivesProfilesOrDistributionTreesIncludedInArtifact=False,
            syntheticDeploymentIsNotOperatorDataOrReleaseArtifact=True, derivedGuardOrRebuiltMapperInstalled=False,
            completeApplicationMigrationPublisherPlatformLegalOrProductionAcceptance=False)
    finally:
        write_json(output / 'browser-runtime.json', result)
    return result
