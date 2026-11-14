// Use Node's real ESM export conditions from the selected installation root.
// The caller enables --experimental-import-meta-resolve for the parent URL.
export function resolveProfile(specifier, parentURL) {
  return import.meta.resolve(specifier, parentURL)
}
