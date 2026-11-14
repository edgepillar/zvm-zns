# Paired browser qualification

This hosted Linux x64 lane extends the source checkpoint in
[BROWSER_INPUTS.md](BROWSER_INPUTS.md). Its assertions become evidence only when
the exact revision's automatic CI command receipts and artifacts are reviewed.
Adding this lane does not establish a successful browser run.

The two frozen pairs are Puppeteer 25.12.0 with full Chrome 154.0.8037.57 and
Puppeteer 25.17.0 with full Chrome 157.0.8103.50. Each pair runs CDP and explicit
WebDriver BiDi. Each archive is downloaded once, checked against its raw digest
and complete 301-file inventory, and extracted once into a new hosted job-owned
directory. The source revisions, executable bytes, browser version process,
actual loaded Node package members, native module resolution, commands, exits,
served static resource pins and bounded screenshots are retained as evidence.
The full product version and executable pin establish the selected browser
revision. User-Agent is retained as a display observation with a matching major
version: [Chromium reduces its minor/build/patch tokens](https://www.chromium.org/updates/ua-reduction/).
That string is not a second full-binary identity check. Failed workers retain
partial session/closure observations with an explicit incomplete status.

The application has no tracked deployment records. The normal baseline and
candidate builds must display that state. Separate fixture builds use the same
71 frozen first-party source files, an explicitly synthetic deployment and a
loopback-only read-only RPC fixture. They check available-name search, yearly
price, name navigation, a two-year price, theme persistence and desktop/mobile
layout. Both candidate builds and the baseline fixture retain the application's
TypeScript check before Vite. The existing baseline normal build is reused.

The separate baseline fixture reconstructs original published package members.
It prefers the already verified, lifecycle-disabled candidate installation when
name, version, URL and integrity all match; baseline-specific publications use
their verified baseline members. This avoids adopting install-time transforms
such as esbuild's optimized hard-linked executable. All fixture destinations
are new portable regular files, individually hash checked. The original normal
baseline installation and its build remain unchanged.

The RPC server uses the actual selected viem package to decode the tracked ABI
and encode its responses. Its finite method, contract and function allowlists
reject unknown requests. It has no upstream RPC forwarding, wallet provider or
signing implementation. The funded verification script is excluded. Synthetic
deployment builds are qualification fixtures, not release artifacts.
The two parameterless reads accept an omitted `params` field or an empty array,
consistent with the [JSON-RPC request shape](https://www.jsonrpc.org/specification#request_object).
Other allowed reads still require explicit positional parameters.

The worker reads the tracked screenshot caller's launch expression, then adds
explicit hosted profile, protocol, timeout and background-networking options.
It does not execute the complete original screenshot script. Both protocols
exercise benign explicit-accuracy geolocation. BiDi also observes omitted
accuracy; the candidate must return the default accuracy and accept a null reset.
Any baseline rejection remains an observation, not a waived security finding.

The two browser archives total 399,750,774 bytes and expand to 838,959,266 bytes.
The lane budgets 3 GiB of working allocations above a 10 GiB free-space floor,
caps the portable baseline package copy at 256 MiB and each SDK's combined
browser profiles at 192 MiB. Only bounded reports, command streams and twelve
PNG captures are uploaded. Archives, profiles, installed package trees and
fixture distributions are excluded from the artifact.

The source and page-request observers are instrumentation, not operating-system
network confinement. The tracked caller's `--no-sandbox` flag remains explicit.
This lane does not authenticate the browser publisher independently, establish a
reproducible Chromium build, qualify other platforms or complete license review.
Raw published baseline/candidate packages remain unchanged: the separately
derived parser guard and rebuilt mapper are not installed into these profiles.
Their coherent integration, shipped maps/notices, broader application acceptance
and the full five-repository D04 acceptance remain open. Production is **NO_GO**.
