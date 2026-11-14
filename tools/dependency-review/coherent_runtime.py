"""Qualify a physical derivative with native Node and real embedded Chrome code."""

import json
import os
import shutil

from browser_staging import hosted_only
from coherent_profile import stage_coherent
from lock_review import read_input, require
from openzeppelin_candidate import run_bounded, write_json
from profile_sources import pin


def qualify_coherent(repo, candidate, output, env, commands, rebuild, execution):
    hosted_only(); execution.update(status='COHERENT_PROFILE_NOT_YET_STAGED', browserWorkerAttempted=False)
    require(shutil.disk_usage(output).free >= (10 << 30) + (512 << 20), 'coherent profile free-space floor and reserved allocations')
    report = {'schema': 1, 'status': 'COHERENT_RUNTIME_INCOMPLETE', 'productionGate': 'NO_GO'}
    try:
        staged, profile = stage_coherent(repo, candidate, output, env, commands, rebuild, execution)
        report['profile'] = staged
        browser_plan = json.loads(read_input(repo, 'tools/dependency-review/browser-inputs.json'))['profiles']['candidate']
        executable = output / 'browsers/candidate/chrome'
        executable_pin = {key: browser_plan['archiveReview']['filePins']['chrome'][key] for key in ['bytes', 'sha256']}
        input_path = output / 'coherent-browser-input.json'
        write_json(input_path, {'schema': 1, 'profile': 'coherentCandidate', 'root': str(profile['root'].resolve(strict=True)),
            'repo': str(repo), 'inventory': str(output / 'candidate-profile-sources.json'),
            'changedSources': str(repo / 'tools/dependency-review/changed-publications.json'),
            'plan': str(repo / 'tools/dependency-review/node-consumer-plan.json'),
            'resolver': str(repo / 'tools/dependency-review/node-consumer-resolve.mjs'),
            'executable': str(executable), 'executablePin': executable_pin, 'browserVersion': browser_plan['version'],
            'abi': str(repo / 'web/src/abi.ts'), 'output': str(output / 'browser-evidence'),
            'runId': os.environ['GITHUB_RUN_ID'], 'distributions': {key: str(value) for key, value in profile['distributions'].items()},
            'derivation': str(profile['manifest']), 'derivationPin': profile['manifestPin'], 'mapperProbe': str(profile['probe'])})
        execution.update(status='COHERENT_NATIVE_NODE_AND_BROWSER_EXECUTION_ATTEMPTED', browserWorkerAttempted=True)
        row = run_bounded(['node', '--max-old-space-size=512', '--experimental-import-meta-resolve',
            str(repo / 'tools/dependency-review/browser-worker.cjs'), str(input_path)], profile['root'], env, output,
            'browser-coherent-candidate', timeout=240)
        commands.append(row); execution['lastCommand'] = row
        require(row['actualExit'] == 0 and row['outputComplete'], 'coherent browser worker failed or incomplete')
        worker = json.loads(read_input(output, 'streams/browser-coherent-candidate.stdout.txt'))
        require(worker['status'] == 'PAIRED_PROTOCOL_AND_SYNTHETIC_APPLICATION_CONTROLS_PASSED'
            and worker['profile'] == 'coherentCandidate' and worker['effectiveLocalDerivativeUsed']
            and worker['derivedGuardOrRebuiltMapperInstalled'], 'coherent worker identity or derivative scope')
        require(worker['sourceGuard']['explicitLocalDerivativeProfile'] and worker['sourceGuard']['sourceGuardViolations'] == 0,
            'coherent effective source guard')
        require(worker['coherentNativeNodeControls']['cases'] == 12 and worker['coherentNativeNodeControls']['importConditionsPreserved'],
            'coherent native Node API controls')
        embedded = worker['sessions'][0]['embeddedMapper']
        require(embedded['status'] == 'INSTALLED_AND_INSPECTED_FULL_BROWSER_MAPPER_BOOTSTRAPS_PASSED'
            and embedded['bootstraps'] == 2 and embedded['generatedBrowserDirectCases'] == 12, 'coherent actual embedded mapper scope')
        require(worker['realBrowserProtocolSessions'] == 2 and len(worker['screenshots']) == 6, 'coherent SDK browser cases')
        for image in worker['screenshots']:
            require(pin(read_input(output, image['path'])) == {key: image[key] for key in ['bytes', 'sha256']}, 'coherent screenshot differs')
        execution['status'] = 'COHERENT_NATIVE_NODE_SDK_AND_EMBEDDED_BROWSER_CONTROLS_PASSED'
        report.update(status=execution['status'], worker=worker, actualSdkChromeSessions=2, actualEmbeddedMapperBootstraps=2,
            nativeNodeDirectCases=12, generatedBrowserDirectCases=12, maximumContainerLength=3,
            additionalChromeDownloads=0, originalRawProfilesModified=False, fullApplicationMigrationOrProductionAcceptance=False)
    finally:
        write_json(output / 'coherent-runtime.json', report)
    return report
