# Selected web dependency patches

The application selects Vite 7.3.8 and source-map-js 1.2.2. Vite's minimum
declared 7.x version is 7.3.8; the source-map package remains a transitive
dependency. No major override, other application lockfile package version, contract
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

The additional Vite 7.3.8 patch addresses the virtual-module escaping issue in
[GHSA-p4f5-76q4-ffq7](https://github.com/vitejs/vite/security/advisories/GHSA-p4f5-76q4-ffq7).
The upstream advisory lists 7.3.7 as affected and 7.3.8 as patched. It requires
an explicitly network-exposed development server. The tracked application
configuration declares a port and filesystem allow list, but no `server.host`;
actual launch flags, runtime network exposure and end-to-end exploitability
have not been established. The earlier retained Bulk response omitted this
advisory; the independently observed upstream record is preserved separately.

## Publication review

Both old and candidate npm archives were bounded, SHA-512 checked against their
selected publications and inspected in memory before the lock update. Every
regular member has a SHA-256 pin. There are no added or removed files between
each reviewed pair. Vite has 39 regular files per version: its package manifest
and bundled Node configuration chunk change. Its public exports, installed
dependency declarations and engine range stay equal; its bundled editor
middleware development selection advances to 2.14.2. Its compiled source labels
also change shell-quote from 1.8.4 to 1.12.0. The
[compiled dependency inventory](COMPILED_DEPENDENCY_LABELS.md) records those
additional provenance clues and their separate advisory/reachability scope.
Source-map-js has 18 regular
files per version: its version and four library files change. The public entry
point stays equal. Original licenses are byte-identical across each pair.

For the subsequent 7.3.7-to-7.3.8 comparison, the previous archive was reused
without another local transport. The candidate is 544,759 bytes, SHA-256
`7d8597eab679d0833d9015f0f29ed145fe4fa1a956b7c80371f85bdd056362c3`.
Exactly two of its 39 files differ: `package.json` changes only the version,
and `dist/node/chunks/config.js` changes the virtual-module and dependency
optimizer stubs. The upstream
[source fix](https://github.com/vitejs/vite/commit/e5f23b60f0c46a906a60986faad88a5bd7611a15)
serializes module names before embedding them into generated JavaScript.
Exports, declarations, engines, all 105 compiled package/version labels and
the original license bytes stay equal. Source-file hashes and the canonical
compiled inventory digest change and are pinned anew. The Vite notice filename
now identifies 7.3.8 and retains the exact original bytes.

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

The [Vite controls](../web/scripts/vite-virtual-module-controls.test.mjs) use
the actual installed plugin container with four development/production and
browser-external/optional-peer branches. Six benign names per branch exercise
quotes, slashes, backticks, line separators and literal interpolation text:
24 cases across four test events. Generated modules must have no imports and
are evaluated in an empty Node VM context with a one-second timeout and string
code generation disabled. Error messages must retain the exact input text.
Each test uses a fresh hosted job-owned root, disables configuration/env file
loading, watchers and WebSockets, and requires a null HTTP server. It sends no
HTTP requests and makes no listen call. This does not exercise the optimizer
prebundle path, an exposed server, browser behavior or the full upstream exploit.

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

The compiler's separate HTTP and temporary-file dependency update is described
in [Compiler dependencies](COMPILER_DEPENDENCIES.md). It does not change the web
application's current locked Puppeteer 25.12.0 or Zod 3.25.76 selection. The
manifest's `^25.11.0` minimum is distinct from that locked parent version.

After the current web build, two additional bounded commands observe npm and
generate a review-only lock proposal for Puppeteer 25.17.0 and Zod 4.6.7 in a
new hosted job-owned directory. The lock-only command disables lifecycle scripts,
audit and funding requests, uses the existing isolated cache and must create no
`node_modules`. The actual application manifest and lock must stay byte-equal.
The lane retains `candidate-web-package.json`, `candidate-web-package-lock.json`,
their strict inventory result or refusal and source/stream pins. A refusal sets
the proposal's inventory to `NOT_ESTABLISHED`, retains its reason and leaves the
complete proposed graph unqualified. It is separate from the actual application's
strict inventory and current-source controls. The observed refusal concerns six
bundled child records without independent tarball identities; those records need
their own binding to the selected parent publication before adoption.
The [bundle-aware source model](BUNDLED_LOCK_RECORDS.md) performs that binding
from the exact parent archive, preserves the registry-only refusal and rebuilds
the complete original declaration graph. This source inventory remains separate
from full graph, source/API, browser and migration acceptance. An explicitly
requested parent binding is strict and fails if any claim cannot be paired.
The raw npm lock and the selector-preserved review candidate have separate
artifact paths and hashes. The
[platform step](PROPOSAL_PLATFORM_SELECTORS.md) preserves existing missing
constraints only for exactly identical publications. The
[changed-source plan](CHANGED_PARENT_SOURCES.md) binds both sides of every
changed registry location and verifies the baseline members against the
existing application installation without an extra install or source request.
The [version gate](PROPOSAL_VERSION_RANGES.md) adds a further bounded command
using a pinned SemVer source tree. Eleven command records cover the existing
eight commands, the two proposal commands and this range evaluation. Proposed
packages are neither installed nor executed. The complete proposed graph,
source/API and browser/platform compatibility need review before adoption;
this proposal does not waive or remediate the current Zod finding.

The previous advisory snapshot's remaining package findings stay open until a
source-bound refresh evaluates the actual new inputs. A combined
source-bound advisory refresh, real application/bundle reachability, full
distribution notices and legal review, publisher identity, supported platforms,
actual browser behavior and independent maintainer/operator acceptance remain
required. No runtime wallet, live-chain, deployment, release or production
acceptance follows from this source update or a green build.
