# Selected Node protocol-parser compatibility

The original BiDi `17.0.2` Node parser reads `safeParse(...).error.errors`.
The proposed `157.0.8090-0` parser reads `.error.issues`. Zod's
[migration guide](https://zod.dev/v4/changelog#drops-errors) records that the
`.errors` alias was removed in v4. Updating only the root library therefore
needs an error-path compatibility check, even when a valid input succeeds.

The same guide documents
[defaults inside optional object fields](https://zod.dev/v4/changelog#defaults-applied-within-optional-fields).
The generated `Script` evaluation schema has an optional `userActivation`
property with a default of `false`. Key presence can change across the migration;
the controls retain that difference rather than silently normalize it away.

## Actual module sources

The [worker](../tools/dependency-review/node-parser-worker.cjs) loads the real
published `protocol-parser.js`, generated parameter schemas and protocol error
classes. Its baseline uses the existing CI installation of BiDi `17.0.2` and
Zod `3.25.76`, already checked against every reviewed baseline member. The
[shared reader](../tools/dependency-review/verified-package-sources.cjs) rechecks
each loaded regular file, canonical path, single-link identity, size and hash.

The proposed pair reuses the two exact raw BiDi/Zod archives already obtained
for the mapper controls. Their raw SHA-512/SHA-256, complete reviewed index,
expanded digest and loaded member hashes remain checked. No additional source
request, baseline installation or candidate dependency installation is needed.

Modules link inside separate Node VM contexts directly from those sources.
Only package-local relative imports and the selected `zod` import are allowed.
The mapper browser bootstrap is not loaded. The VM contexts disable string/Wasm
code generation and impose evaluation time limits, but are not a security
boundary. These are parser calls, not dispatched browser, extension, permission,
wallet, network or chain commands.

## Required bounded cases

| Profile | Malformed namespace parameters | Valid namespace examples | Direct schema cases |
| --- | --- | --- | --- |
| BiDi 17.0.2 / Zod 3.25.76 | 77 | 13 | 2 |
| BiDi 157.0.8090-0 / Zod 4.6.7 | 80 | 16 | 2 |

Each exported namespace method must reject `null` with the actual protocol
`InvalidArgumentException` and an intact error envelope. The valid examples
cover all thirteen namespaces and the three newly added Emulation methods.
The returned data and unchanged input parameters must match the reviewed
expectations. The Script example explicitly records the optional-default key
difference. Direct schema cases cover unknown-key stripping and retained nested
issue paths. Inventorying every method's malformed-input branch does not qualify
every method's successful inputs or downstream browser behavior.

Two additional negative-calibration cases combine the legacy parser with root
Zod 4.6.7: a valid direct parse succeeds, while an invalid direct parse must
expose the legacy `.errors` incompatibility as a `TypeError`. This unsupported
combination is deliberately not accepted. There are **192 parser cases** and
four separate source-reader refusal controls, all using small ordinary inputs.

Every loaded source member, method inventory, outcome and fixture hash is
retained with the actual Node profile. The web lane adds one bounded command,
bringing its total to thirteen. Each new revision requires its own execution;
the counts above describe the required scope, not an assertion that every
revision has already passed.

## Separate upstream snapshot

The [dated source observation](../tools/dependency-review/parent-upstream-observation.json)
records the 2026-11-14 registry snapshot: Puppeteer 25.17.0 still declares BiDi
157.0.8090-0 exactly, while the registry's latest BiDi is 160.0.8161-0. The latter
publication was inspected separately without installation or code execution.
Its mapper and source-map content also carry a 4.6.5 validator version object;
the recorded upper-bound patch markers are absent. Those are source observations,
not formal patch-state or runtime proof. The observation pins the exact raw
publication and selected members. BiDi 160 is not substituted into this proposal,
and no complete absence of upstream fixes is inferred from this bounded snapshot.

## Honest partial execution and remaining gates

The report distinguishes source preparation, attempted execution, returned but
unqualified output and verified bounded results. Once a command is attempted,
package-code execution is unknown until qualified; a failed or partial command
must not become a false claim that no code ran. Actual command receipts and
streams remain available on failure.

Passing these controls qualifies selected real Node parser behavior. It does
not remediate the mapper's separately embedded validator, install or accept the
complete candidate graph, qualify compiled-schema JIT paths, establish actual
application call-path reachability or run a browser. A compatible mapper fix,
broader successful API cases, actual CDP/BiDi consumers, full graph and owner
acceptance remain required. The funded verification script stays outside this
lane. Production remains **NO_GO**.
