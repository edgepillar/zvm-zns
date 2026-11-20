import {createRequire} from 'node:module'
import {dirname, resolve} from 'node:path'
import {defineConfig, loadEnv} from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwind from '@tailwindcss/vite'
import {browserNotices} from './scripts/browser-notices'

/**
 * Libraries in their own chunks, so a deploy that only touches the app does
 * not rename viem and make every returning visitor fetch it again.
 */
function vendorChunk(id: string) {
  if (!id.includes('node_modules')) return
  if (/[\/]node_modules[\/](viem|ox|abitype|@noble|@scure|@adraffy)[\/]/.test(id)) return 'viem'
  if (/[\/]node_modules[\/](vue|vue-router|@vue)[\/]/.test(id)) return 'vue'
}

// Relative paths and hash routes (#/name/alice.znn): one build serves GitHub
// Pages, a domain's root and a gateway's /zns/ unchanged, and a name's
// `external_url` (set on chain, in ZNSRegistrar) is a hash route for that
// reason.
// The shared half of the front ends (@zvm/web) is compiled from the zvm-core
// submodule, the same arrangement as the Go modules' `replace ./zvm-core`. vue
// and viem are its peer dependencies, pinned to this app's own copies so there
// is one Vue instance rather than two.
const require = createRequire(import.meta.url)
const peer = (name: string) => dirname(require.resolve(`${name}/package.json`))

// The node and origins this page reads are never built in (see .env.example).
// A build without them would ship a page that talks to nothing, so it stops
// here and says what to set.
function requireEnv(env: Record<string, string>, names: string[]) {
  const missing = names.filter((n) => !env[n])
  if (missing.length) {
    throw new Error(`${missing.join(', ')} not set: copy .env.example to .env, or set them in the environment`)
  }
}

export default defineConfig(({mode}) => {
  requireEnv(loadEnv(mode, '..', 'VITE_'), ['VITE_ZVM_NODE', 'VITE_GATEWAY'])
  return {
    // One .env for the repository, beside the scripts that read it too.
    envDir: '..',
    base: './',
    resolve: {
      alias: {
        '@zvm/web': resolve(__dirname, '../zvm-core/web/src'),
        vue: peer('vue'),
        viem: peer('viem'),
      },
      dedupe: ['vue', 'viem'],
    },
    plugins: [vue(), tailwind(), browserNotices(__dirname)],
    build: {
      target: 'es2022',
      assetsInlineLimit: 4096,
      rollupOptions: {output: {manualChunks: vendorChunk}},
    },
    // The deployment records live beside the contracts, one directory up, and
    // are compiled into the page.
    server: {port: 47800, fs: {allow: ['..']}},
  }
})
