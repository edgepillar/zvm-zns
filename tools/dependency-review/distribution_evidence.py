"""Bind build-reported source origins to the final ZNS distribution and lock."""

from pathlib import Path
import re

from distribution_notices import read_notice_index, verify_notice_index
from lock_review import decode, read_input, require
from openzeppelin_candidate import checked_name
from profile_sources import pin, read_regular
from proposal_delta import registry_identity

OUTPUT_EVIDENCE = 'vite-distribution-evidence.json'
STAGES = ('normal', 'fixture')
UNRESOLVED = '@generated/unresolved'
TAILWIND_ORIGIN = '@generated/tailwindcss/'
STYLE_ENTRY = 'web/src/style.css'
TAILWIND_IMPORT = re.compile(rb"""^[ \t]*@import[ \t]+(['"])tailwindcss\1[ \t]*;""", re.MULTILINE)
TAILWIND_BANNER = re.compile(rb'/\*! tailwindcss v([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)*)'
    rb' \| MIT License \| https://tailwindcss\.com \*/')
GENERATED_PACKAGES = {
    '@generated/vite/modulepreload-polyfill': 'node_modules/vite',
    '@generated/vite/preload-helper': 'node_modules/vite',
    '@generated/vite/commonjs-helpers': 'node_modules/vite',
    '@generated/vue-export-helper': 'node_modules/@vitejs/plugin-vue',
}
ROLLDOWN_RUNTIME = '@generated/rolldown/runtime'
TAILWIND_STYLESHEETS = {'index.css', 'theme.css', 'preflight.css', 'utilities.css'}
MAGIC = {b'\x7fELF': 'ELF', b'\x00asm': 'WebAssembly', b'\xce\xfa\xed\xfe': 'Mach-O',
    b'\xcf\xfa\xed\xfe': 'Mach-O', b'\xfe\xed\xfa\xce': 'Mach-O', b'\xfe\xed\xfa\xcf': 'Mach-O',
    b'\xca\xfe\xba\xbe': 'possible Mach-O universal binary'}
NATIVE_SUFFIXES = {'.node', '.so', '.dll', '.dylib', '.wasm', '.a', '.o', '.exe'}


def generated_package_locations(sources, rows):
    result = {}
    for source in sorted(sources - {UNRESOLVED}):
        if source == ROLLDOWN_RUNTIME:
            nested = 'node_modules/vite/node_modules/rolldown'
            location = nested if nested in rows else 'node_modules/rolldown'
        elif source.startswith(TAILWIND_ORIGIN):
            location = 'node_modules/tailwindcss'
            require(rows.get(location, {}).get('version') == source.removeprefix(TAILWIND_ORIGIN),
                'Tailwind CSS banner version differs from the selected lock')
        else:
            location = GENERATED_PACKAGES[source]
        require(location in rows, 'generated browser source has no lock location')
        result[source] = location
    return result


def has_tailwind_style_import(repo):
    return bool(TAILWIND_IMPORT.search(read_input(repo, STYLE_ENTRY)))


def complete_trace(web, distribution, output, stage):
    observed = decode(read_input(output, stage + '-bundle.json'))
    require(observed['schema'] == 2 and type(observed['outputs']) is dict
        and type(observed['stylesheets']) is dict, 'distribution observer schema differs')
    files = distribution['files']
    copied = {}
    for name in sorted(set(files) - set(observed['outputs'])):
        copied[name] = pin(read_regular(web, 'public/' + name, 4 << 20))
    signatures, tailwind_banners = {}, {}
    for name in files:
        checked_name(name)
        raw = read_regular(output / (stage + '-dist'), name, 4 << 20)
        require(pin(raw) == files[name], 'distribution file changed during evidence collection')
        header = raw[:4]
        signature = 'possible PE' if header.startswith(b'MZ') else MAGIC.get(header)
        if signature is not None:
            signatures[name] = signature
        if name.endswith('.css'):
            marker = TAILWIND_BANNER.search(raw[:1024])
            if marker:
                tailwind_banners[name] = marker.group(1).decode('ascii')
    return {'observed': observed['outputs'], 'publicCopies': copied, 'nativeHeaderCandidates': signatures,
        'tailwindCssBanners': tailwind_banners, 'stylesheets': observed['stylesheets'],
        'noticeIndex': read_notice_index(output / (stage + '-dist'))}


