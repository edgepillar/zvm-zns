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
