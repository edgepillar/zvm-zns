# ENS publication, source selection and ZNS changes

[`vendor/ens-contracts.lock.json`](vendor/ens-contracts.lock.json) binds the ENS
publication, selected import closure, dependency lock and three local ZNS
contracts. The verifier reads these inputs and reports a JSON result. It does
not install dependencies, execute vendored code, rewrite sources or extract an
archive to disk.

## Verify the inputs

With Node 22 or later, from the repository root:

```sh
node --test contracts/scripts/verify-vendor.test.mjs
node contracts/scripts/verify-vendor.mjs
node contracts/scripts/verify-vendor.mjs --archive /path/to/ens-contracts-1.7.0.tgz
```

The second command checks the local tree against the reviewed manifest. Its
result explicitly has `archiveCompared: false`. The third also verifies the
compressed SHA-256 and npm SHA-512 integrity, then streams the complete archive
and compares each selected file byte for byte. Obtain the archive from the exact
npm URL in the manifest into an explicitly owned location with a 32 MiB transport
cap. CI does this in its job-owned temporary directory and imposes a deadline.

The reviewed publication is `@ensdomains/ens-contracts` 1.7.0. It contains 963
regular files with 137,725,908 payload bytes; its compressed archive is
16,375,725 bytes with SHA-256
`29b7ba0437bf79a129abb88186ed7098b753df75015c578229024f2fb938c699`.
The selected tree has 67 Solidity files and the original MIT `LICENSE.txt`,
196,164 bytes in total. Every selected file matches that publication exactly.
The manifest retains any npm-provided Git revision separately; package digests
bind the actual publication. Registry signature or publisher-identity
attestation verification is a separate requirement.

Nine explicit roots include the unmodified ENS controller as a fork reference.
The verifier follows relative imports without treating comments or unrelated
strings as imports. Missing, extra, changed or linked source files are refused.
Ten external import paths resolve through three installed prefixes:
`@ensdomains/buffer`, `@openzeppelin/contracts` and the
`@openzeppelin/contracts-v5` alias. The complete contracts lock digest and each
prefix's effective package name, version, URL and integrity are bound. This
checks lock identity; it does not execute or independently audit those packages.

The archive reader accepts the reviewed publication's regular-file USTAR
format, verifies header checksums, canonical paths, unique members, padding,
end markers, package identity, complete counts and byte totals. It refuses
links and unreviewed archive extensions. Compressed, expanded, member-count and
selected-source limits are independent of archive declarations. Data is streamed
through the reader; the 138,463,232-byte tar stream is not written to disk.

## Review the ZNS delta

The local source digests bind this table to `src/ZNSController.sol`,
`src/ZNSRegistrar.sol` and `src/ZNSPriceFeed.sol`. Hash agreement makes source
changes visible; it does not replace independent semantic or security review.

| Area | ZNS behavior to review against ENS 1.7.0 |
| --- | --- |
| Naming scope | The controller uses `.znn` and chain-local registry state. A familiar ENS interface does not identify the chain or registry. |
| Labels | `valid` enforces 3–63 ASCII characters and the declared hyphen rules on chain. This is a different policy from client-side ENS normalization. |
| Launch premium | Never-registered short names start the existing decaying premium at launch. Length and launch time are immutable inputs; expiry/grace pricing remains a separate path. |
| Registrar metadata | Registration and renewal record labels in the local registrar so the token can describe its name and expiry. |
| Reverse names | The controller sets `addr.reverse` with `.znn` and refuses the `default.reverse` bit. |
| Rent | Registration and renewal send rent to the declared burn address. `withdraw` sends an unexpected controller balance there as well. |
| Administrative rate | `ZNSPriceFeed` is an owner-set positive rate, rather than a Chainlink observation. The feed affects base rent and premium together. |

`StablePriceOracle` converts an amount with `amount * 1e8 / latestAnswer()`.
At a feed answer of `1e8`, its price units equal native wei. The owner can change
that answer and therefore rescale quoted prices; the positive-value check is
not an economic price bound or an independent market oracle. Review the actual
feed address, current answer and administrative owner for each deployment.
Registry, registrar, controller and resolver addresses must belong to the same
accepted chain/genesis and deployment context. No live addresses or operator
identity are inferred by this source check.

## Updates and remaining qualification

A dependency or local source change intentionally fails the old review pins.
Review its source and behavior, obtain the new publication with explicit bounds,
verify its selected files and original license, and update the manifest and this
delta review together. Do not refresh hashes solely to turn a failed check green.
Action implementation updates remain full-commit pins with readable versions;
weekly dependency proposals require maintainer review.

The separate isolated contract-test contribution covers synthetic registration,
renewal, premium/grace, refunds, resolver and reverse behavior. This provenance
check does not run or requalify that suite. External dependency reachability,
complete distribution notices and output-bound SBOM/license review, current
hosted and supported-platform qualification, real wallet and external gateway
integration, accepted deployment/genesis and independent maintainer/operator
acceptance remain separate gates. See [`NOTICE.md`](../NOTICE.md) for retained
third-party attribution. Byte equality is not production approval.

## Selected OpenZeppelin 4.x update

The contracts lock and its provenance binding now select OpenZeppelin Contracts
4.9.6. The selected ENS publication and local Solidity sources remain unchanged.
The original 4.x license is retained under `vendor/notices/`, and
[`OpenZeppelin source qualification`](../docs/OPENZEPPELIN_CANDIDATE.md) records
the before/after controls and current-source CI requirements. Updating this lock
binding does not reassign the old ENS or contract-test evidence to a new revision.