def stylesheet_sources(seen, stylesheets):
    result = {}
    require(type(stylesheets) is dict and len(stylesheets) <= len(seen), 'stylesheet evidence shape differs')
    for chunk, row in stylesheets.items():
        target, sources = row['file'], row['sources']
        require(chunk in seen and seen[chunk]['type'] == 'chunk' and target in seen
            and seen[target]['type'] == 'asset' and target.endswith('.css'), 'stylesheet has no observed chunk or output')
        require(type(sources) is list and 0 < len(sources) <= 8192
            and all(isinstance(path, str) and path.endswith(('.css', '.vue')) for path in sources)
            and sources == sorted(set(sources)) and set(sources) <= set(seen[chunk]['sources']),
            'stylesheet sources differ from the associated chunk')
        result.setdefault(target, set()).update(sources)
    return {name: sorted(sources) for name, sources in sorted(result.items())}


def review_traces(traces, distributions, rows, tailwind_imported=False):
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
        stylesheets = stylesheet_sources(seen, trace['stylesheets'])
        stage_members, generated = set(), set()
        missing_assets, unresolved_outputs, observed_banners = [], [], {}
        for name, entry in seen.items():
            checked_name(name)
            require(entry['type'] in ('chunk', 'asset') and files[name] == {key: entry[key] for key in ('bytes', 'sha256')},
                'observed bundle member differs: ' + name)
            sources = entry['sources']
            require(type(sources) is list and all(type(source) is str for source in sources)
                and sources == sorted(set(sources)) and len(sources) <= 8192, 'bundle source records differ')
            if entry['type'] == 'asset' and not sources and name not in stylesheets and not name.startswith('notices/npm/'):
                missing_assets.append(name)
            if UNRESOLVED in sources:
                unresolved_outputs.append(name)
            for source in sources:
                if source.startswith(TAILWIND_ORIGIN):
                    require(entry['type'] == 'asset' and name.endswith('.css') and name not in observed_banners,
                        'Tailwind banner belongs to a single CSS asset')
                    observed_banners[name] = source.removeprefix(TAILWIND_ORIGIN)
                    generated.add(source)
                    continue
                if source in GENERATED_PACKAGES or source in (UNRESOLVED, ROLLDOWN_RUNTIME):
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
        require(observed_banners == trace['tailwindCssBanners'], 'bundle origin differs from the final CSS banner')
        tailwind_outputs = [name for name, sources in stylesheets.items() if tailwind_imported and STYLE_ENTRY in sources]
        if tailwind_outputs:
            location = 'node_modules/tailwindcss'
            require(location in rows, 'Tailwind stylesheet input has no lock location')
            generated.add(TAILWIND_ORIGIN + rows[location]['version'])
        role_locations = generated_package_locations(generated, rows)
        for role, location in role_locations.items():
            members = all_members.setdefault(location, set())
            if role.startswith(TAILWIND_ORIGIN):
                members.update(TAILWIND_STYLESHEETS)
        native = sorted(set(trace['nativeHeaderCandidates']) |
            {name for name in files if Path(name).suffix.lower() in NATIVE_SUFFIXES or '.so.' in name})
        stage_reports[stage] = {'outputFiles': len(files), 'bundlerFiles': len(seen), 'copiedFiles': len(copies),
            'packageLocations': sorted(stage_members), 'generatedFamilies': sorted(generated),
            'generatedPackageLocations': role_locations, 'tailwindCssBanners': observed_banners,
            'stylesheetInputs': stylesheets, 'tailwindStyleEntryOutputs': tailwind_outputs,
            'assetsWithoutReportedOrigins': len(missing_assets), 'assetsWithoutOriginNames': sorted(missing_assets),
            'outputsWithUnresolvedOrigins': sorted(unresolved_outputs), 'standaloneNativeCandidates': native}
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


def verify_notice_indexes(traces, distributions, rows, publications, stage_reports):
    for stage, review in stage_reports.items():
        expected = set(review['packageLocations']) | set(review['generatedPackageLocations'].values())
        review['shippedNotices'] = verify_notice_index(
            traces[stage]['noticeIndex'], distributions[stage], rows, publications, expected)
        require(expected == set(review['shippedNotices']['locationsWithOriginalNotices']),
            'an identified browser package has no verified shipped notice')
    return stage_reports
