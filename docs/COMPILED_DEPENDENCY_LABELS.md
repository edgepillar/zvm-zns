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

Vite 7.3.7 has 239 supported header occurrences and 105 distinct package/version
labels. The source bytes are bound to the selected publication's reviewed file
hashes. Six pairs overlap the existing lock/bundled-manifest inventory; 99 add
new candidate pairs. Together the current inputs provide 292 distinct pairs
across 281 package names: 193 from lock/verified bundled manifests, plus the
additional label-derived candidates.

The [web qualification plan](../tools/dependency-review/web-patches.json) pins
the canonical inventory digest. Hosted CI verifies the selected installed
publication files, reproduces the inventory and retains its full output in the
web qualification report. Changed, unsupported or omitted labels fail that
comparison. This deterministic CI check does not fetch fresh advisories or
turn a label into a package manifest. The original web build, bounded controls
and original notice checks still run independently.

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

One Bulk request for the 292 pairs returned 13 advisory records. SemVer 7.8.4
evaluated 23 pair/range comparisons, alongside 20 positive, negative and invalid
input controls: 13 matched, 10 did not match and none remained unknown. Six
matches have lock/bundled-manifest support; seven additional matches rely on
compiled labels. The query and range evaluation do not execute application code.
The six previous manifest-supported findings remain open without a waiver.

The following seven candidates all remain open for source authentication and
reachability review. Source locations refer to the SHA-256-pinned Vite 7.3.7
publication files in the qualification plan; they are not installed package
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

Advisory freshness, independent package/source authentication, actual application
or build-path reachability, complete shipped notices, supported platforms and
maintainer/operator acceptance remain separate requirements. This inventory is
not a complete SBOM, audit, release or production approval.
