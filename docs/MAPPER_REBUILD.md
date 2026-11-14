# Separate guarded mapper rebuild candidate

The web qualification lane rebuilds a separate mapper from published
`chromium-bidi@157.0.8090-0` compiled JavaScript, `zod@4.6.7`, and `mitt@3.0.1`.
It applies the reviewed geolocation type guard before compilation. The original
BiDi publication embeds a Zod 4.6.5 version object; changing the root dependency
alone does not replace that embedded code.

The selected `esbuild@0.28.2` and Linux x64 binary come from the current lock.
Raw SHA-512 integrity and every regular member SHA-256 are checked before use.
The native CLI runs directly: its installer and package lifecycle scripts do
not run. Content equality and version output are not independent publisher or
compiler-source authentication. The compiler is not rebuilt from Go sources.

The browser IIFE, external map, linked legal comments, compiler metafile and
original BiDi, Zod, Mitt and esbuild notices are explicit CI artifact members.
The candidate retains its browser bootstrap. Original TypeScript source-map
directives are removed from the derived input tree; the new map embeds the
actual compiled-JS input bytes, including the guard. It is not a reproduction
of the upstream TypeScript build or production source-map acceptance.

A bounded flat-map reader checks every embedded source against the derived
input pins and validates mapping positions. It follows UTF-16 columns and
persistent source/name deltas from [ECMA-426](https://tc39.es/ecma426/). Its
canonical integer, path and payload restrictions are a selected compiler
profile, not a general source-map consumer conformance claim.

For selected behavior controls only, a memory-only copy of the actual generated
payload is cut at its mapped browser bootstrap and captures mapped declaration
identifiers. Eight tiny array controls check upper-bound traversal and overwrite
ordering; four geolocation controls check protocol errors and valid input.
The largest container has three elements. String and Wasm code generation are
disabled. Node VM contexts are not a security boundary; no browser, CDP
transport or protocol handlers execute in these controls.

The proposal remains separate from the application and from the original
published mapper. Full API/application integration, browser execution, CSP,
JIT behavior, supported platforms, complete advisory/legal review and owner
acceptance remain open. The existing 16 original-mapper controls and 299 Node
parser observations remain in the lane. No migration or production acceptance
is established by this rebuild.

Compiler options and output relationships follow the
[esbuild API](https://esbuild.github.io/api/); the report retains the actual
argument vector, source graph, binary pin and command stream receipts.
