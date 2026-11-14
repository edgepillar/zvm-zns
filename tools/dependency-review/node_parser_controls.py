"""Run source-pinned Node parser APIs without a candidate graph installation."""

import json

from lock_review import read_input, require
from openzeppelin_candidate import run_bounded, sha, write_json
from proposal_delta import registry_identity


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
    require(result['status'] == 'BOUNDED_NODE_PARSER_API_CONTROLS_QUALIFIED_MIGRATION_REQUIRES_REVIEW'
        and result['totalCases'] == 192 and result['sourceGuardCases'] == 4, 'parser control scope differs')
    require(result['packageCodeExecuted'] and result['currentInstalledBaselineAndExactCandidateMemberSourcesUsed'], 'parser sources not executed')
    require(not result['candidateDependencyInstallationPerformed'] and not result['mapperBootstrapOrBrowserOrProtocolCommandsExecuted']
        and not result['networkOrWalletOrLiveChainExecutionPerformed'] and not result['proposalAdopted'], 'parser runtime boundary differs')
    for profile, mapper_role, zod_role in [('baseline', 'baselineMapper', 'baselineZod'),
        ('candidate', 'mapper', 'fixed'), ('unsupportedLegacyOverride', 'baselineMapper', 'fixed')]:
        for member in result[profile]['loaded']:
            selected = plan[mapper_role if member['package'] == 'mapper' else zod_role]
            require(member == {'package': member['package'], 'name': member['name'],
                **{key: selected['members'][member['name']][key] for key in ['bytes', 'sha256']}}, 'executed parser member differs')
    require(not (parent_root / 'node_modules').exists(), 'parser controls installed the candidate graph')
    execution.update(status='QUALIFIED_BOUNDED_CONTROLS', selectedPackageCodeExecution=True)
    return {'schema': 1, 'status': result['status'], 'result': result,
        'baselineSources': {role: {key: plan[role][key] for key in ['kind', 'name', 'version', 'integrity']}
            for role in ['baselineMapper', 'baselineZod']},
        'additionalArchiveRequestsOrBaselineInstallations': 0, 'candidateDependencyInstallationPerformed': False,
        'fullNodeParserOrApplicationCompatibilityQualified': False, 'browserRuntimeQualified': False,
        'unsupportedOverrideAccepted': False, 'proposalAdopted': False, 'productionGate': 'NO_GO'}
