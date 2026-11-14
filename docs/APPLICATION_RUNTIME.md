# Adopted application dependency runtime

The actual `web/package.json` now selects Puppeteer 25.17.0 and root Zod 4.6.7.
The actual lock is the exact candidate lock retained by the earlier qualified
coherent-profile revision. Its original platform selectors are preserved.
This is application dependency adoption in this Draft, not full application,
platform, publisher, legal, maintainer or production acceptance.

```sh
cd web
npm ci
npm run build
# Alternatively prepare/check the developer tooling explicitly:
npm run prepare:runtime
node scripts/prepare-runtime.mjs --check
```

The project-local `.npmrc` disables automatic dependency install scripts. The
explicit `build`, `dev` and `typecheck` commands run the first-party preparation
before their tools. Explicit npm run commands still run with `ignore-scripts`;
pre/post hooks do not, as described in the
[npm configuration documentation](https://docs.npmjs.com/cli/v11/using-npm/config/#ignore-scripts).
No global npm/Git setting is changed. The direct screenshot and funded
verification scripts require already prepared bytes before importing Puppeteer.
This qualification never executes the funded verification script.

Preparation uses nine committed payloads under
`web/vendor/chromium-bidi-157-reviewed`: the guarded Node parser and its map,
the rebuilt embedded mapper and its map, linked legal text and four original
notices. About 4 MiB of explicit source payloads avoids a compiler installation,
mapper rebuild or additional network request during preparation. Original and
effective hashes are separate. Original npm SRI does not authenticate modified
or added bytes. Vendored upstream comments and notices retain their exact bytes.

The helper checks the complete lock hash, application declarations, installed
package manifest, fixed nine-member scope and every original/effective payload.
It accepts either all original inputs or all prepared outputs. Unknown, linked
or mixed states are refused before replacement. A second successful invocation
only verifies. Every replacement is individually atomic; the nine-file operation
is not power-loss atomic. On a synchronous failure, only known outputs of that
invocation are eligible for byte restoration. Uncertain state is preserved and
refused; no unknown file or directory is recursively removed by the helper.

The current hosted Linux x64 glibc controller installs the actual application
once with third-party lifecycle scripts disabled. Before preparation it binds
the installed graph to raw SHA-512-verified current-job npm cache publications.
After preparation it checks all nine effective members. It runs installer
success/idempotency/refusal/rollback controls, current source-map and Vite
controls, the actual normal build, and an explicitly synthetic fixture build.
The fixture uses portable regular copies and explicit preparation/compiler
steps, without npm-generated executable links or operator data.

One pinned Chrome 157 archive is downloaded and extracted. Two SDK sessions
exercise CDP/BiDi and nominal/synthetic UI behavior. Two additional full embedded
mapper bootstraps reuse the CDP Chrome process. Twelve native Node and twelve
generated-browser direct cases remain separate from object-only wire transport
refusals. Source observers return native module resolution/load results unchanged;
they are not operating-system isolation. The tracked launch flag `--no-sandbox`
is unchanged and does not establish a browser sandbox.

Chrome receives a short, physical job-owned temporary directory beside the
evidence directory. Its UTF-8 path length is checked before installation to
leave room for Chrome's generated Unix socket path. No socket or link fixture
is run under local managed scratch.

The controller retains complete bounded command streams, current source binding,
the raw source inventory, the explicit derivative binding and six PNG payloads.
The committed mapper/maps are referenced by exact source pins, not copied into
another artifact. It preserves a 10 GiB free-space floor plus allocation reserve.
No wallet, chain, registration, signing, release or deployment action is included.

The changed JavaScript payloads carry prominent change headers; the replacement
maps begin with `x_edgepillar_changes`. The manifest retains the previous
payload/manifest pins and original source/compiler evidence. The parser's line
map includes its header; the mapper's mappings shift by exactly one generated
line, preserving all 177 embedded compiled-JavaScript sources and existing
mapping deltas. The five original license/legal payloads remain byte-identical.
No package manager, compiler or browser is invoked to add these notices.

The current browser worker enables Node source maps for `node_modules` before
imports. It checks the automatically populated native map cache, every parser
line, an actual mapped parser error stack and seven mapper declaration samples
using Node's native `SourceMap` API. These are compiled-JavaScript coordinates,
not reconstructed original TypeScript coordinates. See the
[Node source-map API](https://nodejs.org/docs/latest-v22.x/api/module.html#source-map-support).

For the installed embedded mapper, the same CDP Chrome parent opens its own
bundled DevTools frontend. The script retains its relative map directive and is
loaded from a finite loopback fixture. DevTools automatically fetches that map;
its actual debugger model resolves seven declaration samples and all 177 embedded
source contents. The controller checks the executed script and served map hashes,
then closes the frontend, target and route. It does not attach a substitute map
or download another browser. The separate inspection copy still executes its
full mapper bootstrap without claiming an unchanged attached map. Added renderer
processes are not counted as extra Chrome parent instances. New exact-head hosted
evidence is required before claiming these controls passed.

The previous raw baseline/candidate and separately rebuilt-profile qualifications
remain pinned to commit `1fb99473f5acbed0c41a40f7ae3eb2e2aa474ef8` and their original
artifacts. The old `web_patches.py` lane must be reproduced at its frozen revision;
it is not a current-input verifier. Those historical runs are not relabelled as
qualification of the new application inputs. Current claims require this exact
revision's successful automatic CI and artifact replay.

The development tooling payloads are outside `web/public` and are not added to
the static site's distribution. Existing static original notices are checked.
Complete shipped-license obligations, advisory reachability, supported-platform
and publisher authentication review remain open, along with all original D04
and roadmap acceptance gates. Production remains **NO_GO**.
