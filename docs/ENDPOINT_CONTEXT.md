# Endpoint and heartbeat context

An explicit node selection owns its pending RPC check by URL and generation.
Concurrent checks share only the same current selection. Selecting another node,
selecting the same URL again, or rejecting invalid input invalidates older work.
Old successes, failures and cleanup cannot replace the current selection. Chain
and optional API information clear while rechecking. Original RPC methods,
normalization, persistence, timeouts, API fallback and failure descriptions remain.

The heartbeat owns each complete height/block read by RPC, chain ID, endpoint
health and generation. Current polls coalesce, including synchronous reentry.
Old completions cannot publish metadata, errors or later listener notifications.
Context changes clear old identity and cadence immediately. Hidden pages do not
start reads, and a visible return starts fresh work. The original minute default,
explicit polling period, pulse fields, eight-gap average and per-block timestamp
calculation remain. Genesis zero and legitimate lower canonical heads are read.

`npm run test:context` executes the shipped modules with declared memory-only
Vue, RPC, clock, visibility and storage capabilities. It starts no SDK, browser,
wallet or network. Type checking, the production build and isolated contract/ABI
checks remain separate CI requirements. These controls do not qualify complete
production-entry routes, real providers, extensions, chain finality or release.

The memory loader explicitly lowers only the private HttpError parameter-property constructor with an exact inverse; all asynchronous source expressions are retained. It uses the supported strip-only Node API.
