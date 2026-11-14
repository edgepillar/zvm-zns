# Independent proposal version and engine checks

The Puppeteer 25.17.0 / BiDi 157.0.8090-0 / Zod 4.6.7 proposal remains separate
from the application. Its source inventory binds every lock row, including six
bundled member manifests, before the version checks run. The original strict
registry reader and the application's current inputs are preserved.
The version cases use the
[selector-preserved candidate](PROPOSAL_PLATFORM_SELECTORS.md). The raw npm
output has its own retained artifact path and hash. Restoring an existing libc
constraint does not turn a version comparison into platform qualification.

## Cases and policies

The [case builder](../tools/dependency-review/proposal_versions.py) checks the
original lock hash and reconstructs its declaration graph. Missing, changed or
duplicated resolved edges and changed unresolved/optional-peer gaps are refused.
Each resolved dependency, optional dependency and peer edge retains its source,
scope, name, requested range and actual target. npm aliases use the effective
package name and the alias's range. No missing peer becomes an invented match.

Every recorded `engines.node` and `engines.npm` constraint, including a root
constraint when present, is compared with the observed producer toolchain.
Optional packages and their OS/CPU/libc declarations remain visible. This is an
all-lock-rows version comparison, not a qualification of installed platforms.

The [range evaluator](../tools/dependency-review/version_ranges.cjs) selects an
explicit policy for each case:

| Purpose | Prereleases | Loose parsing |
| --- | --- | --- |
| Dependency declaration satisfaction | Default exclusion | Disabled |
| Recorded Node/npm engine profile | Included | Disabled |
| Security advisory comparison | Included | Enabled |

The dependency policy follows the default
[node-semver prerelease rules](https://github.com/npm/node-semver#prerelease-tags).
The engine policy follows npm's
[engine check](https://github.com/npm/npm-install-checks/blob/main/lib/index.js).
Advisory comparisons retain the existing scanner policy and remain a separate
evidence class. Ten small positive, negative and invalid-input controls check
these distinctions. Actual dependency cases have no expected-success assertion
inside the worker, so complete violations and unknowns survive for review.

## Reviewed tool source and retained evidence

The web plan pins SemVer 7.8.4: its 29,325-byte npm publication has SHA-256
`700e9afebc59f214dc2d833d159acd050712800e7868ad50b5412994b7731c12`.
All 53 regular members have individual SHA-256 pins. A single capped hosted
request checks SHA-512, the complete archive and member set before extracting
only those regular members into a new job-owned tool directory. No npm tool
installation or lifecycle script is needed. This range stage executes the
separate tool without executing proposed application packages. The subsequent
[mapper controls](MAPPER_ARRAY_CONTROLS.md) execute selected proposed code under
a separate, bounded scope; they do not install the candidate graph.

Before loading SemVer, the worker verifies every supplied source pin and the
dependency-free tool manifest. It checks every loaded scanner module against
the reviewed inventory and rechecks source pins after evaluation. These content
checks do not authenticate the publisher or registry attestations.

The producer retains the original proposed manifest/lock, all version cases,
the observed Node/npm profile, executed tool-source hashes and the bounded raw
command streams. The result reader refuses incomplete, duplicate or rebound
case sets and a different policy. Violations and invalid ranges stay distinct;
either prevents this version gate from passing. The existing web job adds one
range command after its lock-only proposal step. No manual CI retry is implied.

## Acceptance boundary

A satisfied declaration range proves only that the recorded selected version
matches that range. A satisfied engine range proves only the recorded version
comparison for the observed profile. Neither establishes package payload
integrity for the full graph, API/schema/browser compatibility, runtime
reachability, complete advisory coverage, platform support or legal obligations.

The application's Zod 3.25.76 selection and its
[advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) remain open until a
compatible application migration is adopted. Feed omissions and historical
findings are retained without waivers. Full-graph qualification, isolated
browser/API controls and owner acceptance remain required. Production is
**NO_GO**; the proposal and the original roadmap items are not accepted here.
