# Locked npm input review

The read-only inventory covers `contracts/package.json`,
`contracts/package-lock.json`, `web/package.json` and `web/package-lock.json`.
It uses Python's standard library and installs or executes no dependency.

```sh
python3 -B -m unittest discover -s tools/dependency-review -p 'test_*.py' -v
python3 -B tools/dependency-review/application_lock_review.py --archive /path/to/oxide-wasm32-wasi-4.3.3.tgz
```

The consumer requires matching lockfile-v3 root declarations, bounded regular
inputs, canonical package locations and exact npm registry tarball URLs with
SHA-512 integrity. It keeps the effective identity of npm aliases. It checks
the provided parent tarball against the lock and binds the bundled members
by manifest. Semantic-version constraints and publisher identity require
separate evidence. Non-registry dependencies, linked packages and other lock
schemas require a separate review.

The declaration graph resolves nested and hoisted locations, terminates cycles,
and records each root's regular, development, optional and peer routes. These
routes are metadata relationships, not proof that application code calls a
package. All lock locations are included, including optional/platform packages;
no installed-platform projection or runtime reachability is inferred. Schema 2
separates ordinary lock targets, bundled archive declarations, absent optional
peers and genuinely unresolved declarations. A bundle declaration does not by
itself prove archive contents. Peer metadata without a corresponding dependency
declaration stays visible and does not create an invented dependency. Missing
root targets and malformed input identities fail the inventory. A completed
inventory does not mean the lock or application has completed review.

## Current source observations

The contracts lock records 24 package locations. `memorystream` has no declared
license field, so check the actual publication for license material. The web
lock records 182 locations, including six members of the WASI archive.
See the [application runtime](APPLICATION_RUNTIME.md) for installation and
lifecycle script policy.

`@tailwindcss/oxide-wasm32-wasi` is optional with CPU `wasm32`. Its six
`inBundle` rows identify members of that parent archive. Earlier lock snapshots
recorded bundle declarations without separate rows. See the
[current bundle binding](BUNDLED_LOCK_RECORDS.md) and
[npm bundle dependency semantics](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/#bundledependencies).

The locked 4.3.3 publication has 1,829,808 compressed bytes and SHA-256
`d5b61fbe10d237f7565032a74b03b5be6c83b309037ee407e2b5b46f24738823`.
Its original SHA-512 matches the lock. In-memory inspection observed 113 regular
files, 11,574,189 payload bytes and six bundled package manifests:

| Bundled package | Observed version | Declared license |
| --- | --- | --- |
| `@emnapi/core` | 1.11.1 | MIT |
| `@emnapi/runtime` | 1.11.1 | MIT |
| `@emnapi/wasi-threads` | 1.2.2 | MIT |
| `@napi-rs/wasm-runtime` | 1.1.4 | MIT |
| `@tybys/wasm-util` | 0.10.2 | MIT |
| `tslib` | 2.8.1 | 0BSD |

Every declared bundled package manifest is present; no internal regular
dependency declaration lacked an archive target. Name/version/manifest pins
and all regular file SHA-256 values are recorded. This is content inspection,
not independent semantic-version validation or execution of WASI code.

The selected filename profile observed five original notice candidates. The
outer publication, `@napi-rs/wasm-runtime` and `@tybys/wasm-util` have no standalone
candidate under that profile. This is not proof that source headers contain no
attribution or that a license obligation is violated. Original bytes remain
unchanged; complete notice and distribution review is still required.

The contracts/web inventories record 6/14 absent optional peer declarations.
These are optional peers, not evidence of broken installation. The contracts
lock also retains optional `debug` peer metadata under `follow-redirects` without
a corresponding peer dependency declaration. No dependency route is invented
for that metadata. Both roots have zero unresolved regular declarations in
this selected metadata inventory; complete lock review remains false.

The bounded `lock-inputs` job checks out the selected head with read-only
repository permissions and credential persistence disabled. It fetches one
locked publication under a 32 MiB transport cap and prints the combined lock
and notice inventory. A single inspection verifies the complete bounded
gzip/tar stream, paths, member types, hashes and original notice candidates.
The data tests use in-memory archive fixtures. The job records its Python
version. Complete runner and toolchain provenance remains open.

The hosted CI job pins [checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1)
and [setup-node v7.1.0](https://github.com/actions/setup-node/releases/tag/v7.1.0).
The actions use the runner's Node 24 runtime. The npm build and contract jobs
still select Node 22 and use their own current-job caches. The setup action's
automatic package-manager cache is disabled. The workflow runs on
`push` and `pull_request` with `contents: read`.

## Remaining acceptance

Run and retain a source-bound advisory review for both locks, then assess each
finding against actual contract/compiler and browser/build-tool use. The
[npm audit documentation](https://docs.npmjs.com/cli/v11/commands/npm-audit/)
distinguishes a registry report from remediation: `audit fix` changes inputs.
No scan, fix, dependency update or waiver is performed by these consumers.

Original third-party license texts, distribution notices, complete output-bound
SBOM/license obligations, semantic and economic review, supported-platform
qualification and real wallet/chain/operator acceptance remain open. The
[ENS provenance review](../contracts/VENDOR_PROVENANCE.md) and separate isolated
contract contribution retain their original source and qualification bindings.
This change does not requalify those historical revisions or combine the two
Draft PRs. No Pages deployment, release, signing or production acceptance follows
from a completed inventory or green CI.
