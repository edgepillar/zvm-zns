# Compiled dependency labels and advisory scope

An npm lock describes selected package installations. A bundled JavaScript file
can also carry other packages' code without declaring separate installed
locations. Vite's reviewed publication contains textual pnpm region headers
that expose candidate source package/version labels.

The [data-only inventory](../tools/dependency-review/compiled_labels.py) reads
reviewed UTF-8 JavaScript files, retains every supported header and its exact
LF source location, and deduplicates only the package/version request pairs.
Unsupported or malformed pnpm headers remain explicit unknowns. Scope excludes
unlabelled code and other bundlers' annotations. A matching header is a textual
provenance clue, not an independently authenticated npm manifest or proof that
its code executes in the application.

## Current reviewed input

Vite 7.3.8 has 239 supported header occurrences and 105 distinct package/version
labels. The source bytes are bound to the selected publication's reviewed file
hashes. Six pairs overlap the existing lock/bundled-manifest inventory; 99 add
new candidate pairs. Together the current inputs provide 292 distinct pairs
across 281 package names: 193 from lock/verified bundled manifests, plus the
additional label-derived candidates.

The 7.3.7-to-7.3.8 patch keeps all labelled package names and versions equal.
Its reviewed source-file and canonical inventory hashes change. The separate
[virtual-module fix](WEB_DEPENDENCY_PATCHES.md) does not remediate or waive the
seven label-only candidates below.

The [current application qualification plan](../tools/dependency-review/application-runtime.json)
pins the canonical inventory digest. Hosted CI checks the installed Vite
JavaScript files against the publication identified by the job's npm cache.
It reproduces the label inventory before the builds and browser download and
records its digest and counts in the artifact. Changed, unsupported or omitted
labels fail that comparison. The historical web qualification retains the full
inventory. Fresh advisory results, package provenance and runtime reachability
require their own evidence.

## Advisory review boundary

A source-bound Bulk Advisory request can deduplicate the combined public
package names and versions while preserving each pair's evidence class in the
retained report. Label-only range matches need source and reachability review;
they must remain distinct from matches supported by installed or physically
bundled package manifests. A shared pair can have both evidence classes.

The controlled query sends package names and version lists only. It does not
send source locations, project identity, private paths, credentials, environment
or platform information, and it uses no Quick Audit fallback. Scanner source,
request, response and range-evaluation bindings are retained separately from
application execution. Prior findings are not waived merely because a later
provider response omits them.

## Source review snapshot: 2026-11-14

The request used dependency bytes from
`77b824eb70ab1f3faf7cb4ee1e2b83f901510f10` (Vite 7.3.7); those inputs are
unchanged at the inventory-code revision
`a5057615d375af37b2d0e316653b94202cb240cc`. One Bulk request for the 292 pairs
returned 13 advisory records. SemVer 7.8.4
evaluated 23 pair/range comparisons, alongside 20 positive, negative and invalid
input controls: 13 matched, 10 did not match and none remained unknown. Six
matches have lock/bundled-manifest support; seven additional matches rely on
compiled labels. The query and range evaluation do not execute application code.
The six previous manifest-supported findings remain open without a waiver.

