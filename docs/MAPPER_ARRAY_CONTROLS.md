# Bounded generated-mapper and root-library controls

The review-only proposal selects Chromium BiDi `157.0.8090-0` and root Zod
`4.6.7`. Its published `mapperTab.js` and source map contain a separate Zod
version object with `major: 4`, `minor: 6`, `patch: 5`. A root lock update does
not replace this generated mapper payload. The version object is a source
observation, rather than an independently authenticated embedded manifest.

The [upstream advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)
lists versions before `4.6.6` as affected. Its
[source fix](https://github.com/colinhacks/zod/commit/a0ebf970f2d752e5f58527cd2942ff48be4f46bd)
adds upper-size checks before array element parsing where compatible with the
schema's checks. Version labels and missing patch markers alone do not establish
runtime reachability, exploitability or complete semantic equivalence.

## Source and execution boundary

The [preparer](../tools/dependency-review/mapper_size_controls.py) uses the
existing changed-publication plan and preserved candidate lock. In hosted CI it
requests exactly two capped raw archives, verifies their locked SHA-512, raw
SHA-256/bytes, complete regular-member inventory and manifest binding, and
indexes original tar offsets in memory. It creates no extracted package tree
and performs no candidate dependency installation or lifecycle execution.

The [worker](../tools/dependency-review/mapper-size-worker.cjs) rechecks each
raw and expanded archive and each loaded member. It explicitly removes the
unique mapper browser/CDP bootstrap tail, retaining the original declaration
prefix and adding a small capture expression. Original, instrumented and capture
hashes remain in the report. The original published script is unchanged. This
instrumented program is not a qualification of the complete mapper or browser.

The fixed root library is linked from reviewed archive members with Node's
experimental `SourceTextModule` API. Only relative, archive-local imports are
allowed. Both VM contexts disable string and WebAssembly code generation;
each evaluated program has a time limit. VM contexts are not a security
boundary. These controls do not qualify compiled-schema JIT paths, browser
isolation, network exposure or attacker reachability.

## Small calibration cases

Eight cases run for each profile, with arrays of at most three elements:

- Valid upper bound, exceeded upper bound and exceeded exact length.
- A lower-bound failure that still needs element parsing.
- A shortening rewrite before an upper bound, which must retain rewrite behavior.
- A nested upper bound and its issue path.
- A wrong container and invalid elements above an upper bound.

A successful control result requires the generated profile to visit all three
elements above a limit of two, while the fixed profile rejects before element
refinements. The shortening rewrite still visits three elements in both
profiles. Complete success, issue codes/paths, element-visit counts and output
lengths are retained. No oversized or pathological input is used.

This deliberately observed difference is calibration evidence, not a passing
migration requirement or security waiver. The web lane adds one bounded command
and retains its actual stdout/stderr with the report and source binding. Raw
source trees and archives are not recursively uploaded. Local cached-source
results remain separate from each revision's hosted execution.

## Open gates

The current application still uses Puppeteer `25.12.0` and Zod `3.25.76`.
Neither its advisory nor the proposed mapper's embedded copy is remediated by
these controls. A compatible patched/rebuilt parent, complete candidate graph,
actual Node parser/API behavior, browser/CDP/BiDi behavior and owner acceptance
remain required before adoption. The funded chain-verification consumer is not
run here. Production remains **NO_GO**.
