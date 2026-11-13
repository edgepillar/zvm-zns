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
no installed-platform projection or runtime reachability is inferred. Schema 2
separates ordinary lock targets, bundled archive declarations, absent optional
peers and genuinely unresolved declarations. A bundle declaration does not by
itself prove archive contents. Peer metadata without a corresponding dependency
declaration stays visible and does not create an invented dependency. Missing
root targets and malformed input identities fail the inventory. A completed
inventory does not mean the lock or application has completed review.

## Current source observations

The unchanged contracts lock records 25 packages. `memorystream` has no declared
license field; that absence does not establish whether its publication includes
a license. The unchanged web lock records 176 packages. `esbuild` and `fsevents`
declare install scripts; this inventory does not run or review those scripts.

`@tailwindcss/oxide-wasm32-wasi` is optional with CPU `wasm32`. Its six regular
dependencies are also listed in `bundleDependencies`, rather than represented
as separate lock locations. The previous schema-1 report omitted that field
and classified them as missing targets. That classification was incomplete;
it is withdrawn as evidence of a broken lock. The package and lock versions
are unchanged. See npm's [bundle dependency semantics](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/#bundledependencies).

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

CI adds a separate bounded `lock-inputs` job while retaining the existing vendor
and web jobs. The checkout uses the selected head, read-only repository
permissions and no persisted credentials. This job writes its JSON inventory to
the job log, then obtains the one exact bundled publication with a 32 MiB
transport cap and deadline. The reader verifies locked SHA-512, bounded complete
gzip/tar data, paths, member types, counts, identities and original notice hashes
without filesystem extraction. Data tests use only in-memory archive fixtures.
No package, runtime or browser is installed by this job. The runner's Python
identity is observed; complete runner/toolchain provenance remains open.

To inspect an already acquired archive in an explicitly owned location:

```sh
python3 -B tools/dependency-review/bundled_archive.py --root web --location node_modules/@tailwindcss/oxide-wasm32-wasi --archive /path/to/oxide-wasm32-wasi-4.3.3.tgz
```

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