The following seven candidates all remain open for source authentication and
reachability review. Source locations refer to the SHA-256-pinned Vite 7.3.7
publication files in that revision's
[qualification plan](https://github.com/edgepillar/zvm-zns/blob/a5057615d375af37b2d0e316653b94202cb240cc/tools/dependency-review/web-patches.json);
they are not installed package
manifests. These observations identify relevant code and preconditions, and do
not establish application exposure or approve remediation.

| Candidate label and advisory | Reviewed source and remaining condition |
| --- | --- |
| follow-redirects 1.15.11: [custom authentication headers](https://github.com/follow-redirects/follow-redirects/security/advisories/GHSA-r4q5-vmmm-2653) | `dist/node/chunks/config.js:21378` has the built-in header-removal pattern. At line 21618, the proxy selects this implementation only when `followRedirects` is enabled. Actual configuration, custom credentials and cross-domain redirect behavior need qualification. |
| nanoid 5.1.6: [negative non-secure size](https://github.com/advisories/GHSA-28wg-ghj8-5hjv) | `dist/client/client.mjs:229-236` contains the non-secure generator. The one observed call in this file, at line 321, supplies no size and uses the default 21. This is static evidence about that call, not a complete call-graph or runtime waiver. |
| nanoid 5.1.6: [CSPRNG pool overflow](https://github.com/ai/nanoid/security/advisories/GHSA-xwg4-73v4-xw9w) | The same region implements the non-secure generator using `Math.random`; the advisory describes the secure implementation's shared random pool. That implementation distinction prevents treating the label match as proof of this mechanism. Other sources and consumers still need review. |
| postcss-selector-parser 7.1.0: [AST recursion](https://github.com/advisories/GHSA-w9m9-85wc-3x92) | `dist/node/chunks/build2.js:2245-2246` serializes child nodes recursively. CSS module paths call the parser at lines 4891-4895 and 5203-5204. Trust, size and nesting of supplied CSS remain unqualified. |
| postcss-selector-parser 7.1.0: [flat-selector complexity](https://github.com/postcss/postcss-selector-parser/security/advisories/GHSA-rj75-hqrm-r3gf) | `dist/node/chunks/build2.js:3664-3668` and `4199-4242` contain the repeated array searches discussed upstream. The observed consumers are CSS transforms; parsing untrusted selectors in a request path has not been established. |
| ws 8.18.3: [TypedArray close reason](https://github.com/websockets/ws/security/advisories/GHSA-58qx-3vcg-4xpx) | `dist/node/chunks/config.js:18271-18285` contains the close-buffer construction. The selected development-server ping path at line 20636 closes without a reason. No complete enumeration of plugin/custom close calls or runtime qualification is claimed. |
| ws 8.18.3: [fragment memory growth](https://github.com/websockets/ws/security/advisories/GHSA-96hv-2xvq-fx4p) | `dist/node/chunks/config.js:20642` constructs the development WebSocket server. Host/token checks precede connection handling at lines 20626-20643; the receiver still needs review against the upstream resource fix. Actual server exposure and peer access have not been qualified. |

Advisory responses can change. This dated source review does not waive a
candidate, authenticate the labelled package independently or substitute for
testing a reviewed replacement publication. A top-level override alone does
not replace code already embedded in a Vite bundle.

## Vite 8 upgrade review

The hosted web job evaluates the [Vite 8.3.8 npm publication](https://registry.npmjs.org/vite/8.3.8)
in a fresh application checkout. It changes only the Vite declaration in the
candidate manifest and records the npm-generated lock. It requires the existing
Puppeteer and Zod dependency graphs to remain identical before rebinding the
reviewed runtime manifest to the candidate lock. Each command has a deadline
and separate output bounds. Installation runs with lifecycle scripts disabled.

The [platform publication plan](../tools/dependency-review/vite-libc-publications.json)
records the `libc` declarations of ten Linux Rolldown and Lightning CSS optional
archives. Candidates match each exact parent, version, registry URL, integrity,
OS and CPU before restoring a missing field. A conflicting existing selector
fails review. The original npm lock and the selected lock are retained. The
glibc job checks the installed GNU variants against their archive manifests and
requires incompatible variants to be absent. Other platform entries provide
published metadata evidence, with native execution qualified on Linux x64 glibc.

The job reads the exact Vite archive from the same install's npm cache. It
compares its regular members with the installation and records the recognized
compiled labels, unparsed headers, original notice pins and prior exact label
pairs. The original archive notice matches the [upstream release notice](https://github.com/vitejs/vite/blob/b39e6e63dcbfc3cf4be871acf3554efbd6d0e268/packages/vite/LICENSE.md).
Both builds use `npm run build` to check runtime preparation, types, vendor
chunks and current static notices. The default application and synthetic fixture
share one installation. CI retains the locks, label inventory and command reports.

The candidate builds load the application Vite configuration with a read-only
bundle observer. It records relative module and asset origins and hashes the
emitted files. The producer checks that those hashes and the static public
copies cover the final distribution. It then verifies reported npm source files
and original notices against the locked publications in the current job's npm
cache. This reuses the existing builds and avoids retaining another distribution
archive. The report records generated origin categories, assets with empty
origin metadata, standalone native file candidates and exact notice copies.
Generated or inlined material can have incomplete origin metadata.

The normal application build emits a `notices/npm/index.json` from its
reported package origins. It copies the original notice files from the installed
lock selections and reuses identical bytes across packages. Exact virtual IDs
identify the Vite preload modules, the Rolldown runtime and the Vue export
helper. The report binds those roles to the published packages and lists
remaining unresolved outputs by their distribution-relative names. [Vite preload
source](https://github.com/vitejs/vite/blob/b39e6e63dcbfc3cf4be871acf3554efbd6d0e268/packages/vite/src/node/plugins/importAnalysisBuild.ts#L129-L131),
[Rolldown runtime source](https://github.com/rolldown/rolldown/blob/b9c75ddc8bd50f2c1a4c7be0b548bdab5cba85ab/crates/rolldown_common/src/module_loader/runtime_module_brief.rs#L8-L9),
[Vue helper source](https://github.com/vitejs/vite-plugin-vue/blob/822c69d687a5c6bdc4a72f2326aed9b0e1ba7030/packages/plugin-vue/src/helper.ts#L1-L9)

For compiled CSS, the browser build reads the Tailwind version banner and
requires the matching locked package. Hosted verification independently reads
the banner from the final file and checks the installed Tailwind stylesheets
against their archive. The same build path feeds Pages and the candidate
scenarios. Hosted CI compares the index and shipped notice hashes with the
original archive receipts. [Tailwind banner source](https://github.com/tailwindlabs/tailwindcss/blob/c2b24dd15fed1c59dd521bd86082f520c9f5ad0d/packages/tailwindcss/src/index.ts#L721-L724)

The web job also checks the npm registry archive, original package manifest and
notice pins for each added or replaced publication installed on Linux x64 glibc.
Its report identifies changed optional locations absent from that installation.
The pinned Vite notice provides names of dependencies listed by the release
without binding versions of embedded code.

The `vite-evidence` job validates the candidate ZIP against its upload digest
and reads only bounded, expected members. From those bytes it reconstructs the
lock delta and platform carries, validates the derived runtime manifest and
checks every recorded command stream, compiled-label report and notice receipt.
The replay also compares the selected installation with the publication plan.
It checks the captured distribution receipts against the selected lock and the
producer's final file hashes.
It runs without a package install or browser launch. Raw package verification
belongs to the producer, whose records are bound to the same commit and run.

The tracked application uses Vite 7. Hosted CDP and BiDi controls exercise both
Vite versions' normal and synthetic builds from the same two Chrome sessions.
Adoption of Vite 8 requires review of compiled code, other supported platforms
and shipped notice obligations. The textual labels cover supported build
markers and leave unmarked code outside this inventory.

The upstream virtual-module advisory
[GHSA-p4f5-76q4-ffq7](https://github.com/vitejs/vite/security/advisories/GHSA-p4f5-76q4-ffq7)
was observed independently after that response, which did not return it. Its
7.x affected range includes 7.3.7 and its patched list includes 7.3.8. This feed
gap is retained alongside the selected source fix, rather than using the
absence of a returned record as a safety waiver.

Advisory freshness, independent package/source authentication, actual application
or build-path reachability, complete shipped notices, supported platforms and
maintainer/operator acceptance remain separate requirements. This inventory is
not a complete SBOM, audit, release or production approval.
