# OpenZeppelin source qualification

The tracked contracts lock selects OpenZeppelin Contracts 4.9.6. This updates
the 4.x package used directly by `ZNSRegistrar` for four `Base64.encode` calls.
The [upstream advisory](https://github.com/OpenZeppelin/openzeppelin-contracts/security/advisories/GHSA-9vx6-7xxf-x967)
lists 4.9.6 as a patched version. The v5 alias, compiler 0.8.26, ENS publication,
local Solidity sources, production settings and other dependency selections are
unchanged. No deployment or operator state is changed by this source update.

## Reviewed comparison before adoption

The comparison at commit
[`15e373b2c86c08739cdd3e580c4cd0f7057c74b0`](https://github.com/edgepillar/zvm-zns/commit/15e373b2c86c08739cdd3e580c4cd0f7057c74b0)
used two fresh hosted profiles, 4.9.3 and 4.9.6, with the same compiler/settings
and seven hash-verified immutable control files from the separate contract-context
Draft. [Automatic CI run 43523367551](https://github.com/edgepillar/zvm-zns/actions/runs/43523367551)
completed on its first attempt. Each profile passed 33 test/subtest events with
zero failures, skips, cancellations or TODOs. These controls cover synthetic
contract behavior and a bounded Base64 regression; they use no signing keys or
live network transport.

The padding control used lengths 0 through 96 and three allocated tail-byte
values: 291 cases per profile. The legacy profile observed 128 noncanonical
encodings; the patched profile observed zero. All 291 allocated tails were
restored in each profile. All ten ABIs stayed equal; only `ZNSRegistrar` changed
its creation executable part after separating Solidity metadata.

Artifact `14084262404` was 210,439 bytes with SHA-256
`7f155764f6a27d36bf5ad0a009dd2d1fb7ed375dc531efa22d0f7f16cf9fc179`.
The explicit output packet, all retained command streams, 89 compiler source
units and original license bytes were replayed against the source/plan pins
before adoption. This replay did not recompile locally. The packet was a candidate
at its producer commit; its evidence does not qualify later source revisions.
The earlier comparison commit `09e162b13d9ba6d14254d5d60bfcb257ee6f4422`
failed before contract tests because the original build reads package Solidity
files at fixed paths. That failed run remains historical evidence.

The original [comparison plan](../tools/dependency-review/openzeppelin-candidate.json)
and helper remain frozen inputs. Run that historical comparison from its recorded
producer revision, rather than assigning its old source pins to the current tree.

## Current tracked source checks

The [current plan](../tools/dependency-review/openzeppelin-current.json) binds the
tracked inputs, exact generated outputs, selected package, original retained
license and immutable control sources. The current CI lane creates one fresh
job-owned profile and one locked test dependency installation. It ignores npm
lifecycle scripts and uses empty explicit npm configuration files. An import
fallback preserves ordinary nested resolution. Only the 19 reviewed Solidity
package files are staged at the original build's fixed paths, after hash checks;
no dependency tree is copied or linked into a second installation directory.

The lane rebuilds the original application source and requires byte equality for
all twelve tracked generated files: ten contract artifacts, the compiler input
and the frontend ABI module. It then runs the full pinned contract controls and
291 patched padding cases. Source inputs must stay unchanged, all test totals
must pass without skips, and every bounded command stream must be complete.
It retains source bindings, the report and explicit streams, without recursively
packaging caches, profile directories or node_modules. The frozen legacy
calibration is not repeated by this current-source lane.

## Remaining acceptance

The original MIT license for this 4.x package is retained in
[`contracts/vendor/notices/openzeppelin-contracts-4.9.6-LICENSE`](../contracts/vendor/notices/openzeppelin-contracts-4.9.6-LICENSE).
Its npm archive had no standalone license, so the byte-exact license comes from
the immutable upstream Git revision recorded in the package plan. That source
binding is separate from a registry signature or publisher attestation.

Current-source CI must qualify each new revision. Test dependencies need their
own advisory/provenance review. Other application advisory matches, full output
and legal/notice review, supported platforms, real wallet/gateway integration,
accepted bytecode/genesis, and independent maintainer/operator acceptance remain
open. This is neither an independent audit nor release or production approval.

Local reuse of a historical dependency tree was refused by its unchanged
manifest when an unregistered metadata entry was observed. The original entry,
refusal and ownership evidence remain preserved; this lane uses fresh hosted
inputs without changing local storage or cleanup authority.
