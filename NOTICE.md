# Third-party material

zvm-zns is MIT-licensed (LICENSE). `contracts/vendor/ens-contracts/` is ENS's
own source, `@ensdomains/ens-contracts` 1.7.0, under its MIT licence
(`contracts/vendor/ens-contracts/LICENSE.txt`). `ZNSController` is a fork of
ENS's `ETHRegistrarController`, and keeps that licence for the code it carries.

The contracts build selects `@openzeppelin/contracts` 4.9.6 under MIT. Its
original upstream license is retained at
[`contracts/vendor/notices/openzeppelin-contracts-4.9.6-LICENSE`](contracts/vendor/notices/openzeppelin-contracts-4.9.6-LICENSE).
The source and qualification bindings are described in
[`docs/OPENZEPPELIN_CANDIDATE.md`](docs/OPENZEPPELIN_CANDIDATE.md).
This notice covers that selected 4.x package; complete dependency and output
notice/license review remains required, including the separate v5 alias and
Buffer package.

## Selected web build dependencies

The web build selects Vite 7.3.8 (MIT and its bundled notices) and source-map-js
1.2.2 (BSD-3-Clause). Their original publication license files are retained at
[`web/public/notices/vite-7.3.8-LICENSE.md`](web/public/notices/vite-7.3.8-LICENSE.md)
and [`web/public/notices/source-map-js-1.2.2-LICENSE`](web/public/notices/source-map-js-1.2.2-LICENSE).
The build retains these bytes under `notices/` in the static output. This does
not establish complete distribution notices or legal acceptance for all other
packages. See [`docs/WEB_DEPENDENCY_PATCHES.md`](docs/WEB_DEPENDENCY_PATCHES.md)
for source bindings, selected controls and remaining qualification.

The browser build publishes `notices/npm/index.json` with the original notice
files for its reported npm origins and identified bundler runtime helpers.
Identical notice bytes share one file. Hosted CI compares the shipped files
with their locked publication archives. Review of generated and inlined
material remains open.

## Selected compiler runtime dependencies

The unchanged solc 0.8.26 tooling selects follow-redirects 1.16.3 (within its
declared 1.x range) and tmp 0.2.7 through an explicit override scoped to that
compiler version. The original MIT notices are retained at
[`contracts/vendor/notices/follow-redirects-1.16.3-LICENSE`](contracts/vendor/notices/follow-redirects-1.16.3-LICENSE)
and [`contracts/vendor/notices/tmp-0.2.7-LICENSE`](contracts/vendor/notices/tmp-0.2.7-LICENSE).
These are compiler-tooling selections; complete source/output distribution and
license obligations still require review. See
[`docs/COMPILER_DEPENDENCIES.md`](docs/COMPILER_DEPENDENCIES.md) for the override,
actual application installation, bounded controls and remaining platform gates.

## Reviewed browser developer tooling derivative

The application development tooling prepares a local chromium-bidi 157.0.8090-0
derivative rebuilt from published compiled JavaScript, with Zod 4.6.7 and a
reviewed parser type guard. It is outside `web/public`; the static site build
does not ship these payloads. The two changed JavaScript files carry explicit
change notices, and both replacement JSON maps carry `x_edgepillar_changes`.
Original TypeScript maps are not reused for the changed files.

Original chromium-bidi Apache-2.0, Zod MIT and mitt MIT license texts are retained
under [`web/vendor/chromium-bidi-157-reviewed/payload/notices/`](web/vendor/chromium-bidi-157-reviewed/payload/notices/).
That directory also retains the original esbuild MIT compiler notice. The linked
`mapper.js.LEGAL.txt` and existing upstream copyright/license comments are
preserved. These materials retain their own licenses; this project's MIT license
does not replace them. See the
[`derivative notice`](web/vendor/chromium-bidi-157-reviewed/NOTICE.md),
[`manifest`](web/vendor/chromium-bidi-157-reviewed/manifest.json) and
[`runtime qualification boundaries`](docs/APPLICATION_RUNTIME.md).
Original npm integrity covers original archive bytes, not this local derivative.
This selected-file review does not establish complete distribution/legal approval.
