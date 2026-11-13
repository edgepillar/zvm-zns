# Locked npm input review

The read-only inventory covers `contracts/package.json`,
`contracts/package-lock.json`, `web/package.json` and `web/package-lock.json`.
It uses Python's standard library and installs or executes no dependency.

```sh
python3 -B -m unittest discover -s tools/dependency-review -p 'test_*.py' -v
python3 -B tools/dependency-review/lock_review.py
```

The consumer requires the reviewed lockfile-v3 shape, matching manifest/root
declarations, bounded independent regular inputs, canonical package locations,
exact unauthenticated npm registry tarball URLs and canonical SHA-512 integrity
declarations. It retains the effective package identity of npm aliases. This
checks recorded input identities; it does not acquire a tarball, verify its
payload or publisher, or independently evaluate semantic-version constraints.
Non-registry dependencies, linked packages and other lock schemas need a new
review instead of silent acceptance.

The declaration graph resolves nested and hoisted locations, terminates cycles,
and records each root's regular, development, optional and peer routes. These
routes are metadata relationships, not proof that application code calls a
package. All lock locations are included, including optional/platform packages;
no installed-platform projection or runtime reachability is inferred. Missing
transitive targets remain explicit unresolved records with their declaration
scope and the parent's optional/platform metadata. Missing root declarations
and malformed input identities fail the inventory. A completed inventory does
not mean the lock or application has completed review.

## Current source observations

The unchanged contracts lock records 25 packages. `memorystream` has no declared
license field; that absence does not establish whether its publication includes
a license. The unchanged web lock records 176 packages. `esbuild` and `fsevents`
declare install scripts; this inventory does not run or review those scripts.

`@tailwindcss/oxide-wasm32-wasi` is marked optional with CPU `wasm32`, but its six
regular dependency declarations have no resolved location in the web lock:
`@emnapi/core`, `@emnapi/runtime`, `@emnapi/wasi-threads`,
`@napi-rs/wasm-runtime`, `@tybys/wasm-util` and `tslib`. The inventory reports
`allRequiredDeclarationTargetsRecorded: false`; it does not classify these
regular declarations as optional edges or qualify WASI support. Missing peer
and optional declarations are listed separately by scope. Installed-platform
behavior and lock regeneration require separate controlled qualification.

CI adds a separate bounded `lock-inputs` job while retaining the existing vendor
and web jobs. The checkout uses the selected head, read-only repository
permissions and no persisted credentials. This job writes its JSON inventory to
the job log and downloads no runtime, browser or dependency. The runner's Python
identity is observed; complete runner/toolchain provenance remains open.

## Remaining acceptance

Run and retain a source-bound advisory review for both locks, then assess each
finding against actual contract/compiler and browser/build-tool use. The
[npm audit documentation](https://docs.npmjs.com/cli/v11/commands/npm-audit/)
distinguishes a registry report from remediation: `audit fix` changes inputs.
No scan, fix, dependency update or waiver is performed by this inventory.

Original third-party license texts, distribution notices, complete output-bound
SBOM/license obligations, semantic and economic review, supported-platform
qualification and real wallet/chain/operator acceptance remain open. The
[ENS provenance review](../contracts/VENDOR_PROVENANCE.md) and separate isolated
contract contribution retain their original source and qualification bindings.
This change does not requalify those historical revisions or combine the two
Draft PRs. No Pages deployment, release, signing or production acceptance follows
from a completed inventory or green CI.
