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
