"""Run source-pinned Node parser APIs without a candidate graph installation."""

import io
import json
import tarfile

from lock_review import read_input, require
from openzeppelin_candidate import run_bounded, sha, write_json
from proposal_delta import registry_identity
from parser_guard import patch_parser


def qualify_parser_controls(repo, web, parent_root, output, env, commands, source_plan, execution):
    execution.update(status='PREPARING_REVIEWED_INPUTS', selectedPackageCodeExecution=False)
    plan = json.loads(read_input(output, 'mapper-size-input.json'))
    require(plan['schema'] == 1 and set(plan) == {'schema', 'mapper', 'fixed'}, 'mapper input scope differs')
    lock = json.loads(read_input(web, 'package-lock.json'))['packages']
    for role, name, version in [('baselineMapper', 'chromium-bidi', '17.0.2'), ('baselineZod', 'zod', '3.25.76')]:
        location = 'node_modules/' + name; row = lock[location]
        require(row['version'] == version, 'unreviewed parser baseline version')
        expected = source_plan['publications'][row['integrity']]
        require(registry_identity(location, row) == expected['selection'], 'parser baseline publication differs')
        root = web / location
        require(root.is_dir() and not root.is_symlink(), 'parser baseline source directory absent or linked')
        plan[role] = {'kind': 'REVIEWED_INSTALLED_MEMBERS', 'root': str(root.resolve(strict=True)),
            'name': name, 'version': version, 'integrity': row['integrity'], 'members': expected['filePins']}
    guard = json.loads(read_input(repo, 'tools/dependency-review/node-parser-guard.json'))
    candidate_lock = json.loads(read_input(parent_root, 'package-lock.json'))['packages']
    selected = source_plan['publications'][candidate_lock['node_modules/chromium-bidi']['integrity']]
    require(guard['publication'] == selected['selection'] and guard['entry'] == 'out/Default/gen/src/protocol-parser/protocol-parser.js',
        'parser guard publication or entry differs')
    require(guard['original'] == selected['filePins'][guard['entry']], 'parser guard original member is unreviewed')
    raw_archive = read_input(output / 'mapper-control-sources', 'mapper.tgz')
    with tarfile.open(fileobj=io.BytesIO(raw_archive), mode='r:gz') as archive:
        original = archive.extractfile('package/' + guard['entry']).read((64 << 10) + 1)
    _, derivation = patch_parser(original, guard)
    plan['guardPatch'] = guard
    input_path = output / 'node-parser-input.json'; write_json(input_path, plan)
    execution.update(status='COMMAND_ATTEMPTED', selectedPackageCodeExecution=None,
        inputSha256=sha(input_path.read_bytes()))
    command = run_bounded(['node', '--max-old-space-size=128', '--experimental-vm-modules',
        str(repo / 'tools/dependency-review/node-parser-worker.cjs'), str(input_path)],
        parent_root, env, output, 'node-parser-controls', timeout=45)
    commands.append(command); execution['command'] = command
    execution['status'] = 'COMMAND_RETURNED_RESULT_UNQUALIFIED'
    require(command['actualExit'] == 0 and command['outputComplete'], 'Node parser controls failed or incomplete')
    result = json.loads((output / 'streams/node-parser-controls.stdout.txt').read_bytes())
    require(result['status'] == 'NODE_PARSER_OBSERVATIONS_AND_GUARD_CANDIDATE_QUALIFIED_MIGRATION_NOT_ACCEPTED'
        and result['totalCases'] == 299 and result['sourceGuardCases'] == 4 and result['patchGuardCases'] == 2, 'parser control scope differs')
    require(result['packageCodeExecuted'] and result['currentInstalledBaselineAndExactCandidateMemberSourcesUsed'], 'parser sources not executed')
    require(not result['candidateDependencyInstallationPerformed'] and not result['mapperBootstrapOrBrowserOrProtocolCommandsExecuted']
        and not result['networkOrWalletOrLiveChainExecutionPerformed'] and not result['proposalAdopted'], 'parser runtime boundary differs')
    for profile, mapper_role, zod_role in [('baseline', 'baselineMapper', 'baselineZod'),
        ('candidate', 'mapper', 'fixed'), ('guardCandidate', 'mapper', 'fixed'), ('unsupportedLegacyOverride', 'baselineMapper', 'fixed')]:
        for member in result[profile]['loaded']:
            selected = plan[mapper_role if member['package'] == 'mapper' else zod_role]
            expected = {key: selected['members'][member['name']][key] for key in ['bytes', 'sha256']}
            if profile == 'guardCandidate' and member['package'] == 'mapper' and member['name'] == guard['entry']:
                expected = {**guard['derived'], 'derivedFrom': guard['original'], 'transformation': 'REVIEWED_GEOLOCATION_TYPE_GUARD'}
            require(member == {'package': member['package'], 'name': member['name'], **expected}, 'executed parser member differs')
    require(not (parent_root / 'node_modules').exists(), 'parser controls installed the candidate graph')
    execution.update(status='OBSERVATIONS_AND_DERIVED_GUARD_QUALIFIED_SUBJECT_REQUIRES_REVIEW', selectedPackageCodeExecution=True)
    return {'schema': 1, 'status': result['status'], 'result': result,
        'baselineSources': {role: {key: plan[role][key] for key in ['kind', 'name', 'version', 'integrity']}
            for role in ['baselineMapper', 'baselineZod']},
        'additionalArchiveRequestsOrBaselineInstallations': 0, 'candidateDependencyInstallationPerformed': False,
        'derivedGuard': derivation, 'originalPublishedGeolocationBehaviorAccepted': False,
        'fullNodeParserOrApplicationCompatibilityQualified': False, 'browserRuntimeQualified': False,
        'unsupportedOverrideAccepted': False, 'proposalAdopted': False, 'productionGate': 'NO_GO'}
