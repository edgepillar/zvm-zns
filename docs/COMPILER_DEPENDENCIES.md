# Compiler dependency source and compatibility checks

The contract tooling keeps **solc 0.8.26** and selects **follow-redirects 1.16.3**
and **tmp 0.2.7**. The HTTP update stays inside the compiler's declared
`^1.12.1` range. The compiler pins tmp to `0.0.33`, so the manifest declares one
explicit override: `solc@0.8.26 -> tmp@0.2.7`. It does not replace the compiler.
The compiler's original dependency declaration remains visible in its package
and lock metadata. An npm version-range inventory alone does not establish the
override's compatibility or the application's runtime exposure.

## Reviewed sources

The old/new HTTP and tmp archives and the exact compiler archive were bounded,
SHA-512 checked and inspected in memory before the selections changed. Every
regular source member has a SHA-256 pin in the current qualification plan.
Solc has 21 files, including its unchanged `soljson.js`. The HTTP package has
seven and tmp four. No archive was extracted or package executed locally.

The reviewed HTTP source replaces realm-sensitive array detection, normalizes
flat-array request headers and escapes regular-expression syntax in sensitive
header names. The relevant upstream records are
[cross-realm arrays](https://github.com/follow-redirects/follow-redirects/security/advisories/GHSA-mrwp-f3q8-3g9p),
[array-form headers](https://github.com/advisories/GHSA-q3jh-wrc6-jgq8) and
[regular-expression escaping](https://github.com/advisories/GHSA-8r9p-f939-6h3c).
The installed package's generated Vite copy is a different, unchanged label
candidate; updating this compiler dependency does not replace Vite's embedded
follow-redirects code.

The reviewed tmp source checks option types and relative paths against a
canonical temporary base. The relevant records are
[symbolic-link directories](https://github.com/advisories/GHSA-52f5-9888-hmc6) and
[prefix/postfix confinement](https://github.com/raszi/node-tmp/security/advisories/GHSA-ph9p-34f9-6g65).
Its supported Node minimum changes to 14.14; this lane qualifies Node 22 on
Linux and does not inherit the old package's historical Node/platform support.
The original MIT notices are retained under `contracts/vendor/notices/` and
linked from the repository notice.

Solc's published `wrapper.js` imports follow-redirects for `loadRemoteVersion`.
Its `smtsolver.js` uses `tmp.fileSync({postfix: '.smt2'})` and a cleanup callback.
The selected ZNS build uses the locked local compiler. These source observations
do not prove vulnerable option use or that a remote compiler/SMT solver runs.
No such remote compiler or external solver is invoked by the new controls.

## Actual application and test installations

The current-source lane now performs `npm ci --ignore-scripts --no-audit
--no-fund` against the actual contract manifest/lock. The separate frozen test
sources are staged with derived installation inputs selecting the same HTTP
and tmp versions and exact scoped override. Both installations must match all
reviewed files of solc, follow-redirects and tmp. They share one isolated npm
cache; there are two explicit installation trees, one application build and one
contract control run. The frozen legacy calibration is not rerun.

The real build reads the 19 reviewed Solidity package units from the application
installation. It must reproduce all twelve pinned generated outputs and pass
the existing 33 contract test/subtest events and 291 Base64 cases. These are
requirements for each new revision, not claims that an untested revision passed.

The [additional controls](../tools/dependency-review/compiler-dependency-controls.test.mjs)
must pass five events with complete totals:

- Twelve synthetic-header redirect cases cover object/flat-array headers,
  local/cross-realm sensitive-header arrays and valid special header characters.
  Only two owned IPv4 loopback servers are used; unrelated synthetic headers
  must survive while declared sensitive markers are removed.
- Two synchronous and two asynchronous temporary-file/directory cases check
  the compiler's `.smt2` option, file permissions, descriptor and cleanup API.
- Nine bounded invalid option cases must fail before file creation.
- Three symlink-directory cases must reject creation outside the selected
  base; every path stays inside one fresh hosted fixture tree.

The symlink fixture is intentionally hosted-only. Local controls inspect data
and syntax with writes/network denied; they do not execute that fixture under
managed foreground scratch. Supported-platform, actual application reachability,
source/publisher authentication and full legal/output acceptance remain open.

## Validator parent proposal remains separate

The current web application still selects Zod 3.25.76. Its advisory is not waived
by the compiler update. A bounded hosted npm lock-only step stages Puppeteer
25.17.0 and Zod 4.6.7 as a **review-only proposal** in a new job-owned directory.
Puppeteer's declared BiDi selection is `157.0.8090-0`; it must be retained by the
proposal. Lifecycle scripts and audit/funding transport are disabled. No proposed
package is installed or executed and the actual application inputs stay equal.

The two proposed manifest/lock files, source hashes, npm version, command streams
and strict declaration-inventory result or refusal are retained explicitly. The
observed npm proposal expands six bundled child records without independent
tarball URLs/integrities. The registry-only reader refuses that representation.
The original `NOT_ESTABLISHED` packet and exact refusal remain retained. The
separate [parent publication model](BUNDLED_LOCK_RECORDS.md) now requires actual
archive bytes and a bijection with the six hashed manifests before inventorying
those rows. Its original registry-only refusal remains visible in the new report.
The actual application's strict inventory remains its separate required check.
An unqualified proposal packet preserves review inputs and accepts no migration.
Source/API, complete resolved
graph, browser/platform and compatible adoption review must follow before any
proposal becomes an application update. A proposed clean range or a successful
lock-only step does not remediate the current Zod finding or accept production.
