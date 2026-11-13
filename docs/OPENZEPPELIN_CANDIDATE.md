# OpenZeppelin 4.9.6 candidate qualification

The current application lock selects OpenZeppelin Contracts 4.9.3. A source-bound
advisory review matched GHSA-9vx6-7xxf-x967, and `ZNSRegistrar` directly imports
that package's `Base64` and calls `encode` four times. The
[upstream advisory](https://github.com/OpenZeppelin/openzeppelin-contracts/security/advisories/GHSA-9vx6-7xxf-x967)
lists 4.9.6 as a patched 4.x version. This lane qualifies that candidate before
adopting regenerated application outputs. It changes no deployment or operator
state and does not mark the application dependency fixed.

The pinned [candidate plan](../tools/dependency-review/openzeppelin-candidate.json)
binds the unchanged production inputs, the selected npm URL and SHA-512, and
seven immutable public contract-control files. Those controls come from the
separate contract-context Draft at its recorded commit. Their source hashes
are checked before use; this does not merge that Draft or its browser changes.

## Two isolated source variants

The hosted job builds two new job-owned directories from an explicit source-file
manifest. It copies no credentials, environment file, Git metadata, dependency
tree, wallet or deployment record. One shared job-owned npm cache avoids repeated
transport of identical control packages. Dependency installation ignores
lifecycle scripts and receives empty explicit npm configuration files.
One locked test dependency tree serves each profile's build and tests through
an explicit read-only import fallback; ordinary nested resolution is preserved.
No dependency tree is copied or linked into a second installation directory.

The baseline keeps 4.9.3. The candidate changes only the selected 4.x package in
the application and control manifests/locks, and updates the ENS provenance
binding to that new lock. The compiler stays 0.8.26, with the original Paris,
optimizer and metadata settings; the v5 alias, ENS source, local contracts and
other dependency selections remain unchanged. Test dependencies are a separately
pinned qualification input and need their own advisory/provenance review.

Both variants use the original application build script. The baseline's fresh
ABIs and creation executable parts must match the original tracked artifacts.
Original saved source literals and IPFS metadata can differ after the isolated
refresh; that does not retrospectively reproduce the original artifact bytes.
The full immutable contract behavior controls then run against each refreshed
profile, including exact source/artifact/frontend-ABI correspondence.

A bounded Base64 control uses only allocated bytes and in-memory Paris message
frames: lengths 0 through 96, with three tail-byte values. It checks 291 cases
per variant, including restoration of the allocated tail. The legacy 4.9.3
control must observe 128 noncanonical encodings; 4.9.6 must observe zero. These
are regression fixtures, with no signing keys or network transport.

The candidate must retain all ten ABIs and change the creation executable part
only for `ZNSRegistrar`. Unexpected source, ABI, executable, test, stream-cap or
deadline outcomes fail qualification and retain the actual incomplete evidence.
The added 4.x `Context` method and every selected source difference still require
review; a passing fixture is not an independent audit.

## Output and adoption boundary

The artifact contains explicit source bindings, command stream receipts, the
comparison report and one output packet. It does not recursively package npm
caches, node_modules or profile directories, and does not duplicate source
tarballs. Original upstream license bytes are retained separately from the npm
archive, which does not contain a standalone license file.

The output packet is a **candidate**, not an accepted source update or release.
Before adoption, verify the exact workflow head/attempt and artifact digest,
replay member/stream/source pins, review the compiler input and all generated
files, then make a separate reviewed source commit. No historical qualification
is reassigned to that commit. Current-source CI and the original independent
maintainer/operator, bytecode/genesis, notices, supported-platform and release
gates remain required. Other advisory matches stay open.

Local reuse of a historical dependency tree was refused by its unchanged
manifest when an unregistered metadata entry was observed. That refusal and the
original entry remain preserved. This lane obtains fresh hosted inputs and does
not change local ownership records, storage policy or cleanup authority.
