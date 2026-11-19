"""Bind build-reported source origins to the final ZNS distribution and lock."""

from pathlib import Path

from lock_review import decode, read_input, require
from openzeppelin_candidate import checked_name
from profile_sources import pin, read_regular
from proposal_delta import registry_identity

OUTPUT_EVIDENCE = 'vite-distribution-evidence.json'
STAGES = ('normal', 'fixture')
GENERATED = {'@generated/vite', '@generated/rolldown', '@generated/commonjs', '@generated/unresolved'}
MAGIC = {b'\x7fELF': 'ELF', b'\x00asm': 'WebAssembly', b'\xce\xfa\xed\xfe': 'Mach-O',
    b'\xcf\xfa\xed\xfe': 'Mach-O', b'\xfe\xed\xfa\xce': 'Mach-O', b'\xfe\xed\xfa\xcf': 'Mach-O',
    b'\xca\xfe\xba\xbe': 'possible Mach-O universal binary'}
NATIVE_SUFFIXES = {'.node', '.so', '.dll', '.dylib', '.wasm', '.a', '.o', '.exe'}


def complete_trace(web, distribution, output, stage):
    observed = decode(read_input(output, stage + '-bundle.json'))
    require(observed['schema'] == 1 and type(observed['outputs']) is dict, 'distribution observer schema differs')
    files = distribution['files']
    copied = {}
    for name in sorted(set(files) - set(observed['outputs'])):
        copied[name] = pin(read_regular(web, 'public/' + name, 4 << 20))
    signatures = {}
    for name in files:
        checked_name(name)
        raw = read_regular(output / (stage + '-dist'), name, 4 << 20)
        require(pin(raw) == files[name], 'distribution file changed during evidence collection')
        header = raw[:4]
        signature = 'possible PE' if header.startswith(b'MZ') else MAGIC.get(header)
        if signature is not None:
            signatures[name] = signature
    return {'observed': observed['outputs'], 'publicCopies': copied, 'nativeHeaderCandidates': signatures}


def review_traces(traces, distributions, rows):
    require(set(traces) == set(distributions) == set(STAGES), 'distribution evidence phases differ')
    locations = sorted((location for location in rows if location), key=len, reverse=True)
    all_members, stage_reports = {}, {}
    for stage in STAGES:
        trace = traces[stage]
        files = distributions[stage]['files']
        seen = trace['observed']
        copies = trace['publicCopies']
        require(set(seen).isdisjoint(copies) and set(seen) | set(copies) == set(files)
            and all(files[name] == value for name, value in copies.items()), 'distribution public copies differ')
        require(set(trace['nativeHeaderCandidates']) <= set(files)
            and set(trace['nativeHeaderCandidates'].values()) <= set(MAGIC.values()) | {'possible PE'}, 'native header evidence differs')
        stage_members, generated = set(), set()
        empty_assets = 0
        for name, entry in seen.items():
            checked_name(name)
            require(entry['type'] in ('chunk', 'asset') and files[name] == {key: entry[key] for key in ('bytes', 'sha256')},
                'observed bundle member differs: ' + name)
            sources = entry['sources']
            require(type(sources) is list and sources == sorted(set(sources)) and len(sources) <= 8192, 'bundle source records differ')
            empty_assets += int(entry['type'] == 'asset' and not sources)
            for source in sources:
                if source in GENERATED:
                    generated.add(source)
                    continue
                checked_name(source)
                if source.startswith('web/node_modules/'):
                    relative = source.removeprefix('web/')
                    location = next((item for item in locations if relative.startswith(item + '/')), None)
                    require(location is not None, 'bundle source has no lock location: ' + source)
                    member = relative[len(location) + 1:]
                    all_members.setdefault(location, set()).add(member)
                    stage_members.add(location)
                else:
                    require(source.startswith(('web/src/', 'web/public/', 'zvm-core/web/src/'))
                        or source == 'web/index.html' or (stage == 'fixture' and source == 'deployments/browser-fixture.json'),
                        'bundle source is outside the reviewed application')
        native = sorted(set(trace['nativeHeaderCandidates']) |
            {name for name in files if Path(name).suffix.lower() in NATIVE_SUFFIXES or '.so.' in name})
        stage_reports[stage] = {'outputFiles': len(files), 'bundlerFiles': len(seen), 'copiedFiles': len(copies),
            'packageLocations': sorted(stage_members), 'generatedFamilies': sorted(generated),
            'assetsWithoutReportedOrigins': empty_assets, 'standaloneNativeCandidates': native}
    require(0 < len(all_members) <= 128 and sum(map(len, all_members.values())) <= 8192, 'distribution source inventory budget')
    return all_members, stage_reports


def verify_publications(rows, member_paths, package_sources, distributions, stage_reports):
    require(set(package_sources) == set(member_paths), 'distribution publication coverage differs')
    for location, row in package_sources.items():
        require(row['selection'] == registry_identity(location, rows[location])
            and set(row['originalMembers']) == member_paths[location], 'distribution archive source receipt differs')
    for stage, review in stage_reports.items():
        final_pins = {(value['bytes'], value['sha256']) for value in distributions[stage]['files'].values()}
        review['locationsWithOriginalNoticeBytesInOutput'] = sorted(location for location in review['packageLocations']
            if any((value['bytes'], value['sha256']) in final_pins for value in package_sources[location]['originalNotices'].values()))
    return stage_reports
