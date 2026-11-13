# Selected web dependency patches

The application selects Vite 7.3.7 and source-map-js 1.2.2. Vite's minimum
declared 7.x version is 7.3.7; the source-map package remains a transitive
dependency. No major override, other application package version, contract
source or generated contract output changes for these updates.

The reviewed Vite 7.x patch is listed by the upstream advisories
[GHSA-9jrq-w75r-8gcw](https://github.com/advisories/GHSA-9jrq-w75r-8gcw),
[GHSA-rq7h-c2jc-7f22](https://github.com/advisories/GHSA-rq7h-c2jc-7f22),
[GHSA-587h-7wmj-h5pm](https://github.com/advisories/GHSA-587h-7wmj-h5pm),
[GHSA-698v-4r3x-3vcv](https://github.com/advisories/GHSA-698v-4r3x-3vcv) and
[GHSA-r825-w8mm-5pxw](https://github.com/advisories/GHSA-r825-w8mm-5pxw).
Source-map-js 1.2.2 is the patched version for
[GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).
These version/source updates do not establish deployed development-server
exposure or reproduce all Windows/editor or browser middleware conditions.

## Publication review

Both old and candidate npm archives were bounded, SHA-512 checked against their
selected publications and inspected in memory before the lock update. Every
regular member has a SHA-256 pin. There are no added or removed files between
each reviewed pair. Vite has 39 regular files per version: its package manifest
and bundled Node configuration chunk change. Its public exports, installed
dependency declarations and engine range stay equal; its bundled editor
middleware development selection advances to 2.14.2. Source-map-js has 18 regular
files per version: its version and four library files change. The public entry
point stays equal. Original licenses are byte-identical across each pair.

The source-map update also changes its quick-sort behavior when string code
generation is disabled. This is reviewed alongside offset validation, bounded
source-node handling and the nested source getter. Only selecting the patched
version would leave those compatibility observations incomplete.

## Current-source qualification

The [plan](../tools/dependency-review/web-patches.json) pins the application
inputs, core submodule commit, selected publication members and retained notices.
CI uses its existing application dependency installation once, verifies all
57 selected installed package files and obtains the exact 35,340-byte legacy
source-map archive for a small job-owned baseline. It does not install a second
application dependency tree or download a browser for these controls.

Normal source-map controls cover small flat-map round trips, line gaps, indexed
maps extending at most 16 lines beyond short text, twenty constructor-only
malformed-offset checks and four nested sections. Malformed maps are never
iterated or serialized. The four small source-node cases retain the legacy
text differences and require the patch to preserve all four original texts.
A passing legacy comparison records bounded defects; it is not a safety waiver.
The deepest source getter is expected to be read
81 times by the legacy version and once by the patch. Separate small sorting
controls use Node's string-code-generation restriction; observing that restriction
does not qualify an actual browser CSP. Each source-map profile must pass four
normal test events and one restricted-runtime event with complete totals.

The same lane checks the actual Vite CLI version and captures the unchanged
`npm run build` command, including its TypeScript check. It inventories bounded
regular static outputs and requires the two original notice payloads to remain
byte-exact in `dist/notices/`. Reports, source bindings and command streams are
retained explicitly. Neither dependency trees nor the complete static output
are recursively uploaded as evidence.

The normal build and bounded fixtures are qualification requirements, rather
than claims that every revision already passed. Each new source commit needs
its own actual CI and artifact replay. The OpenZeppelin current-source lane
continues independently; its generated contract output pins stay unchanged.

## Remaining acceptance

The previous advisory snapshot's other package findings remain open. A combined
source-bound advisory refresh, real application/bundle reachability, full
distribution notices and legal review, publisher identity, supported platforms,
actual browser behavior and independent maintainer/operator acceptance remain
required. No runtime wallet, live-chain, deployment, release or production
acceptance follows from this source update or a green build.
