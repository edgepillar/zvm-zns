# Changed parent dependency publication sources

The parent migration proposal changes nine registry package names:
`@puppeteer/browsers`, `ansi-regex`, `chromium-bidi`, `devtools-protocol`,
`modern-tar`, `puppeteer-core`, `webdriver-bidi-protocol`, `ws` and `zod`.
Unchanged nested versions remain distinct lock locations. The actual application
still uses its original Puppeteer/Zod selections; this proposal is not adopted.

The [source plan](../tools/dependency-review/changed-publications.json) binds
both sides of the actual changed locations to their exact publication URLs,
locked SHA-512, raw archive SHA-256/bytes, manifest hash and every regular member
hash. Eighteen old/new publications cover the nine locations. The six previously
retained Puppeteer/BiDi/Zod archives are reused; only the twelve missing archives
are acquired locally. Each has one raw protected object. No local source tree,
second ZIP, package installation or browser download is needed for this review.

## Source binding and complete delta

The [reviewer](../tools/dependency-review/changed_publications.py) derives its
required publication set from the actual before/after lock delta. Missing,
unrelated or conflicting source identities fail. An npm alias keeps its
effective publication name, and multiple uses of one identical source share its
digest while retaining every lock location.

Each archive is bounded, SHA-512 checked and inspected in memory. The complete
compressed/tar stream, canonical paths, regular members, hashes, manifest
identity and dependency/bundle declarations are checked. Peer declarations,
platform/license metadata, engine ranges and lifecycle declarations are compared
with the hashed manifest. Source code and lifecycle scripts are not executed.

The report retains selected manifest/API-entry changes, added/removed/changed
members and original notice candidates. It excludes author/contact fields from
the shareable plan. Hashing every member is content accounting; it is not a claim
that every changed line has completed a semantic/API review.

The publications also contain precompiled mapper/IIFE files, third-party code
and source maps. Their member hashes are included. Independent embedded-code
provenance and validator-version/patch review remain separate requirements; a
root lock selection alone does not qualify those generated payloads.

Same-publication metadata, root/top-level changes and added/removed/source-kind
changes remain visible and do not disappear into the nine version changes.
The six bundled rows keep their independent parent-publication binding. The
22 dropped libc selectors have a separate, explicit
[preservation rule and original-output record](PROPOSAL_PLATFORM_SELECTORS.md).

## Selected installed source check

The web lane reuses its actual application installation to verify every reviewed
regular member of the nine **baseline** package locations. This adds no second
baseline installation or archive transport. Canonical paths, regular single-link
files, exact sizes, before/after file identity and SHA-256 must match. The report
retains each selected publication, verified member count and canonical pin-set
hash, bound to the exact source plan and application lock.

The same checker supports a separately qualified candidate installation. This
lane does not install or execute proposed application packages; candidate API
and browser controls remain subsequent work. Matching known files does not
authenticate unknown extra installed files or the publisher.

## Remaining acceptance

Changed-publication source bindings are separate from full-graph payload
integrity, publisher/registry authentication, semantic/API compatibility and
runtime reachability. Protocol/schema changes, actual CDP/BiDi behavior and the
source-pinned browser revision need isolated execution before application
adoption. The funded chain-verification consumer remains outside this lane.
Original notices are recorded, while complete shipped notices and legal/output
obligations remain open. No migration, native-platform, browser, release or
production acceptance follows from these checks. Production remains **NO_GO**.
