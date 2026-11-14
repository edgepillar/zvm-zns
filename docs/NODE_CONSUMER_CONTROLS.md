# Actual Node entry and tracked caller option qualification

The web lane installs the **raw published** review-only candidate into its
existing job-owned proposal directory with `npm ci --ignore-scripts`, including
dev and optional dependencies. Application inputs stay unchanged. The derived
geolocation guard and rebuilt browser mapper are not installed into this profile.
The baseline reuses its existing CI installation.

Before candidate package execution, the lane classifies every lock row for
Linux x64 glibc. Incompatible optional packages and their absent descendants
have explicit exclusion records; missing compatible packages are refused.
Other platforms remain unqualified.

The source reader uses npm's bundled `cacache.ls.stream` API to locate raw
publications in **this job's new configured cache**. It verifies raw SHA-512,
bounded regular tar members, manifest identity/dependencies and every published
installed member SHA-256. It does not assume an opaque cache layout, access a
historical cache, clean/verify/evict cache data or perform a fallback fetch.
The cache is an immediate input, not permanent evidence storage. See the
[npm cache design](https://docs.npmjs.com/cli/v11/commands/npm-cache/) and
[cacache API](https://github.com/npm/cacache). The npm/cacache toolchain is not
independently authenticated by these checks. Extra installed files and complete
publisher, advisory and legal acceptance remain outside this gate.

The default archive-member ceiling is 8,192. The complete locked
`viem@2.57.1` publication has 10,282 regular files. Its
[measured source budget](../tools/dependency-review/profile-source-budgets.json)
allows exactly those 10,282 members only after matching the selected identity,
raw SHA-512/SHA-256, expanded byte count and complete member-pin inventory hash.
Other publications retain the default ceiling. File-type, path, expansion,
per-member and aggregate guards stay in force; this changes no storage quota.

Each profile then runs in a fresh real Node process with filesystem writes,
child processes and workers disallowed by its permission profile. Native ESM
resolution uses the selected installation's parent URL and normal import
conditions. Synchronous `registerHooks` observes ordinary resolution and compares
each loaded file and loader-returned source with its publication member pin.
The hook returns the original loader result. Baseline changed packages use the
existing reviewed publication pins; unchanged publications reuse the matching
candidate source inventory. CommonJS remains under Node's normal synchronous
hook behavior. See [Node module hooks](https://nodejs.org/api/module.html).

Node can leave a CommonJS `.js` load format undefined until native syntax
detection. The observer records this as `node-autodetect` only when both native
format fields are undefined and the load conditions contain `require` without
`import`. It records the native fields and conditions without setting a format
or changing the returned source. Other formats remain refused. Four positive
and eight refusal cases check this boundary before package execution. See the
[Node 22 loader](https://github.com/nodejs/node/blob/v22.23.4/lib/internal/modules/cjs/loader.js)
and [hook result validation](https://github.com/nodejs/node/blob/v22.23.4/lib/internal/modules/customization_hooks.js).

The worker imports real Puppeteer, its BiDi-over-CDP adapter and the BiDi package
main. It observes the expected public API shapes. It extracts only the two
source-pinned `puppeteer.launch` option expressions from `shots.mjs` and
`verify.mjs`, supplies a controlled executable-path string and calls the actual
Puppeteer `defaultArgs` API. It records complete argument arrays, input mutation
checks and changes across profiles. Neither application script is executed.
The verification script's funding, signing and registration path is not invoked.

Both reviewed Puppeteer Node publications expose an asynchronous public
`defaultArgs` method. The worker awaits that public result before checking and
recording the actual returned array. The selected caller options pass directly
to the public API; its returned array is checked without normalization.

Four source-reader refusal controls per profile precede package execution.
Common network entry-point guards record unexpected operations; these guards
and module hooks are not a security sandbox or complete network confinement.
The permission model and instrumentation also limit what this gate establishes
about an ordinary uninstrumented launch.

This gate qualifies actual installed Node imports and the selected option calls.
It does not launch Chrome, connect CDP, invoke protocol handlers, execute browser
mapper bootstrap/JIT, qualify the funded verification workflow or accept browser
argument changes. Real unfunded browser/application controls, installation of
the derived fixes with coherent shipped source maps/notices, broader API cases,
other platforms and maintainer/operator acceptance remain open. Production is
**NO_GO** and the application migration is not adopted.
