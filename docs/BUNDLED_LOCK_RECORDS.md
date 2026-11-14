# Bundled lock records and parent publication bindings

The review-only Puppeteer/Zod proposal produced by npm records six packages
inside `@tailwindcss/oxide-wasm32-wasi` 4.3.3 with `inBundle: true`. Those rows
have no independent tarball URL or integrity. The existing registry-only reader
correctly refuses that representation; its original code and historical refusal
remain preserved.

The separate [source model](../tools/dependency-review/bundled_lock.py) accepts
such a row only with its actual parent archive bytes. It checks the parent's
locked SHA-512, package identity and dependency/bundle declarations. The current
plan additionally pins the archive byte count, SHA-256, parent manifest and all
six member manifests. The publication is **1,829,808 bytes**, SHA-256
`d5b61fbe10d237f7565032a74b03b5be6c83b309037ee407e2b5b46f24738823`.

The archive inspector checks the complete compressed/tar stream, safe regular
members, expansion limits and every member hash in memory. The model then
decodes only canonical package manifests. Package-internal data manifests, such
as a module-format declaration below a package root, remain hashed archive
members and do not become invented package records.

## Identity and graph rules

Each claimed bundled lock location must correspond to exactly one canonical
manifest inside the selected publication. The complete set is a bijection:
missing members, extra claims, another parent, conflicting ownership or moved
locations are refused. Name/version, dependencies, peers, bundle declarations,
platform and license observations, and install-script declarations must agree
with the hashed manifest. Aliases retain their actual manifest identity.

Each member's source identity includes its parent lock location, parent
publication URL/SHA-512/SHA-256 and exact manifest path/size/SHA-256. Its
independent `resolved` and `integrity` fields remain null. The model refuses
attempts to supply either field on an `inBundle` row.

The original strict reader validates a registry-only projection. That projection
removes only the proven member rows and has its own labelled hash; it does not
replace the original lock hash. The final inventory includes every original
row and rebuilds declarations, nearest-location resolution, optional/peer gaps,
cycles and root routes from the complete original table. The projection is a
registry validation step, not the final dependency graph.

## Current qualification scope

Local data controls use in-memory archives with writes and network denied.
They reject unbound flags, wrong bytes/identity/declarations, fabricated tarball
fields, links, missing/extra/moved members and changed parent metadata. They also
cover aliases, cycles, data manifests and unresolved regular declarations.
The retained real proposal has 182 rows: 176 registry declarations and six
members bound to the already retained parent publication. It needs no repeated
local npm resolution, source download, archive extraction or package execution.

The existing web lane obtains the same pinned parent publication once for this
proposal check, with a byte cap and no extraction. This is one additional bounded
request in that job; the independent existing lock-input job still performs its
own original archive check. Reports retain transport pins, every manifest
binding and the original registry-only refusal. An explicit binding failure
fails the requested check and cannot fall back to an unqualified success.

These are requirements for each source revision, not a claim that every revision
has already passed hosted CI. Actual reports must bind the producer commit,
plan, source, streams and original proposed manifest/lock bytes.

## Remaining migration acceptance

This model establishes selected parent/member source bindings. It does not
authenticate publishers or registry attestations, independently verify every
version range, acquire every package payload, qualify WASI/browser runtime or
complete legal/output obligations. The full proposed graph and migration remain
unqualified and unapplied. The application's current Zod finding stays open.

Source/API review and isolated browser compatibility are separate next gates.
The existing funded chain-verification consumer is not executed by this model.
Current application inputs, compiled Solidity outputs and the original 42-item
roadmap acceptance remain unchanged.
