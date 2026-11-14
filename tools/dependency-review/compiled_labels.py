"""Inventory textual pnpm region labels without treating them as manifests."""

import argparse
import json
from pathlib import Path
import re

from lock_review import NAME, VERSION, read_input, require
from openzeppelin_candidate import checked_name, sha

HEADER = re.compile(r'^//#region [^\r\n]*?/node_modules/\.pnpm/([^/\s]+)/node_modules/((?:@[^/\s]+/)?[^/\s]+)(?:/[^\r\n]*)?$')


def inspect_labels(files):
    require(type(files) is dict and 0 < len(files) <= 512, 'compiled source file budget')
    labels, unknowns, source_pins = [], [], {}
    total = 0
    for name, raw in sorted(files.items()):
        checked_name(name)
        require(type(raw) is bytes and len(raw) <= 2 << 20, 'compiled source member budget')
        total += len(raw); require(total <= 32 << 20, 'compiled source payload budget')
        if not name.endswith(('.js', '.mjs', '.cjs')):
            continue
        try:
            text = raw.decode('utf-8')
        except UnicodeError as error:
            raise ValueError('compiled source is not UTF-8') from error
        source_pins[name] = {'bytes': len(raw), 'sha256': sha(raw)}
        # LF positions match the source files; other control characters inside
        # string literals must not be counted as extra source lines.
        for line_number, line in enumerate(text.split('\n'), 1):
            if not line.startswith('//#region ') or not any(value in line for value in ('.pnpm/', '.pnpm\\')):
                continue
            require(len(labels) + len(unknowns) < 8192, 'compiled region label budget')
            context = {'file': name, 'line': line_number}
            match = HEADER.fullmatch(line) if len(line) <= 4096 and line.isascii() and all(32 <= ord(c) < 127 for c in line) else None
            if match:
                locator, package = match.groups(); prefix = package.replace('/', '+') + '@'
                version = locator[len(prefix):].split('_', 1)[0].split('(', 1)[0] if locator.startswith(prefix) else ''
                if NAME.fullmatch(package) and VERSION.fullmatch(version):
                    labels.append({**context, 'generatedLocator': locator, 'name': package, 'version': version})
                    continue
            unknowns.append({**context, 'sourceHeaderSha256': sha(line.encode()), 'reason': 'UNREVIEWED_PNPM_REGION_LABEL'})
    pairs = sorted({(row['name'], row['version']) for row in labels})
    return {'schema': 1, 'status': 'GENERATED_REGION_REVIEW_INCOMPLETE' if unknowns else 'GENERATED_REGION_LABELS_OBSERVED_REVIEW_REQUIRED',
        'sourceFilePins': source_pins, 'generatedRegionLabels': labels, 'unparsedRegionLabels': unknowns,
        'distinctNameVersionLabels': [{'name': name, 'version': version} for name, version in pairs],
        'evidenceAuthority': 'TEXTUAL_BUILD_GENERATED_LABEL_NOT_AUTHENTICATED_PACKAGE_MANIFEST',
        'applicationRuntimeReachabilityEstablished': False, 'independentlyAuthenticatedPackageManifests': False,
        'completeSBOM': False, 'vulnerabilityScanExecuted': False}


def canonical_sha256(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root', type=Path, required=True)
    args = parser.parse_args(); repo = Path(__file__).resolve().parents[2]
    plan = json.loads(read_input(repo, 'tools/dependency-review/web-patches.json'))
    selected = plan['packages']['vite']; files = {}
    for name, pin in selected['filePins'].items():
        raw = read_input(args.package_root, name)
        require({'bytes': len(raw), 'sha256': sha(raw)} == pin, 'installed Vite source differs from reviewed publication')
        files[name] = raw
    result = inspect_labels(files)
    require(canonical_sha256(result) == plan['compiledLabelInventoryExpected']['sha256'], 'compiled inventory differs from reviewed labels')
    print(json.dumps({'selectedPackage': {'name': selected['name'], 'version': selected['version'],
        'publicationArchiveSha256FromReviewedPlan': selected['archiveSha256'], 'publicationArchiveComparedHere': False},
        'installedFilesCheckedAgainstReviewedPublication': len(files), 'inventory': result}, sort_keys=True))


if __name__ == '__main__':
    main()
