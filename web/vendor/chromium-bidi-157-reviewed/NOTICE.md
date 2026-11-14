# Reviewed chromium-bidi derivative

This payload set is a local derivative of chromium-bidi 157.0.8090-0,
rebuilt from its published compiled JavaScript with Zod 4.6.7 and the
reviewed parser type guard. It is not a new npm publication. Original npm
integrity authenticates the original archive, not these changed bytes.

The generated mapper uses compiled-JavaScript source maps and linked legal
comments. Four original notices are retained under payload/notices. The
original TypeScript maps are not reused for the changed files. The Node
parser map is line-level. The inspection copy is not an installed payload.

See manifest.json for original/effective hashes and the frozen source revision.
See docs/APPLICATION_RUNTIME.md for installation and qualification boundaries.
Retaining notices alone does not establish complete license or legal review.

The two modified JavaScript files now begin with explicit edgepillar change
notices. Each modified JSON map begins with x_edgepillar_changes. The Node
parser line map includes its notice line. The mapper's generated positions
shift by one line; all mapping deltas after that offset and all 177 embedded
compiled-JavaScript sources are unchanged. The four original license files
and mapper.js.LEGAL.txt retain their exact bytes. These are developer-tooling
payloads, outside the static public directory, and are not relicensed as MIT.

The manifest retains the previous payload and manifest pins, original archive
member pins and earlier compiler/source evidence. The notice-only derivation
does not invoke a package manager, compiler or browser. Real Node cache/stack
and bundled Chrome DevTools consumption require new exact-revision CI evidence.
