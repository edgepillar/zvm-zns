# Preserve platform constraints in a review-only lock proposal

The recorded npm lock-only output drops `libc` from 22 unchanged Linux package
rows. The affected families are Rollup, Tailwind oxide, Lightning CSS and one
lzma package. Their version, canonical registry URL and locked SHA-512 remain
equal to the current application. This metadata change is separate from the
nine changed registry publications and six newly explicit bundled member rows.

The complete [delta reader](../tools/dependency-review/proposal_delta.py) records
top-level/root changes, every changed common row, added/removed locations and
source-kind changes. It distinguishes a changed publication from changed
metadata for the same publication and retains field presence separately from
its value. A missing field is not silently equated with a null field.

`libc` participates in npm's
[platform selection declarations](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/#libc).
Removing a selector broadens the recorded platform constraints; this review does
not infer which native package a particular npm version would install or that
an application fails on a given platform. Both are execution questions.

## Explicit preservation rule

The proposal step preserves an existing missing `os`, `cpu` or `libc` selector
only when the before/after rows have the exact same effective package name,
version, canonical registry URL and canonical SHA-512 integrity. The baseline
selector must have the reviewed list form. An explicit conflicting selector
fails the check instead of being overwritten. A changed publication cannot
inherit its predecessor's selector through this rule. Links and bundled members
cannot acquire a fabricated independent publication identity.

Only the recorded missing selectors may change. The producer compares the raw
npm result with the preserved result and refuses any unrelated identity, root,
top-level, added/removed or source-kind change. The transformation is idempotent;
an already preserved proposal retains its original bytes.

The exact raw npm output is retained as
`npm-generated-web-package-lock.json`. Its byte count and SHA-256, the baseline
lock hash, preserved lock hash, every carried field/value/publication and all
three deltas remain in the report. The separate
`candidate-web-package-lock.json` is the preserved review candidate. Both are
explicit artifact members; neither replaces historical outputs or application
files. The source-bound inventory and version/engine checks run on the preserved
candidate, whose hash must match the reviewed changed-source plan.

## Evidence limits

This is preservation of an existing lock constraint for identical recorded
publication bytes. It does not authenticate a registry manifest, establish native
platform support or qualify a different publication's platform declarations.
The original npm output remains evidence of the observed metadata loss. The
current application stays unchanged and the proposal remains unapplied.

Small in-memory controls cover conflicting selectors, changed identities,
aliases, all three selector types, incomplete identities, idempotence, null versus
missing fields and added/removed/reclassified rows. Real before/after locks need
their own retained replay and producer evidence. Passing these controls does not
complete the full graph, platform, browser, legal or migration gates.
